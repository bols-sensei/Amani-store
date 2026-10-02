"""Endpoints /api/v1/vendor — gestion du personnel (staff) et permissions.

RÈGLE D'OR : le tenant_id est TOUJOURS déduit du JWT (get_current_tenant),
jamais depuis le body de la requête. Le préfixe /api/v1/vendor est aussi
protégé par TenantStatusMiddleware (403 si tenant non "active").
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    CurrentUser,
    get_current_tenant,
    require_permission,
    require_vendor,
)
from app.core.exceptions import NotFoundError, ValidationError_
from app.db.base import utcnow
from app.db.session import get_db
from app.crud import user as crud_user
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.auth import StaffCreateRequest
from app.schemas.user import UserRead
from app.services import auth_service, permission_service

router = APIRouter(
    prefix="/vendor",
    tags=["vendor"],
    dependencies=[Depends(require_vendor)],
)


@router.post("/staff", response_model=UserRead, status_code=201)
async def create_staff(
    request: Request,
    body: StaffCreateRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("staff.manage")),
) -> UserRead:
    """Crée un compte staff rattaché au tenant du vendor courant."""
    tenant = await get_current_tenant(request, user)
    if tenant is None:
        raise ValidationError_("Aucun tenant rattaché à ce compte")

    staff = await auth_service.register_user(
        db,
        role="staff",
        email=body.email,
        phone=body.phone,
        password=body.password,
        tenant_id=tenant.id,  # ← JAMAIS depuis le body
        first_name=body.first_name,
        last_name=body.last_name,
    )
    if body.permissions:
        await permission_service.grant_permissions(db, staff, body.permissions)
    db.add(
        AuditLog(
            actor_id=user.id,
            actor_role=user.role,
            actor_ip=request.client.host if request.client else None,
            action="staff.create",
            target_type="user",
            target_id=staff.id,
            after={"permissions": body.permissions},
            created_at=utcnow(),
        )
    )
    await db.flush()
    return UserRead.model_validate(staff)


@router.get("/staff", response_model=list[UserRead])
async def list_staff(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("staff.manage")),
) -> list[UserRead]:
    """Liste le staff DU TENANT COURANT uniquement (filtre JWT, jamais body).

    Le tenant est rechargé en base depuis get_current_tenant : si le claim
    du token divergeait de la base, on refuse toute liste plutôt que de
    fuiter des données inter-tenants.
    """
    tenant = await get_current_tenant(request, user)
    if tenant is None or tenant.id != user.tenant_id:
        raise PermissionDeniedError("Aucun tenant valide rattaché à ce compte")
    staff = await crud_user.list_users(db, tenant_id=tenant.id, role="staff")
    return [UserRead.model_validate(s) for s in staff]


@router.get("/staff/{staff_id}", response_model=UserRead)
async def get_staff(
    staff_id: str,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("staff.manage")),
) -> UserRead:
    """Détail d'un staff du même tenant — 404 sinon (pas de fuite d'existence)."""
    staff = await crud_user.get_user_by_id(db, staff_id)
    if staff is None or staff.role != "staff" or staff.tenant_id != user.tenant_id:
        raise NotFoundError("Staff introuvable")
    return UserRead.model_validate(staff)


@router.put("/staff/{staff_id}/permissions")
async def set_staff_permissions(
    request: Request,
    staff_id: str,
    keys: list[str],
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("staff.manage")),
) -> dict:
    """Remplace les permissions d'un staff DU MÊME tenant (isolation)."""
    staff = await crud_user.get_user_with_permissions(db, staff_id)
    if staff is None or staff.role != "staff":
        raise NotFoundError("Staff introuvable")
    if staff.tenant_id != user.tenant_id:
        # Isolation multi-tenant : un vendor ne touche jamais le staff d'un autre.
        # 404 (et non 403) pour ne pas révéler l'existence de la ressource.
        raise NotFoundError("Staff introuvable")
    count = await permission_service.grant_permissions(db, staff, keys)
    db.add(
        AuditLog(
            actor_id=user.id,
            actor_role=user.role,
            actor_ip=request.client.host if request.client else None,
            action="staff.permissions_change",
            target_type="user",
            target_id=staff.id,
            after={"permissions": keys},
            created_at=utcnow(),
        )
    )
    await db.flush()
    return {"granted": count}


@router.get("/me/permissions", response_model=list[str])
async def my_permissions(
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """Liste des permissions effectives du user courant (vendor ou staff)."""
    perms = await permission_service.get_user_permissions(db, user)
    return sorted(perms)
