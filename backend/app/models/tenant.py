"""Modèle Tenant — boutique vendeur (multi-tenant).

Le statut et le plan sont des String (valeurs extensibles en base,
jamais d'enum Python figé).
"""

from decimal import Decimal

from sqlalchemy import Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDType, new_uuid


class Tenant(Base, TimestampMixin):
    """Boutique multi-tenant."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    banner_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # pending | active | suspended | rejected
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # free | pro | business
    plan_name: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.05")
    )
    currency_input: Mapped[str] = mapped_column(String(8), nullable=False, default="CDF")
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="CD")
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Africa/Kinshasa"
    )
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="fr")
    kimia_tenant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    billing_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Renseignées par les actions superadmin (reject/suspend)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    users: Mapped[list["User"]] = relationship(  # noqa: F821
        "User", back_populates="tenant", foreign_keys="User.tenant_id", lazy="selectin"
    )
