"""CRUD Session / TokenBlacklist / VerificationToken / LoginAttempt."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.login_attempt import LoginAttempt
from app.models.session import Session
from app.models.token_blacklist import TokenBlacklist
from app.models.verification_token import VerificationToken


# ---------- Sessions ----------

async def create_session(
    db: AsyncSession, user_id: str, refresh_token_hash: str,
    device_info: Optional[dict] = None, ip_address: Optional[str] = None,
) -> Session:
    s = Session(
        user_id=user_id,
        refresh_token_hash=refresh_token_hash,
        device_info=device_info,
        ip_address=ip_address,
        last_active_at=utcnow(),
        created_at=utcnow(),
    )
    db.add(s)
    await db.flush()
    return s


async def get_session_by_token_hash(db: AsyncSession, token_hash: str) -> Optional[Session]:
    result = await db.execute(
        select(Session).where(Session.refresh_token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def get_session_by_id(db: AsyncSession, session_id: str) -> Optional[Session]:
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def list_active_sessions(db: AsyncSession, user_id: str) -> Sequence[Session]:
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id, Session.is_revoked.is_(False))
        .order_by(Session.last_active_at.desc())
    )
    return result.scalars().all()


async def rotate_session_token(
    db: AsyncSession, session: Session, new_refresh_token_hash: str
) -> Session:
    """Rotation du refresh token : la même session reçoit un nouveau hash."""
    session.refresh_token_hash = new_refresh_token_hash
    session.last_active_at = utcnow()
    await db.flush()
    return session


async def revoke_session(db: AsyncSession, session: Session) -> None:
    session.is_revoked = True
    await db.flush()


async def revoke_all_sessions(db: AsyncSession, user_id: str) -> int:
    sessions = await list_active_sessions(db, user_id)
    for s in sessions:
        s.is_revoked = True
    await db.flush()
    return len(sessions)


# ---------- Token blacklist ----------

async def blacklist_token(
    db: AsyncSession, token_hash: str, reason: str,
    user_id: Optional[str] = None, expires_at: Optional[datetime] = None,
) -> TokenBlacklist:
    entry = TokenBlacklist(
        user_id=user_id,
        token_hash=token_hash,
        reason=reason,
        expires_at=expires_at or utcnow() + timedelta(days=31),
        created_at=utcnow(),
    )
    db.add(entry)
    await db.flush()
    return entry


async def is_token_blacklisted(db: AsyncSession, token_hash: str) -> bool:
    result = await db.execute(
        select(TokenBlacklist.id).where(
            TokenBlacklist.token_hash == token_hash,
            TokenBlacklist.expires_at > utcnow(),
        )
    )
    return result.scalar_one_or_none() is not None


# ---------- Verification tokens ----------

async def create_verification_token(
    db: AsyncSession, user_id: str, token_hash: str, type_: str,
    ttl_minutes: int = 30,
) -> VerificationToken:
    vt = VerificationToken(
        user_id=user_id,
        token_hash=token_hash,
        type=type_,
        expires_at=utcnow() + timedelta(minutes=ttl_minutes),
        created_at=utcnow(),
    )
    db.add(vt)
    await db.flush()
    return vt


async def get_valid_verification_token(
    db: AsyncSession, token_hash: str, type_: str
) -> Optional[VerificationToken]:
    result = await db.execute(
        select(VerificationToken).where(
            VerificationToken.token_hash == token_hash,
            VerificationToken.type == type_,
            VerificationToken.used_at.is_(None),
            VerificationToken.expires_at > utcnow(),
        )
    )
    return result.scalar_one_or_none()


async def mark_verification_token_used(db: AsyncSession, vt: VerificationToken) -> None:
    vt.used_at = utcnow()
    await db.flush()


# ---------- Login attempts ----------

async def record_login_attempt(
    db: AsyncSession, identifier: str, ip_address: Optional[str],
    success: bool, user_agent: Optional[str],
) -> LoginAttempt:
    la = LoginAttempt(
        identifier=identifier.lower(),
        ip_address=ip_address,
        success=success,
        user_agent=user_agent,
        created_at=utcnow(),
    )
    db.add(la)
    await db.flush()
    return la


async def count_failed_attempts_since(
    db: AsyncSession, identifier: str, since: datetime
) -> int:
    result = await db.execute(
        select(LoginAttempt.id).where(
            LoginAttempt.identifier == identifier.lower(),
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at >= since,
        )
    )
    return len(result.all())
