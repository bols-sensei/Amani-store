"""Fixtures de test — SQLite aiosqlite en mémoire + app FastAPI complète.

Les middlewares (rate limit, tenant status, audit) ouvrent leurs propres
sessions via get_session_factory() : l'engine global est donc initialisé
sur la MÊME base SQLite (StaticPool → une seule connexion partagée).
"""

import os

# Config avant tout import applicatif (aucun .env requis en test).
os.environ["APP_ENV"] = "development"
os.environ["JWT_SECRET"] = "test-secret-key-0123456789"
os.environ["SECRET_KEY"] = "test-secret-0123456789"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"  # absent → fallback mémoire

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.core.middlewares as mw  # noqa: E402
from app.core.middlewares import _memory_counter  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.models  # noqa: E402,F401 — enregistre la metadata
from app.db import session as db_session  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.services.seed_service import seed_config  # noqa: E402

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(autouse=True)
async def engine():
    """Créer les tables sur SQLite in-memory et brancher l'engine global."""
    eng = create_async_engine(
        TEST_DB_URL, poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Compteur mémoire du rate-limit vierge + limites en cache pour chaque test.
    _memory_counter._hits.clear()
    mw.RateLimitMiddleware._static_limits = dict(mw.DEFAULT_LIMITS)

    db_session._engine = eng
    db_session._session_factory = async_sessionmaker(eng, expire_on_commit=False)

    # Seed config-driven identique à la migration 0004.
    async with db_session._session_factory() as s:
        await seed_config(s)
        await s.commit()

    yield eng

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()
    db_session._engine = None
    db_session._session_factory = None


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """AsyncClient branché sur l'app FastAPI (ASGI, sans réseau)."""
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------- Helpers ----------

VENDOR_PAYLOAD = {
    "email": "alice@boutique.cd",
    "phone": "+243812345678",
    "password": "Passw0rd123",
    "first_name": "Alice",
    "last_name": "Mbombo",
    "shop_name": "Boutique Alice",
    "accept_cgu": True,
}

CUSTOMER_PAYLOAD = {
    "email": "bob@client.cd",
    "phone": "+243998765432",
    "password": "Cust0mer123",
    "first_name": "Bob",
    "last_name": "Kabasele",
    "accept_cgu": True,
}


async def register_vendor(client: AsyncClient, **overrides) -> dict:
    payload = {**VENDOR_PAYLOAD, **overrides}
    r = await client.post("/api/v1/auth/register/vendor", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def register_customer(client: AsyncClient, **overrides) -> dict:
    payload = {**CUSTOMER_PAYLOAD, **overrides}
    r = await client.post("/api/v1/auth/register/customer", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
