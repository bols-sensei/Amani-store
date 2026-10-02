"""Endpoints /api/v1/auth — inscription, login, refresh, logout, profil, reset."""

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import NotFoundError, ValidationError_
from app.db.session import get_db
from app.schemas.auth import (
    CustomerRegisterRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionInfo,
    TokenResponse,
    VendorRegisterRequest,
    VerifyPhoneRequest,
)
from app.schemas.user import UserRead, UserUpdate
from app.services import auth_service, tenant_service
from app.services.auth_service import REFRESH_COOKIE_NAME
from app.crud import session as crud_session
from app.crud.user import get_user_with_permissions

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/register/vendor", response_model=TokenResponse, status_code=201)
async def register_vendor(
    body: VendorRegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Inscription vendeur : crée le tenant (pending) + le user vendor."""
    tenant = await tenant_service.create_pending_tenant(
        db, name=body.shop_name, billing_email=str(body.billing_email or body.email)
    )
    user = await auth_service.register_user(
        db,
        role="vendor",
        email=body.email,
        phone=body.phone,
        password=body.password,
        tenant_id=tenant.id,
        first_name=body.first_name,
        last_name=body.last_name,
    )
    from app.models.user_consent import UserConsent
    from app.db.base import utcnow

    db.add(
        UserConsent(
            user_id=user.id, document_type="cgu", document_version="1.0",
            accepted=True, accepted_at=utcnow(), ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:500],
        )
    )
    from app.core.security import create_access_token, create_refresh_token, hash_token

    # Le tenant vient D'ÊTRE créé dans la même transaction : flush pour le
    # rendre visible, puis commit — ainsi les sessions indépendantes des
    # middlewares (TenantStatus) voient immédiatement le tenant "pending".
    await db.flush()
    await db.commit()
    # Le JWT porte le tenant_id COURANT, relu en base après commit.
    fresh_user = await get_user_with_permissions(db, user.id)
    access = create_access_token(
        subject=user.id,
        extra_claims={"role": user.role, "tenant_id": fresh_user.tenant_id},
    )
    refresh = create_refresh_token()
    await crud_session.create_session(
        db, user_id=user.id, refresh_token_hash=hash_token(refresh),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, refresh)
    return TokenResponse(
        access_token=access,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role,
        tenant_id=user.tenant_id,
    )


@router.post("/register/customer", response_model=TokenResponse, status_code=201)
async def register_customer(
    body: CustomerRegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Inscription client : user simple, ILLIMITÉ, jamais compté dans un plan."""
    user = await auth_service.register_user(
        db,
        role="customer",
        email=body.email,
        phone=body.phone,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
    )
    from app.models.user_consent import UserConsent
    from app.db.base import utcnow

    db.add(
        UserConsent(
            user_id=user.id, document_type="cgu", document_version="1.0",
            accepted=True, accepted_at=utcnow(), ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:500],
        )
    )
    from app.core.security import create_refresh_token, hash_token, create_access_token

    access = create_access_token(
        subject=user.id, extra_claims={"role": user.role, "tenant_id": user.tenant_id}
    )
    refresh = create_refresh_token()
    await crud_session.create_session(
        db, user_id=user.id, refresh_token_hash=hash_token(refresh),
        ip_address=_client_ip(request),
    )
    _set_refresh_cookie(response, refresh)
    return TokenResponse(
        access_token=access,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role,
        tenant_id=user.tenant_id,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Login par email OU téléphone. Rate limit 5/min/IP via middleware.

    `X-Test-No-Lockout` est un header réservé aux tests (APP_ENV != production)
    qui neutralise le verrouillage DB afin d'éprouver le rate limiting réseau.
    """
    no_lockout = (
        request.headers.get("X-Test-No-Lockout") == "1" and not settings.is_production
    )
    user, access, refresh = await auth_service.login(
        db, body.identifier, body.password, _client_ip(request),
        request.headers.get("user-agent"),
        check_lockout=not no_lockout,
    )
    _set_refresh_cookie(response, refresh)
    return TokenResponse(
        access_token=access,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role,
        tenant_id=user.tenant_id,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    kimia_refresh: str | None = Cookie(None),
) -> TokenResponse:
    """Rotation du refresh token (cookie httpOnly) → nouvel access token."""
    if not kimia_refresh:
        raise ValidationError_("Cookie de rafraîchissement absent")
    user, access, new_refresh = await auth_service.refresh(db, kimia_refresh)
    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(
        access_token=access,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role,
        tenant_id=user.tenant_id,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    user: CurrentUser,
    kimia_refresh: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Révoque la session courante + blackliste l'access token."""
    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else None
    await auth_service.logout(
        db, access_token=token, raw_refresh=kimia_refresh, user_id=user.id
    )
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return MessageResponse(message="Déconnecté")


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    """Profil de l'utilisateur authentifié."""
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead)
async def update_me(
    body: UserUpdate,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    """Préférences utilisateur (langue, devise d'affichage...) — niveau 3 config."""
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    await db.flush()
    return UserRead.model_validate(user)


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(
    user: CurrentUser, db: AsyncSession = Depends(get_db)
) -> list[SessionInfo]:
    """Liste les sessions actives du user (multi-appareils)."""
    sessions = await crud_session.list_active_sessions(db, user.id)
    return [SessionInfo.model_validate(s) for s in sessions]


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def revoke_session(
    session_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Révoque une session précise appartenant au user courant."""
    session = await crud_session.get_session_by_id(db, session_id)
    if session is None or session.user_id != user.id:
        raise NotFoundError("Session introuvable")
    await crud_session.revoke_session(db, session)
    return MessageResponse(message="Session révoquée")


@router.post("/verify-phone", response_model=MessageResponse)
async def verify_phone(
    body: VerifyPhoneRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Double confirmation du numéro via le lien reçu (stub SMS)."""
    user = await auth_service.verify_phone(db, body.token)
    return MessageResponse(message=f"Numéro vérifié pour le compte {user.id}")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    body: ResendVerificationRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Renvoie (stub) le lien de vérification ; loggé en dev."""
    link = await auth_service.resend_verification(db, body.identifier)
    return MessageResponse(
        message="Si le compte existe, un lien a été envoyé.",
        debug_link=link if not settings.is_production else None,
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Génère un lien de reset (stub). Réponse identique quel que soit le cas."""
    link = await auth_service.forgot_password(db, body.identifier)
    return MessageResponse(
        message="Si le compte existe, un lien de réinitialisation a été envoyé.",
        debug_link=link if not settings.is_production else None,
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Applique le nouveau mot de passe et révoque toutes les sessions."""
    await auth_service.reset_password(db, body.token, body.password)
    return MessageResponse(message="Mot de passe réinitialisé")
