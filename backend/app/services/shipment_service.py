"""Service COLIS (shipments) — multi-colis par commande + machine à états.

1 commande = N colis. Les order_items sont rattachés aux colis via
order_items.shipment_id. La création d'un colis ne touche JAMAIS le stock :
le stock a déjà été réservé à la commande ; la libération/décrémentation se
fait à la confirmation de livraison (delivery_confirmation_service).
"""


from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationError_
from app.crud import business_rule as crud_rules
from app.db.base import new_uuid
from app.models.order import Order, OrderItem
from app.models.shipment import Shipment
from app.models.user import User
from app.services import reference_generator
from app.services.shipment_state_machine import can_transition, status_label  # noqa: F401 (réexport)


async def _load_order(db: AsyncSession, order_id: str) -> Order:
    order = (await db.execute(
        select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    )).scalar_one_or_none()
    if order is None:
        raise NotFoundError("Commande introuvable")
    return order


async def count_for_order(db: AsyncSession, order_id: str) -> int:
    """Nombre de colis déjà créés pour une commande."""
    return int((await db.execute(
        select(func.count(Shipment.id)).where(Shipment.order_id == order_id)
    )).scalar_one() or 0)


async def create_shipment(
    db: AsyncSession,
    tenant_id: str,
    order_id: str,
    item_ids: list[str],
    courier_id: Optional[str] = None,
    delivery_zone_id: Optional[str] = None,
    estimated_delivery_at: Optional[datetime] = None,
) -> Shipment:
    """Crée un colis depuis des order_items non encore expédiés de la commande."""
    order = await _load_order(db, order_id)
    if order.tenant_id != tenant_id:
        raise NotFoundError("Commande introuvable pour ce vendeur")
    if order.status in ("cancelled", "delivered", "returned"):
        raise ConflictError(f"Commande au statut '{order.status}' : création de colis impossible")

    max_per_order = int(await crud_rules.get_rule_number(db, "shipment.max_per_order", 20))
    existing = await count_for_order(db, order_id)
    if existing >= max_per_order:
        raise ConflictError(f"Limite atteinte : {max_per_order} colis maximum par commande")

    items = [i for i in order.items if i.id in set(item_ids)]
    if len(items) != len(set(item_ids)):
        raise ValidationError_("Certains articles n'appartiennent pas à cette commande")
    already = [i for i in items if i.shipment_id is not None]
    if already:
        raise ConflictError("Certains articles sont déjà rattachés à un colis")

    shipment = Shipment(
        id=new_uuid(),
        reference=await reference_generator.generate_shipment_reference(
            db, order.reference, existing + 1
        ),
        order_id=order.id,
        tenant_id=tenant_id,
        courier_id=courier_id,
        status="pending",
        delivery_zone_id=delivery_zone_id or order.delivery_zone_id,
        estimated_delivery_at=estimated_delivery_at,
    )
    db.add(shipment)
    await db.flush()
    for item in items:
        item.shipment_id = shipment.id
    if courier_id is not None:
        await _assert_courier_in_tenant(db, courier_id, tenant_id)
    await db.commit()
    return shipment


async def _assert_courier_in_tenant(db: AsyncSession, courier_id: str, tenant_id: str) -> User:
    courier = await db.get(User, courier_id)
    if courier is None or courier.role != "courier" or courier.tenant_id != tenant_id:
        raise ValidationError_("Livreur introuvable pour ce vendeur")
    return courier


async def get_shipment(db: AsyncSession, shipment_id: str) -> Shipment:
    row = (await db.execute(
        select(Shipment).where(Shipment.id == shipment_id).options(
            selectinload(Shipment.items), selectinload(Shipment.order)
        )
    )).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Colis introuvable")
    return row


async def assign_courier(db: AsyncSession, shipment: Shipment, courier_id: str) -> Shipment:
    """Assigne/réassigne un livreur du même tenant (colis non démarré)."""
    if shipment.status not in ("pending", "failed"):
        raise ConflictError("Un colis en cours de livraison ne peut être réassigné")
    await _assert_courier_in_tenant(db, courier_id, shipment.tenant_id)
    shipment.courier_id = courier_id
    await db.commit()
    return shipment


async def _transition(
    db: AsyncSession, shipment: Shipment, to_status: str, actor_role: Optional[str]
) -> None:
    ok, reason = can_transition(shipment.status, to_status, actor_role)
    if not ok:
        raise ConflictError(reason)
    shipment.status = to_status


