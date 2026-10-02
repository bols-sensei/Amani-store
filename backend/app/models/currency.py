"""Modèle Currency — table de référence des devises (config-driven).

Ajouter une devise = INSERT, zéro code.
"""

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDType, new_uuid


class Currency(Base, TimestampMixin):
    """Devise supportée par la plateforme."""

    __tablename__ = "currencies"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    # "before" | "after" — jamais d'enum Python figé : contrainte en DB / seed.
    symbol_position: Mapped[str] = mapped_column(String(10), nullable=False, default="before")
    decimal_places: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    thousands_sep: Mapped[str] = mapped_column(String(4), nullable=False, default=",")
    decimal_sep: Mapped[str] = mapped_column(String(4), nullable=False, default=".")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
