"""Modèle BusinessRule — règles métier paramétrables en base (config-driven)."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDType, new_uuid, utcnow


class BusinessRule(Base):
    """Règle métier clé/valeur typée, éditable selon son niveau."""

    __tablename__ = "business_rules"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    # "number" | "string" | "boolean" | "json"
    type: Mapped[str] = mapped_column(String(10), nullable=False, default="string")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "superadmin" | "vendor" | "system"
    editable_by: Mapped[str] = mapped_column(String(20), nullable=False, default="superadmin")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
