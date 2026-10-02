"""Modèle Category — catégories produits (config-driven, hiérarchiques).

RÈGLE ABSOLUE : les catégories ne sont JAMAIS un enum Python. Une
catégorie = une ligne en base. tenant_id NULL → catégorie GLOBALE créée
par le superadmin, visible par tous les tenants ; sinon catégorie privée
du tenant. UNIQUE(tenant_id, slug) → même slug possible dans deux tenants.
"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDType, new_uuid


class Category(Base, TimestampMixin):
    """Catégorie de produits (globale ou propre à un tenant)."""

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_categories_tenant_slug"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    tenant_id: Mapped[str | None] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        UUIDType, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    products: Mapped[list["Product"]] = relationship(  # noqa: F821
        "Product", back_populates="category"
    )
