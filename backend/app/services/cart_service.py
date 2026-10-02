"""Service Panier — un seul panier actif par client, prix snapshotés USD.

Règles config-driven lues dans business_rules :
  - order.max_quantity_per_item (99)
  - order.cart_expiry_days (30)
"""

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.events import events
from app.core.exceptions import NotFoundError, ValidationError_
from app.crud import business_rule as crud_rules
from app.crud.product import get_product
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User
from app.services import product_service


async def get_or_create_cart(db: AsyncSession, user: User) -> Cart:
    """Retourne le panier du client (créé avec sa devise d'affichage sinon)."""
    cart = (await db.execute(
        select(Cart).where(Cart.customer_id == user.id).options(
            selectinload(Cart.items)
        )
    )).scalar_one_or_none()
    if cart is None:
        cart = Cart(customer_id=user.id, currency_display=user.currency_display or "USD")
        db.add(cart)
        await db.flush()
    return cart


async def add_item(
    db: AsyncSession, user: User, product_id: str, quantity: int
) -> CartItem:
    """Ajoute un produit (doublon => quantités cumulées), prix snapshoté USD."""
    max_qty = int(await crud_rules.get_rule_number(db, "order.max_quantity_per_item", 99))
    if quantity < 1:
        raise ValidationError_("Quantité invalide")
    if quantity > max_qty:
        raise ValidationError_(f"Quantité maximale par article : {max_qty}")

    prod = await get_product(db, product_id)
    if prod is None or not prod.is_active or not prod.is_published:
        raise NotFoundError("Produit introuvable ou indisponible")

    # Snapshot du prix courant en USD (le panier garde le prix au moment de l'ajout)
    cart = await get_or_create_cart(db, user)
    existing = next((i for i in cart.items if i.product_id == prod.id), None)
    if existing is not None:
        new_qty = existing.quantity + quantity
        if new_qty > max_qty:
            raise ValidationError_(f"Quantité maximale par article : {max_qty}")
        existing.quantity = new_qty
        existing.unit_price_usd = Decimal(prod.price_usd)  # re-snapshot prix courant
        item = existing
    else:
        item = CartItem(
            cart_id=cart.id,
            product_id=prod.id,
            tenant_id=prod.tenant_id,
            quantity=quantity,
            unit_price_usd=Decimal(prod.price_usd),
        )
        db.add(item)
    cart.is_empty = False
    await db.flush()
    await db.refresh(item)
    await events.emit("cart.item_added", {"cart_id": cart.id, "item_id": item.id})
    return item


async def update_item_quantity(
    db: AsyncSession, user: User, item_id: str, quantity: int
) -> Optional[CartItem]:
    """Met à jour la quantité ; 0 retire l'article."""
    cart = await get_or_create_cart(db, user)
    item = next((i for i in cart.items if i.id == item_id), None)
    if item is None:
        raise NotFoundError("Article introuvable dans le panier")
    if quantity <= 0:
        await remove_item(db, user, item_id)
        return None
    max_qty = int(await crud_rules.get_rule_number(db, "order.max_quantity_per_item", 99))
    if quantity > max_qty:
        raise ValidationError_(f"Quantité maximale par article : {max_qty}")
    item.quantity = quantity
    await db.flush()
    return item


async def remove_item(db: AsyncSession, user: User, item_id: str) -> None:
    """Retire une ligne du panier."""
    cart = await get_or_create_cart(db, user)
    item = next((i for i in cart.items if i.id == item_id), None)
    if item is None:
        raise NotFoundError("Article introuvable dans le panier")
    await db.delete(item)
    await db.flush()
    remaining = [i for i in cart.items if i.id != item_id]
    cart.is_empty = not remaining
    await events.emit("cart.item_removed", {"cart_id": cart.id, "item_id": item_id})


async def clear_cart(db: AsyncSession, user: User) -> None:
    """Vide entièrement le panier."""
    cart = await get_or_create_cart(db, user)
    await db.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    cart.is_empty = True
    await db.flush()
    await events.emit("cart.cleared", {"cart_id": cart.id})


async def _tenant_map(db: AsyncSession, tenant_ids: set[str]) -> dict[str, Tenant]:
    if not tenant_ids:
        return {}
    rows = (await db.execute(select(Tenant).where(Tenant.id.in_(tenant_ids)))).scalars().all()
    return {t.id: t for t in rows}


