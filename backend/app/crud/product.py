"""CRUD Catalogue — accès base de données (catégories, produits, images).

Toutes les fonctions vendeur prennent explicitement un `tenant_id` issu du
JWT : le filtre est appliqué DANS chaque requête (défense en profondeur,
règle d'or multi-tenant).
"""

from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.tenant import slugify
from app.models.category import Category
from app.models.product import Product, ProductImage
from app.models.search_query import SearchQuery

# ------------------------------------------------------------------ Catégories


async def list_categories(
    db: AsyncSession, tenant_id: Optional[str] = None, active_only: bool = False
) -> Sequence[Category]:
    """Catégories globales (tenant_id NULL) + catégories du tenant."""
    stmt = select(Category).where(
        or_(Category.tenant_id.is_(None), Category.tenant_id == tenant_id)
        if tenant_id
        else Category.tenant_id.is_(None)
    )
    if active_only:
        stmt = stmt.where(Category.is_active.is_(True))
    stmt = stmt.order_by(Category.display_order, Category.name)
    return (await db.execute(stmt)).scalars().all()


async def get_category(db: AsyncSession, category_id: str) -> Optional[Category]:
    result = await db.execute(select(Category).where(Category.id == category_id))
    return result.scalar_one_or_none()


async def get_tenant_category(
    db: AsyncSession, tenant_id: str, category_id: str
) -> Optional[Category]:
    """Catégorie appartenant au tenant (globale incluse pour lecture seule)."""
    result = await db.execute(
        select(Category).where(
            Category.id == category_id,
            or_(Category.tenant_id == tenant_id, Category.tenant_id.is_(None)),
        )
    )
    return result.scalar_one_or_none()


async def unique_category_slug(
    db: AsyncSession, name: str, tenant_id: Optional[str]
) -> str:
    """Slug unique dans l'espace (tenant_id, slug) — contrainte uq_categories_tenant_slug."""
    base = slugify(name)
    slug, i = base, 1
    while True:
        stmt = select(Category.id).where(Category.slug == slug)
        stmt = (
            stmt.where(Category.tenant_id.is_(None))
            if tenant_id is None
            else stmt.where(Category.tenant_id == tenant_id)
        )
        if (await db.execute(stmt)).scalar_one_or_none() is None:
            return slug
        i += 1
        slug = f"{base}-{i}"


async def create_category(db: AsyncSession, **fields) -> Category:
    cat = Category(**fields)
    db.add(cat)
    await db.flush()
    return cat


async def count_child_categories(db: AsyncSession, category_id: str) -> int:
    stmt = select(func.count()).select_from(Category).where(
        Category.parent_id == category_id, Category.is_active.is_(True)
    )
    return int((await db.execute(stmt)).scalar_one())


# -------------------------------------------------------------------- Produits


async def unique_product_slug(db: AsyncSession, tenant_id: str, name: str) -> str:
    base = slugify(name)
    slug, i = base, 1
    while True:
        exists = await db.execute(
            select(Product.id).where(
                Product.tenant_id == tenant_id, Product.slug == slug
            )
        )
        if exists.scalar_one_or_none() is None:
            return slug
        i += 1
        slug = f"{base}-{i}"


