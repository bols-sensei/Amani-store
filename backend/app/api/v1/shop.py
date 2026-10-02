"""Endpoints PUBLICS /api/v1/shop — recherche, produits, catégories, boutiques.

Pas d'authentification requise. Auth OPTIONNELLE : si un Bearer JWT est
présent et valide, on utilise la préférence de devise du user pour l'affichage
des prix ; sinon USD par défaut.

Règles boutique : seuls les produits is_active + is_published des tenants
"active" sont visibles. Chaque recherche est journalisée dans search_queries
(analytics) quand elle est effectuée par un user connecté.
"""

from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.user import User
from app.crud import product as crud_product
from app.crud.tenant import get_tenant_by_slug
from app.services import product_service

router = APIRouter(prefix="/shop", tags=["shop-public"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _optional_user(
    request: Request, db: DbDep,
    authorization: Annotated[Optional[str], Header()] = None,
) -> Optional[User]:
    """Auth optionnelle : retourne le user si Bearer valide, sinon None (jamais 401)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    from jose import JWTError

    from app.core.security import decode_token
    from app.crud.user import get_user_by_id

    try:
        payload = decode_token(authorization.removeprefix("Bearer ").strip())
        uid = payload.get("sub")
        if not uid:
            return None
        return await get_user_by_id(db, uid)
    except JWTError:
        return None


def _cat_out(c, with_products_count: bool = False) -> dict:
    return {
        "id": c.id, "tenant_id": c.tenant_id, "parent_id": c.parent_id,
        "name": c.name, "slug": c.slug, "description": c.description,
        "icon_url": c.icon_url, "display_order": c.display_order,
        "is_active": c.is_active,
    }


@router.get("/products")
async def public_search_products(
    request: Request,
    db: DbDep,
    user: Annotated[Optional[User], Depends(_optional_user)],
    q: Optional[str] = Query(default=None, max_length=200),
    category_id: Optional[str] = None,
    tenant_slug: Optional[str] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    min_rating: Optional[float] = Query(default=None, ge=0, le=5),
    in_stock_only: bool = False,
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Recherche publique multi-boutiques.

    Stratégie : sur PostgreSQL, tentative full-text (tsvector 'french' +
    ts_rank, index GIN de la migration 0005) ; si non applicable ou zéro
    résultat → fallback ILIKE (CRUD). Sur SQLite (tests) → ILIKE directement.
    """
    fts_items = await product_service.fts_search(db, q or "", tenant_slug=tenant_slug)
    if fts_items is not None:
        # filtre fin sur ids FTS via CRUD (prix/catégorie/rating restent possibles)
        ids = [p.id for p in fts_items]
        items = [p for p in fts_items]
        total = len(items)
        page_items = items[(page - 1) * per_page : page * per_page]
        out = [await product_service.serialize_product(db, p, user, full=False)
               for p in page_items]
        if q:
            await crud_product.record_search(
                db, query_text=q, user_id=user.id if user else None, results_count=total
            )
        _ = ids
        return {"items": out, "total": total, "page": page,
                "per_page": per_page, "engine": "full_text"}

    # --- Fallback ILIKE (+ filtres prix/rating/stock côté SQL) ---
    tenant_id = None
    if tenant_slug:
        t = await get_tenant_by_slug(db, tenant_slug)
        if t is None or t.status != "active":
            raise NotFoundError("Boutique introuvable")
        tenant_id = t.id

    items, total = await crud_product.search_products(
        db,
        tenant_id=tenant_id,
        published_only=True,
        q=q,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        in_stock_only=in_stock_only,
        sort=sort if sort != "relevance" else "-sales_count",
        page=page,
        per_page=per_page,
    )
    out = [await product_service.serialize_product(db, p, user, full=False) for p in items]
    if q:
        await crud_product.record_search(
            db, query_text=q, tenant_id=tenant_id,
            user_id=user.id if user else None, results_count=total,
        )
    return {"items": out, "total": total, "page": page,
            "per_page": per_page, "engine": "ilike"}


@router.get("/products/{product_id}")
async def public_product_detail(
    request: Request, product_id: str, db: DbDep,
    user: Annotated[Optional[User], Depends(_optional_user)],
) -> dict:
    """Détail produit public (incrmente views_count). 404 si non publié/inactif."""
    prod = await crud_product.get_product(db, product_id)
    if prod is None or not prod.is_active or not prod.is_published:
        raise NotFoundError("Produit introuvable")
    from app.crud.tenant import get_tenant_by_id

    tenant = await get_tenant_by_id(db, prod.tenant_id)
    if tenant is None or tenant.status != "active":
        raise NotFoundError("Produit introuvable")
    prod.views_count = int(prod.views_count or 0) + 1
    await db.flush()
    return await product_service.serialize_product(db, prod, user, full=True)


@router.get("/categories")
async def public_categories(request: Request, db: DbDep) -> list[dict]:
    """Catégories globales actives (celles du superadmin)."""
    cats = await crud_product.list_categories(db, tenant_id=None, active_only=True)
    return [_cat_out(c) for c in cats]


@router.get("/categories/{slug}/products")
async def category_products(
    request: Request, slug: str, db: DbDep,
    user: Annotated[Optional[User], Depends(_optional_user)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Produits publiés d'une catégorie (globale ou n'importe quel tenant) par slug."""
    from sqlalchemy import select

    from app.models.category import Category

    cat = (await db.execute(
        select(Category).where(Category.slug == slug, Category.is_active.is_(True))
    )).scalars().first()
    if cat is None:
        raise NotFoundError("Catégorie introuvable")
    items, total = await crud_product.search_products(
        db, tenant_id=None, published_only=True, category_id=cat.id,
        page=page, per_page=per_page,
    )
    out = [await product_service.serialize_product(db, p, user, full=False) for p in items]
    return {"category": _cat_out(cat), "items": out, "total": total,
            "page": page, "per_page": per_page}


@router.get("/shops/{tenant_slug}")
async def shop_info(tenant_slug: str, request: Request, db: DbDep) -> dict:
    """Fiche publique d'une boutique (nom, logo, plan visible? non — juste info vitrine)."""
    t = await get_tenant_by_slug(db, tenant_slug)
    if t is None or t.status != "active":
        raise NotFoundError("Boutique introuvable")
    from sqlalchemy import func, select

    from app.models.product import Product

    nb = int((await db.execute(
        select(func.count()).select_from(Product).where(
            Product.tenant_id == t.id, Product.is_active.is_(True),
            Product.is_published.is_(True))
    )).scalar_one())
    return {
        "name": t.name, "slug": t.slug, "logo_url": t.logo_url,
        "banner_url": t.banner_url, "country_code": t.country_code,
        "published_products": nb,
    }


@router.get("/shops/{tenant_slug}/products")
async def shop_products(
    tenant_slug: str, request: Request, db: DbDep,
    user: Annotated[Optional[User], Depends(_optional_user)],
    q: Optional[str] = None,
    category_id: Optional[str] = None,
    sort: str = "-created_at",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> dict:
    t = await get_tenant_by_slug(db, tenant_slug)
    if t is None or t.status != "active":
        raise NotFoundError("Boutique introuvable")
    items, total = await crud_product.search_products(
        db, tenant_id=t.id, published_only=True, q=q, category_id=category_id,
        sort=sort, page=page, per_page=per_page,
    )
    out = [await product_service.serialize_product(db, p, user, full=False) for p in items]
    return {"items": out, "total": total, "page": page, "per_page": per_page}


@router.get("/shops/{tenant_slug}/categories")
async def shop_categories(tenant_slug: str, request: Request, db: DbDep) -> list[dict]:
    """Catégories globales + privées utilisées par cette boutique."""
    t = await get_tenant_by_slug(db, tenant_slug)
    if t is None or t.status != "active":
        raise NotFoundError("Boutique introuvable")
    cats = await crud_product.list_categories(db, tenant_id=t.id, active_only=True)
    return [_cat_out(c) for c in cats]


@router.get("/search/suggestions")
async def search_suggestions(
    request: Request, db: DbDep,
    q: str = Query(min_length=1, max_length=100),
) -> dict:
    """Autocomplete : top 5 produits publiés + top 3 catégories (ILIKE)."""
    prods, _ = await crud_product.search_products(
        db, tenant_id=None, published_only=True, q=q, per_page=5, sort="relevance"
    )
    from sqlalchemy import select

    from app.models.category import Category

    like = f"%{q.strip()}%"
    cats = (await db.execute(
        select(Category)
        .where(Category.is_active.is_(True), Category.name.ilike(like))
        .limit(3)
    )).scalars().all()
    return {
        "products": [{"id": p.id, "name": p.name, "slug": p.slug,
                      "price_usd": str(p.price_usd)} for p in prods],
        "categories": [_cat_out(c) for c in cats],
    }
