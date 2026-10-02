"""Service Tenant — cycle de vie des boutiques (validation superadmin).

Transitions d'état gérées par table de référence (jamais de if/elif métier
complexe) : le graphe autoritaire est `ALLOWED_TRANSITIONS`, aligné sur la
spec. Les règles globales (tenant.validation_required) viennent de
business_rules.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import events
from app.core.exceptions import ConflictError, NotFoundError, ValidationError_
from app.crud import tenant as crud_tenant
from app.crud.business_rule import get_rule

# Graphe de transitions statut -> statuts cibles autorisés.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"active", "rejected"},
    "active": {"suspended"},
    "suspended": {"active"},
    "rejected": set(),
}


def _check_transition(current: str, target: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ConflictError(
            f"Transition interdite : {current} -> {target}"
        )


async def create_pending_tenant(db: AsyncSession, name: str, **fields):
    """Crée un tenant. Si rule tenant.validation_required=false → actif direct."""
    validation_required = await get_rule(db, "tenant.validation_required", True)
    status = "pending" if validation_required else "active"
    tenant = await crud_tenant.create_tenant(db, name=name, status=status, **fields)
    await events.emit("tenant.created", tenant)
    return tenant


async def approve_tenant(db: AsyncSession, tenant_id: str):
    tenant = await crud_tenant.get_tenant_by_id(db, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant introuvable")
    _check_transition(tenant.status, "active")
    before = {"status": tenant.status}
    tenant.status = "active"
    tenant.rejection_reason = None
    await events.emit("tenant.approved", tenant)
    return tenant, before


async def reject_tenant(db: AsyncSession, tenant_id: str, reason: Optional[str] = None):
    tenant = await crud_tenant.get_tenant_by_id(db, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant introuvable")
    _check_transition(tenant.status, "rejected")
    before = {"status": tenant.status}
    tenant.status = "rejected"
    tenant.rejection_reason = reason
    await events.emit("tenant.rejected", tenant)
    return tenant, before


async def suspend_tenant(db: AsyncSession, tenant_id: str, reason: Optional[str] = None):
    tenant = await crud_tenant.get_tenant_by_id(db, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant introuvable")
    _check_transition(tenant.status, "suspended")
    before = {"status": tenant.status}
    tenant.status = "suspended"
    tenant.suspension_reason = reason
    await events.emit("tenant.suspended", tenant)
    return tenant, before


async def reactivate_tenant(db: AsyncSession, tenant_id: str):
    tenant = await crud_tenant.get_tenant_by_id(db, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant introuvable")
    _check_transition(tenant.status, "active")
    before = {"status": tenant.status}
    tenant.status = "active"
    tenant.suspension_reason = None
    await events.emit("tenant.reactivated", tenant)
    return tenant, before