async def get_product(
    db: AsyncSession, product_id: str, with_rel: bool = True
) -> Optional[Product]:
    """Produit par id SANS filtre tenant : le SERVICE vérifie la propriété."""
    stmt = select(Product).where(Product.id == product_id)
    if with_rel:
        stmt = stmt.options(
            selectinload(Product.images), selectinload(Product.category)
        )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_tenant_product(db: AsyncSession, tenant_id: str, product_id: str) -> Optional[Product]:
    """Isolation stricte : le produit doit appartenir au tenant du JWT."""
    stmt = (
        select(Product)
        .where(Product.id == product_id, Product.tenant_id == tenant_id)
        .options(selectinload(Product.images), selectinload(Product.category))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def count_tenant_products(db: AsyncSession, tenant_id: str) -> int:
    """Nombre de produits ACTIFS du tenant (pour les limites de plan)."""
    stmt = (
        select(func.count())
        .select_from(Product)
        .where(Product.tenant_id == tenant_id, Product.is_active.is_(True))
    )
    return int((await db.execute(stmt)).scalar_one())


async def create_product(db: AsyncSession, **fields) -> Product:
    prod = Product(**fields)
    db.add(prod)
    await db.flush()
    return prod


async def search_products(
    db: AsyncSession,
    *,
    tenant_id: Optional[str] = None,          # None → shop public multi-boutiques
    published_only: bool = False,
    q: Optional[str] = None,
    category_id: Optional[str] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    min_rating: Optional[float] = None,
    stock_status: Optional[str] = None,       # in_stock | low_stock | out_of_stock
    in_stock_only: bool = False,
    sort: str = "-created_at",
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Product], int]:
    """Recherche/filtrage/pagination. Fallback ILIKE universel (PG et SQLite).

    Note PG : la migration ajoute un index GIN tsvector('french') ; sur
    PostgreSQL, `product_service` peut tenter d'abord to_tsquery puis retomber
    ici si le dialecte n'est pas PG ou si le tsquery ne retourne rien.
    """
    stmt = select(Product)
    count_stmt = select(func.count()).select_from(Product)

    def apply_filters(s):
        if tenant_id is not None:
            s = s.where(Product.tenant_id == tenant_id)
        if published_only:
            s = s.where(Product.is_published.is_(True))
        if not _is_vendor_scope(tenant_id):
            # Shop public : uniquement actifs + publiés
            s = s.where(Product.is_active.is_(True), Product.is_published.is_(True))
        else:
            s = s.where(Product.is_active.is_(True))
        if q:
            like = f"%{q.strip()}%"
            s = s.where(or_(Product.name.ilike(like), Product.short_description.ilike(like)))
        if category_id:
            s = s.where(Product.category_id == category_id)
        if min_price is not None:
            s = s.where(Product.price_usd >= min_price)
        if max_price is not None:
            s = s.where(Product.price_usd <= max_price)
        if min_rating is not None:
            s = s.where(Product.rating_avg >= Decimal(str(min_rating)))
        if in_stock_only:
            s = s.where(Product.stock > Product.reserved_stock)
        if stock_status == "in_stock":
            s = s.where(Product.stock - Product.reserved_stock > 0)
        elif stock_status == "out_of_stock":
            s = s.where(Product.stock - Product.reserved_stock <= 0)
        elif stock_status == "low_stock":
            s = s.where(
                Product.stock - Product.reserved_stock > 0,
                Product.stock - Product.reserved_stock <= 5,
            )
        return s

    stmt = apply_filters(stmt).options(selectinload(Product.images))
    count_stmt = apply_filters(count_stmt)

    total = int((await db.execute(count_stmt)).scalar_one())

    order_map = {
        "created_at": Product.created_at.asc(),
        "-created_at": Product.created_at.desc(),
        "price_usd": Product.price_usd.asc(),
        "-price_usd": Product.price_usd.desc(),
        "sales_count": Product.sales_count.desc(),
        "views_count": Product.views_count.desc(),
        "relevance": Product.sales_count.desc(),  # proxy pertinence sans FTS
    }
    stmt = stmt.order_by(order_map.get(sort, Product.created_at.desc()), Product.id)
    stmt = stmt.offset(max(page - 1, 0) * per_page).limit(per_page)
    items = list((await db.execute(stmt)).unique().scalars().all())
    return items, total


def _is_vendor_scope(tenant_id: Optional[str]) -> bool:
    """Le scope vendeur voit ses brouillons ; le shop public non."""
    return tenant_id is not None


async def increment_views(db: AsyncSession, product_id: str) -> None:
    prod = await get_product(db, product_id, with_rel=False)
    if prod is not None:
        prod.views_count = int(prod.views_count or 0) + 1
        await db.flush()


# ---------------------------------------------------------------------- Images


async def get_product_image(
    db: AsyncSession, product_id: str, image_id: str
) -> Optional[ProductImage]:
    result = await db.execute(
        select(ProductImage).where(
            ProductImage.id == image_id, ProductImage.product_id == product_id
        )
    )
    return result.scalar_one_or_none()


async def add_image(db: AsyncSession, **fields) -> ProductImage:
    img = ProductImage(**fields)
    db.add(img)
    await db.flush()
    return img


async def count_images(db: AsyncSession, product_id: str) -> int:
    stmt = (
        select(func.count())
        .select_from(ProductImage)
        .where(ProductImage.product_id == product_id)
    )
    return int((await db.execute(stmt)).scalar_one())


async def set_primary_image(db: AsyncSession, product_id: str, image_id: str) -> None:
    imgs = (
        await db.execute(select(ProductImage).where(ProductImage.product_id == product_id))
    ).scalars().all()
    for im in imgs:
        im.is_primary = im.id == image_id
    await db.flush()


# ------------------------------------------------------------- Search queries


async def record_search(
    db: AsyncSession,
    *,
    query_text: str,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    results_count: int = 0,
) -> SearchQuery:
    sq = SearchQuery(
        query_text=query_text[:200],
        tenant_id=tenant_id,
        user_id=user_id,
        results_count=results_count,
    )
    db.add(sq)
    await db.flush()
    return sq
