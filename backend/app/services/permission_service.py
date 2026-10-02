"""Service Permissions — résolution des permissions effectives d'un user.

Règles :
- superadmin / vendor(owner) : toutes les permissions du tenant (wildcard "*").
- staff : permissions individuelles (user_permissions) accordées par le vendor.
- Wildcards supportées dans role_templates : "products.*".
"""

from typing import Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission
from app.models.user import User
from app.models.user_permission import UserPermission


async def all_permission_keys(db: AsyncSession) -> Set[str]:
    result = await db.execute(select(Permission.key))
    return set(result.scalars().all())


async def get_user_permissions(db: AsyncSession, user: User) -> Set[str]:
    """Retourne l'ensemble des permission keys effectives d'un user."""
    if user.role in ("superadmin", "vendor"):
        # Le propriétaire du tenant dispose de tout ce qui existe en base.
        return await all_permission_keys(db)
    if user.role == "staff":
        result = await db.execute(
            select(UserPermission.permission_key).where(UserPermission.user_id == user.id)
        )
        return set(result.scalars().all())
    return set()


def has_permission(user_perms: Set[str], required: str) -> bool:
    """Vérifie une permission avec support de wildcard exacte (pas de '*.*')."""
    if "*" in user_perms or required in user_perms:
        return True
    # wildcard par catégorie : "products.*" couvre "products.create"
    category = required.split(".")[0]
    return f"{category}.*" in user_perms


async def expand_template_permissions(
    db: AsyncSession, template_perms: list[str]
) -> list[str]:
    """Développe les wildcards d'un role_template en permission keys concrètes."""
    available = await all_permission_keys(db)
    out: set[str] = set()
    for tp in template_perms:
        if tp == "*":
            out |= available
        elif tp.endswith(".*"):
            cat = tp[:-2]
            out |= {k for k in available if k.split(".")[0] == cat}
        elif tp in available:
            out.add(tp)
    return sorted(out)


async def grant_permissions(
    db: AsyncSession, user: User, keys: list[str]
) -> int:
    """Remplace les permissions d'un staff par `keys` ; retourne le nombre accordé."""
    from datetime import timezone  # local import to avoid cycles

    from app.db.base import utcnow

    existing = await db.execute(
        select(UserPermission).where(UserPermission.user_id == user.id)
    )
    for row in existing.scalars():
        await db.delete(row)
    count = 0
    valid = await all_permission_keys(db)
    for key in keys:
        if key in valid:
            db.add(UserPermission(user_id=user.id, permission_key=key, granted_at=utcnow()))
            count += 1
    await db.flush()
    return count