async def get_cart_summary(
    db: AsyncSession, user: User, currency_code: Optional[str] = None
) -> dict[str, Any]:
    """Panier complet groupé par tenant, totaux USD + display selon devise."""
    cart = await get_or_create_cart(db, user)
    code = currency_code or cart.currency_display or user.currency_display or "USD"

    items_out: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}
    tenants = await _tenant_map(db, {i.tenant_id for i in cart.items})

    # Chargement explicite des produits + images (évite un lazy-load async
    # « MissingGreenlet » sur la relation prod.images).
    prods = (await db.execute(
        select(Product)
        .where(Product.id.in_({i.product_id for i in cart.items}))
        .options(selectinload(Product.images))
    )).scalars().all() if cart.items else []
    pmap = {p.id: p for p in prods}

    subtotal_usd = Decimal("0")
    for item in sorted(cart.items, key=lambda i: i.added_at):
        prod = pmap.get(item.product_id)
        if prod is None:
            continue
        _, value, _ = await product_service.display_price(
            db, Decimal(item.unit_price_usd), _FakeUser(code)
        )
        line_usd = Decimal(item.unit_price_usd) * item.quantity
        subtotal_usd += line_usd
        _, line_disp, _ = await product_service.display_price(db, line_usd, _FakeUser(code))
        tenant = tenants.get(item.tenant_id)
        row = {
            "id": item.id,
            "product": {
                "id": prod.id, "name": prod.name, "slug": prod.slug,
                "price_usd": Decimal(prod.price_usd), "stock": prod.stock,
                "reserved_stock": prod.reserved_stock, "is_active": prod.is_active,
                "is_published": prod.is_published,
                "image_url": next((im.url for im in prod.images if im.is_primary), None),
            },
            "tenant": _tenant_summary(tenant),
            "quantity": item.quantity,
            "unit_price_usd": Decimal(item.unit_price_usd),
            "subtotal_usd": line_usd,
            "subtotal_display": line_disp,
            "available_stock": prod.stock - prod.reserved_stock,
        }
        items_out.append(row)
        g = groups.setdefault(item.tenant_id, {
            "tenant": _tenant_summary(tenant), "items": [],
            "subtotal_usd": Decimal("0"), "subtotal_display": "$0.00",
            "delivery_fee_usd": Decimal("0"), "delivery_fee_display": "$0.00",
        })
        g["items"].append(row)
        g["subtotal_usd"] += line_usd

    for g in groups.values():
        _, disp, _ = await product_service.display_price(db, g["subtotal_usd"], _FakeUser(code))
        g["subtotal_display"] = disp

    _, sub_disp, _ = await product_service.display_price(db, subtotal_usd, _FakeUser(code))
    _, tot_disp, _ = await product_service.display_price(db, subtotal_usd, _FakeUser(code))
    return {
        "id": cart.id,
        "currency_display": code,
        "items": items_out,
        "tenant_groups": list(groups.values()),
        "subtotal_usd": subtotal_usd,
        "subtotal_display": sub_disp,
        "delivery_fee_usd": Decimal("0"),
        "delivery_fee_display": "$0.00",
        "total_usd": subtotal_usd,
        "total_display": tot_disp,
        "items_count": sum(i["quantity"] for i in items_out),
        "updated_at": cart.updated_at,
    }


class _FakeUser:
    """Astuce interne : display_price attend un User avec currency_display."""

    def __init__(self, code: str) -> None:
        self.currency_display = code


def _tenant_summary(t: Optional[Tenant]) -> dict[str, Any]:
    if t is None:
        return {"id": "", "name": "—", "slug": "", "logo_url": None}
    return {"id": t.id, "name": t.name, "slug": t.slug, "logo_url": t.logo_url}


async def validate_cart(db: AsyncSession, user: User) -> dict[str, Any]:
    """Vérifie stock disponible + produits actifs/publiés avant commande."""
    summary = await get_cart_summary(db, user)
    issues: list[dict[str, Any]] = []
    for row in summary["items"]:
        prod = row["product"]
        if not prod["is_active"] or not prod["is_published"]:
            issues.append({
                "item_id": row["id"], "product_id": prod["id"], "product_name": prod["name"],
                "code": "unavailable", "message": f"« {prod['name']} » n'est plus disponible",
            })
        elif prod["available_stock"] < row["quantity"]:
            issues.append({
                "item_id": row["id"], "product_id": prod["id"], "product_name": prod["name"],
                "code": "insufficient_stock",
                "message": (f"Stock insuffisant pour « {prod['name']} » "
                            f"(disponible : {prod['available_stock']})"),
            })
    return {"valid": not issues and bool(summary["items"]), "issues": issues}


async def cleanup_expired_carts(db: AsyncSession) -> int:
    """Supprime les lignes des paniers inactifs > order.cart_expiry_days. Job ARQ."""
    from datetime import datetime, timedelta, timezone

    days = int(await crud_rules.get_rule_number(db, "order.cart_expiry_days", 30))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        delete(CartItem).where(CartItem.added_at < cutoff)
    )
    await db.execute(
        Cart.__table__.update()
        .where(
            Cart.id.notin_(select(CartItem.cart_id))
        )
        .values(is_empty=True)
    )
    await db.commit()
    return int(result.rowcount or 0)
