"""Modèles Cart / CartItem — panier client (un seul panier actif par client).

Les prix unitaires sont snapshotés en USD au moment de l'ajout ; le tenant_id
est dénormalisé sur chaque ligne pour faciliter le split multi-vendeurs.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDType, new_uuid


class Cart(Base, TimestampMixin):
    """Panier d'un client (unique par client)."""

    __tablename__ = "carts"
    __table_args__ = (
        UniqueConstraint("customer_id", name="uq_carts_customer"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    customer_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    currency_display: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    is_empty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    items: Mapped[list["CartItem"]] = relationship(
        back_populates="cart", cascade="all, delete-orphan", lazy="raise"
    )


class CartItem(Base):
    """Ligne de panier : produit + quantité + prix snapshoté USD."""

    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "product_id", name="uq_cart_items_cart_product"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    cart_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )

    cart: Mapped[Cart] = relationship(back_populates="items")
