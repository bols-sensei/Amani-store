"""CRUD Tenant — accès base de données."""

import re
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant


def slugify(name: str) -> str:
    """Convertit un nom de boutique en slug URL-safe."""
    slug = name.lower().strip()
    slug = re.sub(r"[àáâãäåçèéêëìíîïñòóôõùúûüÿœ]", lambda m: m.group(0), slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug[:60] or "boutique"


async def unique_slug(db: AsyncSession, name: str) -> str:
    """Génère un slug unique en ajoutant un suffixe numérique si besoin."""
    base = slugify(name)
    slug = base
    i = 1
    while True:
        existing = await db.execute(select(Tenant.id).where(Tenant.slug == slug))
        if existing.scalar_one_or_none() is None:
            return slug
        i += 1
        slug = f"{base}-{i}"


async def get_tenant_by_id(db: AsyncSession, tenant_id: str) -> Optional[Tenant]:
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Optional[Tenant]:
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    return result.scalar_one_or_none()


async def create_tenant(db: AsyncSession, **fields) -> Tenant:
    if "slug" not in fields or not fields["slug"]:
        fields["slug"] = await unique_slug(db, fields.get("name", "boutique"))
    tenant = Tenant(**fields)
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    return tenant


async def list_tenants(
    db: AsyncSession,
    status: Optional[str] = None,
    plan_name: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[Sequence[Tenant], int]:
    """Liste paginée avec filtres ; retourne (items, total)."""
    conds = []
    if status:
        conds.append(Tenant.status == status)
    if plan_name:
        conds.append(Tenant.plan_name == plan_name)
    if search:
        like = f"%{search.lower()}%"
        conds.append(func.lower(Tenant.name).like(like) | func.lower(Tenant.slug).like(like))

    count_stmt = select(func.count()).select_from(Tenant)
    stmt = select(Tenant)
    for c in conds:
        count_stmt = count_stmt.where(c)
        stmt = stmt.where(c)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Tenant.created_at.desc()).offset(offset).limit(limit)
    items = (await db.execute(stmt)).scalars().all()
    return items, total
