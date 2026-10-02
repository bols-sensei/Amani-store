"""Modèle User — tous les rôles (superadmin, vendor, staff, courier, customer).

RÈGLE D'OR multi-tenant : `tenant_id` provient TOUJOURS du JWT/user,
jamais du body de requête.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDType, new_uuid


class User(Base, TimestampMixin):
    """Utilisateur de la plateforme."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # superadmin | vendor | staff | courier | customer
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    tenant_id: Mapped[str | None] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="fr")
    currency_display: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tenant: Mapped["Tenant | None"] = relationship(  # noqa: F821
        "Tenant", back_populates="users", foreign_keys=[tenant_id]
    )
    permissions: Mapped[list["UserPermission"]] = relationship(  # noqa: F821
        "UserPermission", back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(  # noqa: F821
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
