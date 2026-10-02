"""Endpoints superadmin — gestion des tenants (validation, suspension...)."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_superadmin  # noqa: F401 (utilisé via dependencies)
from app.core.exceptions import NotFoundError
from app.db.base import utcnow
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.schemas.tenant import (
    TenantActionRequest,
    TenantListPage,
    TenantRead,
    TenantUpdate,
)
from app.crud import tenant as crud_tenant
from app.services import tenant_service

router = APIRouter(
    prefix="/superadmin/tenants",
    tags=["superadmin"],
    dependencies=[Depends(require_superadmin)],
)


async def _audit(request: Request, db: AsyncSession, action: str,
                 tenant_id: str, before: dict, after: dict) -> None:
    """Écrit une entrée audit_logs pour une action superadmin."""
    db.add(
        AuditLog(
            actor_id=getattr(request.state, "user_id", None),
            actor_role="superadmin",
            actor_ip=request.client.host if request.client else None,
            action=action,
            target_type="tenant",
            target_id=tenant_id,
            before=before,
            after=after,
            created_at=utcnow(),
        )
    )
    await db.flush()


@router.get("/pending", response_model=TenantListPage)
async def pending_queue(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> TenantListPage:
    """File d'attente des boutiques à valider."""
    items, total = await crud_tenant.list_tenants(
        db, status="pending", offset=(page - 1) * page_size, limit=page_size
    )
    return TenantListPage(
        items=[TenantRead.model_validate(t) for t in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("", response_model=TenantListPage)
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None, max_length=20),
    plan: Optional[str] = Query(None, max_length=20),
    search: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> TenantListPage:
    """Liste paginée filtrable (status, plan, recherche nom/slug)."""
    items, total = await crud_tenant.list_tenants(
        db, status=status, plan_name=plan, search=search,
        offset=(page - 1) * page_size, limit=page_size,
    )
    return TenantListPage(
        items=[TenantRead.model_validate(t) for t in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{tenant_id}", response_model=TenantRead)
async def get_tenant(tenant_id: str, db: AsyncSession = Depends(get_db)) -> TenantRead:
    tenant = await crud_tenant.get_tenant_by_id(db, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant introuvable")
    return TenantRead.model_validate(tenant)


@router.post("/{tenant_id}/approve", response_model=TenantRead)
async def approve(
    request: Request, tenant_id: str, db: AsyncSession = Depends(get_db)
) -> TenantRead:
    tenant, before = await tenant_service.approve_tenant(db, tenant_id)
    await _audit(request, db, "tenant.approve", tenant_id,
                 before, {"status": tenant.status})
    return TenantRead.model_validate(tenant)


@router.post("/{tenant_id}/reject", response_model=TenantRead)
async def reject(
    request: Request, tenant_id: str, body: TenantActionRequest,
    db: AsyncSession = Depends(get_db),
) -> TenantRead:
    tenant, before = await tenant_service.reject_tenant(db, tenant_id, body.reason)
    await _audit(request, db, "tenant.reject", tenant_id,
                 before, {"status": tenant.status, "reason": body.reason})
    return TenantRead.model_validate(tenant)


@router.post("/{tenant_id}/suspend", response_model=TenantRead)
async def suspend(
    request: Request, tenant_id: str, body: TenantActionRequest,
    db: AsyncSession = Depends(get_db),
) -> TenantRead:
    tenant, before = await tenant_service.suspend_tenant(db, tenant_id, body.reason)
    await _audit(request, db, "tenant.suspend", tenant_id,
                 before, {"status": tenant.status, "reason": body.reason})
    return TenantRead.model_validate(tenant)


@router.post("/{tenant_id}/reactivate", response_model=TenantRead)
async def reactivate(
    request: Request, tenant_id: str, db: AsyncSession = Depends(get_db)
) -> TenantRead:
    tenant, before = await tenant_service.reactivate_tenant(db, tenant_id)
    await _audit(request, db, "tenant.reactivate", tenant_id,
                 before, {"status": tenant.status})
    return TenantRead.model_validate(tenant)


@router.patch("/{tenant_id}", response_model=TenantRead)
async def update_tenant(
    request: Request, tenant_id: str, body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
) -> TenantRead:
    """Modification superadmin : plan, commission_rate, email facturation..."""
    tenant = await crud_tenant.get_tenant_by_id(db, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant introuvable")
    before = {
        "plan_name": tenant.plan_name,
        "commission_rate": str(tenant.commission_rate),
        "name": tenant.name,
    }
    changes = {
        k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v)
        for k, v in body.model_dump(exclude_unset=True).items()
    }
    for k, v in changes.items():
        setattr(tenant, k, v)
    await db.flush()
    await _audit(request, db, "tenant.update", tenant_id, before, changes)
    return TenantRead.model_validate(tenant)
