"""Middlewares : sécurité headers, auth context, tenant status, rate limit, audit.

- SecurityHeadersMiddleware : X-Content-Type-Options, X-Frame-Options, CSP, HSTS.
- AuthContextMiddleware     : parse le JWT (non bloquant) et injecte
                              request.state.user_id / tenant_id pour les
                              autres middlewares + AuditMiddleware.
- TenantStatusMiddleware    : /vendor/* & /shop/* → 403 si tenant non actif.
- RateLimitMiddleware       : Redis si dispo, sinon compteur en mémoire
                              (dev/tests). Limites configurables via
                              business_rules (cliques rates.public/login/api).
- AuditMiddleware           : logue les actions sensibles dans audit_logs.
"""

import logging
import time
from collections import defaultdict, deque
from typing import Optional

from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.security import decode_token

logger = logging.getLogger("kimia.middleware")

# ---------- Sécurité headers ----------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Ajoute les headers de sécurité sur toutes les réponses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'"
        )
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


# ---------- Contexte d'authentification (non bloquant) ----------


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Décode le JWT présent (sans imposer l'auth) → request.state."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.user_id = None
        request.state.tenant_id = None
        request.state.token_jti = None
        header = request.headers.get("Authorization", "")
        # Le contexte DB par requête (utilisé par les dépendances).
        request.state.db = None
        if header.startswith("Bearer "):
            try:
                payload = decode_token(header.removeprefix("Bearer ").strip())
                request.state.user_id = payload.get("sub")
                request.state.tenant_id = payload.get("tenant_id")
                request.state.token_jti = payload.get("jti")
            except JWTError:
                pass  # La dépendance get_current_user produira l'erreur 401.
        return await call_next(request)


# ---------- Statut tenant ----------

PROTECTED_PREFIXES = ("/api/v1/vendor", "/api/v1/shop", "/vendor", "/shop")


class TenantStatusMiddleware(BaseHTTPMiddleware):
    """/vendor/* et /shop/* exigent un tenant au statut "active".

    Autonome : décode le JWT lui-même si request.state.tenant_id n'est pas
    encore posé (insensible à l'ordre d'empilement des middlewares).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in PROTECTED_PREFIXES):
            tenant_id = getattr(request.state, "tenant_id", None)
            if tenant_id is None:
                header = request.headers.get("Authorization", "")
                if header.startswith("Bearer "):
                    try:
                        payload = decode_token(header.removeprefix("Bearer ").strip())
                        tenant_id = payload.get("tenant_id")
                        request.state.tenant_id = tenant_id
                        if not getattr(request.state, "user_id", None):
                            request.state.user_id = payload.get("sub")
                    except JWTError:
                        pass  # get_current_user produira l'erreur 401 en aval.
            if tenant_id is None:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Aucun tenant rattaché à ce compte"},
                )
            from app.db.session import get_session_factory

            factory = get_session_factory()
            async with factory() as db:
                from app.crud.tenant import get_tenant_by_id

                tenant = await get_tenant_by_id(db, tenant_id)
            if tenant is None or tenant.status != "active":
                status = tenant.status if tenant else "inconnu"
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": f"Boutique inactive (statut : {status})",
                        "code": "tenant_not_active",
                    },
                )
        return await call_next(request)


# ---------- Rate limiting ----------

# Seuils par défaut ; surchargeables via business_rules (rate_limit.*).
DEFAULT_LIMITS = {"public": 60, "login": 5, "api": 300}
RULE_KEYS = {"public": "rate_limit.public_per_minute",
             "login": "rate_limit.login_per_minute",
             "api": "rate_limit.api_per_minute"}


class _MemoryCounter:
    """Compteur glissant en mémoire (fallback dev/tests sans Redis)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def incr_window(self, key: str, window_seconds: int) -> int:
        now = time.monotonic()
        dq = self._hits[key]
        while dq and dq[0] < now - window_seconds:
            dq.popleft()
        dq.append(now)
        return len(dq)


_memory_counter = _MemoryCounter()


async def _redis_counter():
    try:
        from redis.asyncio import Redis

        r = Redis.from_url(settings.REDIS_URL)
        await r.ping()
        return r
    except Exception:  # noqa: BLE001
        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit par IP (+ user si authentifié), configurable en base."""

    def __init__(self, app, redis=None) -> None:  # type: ignore[override]
        super().__init__(app)
        self._redis = redis
        self._limits_cache: Optional[dict] = None
        self._limits_cached_at = 0.0

    def _bucket(self, path: str) -> str:
        # /auth/register* → clique "public" (un test d'isolation peut inscrire
        # plusieurs vendeurs sans consommer le quota login de 5/min).
        if "/auth/login" in path:
            return "login"
        if "/auth/register" in path:
            return "public"
        if path.startswith("/api/"):
            return "api"
        return "public"

    async def _get_limits(self) -> dict:
        # Surcharge de test (déterminisme) : pas d'accès DB.
        static = type(self).__dict__.get("_static_limits")
        if static is not None:
            return dict(static)
        # Cache 30 s : la config DB prime sur les valeurs par défaut.
        if self._limits_cache and time.monotonic() - self._limits_cached_at < 30:
            return self._limits_cache
        limits = dict(DEFAULT_LIMITS)
        try:
            from app.db.session import get_session_factory
            from app.crud.business_rule import get_rule

            factory = get_session_factory()
            async with factory() as db:
                for bucket, rule_key in RULE_KEYS.items():
                    val = await get_rule(db, rule_key, None)
                    if val is not None:
                        limits[bucket] = int(val)
        except Exception:  # noqa: BLE001 — DB indisponible → defaults.
            pass
        self._limits_cache = limits
        self._limits_cached_at = time.monotonic()
        return limits

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not path.startswith("/api"):
            return await call_next(request)

        bucket = self._bucket(path)
        limits = await self._get_limits()
        limit = limits[bucket]
        client_ip = request.client.host if request.client else "unknown"
        user_id = getattr(request.state, "user_id", None) or "anon"
        key = f"rl:{bucket}:{client_ip}:{user_id}"

        if self._redis is not None:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 60)
        else:
            count = await _memory_counter.incr_window(key, 60)

        if count > limit:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Trop de requêtes. Réessayez dans une minute.",
                    "code": "rate_limit_exceeded",
                },
                headers={"Retry-After": "60"},
            )
        return await call_next(request)


# ---------- Audit ----------

SENSITIVE_PATTERNS = (
    ("/api/v1/auth/login", "auth.login"),
    ("/api/v1/auth/logout", "auth.logout"),
    ("/api/v1/auth/register", "auth.register"),
    ("/api/v1/auth/reset-password", "auth.password_reset"),
    ("/api/v1/superadmin", "superadmin.action"),
)


class AuditMiddleware(BaseHTTPMiddleware):
    """Journalise les actions sensibles (POST/PATCH/DELETE) dans audit_logs."""

    async def dispatch(self, request: Request, call_next) -> Response:
        action: Optional[str] = None
        target_type: Optional[str] = None
        for pattern, name in SENSITIVE_PATTERNS:
            if request.url.path.startswith(pattern):
                action = name
                break
        if action and request.method in ("POST", "PATCH", "PUT", "DELETE"):
            if "/superadmin/tenants" in request.url.path:
                target_type = "tenant"
            elif "/auth/" in request.url.path:
                target_type = "user"

        response = await call_next(request)

        if action and response.status_code < 400:
            try:
                await self._write_log(request, response, action, target_type)
            except Exception:  # noqa: BLE001 — l'audit ne casse jamais la requête.
                logger.exception("Échec d'écriture de l'audit log")
        return response

    async def _write_log(
        self, request: Request, response: Response, action: str,
        target_type: Optional[str],
    ) -> None:
        from app.db.base import utcnow
        from app.db.session import get_session_factory
        from app.models.audit_log import AuditLog

        factory = get_session_factory()
        async with factory() as db:
            db.add(
                AuditLog(
                    actor_id=getattr(request.state, "user_id", None),
                    actor_role=None,
                    actor_ip=request.client.host if request.client else None,
                    action=f"{action}:{request.method.lower()}",
                    target_type=target_type,
                    target_id=None,
                    metadata_={"path": request.url.path, "status": response.status_code},
                    created_at=utcnow(),
                )
            )
            await db.commit()
