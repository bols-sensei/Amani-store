"""Service Auth — logique métier d'authentification.

Décisions techniques :
- Refresh token OPAQUE (non-JWT) stocké haché SHA-256 en table `sessions`,
  cookie httpOnly, rotation à chaque /refresh.
- Access token JWT HS256 renvoyé en body (mémoire JS), blacklisté via
  hash du token complet en table `token_blacklist` au logout/changement mdp.
- Verrouillage anti-brute-force lu depuis business_rules (config-driven).
"""

from datetime import timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import events
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    RateLimitExceededError,
    ValidationError_,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    needs_rehash,
    verify_password,
)
from app.crud import session as crud_session
from app.crud.business_rule import get_rule
from app.crud.user import create_user, get_user_by_identifier, get_user_with_permissions
from app.db.base import utcnow
from app.models.user import User
from app.services.sms_service import send_verification_link

REFRESH_COOKIE_NAME = "kimia_refresh"


async def _gen_verification_link(db: AsyncSession, user: User, type_: str) -> str:
    """Génère un token de vérification et le lien associé (SMS stub → log)."""
    raw = create_refresh_token()  # token opaque fort
    await crud_session.create_verification_token(
        db, user_id=user.id, token_hash=hash_token(raw), type_=type_
    )
    link = f"{settings.APP_URL}/api/v1/auth/verify-phone?token={raw}"
    if user.phone:
        await send_verification_link(user.phone, link)
    return link


async def register_user(
    db: AsyncSession,
    *,
    role: str,
    password: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    tenant_id: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> User:
    """Crée un user avec mot de passe haché ; refuse les doublons email/phone."""
    if email:
        existing = await get_user_by_identifier(db, email)
        if existing:
            raise ConflictError("Cet email est déjà utilisé")
    if phone:
        from sqlalchemy import select as _select

        by_phone = (
            await db.execute(_select(User).where(User.phone == phone))
        ).scalar_one_or_none()
        if by_phone:
            raise ConflictError("Ce numéro de téléphone est déjà utilisé")
    user = await create_user(
        db,
        role=role,
        email=email.lower() if email else None,
        phone=phone,
        hashed_password=hash_password(password),
        tenant_id=tenant_id,
        first_name=first_name,
        last_name=last_name,
    )
    await events.emit("user.registered", user)
    return user


async def login(
    db: AsyncSession, identifier: str, password: str,
    ip_address: Optional[str], user_agent: Optional[str],
    check_lockout: bool = True,
) -> tuple[User, str, str]:
    """Vérifie les identifiants, applique le lockout config-driven.

    Retourne (user, access_token, refresh_token).
    """
    attempts = 0
    max_attempts: int | float = float("inf")
    if check_lockout:
        raw_max = await get_rule(db, "login.max_attempts", 5)
        try:
            max_attempts = int(raw_max)
        except (TypeError, ValueError):
            max_attempts = float("inf")
        lockout_minutes = int(await get_rule(db, "login.lockout_minutes", 15))
        attempts = await crud_session.count_failed_attempts_since(
            db, identifier, utcnow() - timedelta(minutes=lockout_minutes)
        )
    if max_attempts != float("inf") and attempts >= max_attempts:
        await crud_session.record_login_attempt(
            db, identifier, ip_address, False, user_agent
        )
        raise RateLimitExceededError(
            "Trop de tentatives échouées. Réessayez dans quelques minutes."
        )

    user = await get_user_by_identifier(db, identifier)
    ok = bool(user and user.is_active and verify_password(password, user.hashed_password))
    await crud_session.record_login_attempt(db, identifier, ip_address, ok, user_agent)
    if not ok:
        raise AuthenticationError("Identifiants incorrects")

    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(password)

    user.last_login_at = utcnow()
    access = create_access_token(
        subject=user.id, extra_claims={"role": user.role, "tenant_id": user.tenant_id}
    )
    refresh = create_refresh_token()
    await crud_session.create_session(
        db,
        user_id=user.id,
        refresh_token_hash=hash_token(refresh),
        device_info={"user_agent": (user_agent or "")[:200] or None},
        ip_address=ip_address,
    )
    await events.emit("user.login", user)
    return user, access, refresh


async def refresh(db: AsyncSession, raw_refresh: str) -> tuple[User, str, str]:
    """Valide + ROTATE le refresh token (une session = un token à la fois)."""
    token_hash = hash_token(raw_refresh)
    session = await crud_session.get_session_by_token_hash(db, token_hash)
    if session is None or session.is_revoked:
        raise AuthenticationError("Refresh token invalide ou révoqué")
    user = await get_user_with_permissions(db, session.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Compte inactive")
    new_refresh = create_refresh_token()
    await crud_session.rotate_session_token(db, session, hash_token(new_refresh))
    access = create_access_token(
        subject=user.id, extra_claims={"role": user.role, "tenant_id": user.tenant_id}
    )
    return user, access, new_refresh


async def logout(
    db: AsyncSession, *, access_token: Optional[str], raw_refresh: Optional[str],
    user_id: Optional[str],
) -> None:
    """Révoque la session (refresh) et blackliste l'access token courant."""
    if raw_refresh:
        session = await crud_session.get_session_by_token_hash(db, hash_token(raw_refresh))
        if session and session.user_id == user_id:
            await crud_session.revoke_session(db, session)
    if access_token:
        await crud_session.blacklist_token(
            db, hash_token(access_token), reason="logout", user_id=user_id
        )
    await events.emit("user.logout", user_id)


async def forgot_password(db: AsyncSession, identifier: str) -> Optional[str]:
    """Génère un lien de reset (stub SMS/email loggé). Ne révèle pas l'existence."""
    user = await get_user_by_identifier(db, identifier)
    if user is None:
        return None
    link = await _gen_verification_link(db, user, "password_reset")
    return link


async def reset_password(db: AsyncSession, raw_token: str, new_password: str) -> None:
    """Consomme le token de reset, change le mot de passe, révoque TOUTES les sessions."""
    vt = await crud_session.get_valid_verification_token(
        db, hash_token(raw_token), "password_reset"
    )
    if vt is None:
        raise ValidationError_("Lien de réinitialisation invalide ou expiré")
    user = await get_user_with_permissions(db, vt.user_id)
    if user is None:
        raise NotFoundError("Utilisateur introuvable")
    await crud_session.mark_verification_token_used(db, vt)
    user.hashed_password = hash_password(new_password)
    await crud_session.revoke_all_sessions(db, user.id)
    await events.emit("user.password_changed", user.id)


async def verify_phone(db: AsyncSession, raw_token: str) -> User:
    """Confirme le numéro via le lien (double confirmation)."""
    vt = await crud_session.get_valid_verification_token(
        db, hash_token(raw_token), "phone_verification"
    )
    if vt is None:
        raise ValidationError_("Lien de vérification invalide ou expiré")
    user = await get_user_with_permissions(db, vt.user_id)
    if user is None:
        raise NotFoundError("Utilisateur introuvable")
    await crud_session.mark_verification_token_used(db, vt)
    user.is_verified = True
    await events.emit("user.phone_verified", user)
    return user


async def resend_verification(db: AsyncSession, identifier: str) -> Optional[str]:
    user = await get_user_by_identifier(db, identifier)
    if user is None or user.is_verified:
        return None
    return await _gen_verification_link(db, user, "phone_verification")
