"""CRUD Commandes — filtres tenant/customer obligatoires selon le rôle."""

from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import DeliveryZone, Order, OrderItem, OrderStatusHistory


def _with_rel(stmt):
    return stmt.options(selectinload(Order.items), selectinload(Order.history))


async def get_order(db: AsyncSession, order_id: str) -> Optional[Order]:
    return (await db.execute(_with_rel(select(Order)).where(Order.id == order_id))
            ).scalar_one_or_none()


async def get_order_for_tenant(
    db: AsyncSession, tenant_id: str, order_id: str
) -> Optional[Order]:
    return (await db.execute(
        _with_rel(select(Order)).where(Order.id == order_id, Order.tenant_id == tenant_id)
    )).scalar_one_or_none()


async def get_order_for_customer(
    db: AsyncSession, customer_id: str, order_id: str
) -> Optional[Order]:
    return (await db.execute(
        _with_rel(select(Order)).where(Order.id == order_id, Order.customer_id == customer_id)
    )).scalar_one_or_none()


async def list_orders(
    db: AsyncSession,
    *,
    tenant_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Order], int]:
    conds = []
    if tenant_id is not None:
        conds.append(Order.tenant_id == tenant_id)
    if customer_id is not None:
        conds.append(Order.customer_id == customer_id)
    if status:
        conds.append(Order.status == status)
    if date_from:
        conds.append(Order.created_at >= date_from)
    if date_to:
        conds.append(Order.created_at <= date_to)
    if search:
        conds.append(or_(Order.reference.ilike(f"%{search}%")))

    total = (await db.execute(select(func.count(Order.id)).where(*conds))).scalar_one()
    rows = (await db.execute(
        _with_rel(select(Order).where(*conds))
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return list(rows), int(total)


async def add_history(
    db: AsyncSession, order_id: str, old_status: Optional[str], new_status: str,
    changed_by: Optional[str], changed_by_role: Optional[str],
    reason: Optional[str] = None, metadata: Optional[dict] = None,
) -> OrderStatusHistory:
    h = OrderStatusHistory(
        order_id=order_id, old_status=old_status, new_status=new_status,
        changed_by=changed_by, changed_by_role=changed_by_role,
        reason=reason, metadata_=metadata,
    )
    db.add(h)
    await db.flush()
    return h


async def count_by_status(db: AsyncSession, tenant_id: Optional[str] = None) -> dict[str, int]:
    stmt = select(Order.status, func.count(Order.id)).group_by(Order.status)
    if tenant_id:
        stmt = stmt.where(Order.tenant_id == tenant_id)
    rows = (await db.execute(stmt)).all()
    return {status: int(n) for status, n in rows}


# ---------------------------------------------------------------- Zones
async def list_zones(db: AsyncSession, tenant_id: str, active_only: bool = False) -> list[DeliveryZone]:
    conds = [DeliveryZone.tenant_id == tenant_id]
    if active_only:
        conds.append(DeliveryZone.is_active.is_(True))
    rows = (await db.execute(
        select(DeliveryZone).where(*conds).order_by(DeliveryZone.name)
    )).scalars().all()
    return list(rows)


async def get_zone(db: AsyncSession, tenant_id: str, zone_id: str) -> Optional[DeliveryZone]:
    return (await db.execute(
        select(DeliveryZone).where(DeliveryZone.id == zone_id,
                                   DeliveryZone.tenant_id == tenant_id)
    )).scalar_one_or_none()


async def create_zone(db: AsyncSession, zone: DeliveryZone) -> DeliveryZone:
    db.add(zone)
    await db.flush()
    return zone
