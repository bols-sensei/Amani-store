"""Endpoints /api/v1/vendor — catalogue (catégories + produits).

RÈGLE D'OR : tenant_id TOUJOURS via get_current_tenant (JWT), jamais le body.
Préfixe /vendor → aussi gardé par TenantStatusMiddleware (403 si tenant non actif).
Permissions granulaires : products.view/create/edit/delete/stock.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_tenant, require_permission, require_vendor
from app.core.exceptions import NotFoundError, ValidationError_
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.crud import product as crud_product
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.product import (
    BulkAction,
    ProductCreate,
    ProductUpdate,
    StockAdjust,
)
from app.services import product_service
from app.services.storage_service import get_storage

router = APIRouter(
    prefix="/vendor",
    tags=["vendor-catalog"],
    dependencies=[Depends(require_vendor)],
)

TenantDep = Annotated[Tenant, Depends(get_current_tenant)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _require_tenant(tenant: Optional[Tenant]) -> Tenant:
    if tenant is None:
        raise ValidationError_("Aucun tenant rattaché à ce compte")
    return tenant


def _cat_out(c) -> dict:
    return {
        "id": c.id, "tenant_id": c.tenant_id, "parent_id": c.parent_id,
        "name": c.name, "slug": c.slug, "description": c.description,
        "icon_url": c.icon_url, "display_order": c.display_order,
        "is_active": c.is_active, "children": [],
    }


# ------------------------------------------------------------------ Catégories


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(
    request: Request, db: DbDep, user: CurrentUser, tenant: TenantDep
) -> list[dict]:
    """Catégories du tenant + globales superadmin (lecture)."""
    t = _require_tenant(tenant)
    cats = await crud_product.list_categories(db, tenant_id=t.id)
    return [_cat_out(c) for c in cats]


@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(
    request: Request,
    body: CategoryCreate,
    db: DbDep,
    user: CurrentUser,
    tenant: TenantDep,
    _: object = Depends(require_permission("products.create")),
) -> dict:
    t = _require_tenant(tenant)
    cat = await product_service.create_category(
        db, t, name=body.name, parent_id=body.parent_id,
        description=body.description, icon_url=body.icon_url,
        display_order=body.display_order,
    )
    return _cat_out(cat)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    request: Request,
    category_id: str,
    body: CategoryUpdate,
    db: DbDep,
    user: CurrentUser,
    tenant: TenantDep,
    _: object = Depends(require_permission("products.edit")),
) -> dict:
    t = _require_tenant(tenant)
    cat = await product_service.update_category(
        db, t, category_id, body.model_dump(exclude_unset=True)
    )
    return _cat_out(cat)


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(
    request: Request,
    category_id: str,
    db: DbDep,
    user: CurrentUser,
    tenant: TenantDep,
    _: object = Depends(require_permission("products.delete")),
) -> None:
    """Soft delete (désactivation)."""
    t = _require_tenant(tenant)
    await product_service.deactivate_category(db, t, category_id)


# -------------------------------------------------------------------- Produits


@router.get("/products")
async def list_products(
    request: Request,
    db: DbDep,
    user: CurrentUser,
    tenant: TenantDep,
    _: object = Depends(require_permission("products.view")),
    q: Optional[str] = Query(default=None, max_length=200),
    category_id: Optional[str] = None,
    is_published: Optional[bool] = None,
    stock_status: Optional[str] = Query(
        default=None, pattern="^(in_stock|low_stock|out_of_stock)$"
    ),
    search: Optional[str] = Query(default=None, max_length=200),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Liste paginée des produits du tenant (brouillons inclus)."""
    t = _require_tenant(tenant)
    items, total = await crud_product.search_products(
        db,
        tenant_id=t.id,
        published_only=bool(is_published) if is_published is not None else False,
        q=search or q,
        category_id=category_id,
        stock_status=stock_status,
        sort=sort,
        page=page,
        per_page=per_page,
    )
    # filtre publié explicite seulement si demandé ; sinon tout (vue vendor)
    out = []
    for p in items:
        s = await product_service.serialize_product(db, p, user, full=False)
        if is_published is not None and p.is_published != is_published:
            continue
        s["is_published"] = p.is_published
        out.append(s)
    pages = (total + per_page - 1) // per_page
    return {"items": out, "total": total, "page": page, "per_page": per_page, "pages": pages}


