"""Service Commandes — création atomique avec split multi-vendeurs.

Points critiques (règles du prompt) :
  - transaction ATOMIQUE : vérif stock → orders + items → réservation stock →
    vidage panier → commit ; événements APRÈS commit ;
  - snapshots : prix unitaire USD, taux de change, taux commission ;
  - tenant_id JAMAIS depuis le body (dénormalisé depuis les produits) ;
  - delivered_at = point de vérité financière (COD encaissé par le vendeur).
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.events import events
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError_
from app.crud import business_rule as crud_rules
from app.models.cart import Cart, CartItem
from app.models.order import DeliveryZone, Order, OrderItem, OrderStatusHistory
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User
from app.services import order_state_machine as osm
from app.services import product_service
from app.services.reference_generator import generate_order_reference

# Colonnes temporelles alimentées automatiquement selon le statut atteint.
_STATUS_TIMESTAMP = {
    "confirmed": "confirmed_at",
    "preparing": "preparing_at",
    "shipped": "shipped_at",
    "delivered": "delivered_at",
    "cancelled": "cancelled_at",
}


async def _commission_rate_for(db: AsyncSession, tenant: Tenant) -> Decimal:
    """Taux applicable = règle plan.* si définie, sinon taux contractuel tenant."""
    plan = (tenant.plan_name or "free").lower()
    rate = await crud_rules.get_rule(db, f"commission.rate.{plan}", None)
    if rate is not None:
        try:
            return Decimal(str(rate))
        except Exception:  # noqa: BLE001
            pass
    return Decimal(str(tenant.commission_rate))


def compute_commission(subtotal_usd: Decimal, rate: Decimal, min_usd: Decimal) -> Decimal:
    """Commission = max(subtotal × taux, minimum plan), arrondi centime."""
    raw = (subtotal_usd * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return max(raw, min_usd.quantize(Decimal("0.01")))


async def _min_commission_usd(db: AsyncSession, tenant: Tenant) -> Decimal:
    plan = (tenant.plan_name or "free").lower()
    val = await crud_rules.get_rule(db, f"commission.min_usd.{plan}", 0)
    return Decimal(str(val))


async def calculate_delivery_fee(
    db: AsyncSession, tenant_id: str, delivery_zone_id: Optional[str]
) -> Decimal:
    """Frais de livraison = base_fee_usd de la zone (None => 0)."""
    if not delivery_zone_id:
        return Decimal("0")
    zone = (await db.execute(
        select(DeliveryZone).where(
            DeliveryZone.id == delivery_zone_id,
            DeliveryZone.tenant_id == tenant_id,
            DeliveryZone.is_active.is_(True),
        )
    )).scalar_one_or_none()
    if zone is None:
        raise NotFoundError("Zone de livraison introuvable pour ce vendeur")
    return Decimal(zone.base_fee_usd)


async def create_orders_from_cart(
    db: AsyncSession,
    user: User,
    delivery_address: dict[str, Any],
    delivery_zone_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> list[Order]:
    """Split auto multi-vendeurs : 1 commande par tenant, tout ou rien.

    ⚠️ Le commit est fait ICI (atomicité), les événements sont émis après.
    """
    cart = (await db.execute(
        select(Cart).where(Cart.customer_id == user.id).options(selectinload(Cart.items))
    )).scalar_one_or_none()
    if cart is None or not cart.items:
        raise ValidationError_("Le panier est vide")

    max_qty = int(await crud_rules.get_rule_number(db, "order.max_quantity_per_item", 99))

    # 1) Verrouiller et vérifier le stock pour TOUS les items (une seule requête).
    product_ids = {i.product_id for i in cart.items}
    products = (await db.execute(
        select(Product).where(Product.id.in_(product_ids)).with_for_update()
    )).scalars().all()
    pmap = {p.id: p for p in products}

    needed: dict[str, int] = {}
    for item in cart.items:
        prod = pmap.get(item.product_id)
        if prod is None or not prod.is_active or not prod.is_published:
            raise ConflictError("Un produit du panier n'est plus disponible")
        needed[item.product_id] = needed.get(item.product_id, 0) + item.quantity

    for pid, qty in needed.items():
        prod = pmap[pid]
        if qty > max_qty:
            raise ValidationError_(f"Quantité maximale par article : {max_qty}")
        available = prod.stock - prod.reserved_stock
        if available < qty:
            raise ConflictError(
                f"Stock insuffisant pour « {prod.name} » (disponible : {max(available, 0)})"
            )

    # 2) Snapshot taux de change + devise client.
    currency = cart.currency_display or user.currency_display or "USD"
    rate_usd = Decimal("1")
    if currency != "USD":
        rate_usd = await product_service.get_rate_usd_to(db, currency)

    tenants_cache: dict[str, Tenant] = {}
    commission_min: dict[str, Decimal] = {}
    commission_rate: dict[str, Decimal] = {}

    async def _tenant(tid: str) -> Tenant:
        if tid not in tenants_cache:
            t = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one_or_none()
            if t is None:
                raise NotFoundError("Vendeur introuvable")
            tenants_cache[tid] = t
            commission_rate[tid] = await _commission_rate_for(db, t)
            commission_min[tid] = await _min_commission_usd(db, t)
        return tenants_cache[tid]

    # 3) Grouper les lignes par tenant → commandes.
    by_tenant: dict[str, list[CartItem]] = {}
    for item in cart.items:
        by_tenant.setdefault(item.tenant_id, []).append(item)

    orders: list[Order] = []
    for tid, items in by_tenant.items():
        tenant = await _tenant(tid)
        subtotal = sum((Decimal(i.unit_price_usd) * i.quantity for i in items), Decimal("0"))
        fee = await calculate_delivery_fee(db, tid, delivery_zone_id if len(by_tenant) == 1 else None)
        reference = await generate_order_reference(db)
        order = Order(
            reference=reference,
            tenant_id=tid,
            customer_id=user.id,
            status="pending",
            subtotal_usd=subtotal,
            delivery_fee_usd=fee,
            total_usd=subtotal + fee,
            currency_at_creation=currency,
            exchange_rate_used=rate_usd,
            delivery_address=delivery_address,
            delivery_zone_id=delivery_zone_id if len(by_tenant) == 1 else None,
            delivery_notes=notes,
        )
        db.add(order)
        await db.flush()

        for ci in items:
            prod = pmap[ci.product_id]
            primary_img = next((im.url for im in prod.images if im.is_primary), None)
            line_usd = Decimal(ci.unit_price_usd) * ci.quantity
            db.add(OrderItem(
                order_id=order.id,
                product_id=prod.id,
                tenant_id=tid,
                product_name=prod.name,
                product_short_description=prod.short_description,
                product_image_url=primary_img,
                sku=prod.sku,
                unit_price_usd=Decimal(ci.unit_price_usd),
                quantity=ci.quantity,
                subtotal_usd=line_usd,
                commission_rate=commission_rate[tid],
                commission_amount_usd=Decimal("0"),  # calculé à la livraison (point de vérité)
            ))
        db.add(OrderStatusHistory(
            order_id=order.id, old_status=None, new_status="pending",
            changed_by=user.id, changed_by_role="customer",
        ))
        orders.append(order)

    # 4) Réservation du stock (UPDATE arithmétique atomique).
    for pid, qty in needed.items():
        await db.execute(
            update(Product)
            .where(Product.id == pid)
            .values(reserved_stock=Product.reserved_stock + qty)
        )

    # 5) Vider le panier.
    from sqlalchemy import delete
    await db.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    cart.is_empty = True

    # 6) Commit ATOMIQUE puis événements APRÈS commit.
    await db.commit()
    for order in orders:
        await db.refresh(order)
        await events.emit("order.created", {"id": order.id, "reference": order.reference,
                                            "tenant_id": order.tenant_id})
    await events.emit("cart.cleared", {"cart_id": cart.id})
    return orders


async def load_order(db: AsyncSession, order_id: str) -> Order:
    order = (await db.execute(
        select(Order).where(Order.id == order_id).options(
            selectinload(Order.items), selectinload(Order.history)
        )
    )).scalar_one_or_none()
    if order is None:
        raise NotFoundError("Commande introuvable")
    return order


async def _release_reserved_stock(db: AsyncSession, order: Order) -> None:
    """Libère reserved_stock (jamais négatif) — annulation/échec."""
    for oi in order.items:
        if oi.product_id:
            await db.execute(
                update(Product)
                .where(Product.id == oi.product_id)
                .values(reserved_stock=Product.reserved_stock - oi.quantity)
            )
            # Garde-fou SQLite/PG : clamp à 0 si anomalie de données.
            await db.execute(
                Product.__table__.update()
                .where(Product.id == oi.product_id, Product.reserved_stock < 0)
                .values(reserved_stock=0)
            )


async def _apply_delivered_stock(db: AsyncSession, order: Order) -> None:
    """À la livraison : décrément stock ET reserved_stock (point de vérité)."""
    now = datetime.now(timezone.utc)
    tenant = await db.get(Tenant, order.tenant_id)
    rate = await _commission_rate_for(db, tenant) if tenant else Decimal("0")
    min_usd = await _min_commission_usd(db, tenant) if tenant else Decimal("0")
    for oi in order.items:
        if oi.product_id:
            await db.execute(
                update(Product)
                .where(Product.id == oi.product_id)
                .values(
                    stock=Product.stock - oi.quantity,
                    reserved_stock=Product.reserved_stock - oi.quantity,
                    sales_count=Product.sales_count + oi.quantity,
                )
            )
        if oi.delivered_at is None:
            oi.delivered_at = now
            # Commission recalculée au point de vérité (snapshot du taux à la commande).
            oi.commission_amount_usd = compute_commission(
                Decimal(str(oi.subtotal_usd)), Decimal(str(oi.commission_rate)), min_usd
            )
    order.delivered_at = now
    order.paid_at = now  # COD : payé à la livraison (encaissé par le vendeur)


async def adjust_reserved_stock(db: AsyncSession, product_id: str, delta: int) -> None:
    """Ajustement atomique de reserved_stock avec clamp à 0 (utilisé colis retournés)."""
    if delta == 0:
        return
    await db.execute(
        update(Product)
        .where(Product.id == product_id)
        .values(reserved_stock=Product.reserved_stock + delta)
    )
    await db.execute(
        Product.__table__.update()
        .where(Product.id == product_id, Product.reserved_stock < 0)
        .values(reserved_stock=0)
    )


async def update_order_status(
    db: AsyncSession,
    order_id: str,
    new_status: str,
    actor: User,
    reason: Optional[str] = None,
    *,
    system: bool = False,
) -> Order:
    """Transition stricte via machine à états + journal + effets financiers."""
    order = await load_order(db, order_id)
    old_status = order.status
    role = "system" if system else ("superadmin" if actor.role == "superadmin"
                                    else ("vendor" if actor.role in ("vendor", "staff") else actor.role))

    ok, why = osm.can_transition(old_status, new_status, role)
    if not ok:
        raise ValidationError_(why or "Transition interdite")

    # Vérification d'appartenance (isolation).
    if role == "vendor" and order.tenant_id != actor.tenant_id:
        raise PermissionDeniedError("Commande d'un autre vendeur")
    if role == "customer" and order.customer_id != actor.id:
        raise PermissionDeniedError("Commande d'un autre client")

    order.status = new_status
    ts_field = _STATUS_TIMESTAMP.get(new_status)
    if ts_field:
        setattr(order, ts_field, datetime.now(timezone.utc))
    if new_status == "cancelled":
        order.cancel_reason = reason
        order.cancelled_by = None if system else actor.id
        await _release_reserved_stock(db, order)
    elif new_status == "delivered":
        await _apply_delivered_stock(db, order)

    db.add(OrderStatusHistory(
        order_id=order.id, old_status=old_status, new_status=new_status,
        changed_by=None if system else actor.id,
        changed_by_role=role, reason=reason,
    ))
    await db.commit()
    await db.refresh(order)

    await events.emit("order.status_changed",
                      {"id": order.id, "old": old_status, "new": new_status})
    if new_status == "delivered":
        await events.emit("order.delivered", {"id": order.id, "reference": order.reference})
    elif new_status == "cancelled":
        await events.emit("order.cancelled", {"id": order.id, "reason": reason})
    elif new_status == "confirmed":
        await events.emit("order.confirmed", {"id": order.id})
    elif new_status == "shipped":
        await events.emit("order.shipped", {"id": order.id})
    elif new_status == "failed":
        await events.emit("order.failed", {"id": order.id, "reason": reason})
    elif new_status == "rescheduled":
        await events.emit("order.rescheduled", {"id": order.id, "reason": reason})
    return order


async def auto_cancel_expired_orders(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Job ARQ : annule les pending > order.auto_cancel_hours, libère le stock."""
    from datetime import timedelta

    hours = float(await crud_rules.get_rule_number(db, "order.auto_cancel_hours", 48))
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    # Colonnes DateTime(timezone=True) : comparaison en UTC naive pour rester
    # compatible PostgreSQL et SQLite (tests).
    cutoff_naive = cutoff.replace(tzinfo=None) if cutoff.tzinfo else cutoff
    stale = (await db.execute(
        select(Order).where(
            Order.status == "pending",
            Order.created_at < cutoff_naive,
        ).options(selectinload(Order.items))
    )).scalars().all()
    count = 0
    for order in stale:
        order.status = "cancelled"
        order.cancelled_at = now
        order.cancel_reason = "auto_expired"
        await _release_reserved_stock(db, order)
        db.add(OrderStatusHistory(
            order_id=order.id, old_status="pending", new_status="cancelled",
            changed_by=None, changed_by_role="system", reason="auto_expired",
        ))
        count += 1
    if count:
        await db.commit()
        for order in stale:
            await events.emit("order.cancelled",
                              {"id": order.id, "reason": "auto_expired"})
    return count
