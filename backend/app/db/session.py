"""Engine et sessions async (SQLAlchemy 2.0 + asyncpg).

En tests, l'engine peut être remplacé (SQLite aiosqlite) via
`init_engine(url)` appelé par conftest.py.
"""

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def init_engine(url: Optional[str] = None, **kw) -> None:
    """(Ré)initialise l'engine global avec l'URL donnée."""
    global _engine, _session_factory
    if _engine is not None:
        _engine = None
    _engine = create_async_engine(url or settings.DATABASE_URL, **kw)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def get_engine():
    """Retourne l'engine courant (lazy-init depuis la config)."""
    global _engine, _session_factory
    if _engine is None:
        init_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retourne la fabrique de sessions courante."""
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dépendance FastAPI : fournit une session async par requête."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Ferme proprement le pool de connexions (shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