async def start_delivery(db: AsyncSession, shipment: Shipment, courier: User) -> Shipment:
    """Le livreur démarre la tournée : pending → in_transit."""
    if shipment.courier_id != courier.id:
        raise ConflictError("Ce colis n'est pas assigné à ce livreur")
    await _transition(db, shipment, "in_transit", courier.role)
    shipment.started_at = datetime.now(timezone.utc)
    await db.commit()
    return shipment


async def mark_failed(
    db: AsyncSession, shipment: Shipment, reason: str, actor_role: str
) -> Shipment:
    """Échec de livraison (client absent, adresse introuvable…)."""
    await _transition(db, shipment, "failed", actor_role)
    shipment.failed_at = datetime.now(timezone.utc)
    shipment.failure_reason = reason[:300]
    await db.commit()
    return shipment


async def mark_returned(db: AsyncSession, shipment: Shipment, actor_role: str) -> Shipment:
    """Retour au vendeur après échec (terminal). Libère la réservation stock."""
    from app.services import order_service  # local import : évite cycle

    await _transition(db, shipment, "returned", actor_role)
    items = shipment.items or []
    for item in items:
        if item.product_id is not None and item.delivered_at is None:
            await order_service.adjust_reserved_stock(db, item.product_id, -item.quantity)
    await db.commit()
    return shipment


async def mark_rescheduled(
    db: AsyncSession, shipment: Shipment, new_date: datetime,
    reason: Optional[str], by_user: User,
):
    """Demande de report : enregistre DeliveryReschedule + remise pending si failed."""
    from app.models.delivery import DeliveryReschedule

    pending_count = int((await db.execute(
        select(func.count(DeliveryReschedule.id)).where(
            DeliveryReschedule.shipment_id == shipment.id,
            DeliveryReschedule.status.in_(["pending", "approved"]),
        )
    )).scalar_one() or 0)
    max_reschedules = int(await crud_rules.get_rule_number(db, "delivery.max_reschedule_count", 2))
    if pending_count >= max_reschedules:
        raise ConflictError(f"Limite de {max_reschedules} reports atteinte pour ce colis")

    reschedule = DeliveryReschedule(
        id=new_uuid(),
        shipment_id=shipment.id,
        requested_by=by_user.id,
        requested_by_role=by_user.role,
        old_date=shipment.estimated_delivery_at,
        new_date=new_date,
        reason=reason,
        status="pending",
    )
    db.add(reschedule)
    if shipment.status == "failed":
        await _transition(db, shipment, "pending", by_user.role)
    await db.commit()
    return reschedule


def shipment_total_usd(shipment: Shipment) -> Decimal:
    """Sous-total produits du colis (les frais de livraison restent à la commande)."""
    return sum((Decimal(str(i.subtotal_usd)) for i in shipment.items), Decimal("0"))


async def get_shipment_summary(db: AsyncSession, shipment: Shipment) -> dict[str, Any]:
    """Résumé lisible : items, totaux USD + affichage, dates clés."""
    total = shipment_total_usd(shipment)
    return {
        "id": shipment.id,
        "reference": shipment.reference,
        "status": shipment.status,
        "status_label": status_label(shipment.status),
        "order_reference": shipment.order.reference if shipment.order else None,
        "items": [
            {
                "id": i.id,
                "product_name": i.product_name,
                "quantity": i.quantity,
                "unit_price_usd": str(i.unit_price_usd),
                "subtotal_usd": str(i.subtotal_usd),
            }
            for i in shipment.items
        ],
        "total_usd": str(total),
        "currency_at_creation": shipment.order.currency_at_creation if shipment.order else "USD",
        "started_at": shipment.started_at,
        "delivered_at": shipment.delivered_at,
        "confirmation_method": shipment.confirmation_method,
        "receipt_number": shipment.receipt_number,
    }


async def check_all_shipments_delivered(db: AsyncSession, order_id: str) -> bool:
    """True si TOUS les colis de la commande sont 'delivered' (et qu'il y en a ≥1)."""
    counts = (await db.execute(
        select(Shipment.status, func.count(Shipment.id))
        .where(Shipment.order_id == order_id)
        .group_by(Shipment.status)
    )).all()
    if not counts:
        return False
    total = sum(c for _, c in counts)
    delivered = sum(c for s, c in counts if s == "delivered")
    return total > 0 and delivered == total