@router.get("/products/stats/summary")
async def products_stats_summary(
    request: Request,
    db: DbDep,
    user: CurrentUser,
    tenant: TenantDep,
    _: object = Depends(require_permission("analytics.view")),
) -> dict:
    """Agrégats catalogue du tenant (seuil low-stock via business_rules)."""
    t = _require_tenant(tenant)
    threshold = await product_service.low_stock_threshold(db, t)
    from sqlalchemy import func, select

    from app.models.product import Product

    base = select(func.count()).select_from(Product).where(
        Product.tenant_id == t.id, Product.is_active.is_(True)
    )
    total = int((await db.execute(base)).scalar_one())
    published = int((await db.execute(
        base.where(Product.is_published.is_(True)))).scalar_one())
    drafts = total - published
    out_of_stock = int((await db.execute(
        base.where(Product.stock - Product.reserved_stock <= 0))).scalar_one())
    low_stock = int((await db.execute(
        base.where(
            Product.stock - Product.reserved_stock > 0,
            Product.stock - Product.reserved_stock <= threshold,
        ))).scalar_one())
    return {
        "total": total, "active": total, "published": published,
        "drafts": drafts, "low_stock": low_stock, "out_of_stock": out_of_stock,
    }


@router.get("/products/stats/low-stock")
async def products_low_stock(
    request: Request,
    db: DbDep,
    user: CurrentUser,
    tenant: TenantDep,
    _: object = Depends(require_permission("products.stock")),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Produits dont le stock disponible < seuil (business_rule stock.low_stock_threshold)."""
    t = _require_tenant(tenant)
    threshold = await product_service.low_stock_threshold(db, t)
    from sqlalchemy import select

    from app.models.product import Product

    stmt = (
        select(Product)
        .where(
            Product.tenant_id == t.id,
            Product.is_active.is_(True),
            Product.stock - Product.reserved_stock <= threshold,
        )
        .order_by(Product.stock.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    items = (await db.execute(stmt)).scalars().all()
    out = [await product_service.serialize_product(db, p, user, full=False) for p in items]
    return {"items": out, "threshold": threshold, "page": page, "per_page": per_page}


@router.get("/products/{product_id}")
async def get_product(
    request: Request,
    product_id: str,
    db: DbDep,
    user: CurrentUser,
    tenant: TenantDep,
    _: object = Depends(require_permission("products.view")),
) -> dict:
    t = _require_tenant(tenant)
    prod = await crud_product.get_tenant_product(db, t.id, product_id)
    if prod is None:
        raise NotFoundError("Produit introuvable")
    return await product_service.serialize_product(db, prod, user, full=True)


@router.post("/products", status_code=201)
async def create_product(
    request: Request,
    db: DbDep,
    user: CurrentUser,
    tenant: TenantDep,
    _: object = Depends(require_permission("products.create")),
    data: Annotated[str | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> dict:
    """Création produit en multipart : `data` = JSON ProductCreate, `files` = images.

    Accepte aussi l'application/json pur (corps lu manuellement) pour les
    clients qui n'envoient pas de fichier.
    """
    t = _require_tenant(tenant)
    payload = data
    if payload is None:
        try:
            payload = (await request.json()).get("data") or __import__("json").dumps(await request.json())
        except Exception:
            payload = None
    import json as _json

    raw = _json.loads(payload) if isinstance(payload, str) else (payload or {})
    body = ProductCreate.model_validate(raw)

    prod = await product_service.create_product(db, t, user, body.model_dump())

    added = []
    if files:
        storage = get_storage()
        for f in files:
            content = await f.read()
            ext = (f.filename or "img.jpg").rsplit(".", 1)[-1]
            try:
                urls = await storage.save_image(content, ext, t.id, prod.id)
            except ValueError as exc:
                raise ValidationError_(str(exc)) from exc
            img = await product_service.attach_image(db, t, prod, urls, alt_text=body.name)
            added.append(img)
        await db.flush()

    db.add(AuditLog(
        actor_id=user.id, actor_role=user.role, actor_ip=request.client.host if request.client else None,
        action="product.create", target_type="product", target_id=prod.id,
        after={"name": prod.name},
    ))
    await db.flush()  # insère l'audit AVANT le lazy-load des images (évite MissingGreenlet)
    result = await product_service.serialize_product(db, prod, user, full=True)
    return result


@router.patch("/products/{product_id}")
async def update_product(
    request: Request,
    product_id: str,
    body: ProductUpdate,
    db: DbDep,
    user: CurrentUser,
    tenant: TenantDep,
    _: object = Depends(require_permission("products.edit")),
) -> dict:
    t = _require_tenant(tenant)
    changes = body.model_dump(exclude_unset=True)
    prod = await product_service.update_product(db, t, product_id, changes)
    return await product_service.serialize_product(db, prod, user, full=True)


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    request: Request,
    product_id: str,
    db: DbDep,
    user: CurrentUser,
    tenant: TenantDep,
    _: object = Depends(require_permission("products.delete")),
) -> None:
    """Soft delete : is_active=false."""
    t = _require_tenant(tenant)
    await product_service.deactivate_product(db, t, product_id)


@router.post("/products/{product_id}/publish")
async def publish_product(
    request: Request, product_id: str, db: DbDep, user: CurrentUser, tenant: TenantDep,
    _: object = Depends(require_permission("products.edit")),
) -> dict:
    t = _require_tenant(tenant)
    prod = await product_service.publish_product(db, t, product_id, True)
    return await product_service.serialize_product(db, prod, user, full=False)


@router.post("/products/{product_id}/unpublish")
async def unpublish_product(
    request: Request, product_id: str, db: DbDep, user: CurrentUser, tenant: TenantDep,
    _: object = Depends(require_permission("products.edit")),
) -> dict:
    t = _require_tenant(tenant)
    prod = await product_service.publish_product(db, t, product_id, False)
    return await product_service.serialize_product(db, prod, user, full=False)


@router.post("/products/{product_id}/images", status_code=201)
async def add_images(
    request: Request,
    product_id: str,
    files: Annotated[list[UploadFile], File()],
    db: DbDep,
    user: CurrentUser,
    tenant: TenantDep,
    _: object = Depends(require_permission("products.edit")),
    alt_text: Annotated[Optional[str], Form()] = None,
) -> dict:
    t = _require_tenant(tenant)
    prod = await crud_product.get_tenant_product(db, t.id, product_id)
    if prod is None:
        raise NotFoundError("Produit introuvable")
    from app.crud.business_rule import get_rule_number

    max_upload = int(await get_rule_number(db, "images.max_per_upload", default=10))
    if len(files) > max_upload:
        raise ValidationError_(f"Maximum {max_upload} images par upload")
    storage = get_storage()
    added = []
    for f in files:
        content = await f.read()
        ext = (f.filename or "img.jpg").rsplit(".", 1)[-1]
        try:
            urls = await storage.save_image(content, ext, t.id, prod.id)
        except ValueError as exc:
            raise ValidationError_(str(exc)) from exc
        img = await product_service.attach_image(db, t, prod, urls, alt_text=alt_text)
        added.append(img)
    await db.flush()
    quota = await product_service.max_images_per_product(db, t)
    current = await crud_product.count_images(db, prod.id)
    return {
        "added": [
            {"id": i.id, "url": i.url, "thumb_url": i.thumb_url,
             "medium_url": i.medium_url, "alt_text": i.alt_text,
             "display_order": i.display_order, "is_primary": i.is_primary}
            for i in added
        ],
        "remaining_quota": max(0, quota - current),
    }


@router.delete("/products/{product_id}/images/{image_id}", status_code=204)
async def delete_image(
    request: Request, product_id: str, image_id: str,
    db: DbDep, user: CurrentUser, tenant: TenantDep,
    _: object = Depends(require_permission("products.edit")),
) -> None:
    t = _require_tenant(tenant)
    prod = await crud_product.get_tenant_product(db, t.id, product_id)
    if prod is None:
        raise NotFoundError("Produit introuvable")
    img = await crud_product.get_product_image(db, prod.id, image_id)
    if img is None:
        raise NotFoundError("Image introuvable")
    await get_storage().delete_image(img.url)
    await db.delete(img)
    await db.flush()


@router.patch("/products/{product_id}/images/{image_id}/primary")
async def set_primary_image(
    request: Request, product_id: str, image_id: str,
    db: DbDep, user: CurrentUser, tenant: TenantDep,
    _: object = Depends(require_permission("products.edit")),
) -> dict:
    t = _require_tenant(tenant)
    prod = await crud_product.get_tenant_product(db, t.id, product_id)
    if prod is None:
        raise NotFoundError("Produit introuvable")
    img = await crud_product.get_product_image(db, prod.id, image_id)
    if img is None:
        raise NotFoundError("Image introuvable")
    await crud_product.set_primary_image(db, prod.id, image_id)
    return {"ok": True}


@router.patch("/products/{product_id}/stock")
async def adjust_stock(
    request: Request, product_id: str, body: StockAdjust,
    db: DbDep, user: CurrentUser, tenant: TenantDep,
    _: object = Depends(require_permission("products.stock")),
) -> dict:
    t = _require_tenant(tenant)
    prod = await product_service.adjust_stock(db, t, product_id, body.delta, reason=body.reason or "")
    return await product_service.serialize_product(db, prod, user, full=False)


@router.post("/products/bulk-action")
async def bulk_action(
    request: Request, body: BulkAction,
    db: DbDep, user: CurrentUser, tenant: TenantDep,
    _: object = Depends(require_permission("products.edit")),
) -> dict:
    t = _require_tenant(tenant)
    return await product_service.bulk_action(db, t, body.product_ids, body.action)
