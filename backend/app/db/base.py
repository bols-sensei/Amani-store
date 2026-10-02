"""Base déclarative SQLAlchemy 2.0 (async).

Note de design : les colonnes `id` sont des UUID (str hex en base) pour
éviter la génération séquentielle côté Python qui casse en async.
Les valeurs extensibles (roles, statuts, plans...) sont des String +
tables de référence / CHECK config-driven — jamais d'Enum Python figé.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Uuid


def utcnow() -> datetime:
    """Timestamp UTC aware (utilisé pour created_at/updated_at)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Classe de base pour tous les modèles."""

    pass


class TimestampMixin:
    """Mixing created_at / updated_at."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# Type alias : UUID natif sur PostgreSQL, GUID string sur SQLite (tests).
UUIDType = PG_UUID(as_uuid=False).with_variant(Uuid(as_uuid=False, native_uuid=False), "sqlite")


def new_uuid() -> str:
    """Génère un UUID4 en chaîne (compatible PG + SQLite)."""
    import uuid as _uuid

    return str(_uuid.uuid4())
