"""Endpoints /api/v1/vendor/orders + /vendor/delivery-zones.

RÈGLE D'OR : tenant_id via get_current_tenant (JWT), jamais le body.
Permissions granulaires : orders.view/manage, shipments.view/manage,
zones.manage.
"""

from datetime import datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_tenant, require_permission, require_vendor
from app.core.exceptions import NotFoundError, ValidationError_
from app.db.session import get_db
from app.models.tenant import Tenant
from app.crud import order as crud_order
from app.schemas.order import (
    DeliveryZoneCreate, DeliveryZoneUpdate, OrderStatusUpdate, OrdersStatsSummary,
)
from app.services import order_service
from app.services.order_state_machine import ALL_STATUSES, status_label

router = APIRouter(
    prefix="/vendor",
    tags=["vendor-orders"],
    dependencies=[Depends(require_vendor)],
)

TenantDep = Annotated[Tenant, Depends(get_current_tenant)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _require_tenant(tenant: Optional[Tenant]) -> Tenant:
    if tenant is None:
        raise ValidationError_("Aucun tenant rattaché à ce compte")
    return tenant


# ------------------------------------------------------------------ Commandes


@router.get("/orders")
async def list_orders(
    db: DbDep, user: CurrentUser, tenant: TenantDep,
    _: Annotated[dict, Depends(require_permission("orders.view"))],
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Liste des commandes du tenant avec filtres statut/période/recherche."""
    t = _require_tenant(tenant)
    rows, total = await crud_order.list_orders(
        db, tenant_id=t.id, status=status, date_from=date_from, date_to=date_to,
        search=search, page=page, page_size=page_size,
    )
    from app.api.v1.orders import _order_out
    return {
        "items": [_order_out(o) for o in rows],
        "total": total, "page": page, "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }


@router.get("/orders/stats/summary", response_model=OrdersStatsSummary)
async def orders_stats(db: DbDep, user: CurrentUser, tenant: TenantDep,
                       _: Annotated[dict, Depends(require_permission("orders.view"))]
                       ) -> dict[str, int]:
    """Compteurs par statut pour le dashboard vendeur."""
    t = _require_tenant(tenant)
    counts = await crud_order.count_by_status(db, tenant_id=t.id)
    return {"total": sum(counts.values()), **counts}


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str, db: DbDep, user: CurrentUser, tenant: TenantDep,
    _: Annotated[dict, Depends(require_permission("orders.view"))],
) -> dict[str, Any]:
    """Détail d'une commande du tenant (404 sinon — pas de fuite inter-tenant)."""
    t = _require_tenant(tenant)
    order = await crud_order.get_order_for_tenant(db, t.id, order_id)
    if order is None:
        raise NotFoundError("Commande introuvable")
    from app.api.v1.orders import _order_out
    out = _order_out(order)
    customer = order.customer if hasattr(order, "customer") else None
    out["delivery_address"] = order.delivery_address
    return out


@router.patch("/orders/{order_id}/status")
async def change_status(
    order_id: str, payload: OrderStatusUpdate, db: DbDep, user: CurrentUser,
    tenant: TenantDep,
    _: Annotated[dict, Depends(require_permission("orders.manage"))],
) -> dict[str, Any]:
    """Transition de statut (machine à états stricte côté service)."""
    t = _require_tenant(tenant)
    order = await crud_order.get_order_for_tenant(db, t.id, order_id)
    if order is None:
        raise NotFoundError("Commande introuvable")
    order = await order_service.update_order_status(
        db, order.id, payload.status, user, reason=payload.reason
    )
    from app.api.v1.orders import _order_out
    return _order_out(order)


# ------------------------------------------------------------- Zones livraison


@router.get("/delivery-zones")
async def list_zones(db: DbDep, user: CurrentUser, tenant: TenantDep,
                     _: Annotated[dict, Depends(require_permission("shipments.view"))]
                     ) -> list[dict[str, Any]]:
    """Zones de livraison du tenant."""
    t = _require_tenant(tenant)
    zones = await crud_order.list_zones(db, t.id)
    return [_zone_out(z) for z in zones]


@router.post("/delivery-zones", status_code=201)
async def create_zone(payload: DeliveryZoneCreate, db: DbDep, user: CurrentUser,
                      tenant: TenantDep,
                      _: Annotated[dict, Depends(require_permission("zones.manage"))]
                      ) -> dict[str, Any]:
    """Crée une zone (frais base_fee_usd snapshotés aux commandes)."""
    t = _require_tenant(tenant)
    from app.models.order import DeliveryZone

    zone = await crud_order.create_zone(db, DeliveryZone(
        tenant_id=t.id, name=payload.name, regions=payload.regions,
        base_fee_usd=payload.base_fee_usd,
        estimated_days_min=payload.estimated_days_min,
        estimated_days_max=payload.estimated_days_max,
    ))
    await db.commit()
    await db.refresh(zone)
    from app.core.events import events
    await events.emit("delivery_zone.created", {"id": zone.id, "tenant_id": t.id})
    return _zone_out(zone)


@router.patch("/delivery-zones/{zone_id}")
async def update_zone(zone_id: str, payload: DeliveryZoneUpdate, db: DbDep,
                      user: CurrentUser, tenant: TenantDep,
                      _: Annotated[dict, Depends(require_permission("zones.manage"))]
                      ) -> dict[str, Any]:
    """Modifie une zone (les commandes existantes gardent leur snapshot)."""
    t = _require_tenant(tenant)
    zone = await crud_order.get_zone(db, t.id, zone_id)
    if zone is None:
        raise NotFoundError("Zone introuvable")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(zone, k, v)
    await db.commit()
    await db.refresh(zone)
    return _zone_out(zone)


@router.delete("/delivery-zones/{zone_id}")
async def deactivate_zone(zone_id: str, db: DbDep, user: CurrentUser, tenant: TenantDep,
                          _: Annotated[dict, Depends(require_permission("zones.manage"))]
                          ) -> dict[str, Any]:
    """Désactive une zone (soft delete — les commandes la référencent encore)."""
    t = _require_tenant(tenant)
    zone = await crud_order.get_zone(db, t.id, zone_id)
    if zone is None:
        raise NotFoundError("Zone introuvable")
    zone.is_active = False
    await db.commit()
    return {"ok": True, "id": zone.id}


def _zone_out(z) -> dict[str, Any]:
    return {
        "id": z.id, "tenant_id": z.tenant_id, "name": z.name,
        "regions": z.regions or [], "base_fee_usd": str(z.base_fee_usd),
        "base_fee_display": f"${z.base_fee_usd}",
        "estimated_days_min": z.estimated_days_min,
        "estimated_days_max": z.estimated_days_max,
        "is_active": z.is_active,
        "created_at": z.created_at.isoformat() if z.created_at else None,
    }
