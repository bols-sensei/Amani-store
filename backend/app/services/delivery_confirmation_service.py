"""Service CONFIRMATION DE LIVRAISON — point de vérité financière du COD.

Transaction atomique déclenchée par la confirmation (QR, code manuel ou
validation manuelle vendeur après délai) :

1. shipment.status = "delivered" + delivered_at ;
2. pour chaque order_item du colis :
   - products.stock          -= qty   (la marchandise est sortie)
   - products.reserved_stock -= qty   (la réservation de commande est soldée)
   - order_item.delivered_at  = now()
   - commission_amount_usd    = MAX(subtotal × rate_snapshot, min_usd_plan)
     → calculée UNIQUEMENT sur le sous-total produits (jamais la livraison),
     avec le taux snapshoté à la commande (principe P1 : l'argent des ventes
     reste chez le vendeur, la commission est une dette SaaS facturée ensuite) ;
3. reçu PDF généré automatiquement ;
4. si TOUS les colis de la commande sont livrés → order "delivered" ;
5. COMMIT, puis événements APRÈS commit (bus events.emit).

Aucune valeur métier en dur : délais et exigences (photo) viennent des
business_rules.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, PermissionDeniedError, ValidationError_
from app.crud import business_rule as crud_rules
from app.db.base import new_uuid
from app.core.events import events
from app.models.delivery import DeliveryConfirmation
from app.models.order import Order
from app.models.shipment import Shipment
from app.models.user import User
from app.services import receipt_service, shipment_service
from app.services.order_service import compute_commission


async def _apply_delivered_effects(db: AsyncSession, shipment: Shipment) -> Decimal:
    """Décrément stock/réservation + calcule la commission par item livré.

    Retourne le total des commissions générées pour ce colis (USD).
    Les items déjà marqués livrés (idempotence) sont ignorés.
    """
    # Import local : évite tout cycle d'import au chargement du module.
    from sqlalchemy import update as sa_update

    from app.models.product import Product
    from app.models.tenant import Tenant

    tenant = await db.get(Tenant, shipment.tenant_id)
    plan = (tenant.plan_name if tenant else "free") or "free"
    min_usd = Decimal(str(await crud_rules.get_rule_number(db, f"commission.min_usd.{plan}", 0)))

    total_commission = Decimal("0")
    for item in shipment.items or []:
        if item.delivered_at is not None:
            continue  # déjà comptabilisé (multi-colis / retry)
        item.delivered_at = datetime.now(timezone.utc)
        amount = compute_commission(
            Decimal(str(item.subtotal_usd)), Decimal(str(item.commission_rate)), min_usd
        )
        item.commission_amount_usd = amount
        total_commission += amount
        if item.product_id is not None:
            # UPDATE SQL atomique (clamp à 0 défensif, jamais de passif).
            await db.execute(
                sa_update(Product)
                .where(Product.id == item.product_id)
                .values(
                    stock=sa_case_zero_floor(Product.stock - item.quantity),
                    reserved_stock=sa_case_zero_floor(Product.reserved_stock - item.quantity),
                )
            )
    return total_commission


def sa_case_zero_floor(expr):
    """Garde-fous SQL : un stock ne devient jamais négatif."""
    from sqlalchemy import case

    return case((expr < 0, 0), else_=expr)


async def confirm_delivery(
    db: AsyncSession,
    shipment: Shipment,
    method: str,
    actor: User,
    *,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict[str, Any]:
    """Confirme la livraison d'un colis (QR | manual_code | vendor_manual).

    Vérifications strictes d'autorisation avant toute écriture :
    - client : uniquement SES propres livraisons (order.customer_id) ;
    - courier : uniquement les colis qui lui sont assignés ;
    - vendor/staff : uniquement ses propres tenants, et seulement en mode
      "vendor_manual" après le délai delivery.auto_confirm_after_hours ;
    - superadmin : override total.
    """
    if shipment.status != "in_transit":
        raise ConflictError(
            f"Le colis doit être en cours de livraison (statut actuel : {shipment.status})"
        )
    if method not in ("qr_scan", "manual_code", "vendor_manual"):
        raise ValidationError_("Méthode de confirmation inconnue")

    order = shipment.order
    if order is None:
        order = await shipment_service._load_order(db, shipment.order_id)

    role = actor.role
    if role == "customer":
        if order.customer_id != actor.id:
            raise PermissionDeniedError("Vous ne pouvez confirmer que vos propres livraisons")
    elif role == "courier":
        if shipment.courier_id != actor.id:
            raise PermissionDeniedError("Ce colis ne vous est pas assigné")
        if method != "manual_code":
            raise ValidationError_("Le livreur confirme uniquement par code manuel client")
    elif role in ("vendor", "staff"):
        if shipment.tenant_id != actor.tenant_id:
            raise PermissionDeniedError("Colis d'un autre vendeur")
        if method != "vendor_manual":
            raise ValidationError_("La validation vendeur doit être manuelle (fallback)")
        hours = float(await crud_rules.get_rule_number(db, "delivery.auto_confirm_after_hours", 48))
        started = shipment.started_at
        if started is not None:
            elapsed = (datetime.now(timezone.utc) - started).total_seconds() / 3600.0
            if elapsed < hours and role != "vendor":
                raise ConflictError(
                    f"Validation manuelle disponible après {hours:.0f}h en tournée"
                )
    elif role != "superadmin":
        raise PermissionDeniedError("Rôle non autorisé pour confirmer une livraison")

    now = datetime.now(timezone.utc)
    shipment.status = "delivered"
    shipment.delivered_at = now
    shipment.confirmation_method = method
    if method == "qr_scan":
        shipment.confirmed_by_qr = True
    else:
        shipment.confirmed_by_manual = True

    customer_id = order.customer_id
    db.add(DeliveryConfirmation(
        id=new_uuid(),
        shipment_id=shipment.id,
        customer_id=customer_id,
        method=method,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:300] or None,
        confirmed_at=now,
    ))

    total_commission = await _apply_delivered_effects(db, shipment)

    # Reçu PDF automatique (best effort : un échec de rendu ne bloque pas
    # la livraison, mais le document sera régénérable).
    receipt = None
    try:
        receipt = await receipt_service.generate_receipt(db, shipment.id)
    except Exception:  # noqa: BLE001 — le reçu n'est jamais critique
        receipt = None

    order_completed = await shipment_service.check_all_shipments_delivered(db, order.id)
    if order_completed:
        from app.services import order_service

        await order_service.update_order_status(
            db, order.id, "delivered", actor, reason="Tous les colis livrés", system=True
        )

    await db.commit()

    payload = {
        "shipment": shipment,
        "receipt": receipt,
        "commission_total_usd": str(total_commission),
        "order_completed": order_completed,
    }
    await events.emit("shipment.delivered", {"id": shipment.id, "reference": shipment.reference})
    await events.emit("delivery.confirmed", {"shipment_id": shipment.id, "method": method})
    if receipt is not None:
        await events.emit("receipt.generated", {"number": receipt.number, "shipment_id": shipment.id})
    if order_completed:
        await events.emit("order.delivered", {"id": order.id, "reference": order.reference})
    return payload
