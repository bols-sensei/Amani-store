"""Modèle Permission — table de référence des permissions (config-driven)."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDType, new_uuid


class Permission(Base):
    """Permission granulaire, ex: products.create."""

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Plan minimum requis : free | pro | business
    plan_min: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
