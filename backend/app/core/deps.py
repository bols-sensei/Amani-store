"""Dépendances FastAPI : auth, rôles, permissions, tenant.

RÈGLE D'OR : le tenant_id est TOUJOURS déduit du token JWT (via user en DB),
jamais depuis le body de la requête.
"""

from typing import Annotated, Optional, Set

from fastapi import Depends, Request
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    PermissionDeniedError,
    TenantInactiveError,
)
from app.core.security import decode_token, hash_token
from app.crud import session as crud_session
from app.crud.user import get_user_with_permissions
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.services.permission_service import get_user_permissions, has_permission

REFRESH_COOKIE_NAME = "kimia_refresh"


async def get_current_user(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """Extrait et valide le Bearer JWT, charge le user, vérifie la blacklist."""
    user = getattr(request.state, "current_user", None)
    if user is not None:
        return user

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AuthenticationError("Token manquant")
    token = header.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
    except JWTError:
        raise AuthenticationError("Token invalide ou expiré")
    if payload.get("type") != "access":
        raise AuthenticationError("Type de token incorrect")
    if await crud_session.is_token_blacklisted(db, hash_token(token)):
        raise AuthenticationError("Token révoqué")

    user = await get_user_with_permissions(db, payload["sub"])
    if user is None or not user.is_active:
        raise AuthenticationError("Compte introuvable ou désactivé")
    request.state.current_user = user
    request.state.current_token = token
    request.state.db = db
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_authenticated(user: CurrentUser) -> User:
    """Alias explicite : tout user authentifié."""
    return user


def _role_checker(*roles: str):
    async def _check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise PermissionDeniedError("Rôle insuffisant pour cette action")
        return user

    return _check


require_superadmin = _role_checker("superadmin")
require_vendor = _role_checker("vendor", "staff")  # vendor OU staff
require_courier = _role_checker("courier")
require_customer = _role_checker("customer")


async def get_current_tenant(
    request: Request, user: CurrentUser
) -> Optional[Tenant]:
    """Retourne le tenant du user courant (déduit du JWT). Aucun tenant → None."""
    if user.tenant_id is None:
        return None
    tenant = getattr(request.state, "current_tenant", None)
    if tenant is not None and tenant.id == user.tenant_id:
        return tenant
    from app.crud.tenant import get_tenant_by_id

    db = request.state.db
    tenant = await get_tenant_by_id(db, user.tenant_id)
    if tenant is None:
        raise AuthenticationError("Tenant introuvable")
    request.state.current_tenant = tenant
    return tenant


async def require_active_tenant(request: Request, user: CurrentUser) -> Tenant:
    """Pour /vendor/* et /shop/* : exige un tenant actif (règle d'isolation)."""
    tenant = await get_current_tenant(request, user)
    if tenant is None:
        raise PermissionDeniedError("Aucun tenant rattaché à ce compte")
    if tenant.status != "active":
        raise TenantInactiveError(
            f"Boutique inactive (statut : {tenant.status}). "
            "Contactez l'administrateur."
        )
    return tenant


def require_permission(permission_key: str):
    """Dépendance : exige une permission granulaire (staff filtré par tenant)."""

    async def _check(request: Request, user: CurrentUser) -> User:
        perms: Set[str] = await get_user_permissions(request.state.db, user)
        if not has_permission(perms, permission_key):
            raise PermissionDeniedError(
                f"Permission manquante : {permission_key}"
            )
        return user

    return _check
