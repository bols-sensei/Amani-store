"""Service Catalogue — logique métier produits/catégories.

Responsabilités :
- conversion de prix via exchange_rates (jamais de taux en dur) ;
- formatage d'affichage selon la devise (symbol position, séparateurs) ;
- limites de plan lues depuis business_rules (limits.<plan>.max_products...) ;
- gestion du stock + événements product.* sur le bus ;
- full-text search PostgreSQL (tsvector/ts_rank) avec fallback ILIKE.

AUCUNE valeur métier ici n'est codée en dur : tout vient de la base.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import events
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError_
from app.crud import product as crud_product
from app.crud.business_rule import get_rule, get_rule_number
from app.models.category import Category
from app.models.currency import Currency
from app.models.product import Product, ProductImage
from app.models.tenant import Tenant
from app.models.user import User

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ Devises


async def _get_currency(db: AsyncSession, code: str) -> Currency:
    from sqlalchemy import select

    cur = (await db.execute(select(Currency).where(Currency.code == code))).scalar_one_or_none()
    if cur is None or not cur.is_active:
        raise ValidationError_(f"Devise inconnue ou inactive : {code}")
    return cur


async def get_rate_usd_to(db: AsyncSession, code: str) -> Decimal:
    """Taux USD → `code` lu dans exchange_rates (snapshot manuel/API par superadmin)."""
    if code == "USD":
        return Decimal("1")
    from sqlalchemy import select

    from app.models.exchange_rate import ExchangeRate

    rate_row = (
        await db.execute(
            select(ExchangeRate)
            .where(ExchangeRate.from_currency == "USD", ExchangeRate.to_currency == code)
            .order_by(ExchangeRate.effective_at.desc())
        )
    ).scalars().first()
    if rate_row is None:
        raise ValidationError_(f"Aucun taux de change USD → {code} configuré")
    return Decimal(str(rate_row.rate))


def convert_price_input(db_rate: Decimal, price_input: Decimal, currency_input: str) -> Decimal:
    """Convertit un prix saisi (USD ou CDF) en USD stocké (2 décimales)."""
    if currency_input == "USD":
        usd = price_input
    else:
        usd = price_input / db_rate  # db_rate = nombre de CDF pour 1 USD
    return Decimal(usd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_amount(amount: Decimal, currency: Currency) -> str:
    """Formate selon les règles de la devise en base : $20.00 / 50 000 FC."""
    dp = int(currency.decimal_places or 0)
    q = Decimal(amount).quantize(Decimal("1") if dp == 0 else Decimal("0." + "0" * dp),
                                 rounding=ROUND_HALF_UP)
    sign = "-" if q < 0 else ""
    q = abs(q)
    int_part, _, frac = str(q).partition(".")
    grouped = ""
    for i, ch in enumerate(reversed(int_part)):
        grouped = ch + (currency.thousands_sep if i and i % 3 == 0 else "") + grouped
    body = grouped + (f"{currency.decimal_sep}{frac}" if dp else "")
    return f"{sign}{currency.symbol}{body}" if currency.symbol_position == "before" \
        else f"{sign}{body} {currency.symbol}"


async def display_price(db: AsyncSession, price_usd: Decimal, user: Optional[User]) -> tuple[str, Decimal, str]:
    """Retourne (texte formaté, valeur, code) selon la préférence devise du user (ou USD)."""
    code = getattr(user, "currency_display", None) or "USD"
    try:
        cur = await _get_currency(db, code)
    except ValidationError_:
        code, cur = "USD", await _get_currency(db, "USD")
    value = (price_usd * await get_rate_usd_to(db, code)) if code != "USD" else price_usd
    return format_amount(value, cur), Decimal(value), code


# ------------------------------------------------------------------ Limites plan


async def check_product_limit(db: AsyncSession, tenant: Tenant) -> None:
    """403 explicite si la limite produits du plan est atteinte (config-driven)."""
    limit = await get_rule(db, f"limits.{tenant.plan_name}.max_products", None)
    if limit is None:
        return  # pas de règle → pas de limite (extensible sans code)
    limit = int(limit)
    if limit < 0:
        return  # -1 = illimité
    current = await crud_product.count_tenant_products(db, tenant.id)
    if current >= limit:
        raise PermissionDeniedError(
            f"Limite de votre plan atteinte ({limit} produits). "
            "Passez au plan supérieur pour ajouter plus de produits."
        )


async def max_images_per_product(db: AsyncSession, tenant: Tenant) -> int:
    val = await get_rule(db, f"limits.{tenant.plan_name}.max_images_per_product", 10)
    return int(val)


# ------------------------------------------------------------------ CRUD métier


async def create_category(
    db: AsyncSession, tenant: Tenant, *, name: str, parent_id: Optional[str],
    description: Optional[str], icon_url: Optional[str], display_order: int,
) -> Category:
    """Catégorie PRIVÉE du tenant (les globales sont réservées au superadmin)."""
    if parent_id is not None:
        parent = await crud_product.get_tenant_category(db, tenant.id, parent_id)
        if parent is None:
            raise NotFoundError("Catégorie parente introuvable")
    slug = await crud_product.unique_category_slug(db, name, tenant.id)
    cat = await crud_product.create_category(
        db, tenant_id=tenant.id, name=name, slug=slug, parent_id=parent_id,
        description=description, icon_url=icon_url, display_order=display_order,
        is_active=True,
    )
    await events.emit("category.created", {"id": cat.id, "tenant_id": tenant.id})
    return cat


async def update_category(db: AsyncSession, tenant: Tenant, category_id: str, changes: dict) -> Category:
    cat = await crud_product.get_category(db, category_id)
    if cat is None:
        raise NotFoundError("Catégorie introuvable")
    if cat.tenant_id is None:
        raise PermissionDeniedError("Catégorie globale : modification réservée au superadmin")
    if cat.tenant_id != tenant.id:
        raise NotFoundError("Catégorie introuvable")  # isolation : pas de fuite d'existence
    if changes.get("name"):
        cat.name = changes["name"]
        cat.slug = await crud_product.unique_category_slug(db, changes["name"], tenant.id)
    for field in ("description", "icon_url", "display_order", "is_active", "parent_id"):
        if field in changes and changes[field] is not None:
            setattr(cat, field, changes[field])
    await db.flush()
    return cat


async def deactivate_category(db: AsyncSession, tenant: Tenant, category_id: str) -> Category:
    """Soft delete : is_active=false. Les globales et les autres tenants → 404."""
    cat = await crud_product.get_category(db, category_id)
    if cat is None or cat.tenant_id != tenant.id:
        raise NotFoundError("Catégorie introuvable")
    cat.is_active = False
    await db.flush()
    return cat


async def create_product(
    db: AsyncSession, tenant: Tenant, user: User, data: dict,
) -> Product:
    """Crée un produit : vérifie limite de plan, catégorie, convertit le prix en USD."""
    await check_product_limit(db, tenant)

    category_id = data.get("category_id")
    if category_id:
        cat = await crud_product.get_tenant_category(db, tenant.id, category_id)
        if cat is None or not cat.is_active:
            raise ValidationError_("Catégorie invalide ou inactive")

    currency_input = data.get("currency_input", "CDF")
    rate = await get_rate_usd_to(db, currency_input) if currency_input != "USD" else Decimal("1")
    price_usd = convert_price_input(rate, Decimal(str(data["price_input"])), currency_input)

    slug = await crud_product.unique_product_slug(db, tenant.id, data["name"])
    prod = await crud_product.create_product(
        db,
        tenant_id=tenant.id,  # ← JAMAIS depuis le body : depuis le JWT
        category_id=category_id,
        name=data["name"],
        slug=slug,
        description=data.get("description"),
        short_description=data.get("short_description"),
        price_usd=price_usd,
        price_input=Decimal(str(data["price_input"])),
        currency_input=currency_input,
        stock=int(data.get("stock", 0)),
        reserved_stock=0,
        sku=data.get("sku"),
        weight_kg=Decimal(str(data["weight_kg"])) if data.get("weight_kg") else None,
        is_active=True,
        is_published=bool(data.get("is_published", False)),
        created_by=user.id,
    )
    await events.emit("product.created", {"id": prod.id, "tenant_id": tenant.id})
    if prod.is_published:
        await events.emit("product.published", {"id": prod.id})
    return prod


async def update_product(db: AsyncSession, tenant: Tenant, product_id: str, changes: dict) -> Product:
    prod = await _owned_product(db, tenant, product_id)
    before = {"price_usd": str(prod.price_usd), "stock": prod.stock}
    if changes.get("name"):
        prod.name = changes["name"]
        prod.slug = await crud_product.unique_product_slug(db, tenant.id, changes["name"])
    currency_input = changes.get("currency_input", prod.currency_input)
    if changes.get("price_input") is not None:
        rate = await get_rate_usd_to(db, currency_input)
        prod.price_input = Decimal(str(changes["price_input"]))
        prod.currency_input = currency_input
        prod.price_usd = convert_price_input(rate, prod.price_input, currency_input)
    for field in ("description", "short_description", "sku", "is_active"):
        if field in changes and changes[field] is not None:
            setattr(prod, field, changes[field])
    if "category_id" in changes:
        if changes["category_id"]:
            cat = await crud_product.get_tenant_category(db, tenant.id, changes["category_id"])
            if cat is None:
                raise ValidationError_("Catégorie invalide")
        prod.category_id = changes["category_id"]
    if "weight_kg" in changes and changes["weight_kg"] is not None:
        prod.weight_kg = Decimal(str(changes["weight_kg"]))
    if "stock" in changes and changes["stock"] is not None:
        await set_stock(db, prod, int(changes["stock"]), reason="update")
    await db.flush()
    await events.emit("product.updated", {"id": prod.id, "changes": [k for k in changes]})
    _ = before
    return prod


async def publish_product(db: AsyncSession, tenant: Tenant, product_id: str, published: bool) -> Product:
    prod = await _owned_product(db, tenant, product_id)
    if prod.is_published != published:
        prod.is_published = published
        await db.flush()
        await events.emit(
            "product.published" if published else "product.unpublished",
            {"id": prod.id, "tenant_id": tenant.id},
        )
    return prod


async def deactivate_product(db: AsyncSession, tenant: Tenant, product_id: str) -> Product:
    """Soft delete (is_active=false) — jamais de suppression dure des données client."""
    prod = await _owned_product(db, tenant, product_id)
    prod.is_active = False
    await db.flush()
    await events.emit("product.deleted", {"id": prod.id, "mode": "soft"})
    return prod


async def bulk_action(db: AsyncSession, tenant: Tenant, ids: list[str], action: str) -> dict:
    results = {"updated": [], "not_found": []}
    for pid in ids:
        prod = await crud_product.get_tenant_product(db, tenant.id, pid)
        if prod is None:
            results["not_found"].append(pid)
            continue
        if action == "publish":
            prod.is_published = True
        elif action == "unpublish":
            prod.is_published = False
        elif action == "deactivate":
            prod.is_active = False
        results["updated"].append(pid)
    await db.flush()
    return results


# ------------------------------------------------------------------ Stock


async def set_stock(db: AsyncSession, prod: Product, new_stock: int, reason: str = "") -> Product:
    """Définit le stock physique et émet stock_changed / out_of_stock."""
    old = int(prod.stock or 0)
    new_stock = max(0, int(new_stock))
    if new_stock < int(prod.reserved_stock or 0):
        raise ValidationError_(
            f"Stock insuffisant : {prod.reserved_stock} unité(s) déjà réservée(s) par des commandes"
        )
    prod.stock = new_stock
    await db.flush()
    await events.emit("product.stock_changed",
                      {"id": prod.id, "old_stock": old, "new_stock": new_stock, "reason": reason})
    if new_stock - int(prod.reserved_stock or 0) <= 0 and old > 0:
        await events.emit("product.out_of_stock", {"id": prod.id, "tenant_id": prod.tenant_id})
    return prod


async def adjust_stock(db: AsyncSession, tenant: Tenant, product_id: str, delta: int, reason: str = "") -> Product:
    prod = await _owned_product(db, tenant, product_id)
    target = int(prod.stock or 0) + int(delta)
    return await set_stock(db, prod, target, reason=reason or "manual_adjust")


async def reserve_stock(db: AsyncSession, prod: Product, qty: int) -> None:
    """Réservation à la création de commande (Prompt 3). Refuse si indisponible."""
    available = int(prod.stock or 0) - int(prod.reserved_stock or 0)
    if qty > available:
        raise ValidationError_(
            f"Stock insuffisant pour « {prod.name} » : disponible {available}, demandé {qty}"
        )
    prod.reserved_stock = int(prod.reserved_stock or 0) + qty
    await db.flush()


async def release_reserved_stock(db: AsyncSession, prod: Product, qty: int, delivered: bool = False) -> None:
    """Livraison (décrémente stock aussi) ou annulation → libère la réservation."""
    prod.reserved_stock = max(0, int(prod.reserved_stock or 0) - qty)
    if delivered:
        prod.stock = max(0, int(prod.stock or 0) - qty)
        prod.sales_count = int(prod.sales_count or 0) + qty
        await db.flush()
        if int(prod.stock) <= 0:
            await events.emit("product.out_of_stock", {"id": prod.id, "tenant_id": prod.tenant_id})
    await db.flush()


async def low_stock_threshold(db: AsyncSession, tenant: Tenant) -> int:
    val = await get_rule_number(db, "stock.low_stock_threshold", default=5)
    return int(val)


# ------------------------------------------------------------------ Images


async def attach_image(db: AsyncSession, tenant: Tenant, prod: Product, urls: dict[str, str],
                       alt_text: Optional[str] = None) -> ProductImage:
    quota = await max_images_per_product(db, tenant)
    current = await crud_product.count_images(db, prod.id)
    if current >= quota:
        raise PermissionDeniedError(
            f"Limite de votre plan atteinte ({quota} images/produit). "
            "Passez au plan supérieur pour ajouter plus d'images."
        )
    img = await crud_product.add_image(
        db,
        product_id=prod.id,
        url=urls["url"],
        thumb_url=urls.get("thumb_url"),
        medium_url=urls.get("medium_url"),
        alt_text=alt_text,
        display_order=current,
        is_primary=(current == 0),  # la première image devient principale
    )
    return img


# ------------------------------------------------------------------ Sérialisation


async def serialize_product(
    db: AsyncSession, prod: Product, user: Optional[User], full: bool = True
) -> dict[str, Any]:
    """Produit → dict avec prix affiché selon la devise de préférence du user."""
    price_display, price_value, cur_code = await display_price(db, Decimal(prod.price_usd), user)
    primary = next((i for i in prod.images if i.is_primary), prod.images[0] if prod.images else None)
    data: dict[str, Any] = {
        "id": prod.id,
        "tenant_id": prod.tenant_id,
        "category_id": prod.category_id,
        "name": prod.name,
        "slug": prod.slug,
        "price_usd": Decimal(prod.price_usd),
        "price_display": price_display,
        "price_value_display": Decimal(price_value),
        "currency_display": cur_code,
        "currency_input": prod.currency_input,
        "stock": int(prod.stock),
        "reserved_stock": int(prod.reserved_stock),
        "available_stock": prod.available_stock,
        "sku": prod.sku,
        "weight_kg": Decimal(prod.weight_kg) if prod.weight_kg is not None else None,
        "is_active": prod.is_active,
        "is_published": prod.is_published,
        "views_count": int(prod.views_count),
        "sales_count": int(prod.sales_count),
        "rating_avg": Decimal(prod.rating_avg),
        "rating_count": int(prod.rating_count),
        "primary_image_url": (primary.thumb_url or primary.url) if primary else None,
    }
    if full:
        data["description"] = prod.description
        data["short_description"] = prod.short_description
        data["images"] = [
            {
                "id": i.id, "url": i.url, "thumb_url": i.thumb_url,
                "medium_url": i.medium_url, "alt_text": i.alt_text,
                "display_order": i.display_order, "is_primary": i.is_primary,
            }
            for i in prod.images
        ]
        data["category"] = (
            {"id": prod.category.id, "name": prod.category.name, "slug": prod.category.slug}
            if prod.category else None
        )
        data["created_at"] = prod.created_at.isoformat() if prod.created_at else None
        data["updated_at"] = prod.updated_at.isoformat() if prod.updated_at else None
    return data


# ------------------------------------------------------------------ Recherche FTS


async def fts_search(
    db: AsyncSession, q: str, *, tenant_slug: Optional[str] = None, limit: int = 50
) -> list[Product] | None:
    """Full-text PostgreSQL ('french' + ts_rank). Retourne None si non applicable.

    Appelé par l'endpoint shop : si None (SQLite/tests ou zéro résultat),
    on retombe sur la recherche ILIKE du CRUD (fallback exigé par le cahier
    des charges).
    """
    if db.bind is None or db.bind.dialect.name != "postgresql" or not q.strip():
        return None
    sql = """
        SELECT p.id FROM products p
        LEFT JOIN tenants t ON t.id = p.tenant_id
        WHERE p.is_active AND p.is_published
          AND (:slug IS NULL OR t.slug = :slug)
          AND to_tsvector('french', coalesce(p.name,'') || ' ' || coalesce(p.description,''))
              @@ plainto_tsquery('french', :q)
        ORDER BY ts_rank(
            to_tsvector('french', coalesce(p.name,'') || ' ' || coalesce(p.description,'')),
            plainto_tsquery('french', :q)
        ) DESC
        LIMIT :lim
    """
    try:
        rows = (await db.execute(sa_text(sql), {"q": q, "slug": tenant_slug, "lim": limit})).all()
    except Exception as exc:  # config_text_search_configuration absente etc.
        logger.warning("FTS unavailable, falling back to ILIKE: %s", exc)
        return None
    if not rows:
        return None  # tsquery muet → fallback ILIKE côté appelant
    ids = [r[0] for r in rows]
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    prods = (
        await db.execute(
            select(Product).where(Product.id.in_(ids)).options(
                selectinload(Product.images)
            )
        )
    ).scalars().all()
    order = {pid: idx for idx, pid in enumerate(ids)}
    return sorted(prods, key=lambda p: order.get(p.id, 999))


# ------------------------------------------------------------------ Interne


async def _owned_product(db: AsyncSession, tenant: Tenant, product_id: str) -> Product:
    prod = await crud_product.get_tenant_product(db, tenant.id, product_id)
    if prod is None:
        raise NotFoundError("Produit introuvable")  # 404 même si existe chez B (isolation)
    return prod
