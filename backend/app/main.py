"""Application FastAPI — point d'entrée.

Ordre des middlewares (Starlette : l'ajouté en dernier s'exécute EN PREMIER) :
  SecurityHeaders → Audit → RateLimit → TenantStatus → AuthContext → routes
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.middlewares import (
    AuditMiddleware,
    AuthContextMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    TenantStatusMiddleware,
)
from app.api.v1.auth import router as auth_router
from app.api.v1.superadmin.tenants import router as superadmin_tenants_router

logger = logging.getLogger("kimia")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Démarrage/arrêt : Sentry (si DSN), disposal du pool DB."""
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk

            sentry_sdk.init(dsn=settings.SENTRY_DSN, environment=settings.APP_ENV)
        except ImportError:
            logger.warning("sentry-sdk non installé, ignoré")
    from app.db.session import dispose_engine

    yield
    await dispose_engine()


app = FastAPI(
    title="Kimia — SaaS e-commerce RDC",
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# --- Middlewares (ordre inverse d'exécution) ---
app.add_middleware(AuthContextMiddleware)
app.add_middleware(TenantStatusMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# --- Handlers d'erreurs ---


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code, "details": exc.details},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """500 générique sans fuite de stack trace côté client."""
    logger.exception("Erreur non gérée sur %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne du serveur", "code": "internal_error"},
    )


# --- Routers API v1 ---
api_v1_prefix = "/api/v1"
app.include_router(auth_router, prefix=api_v1_prefix)
app.include_router(superadmin_tenants_router, prefix=api_v1_prefix)
from app.api.v1.vendor.staff import router as vendor_staff_router  # noqa: E402

app.include_router(vendor_staff_router, prefix=api_v1_prefix)


@app.get("/healthz", tags=["system"])
async def healthz() -> dict:
    """Vérification de vie (non limité, hors /api)."""
    return {"status": "ok", "env": settings.APP_ENV}
