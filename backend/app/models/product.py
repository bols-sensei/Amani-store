"""Modèles Product / ProductImage / ProductVariant — catalogue multi-tenant.

Prix TOUJOURS stockés en USD (devise de référence) ; `price_input` garde la
valeur telle que saisie par le vendeur dans sa devise d'entrée (USD ou CDF).
Le stock disponible = stock - reserved_stock (réservé par les commandes en cours).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDType, new_uuid, utcnow


class Product(Base, TimestampMixin):
    """Produit d'un tenant (jamais rattachable sans tenant : NOT NULL)."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_products_tenant_slug"),
        Index("ix_products_tenant_active_published", "tenant_id", "is_active", "is_published"),
        Index("ix_products_tenant_category", "tenant_id", "category_id"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[str | None] = mapped_column(
        UUIDType, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # --- Prix : stockage toujours en USD ---------------------------------
    price_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_input: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency_input: Mapped[str] = mapped_column(String(8), nullable=False, default="CDF")

    # --- Stock ------------------------------------------------------------
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    sku: Mapped[str | None] = mapped_column(String(80), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Stats --------------------------------------------------------------
    views_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sales_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, default=Decimal("0"))
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_by: Mapped[str | None] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    tenant: Mapped["Tenant"] = relationship("Tenant")  # noqa: F821
    category: Mapped["Category | None"] = relationship(  # noqa: F821
        "Category", back_populates="products"
    )
    images: Mapped[list["ProductImage"]] = relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.display_order",
    )
    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan"
    )

    @property
    def available_stock(self) -> int:
        """Stock commandable = stock physique - stock réservé."""
        return int(self.stock or 0) - int(self.reserved_stock or 0)


class ProductImage(Base):
    """Image d'un produit (disque local, thumbnails générés par Pillow)."""

    __tablename__ = "product_images"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    thumb_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    medium_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    alt_text: Mapped[str | None] = mapped_column(String(250), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    product: Mapped["Product"] = relationship("Product", back_populates="images")


class ProductVariant(Base):
    """Variante optionnelle (taille, couleur...) — table prévue dès le MVP."""

    __tablename__ = "product_variants"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[str] = mapped_column(String(80), nullable=False)
    price_delta_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    product: Mapped["Product"] = relationship("Product", back_populates="variants")
