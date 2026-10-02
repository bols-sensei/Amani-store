"""CRUD User — accès base de données (sans logique métier)."""

from typing import Optional, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_identifier(db: AsyncSession, identifier: str) -> Optional[User]:
    """Retrouve un user par email OU téléphone (normalisé simplement)."""
    stmt = select(User).where(
        or_(
            func.lower(User.email) == identifier.lower(),
            User.phone == identifier,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_with_permissions(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(
        select(User).options(selectinload(User.permissions)).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, **fields) -> User:
    user = User(**fields)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def list_users(
    db: AsyncSession, tenant_id: Optional[str] = None, role: Optional[str] = None,
    offset: int = 0, limit: int = 50,
) -> Sequence[User]:
    stmt = select(User)
    if tenant_id is not None:
        stmt = stmt.where(User.tenant_id == tenant_id)
    if role is not None:
        stmt = stmt.where(User.role == role)
    stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()
