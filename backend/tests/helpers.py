"""Helpers partagés par les tests (superadmin, login)."""

from sqlalchemy import select

from app.core.security import hash_password
from app.db import session as db_session
from app.models.user import User


async def create_superadmin(
    email: str = "root@kimia.cd", password: str = "Sup3rAdmin1"
) -> None:
    """Insère un user superadmin en base (pas d'inscription publique)."""
    factory = db_session.get_session_factory()
    async with factory() as s:
        existing = (
            await s.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is None:
            s.add(
                User(
                    email=email,
                    hashed_password=hash_password(password),
                    role="superadmin",
                    is_active=True,
                    is_verified=True,
                )
            )
            await s.commit()


async def login_as(client, identifier: str, password: str) -> dict:
    """Login et retourne le payload TokenResponse."""
    r = await client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()
