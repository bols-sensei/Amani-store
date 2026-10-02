"""Modèles Order / OrderItem / OrderStatusHistory / DeliveryZone.

Split automatique multi-vendeurs : une commande client (panier) devient N
orders (une par tenant). Les statuts sont des String extensibles en base
(JAMAIS d'Enum Python figé) ; la machine à états vit dans
app/services/order_state_machine.py.

Snapshot à la création : prix unitaire USD, taux de change, taux de
commission. delivered_at = point de vérité financière (COD encaissé par le
vendeur directement auprès du client — PRINCIPE FONDATEUR #1).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDType, new_uuid, utcnow


class Order(Base, TimestampMixin):
    """Commande d'un tenant unique (résultat du split multi-vendeurs)."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_tenant_status", "tenant_id", "status"),
        Index("ix_orders_customer_created", "customer_id", "created_at"),
        Index("ix_orders_status_created", "status", "created_at"),
        Index("ix_orders_reference", "reference"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")

    subtotal_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    delivery_fee_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    currency_at_creation: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    exchange_rate_used: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)

    delivery_address: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    delivery_zone_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("delivery_zones.id", ondelete="SET NULL"), nullable=True
    )
    delivery_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    preparing_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    cancelled_by: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Champs Kimia (sync future — prompt 7)
    kimia_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    kimia_sync_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    kimia_sync_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kimia_last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    """Ligne de commande avec snapshots produits/prix/commission."""

    __tablename__ = "order_items"
    __table_args__ = (
        Index("ix_order_items_order_id", "order_id"),
        Index("ix_order_items_tenant_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    shipment_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("shipments.id", ondelete="SET NULL"), nullable=True
    )

    # Snapshots (produit peut changer/disparaître après la commande)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_short_description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    product_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    unit_price_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    subtotal_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    commission_amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    order: Mapped[Order] = relationship(back_populates="items")


class OrderStatusHistory(Base):
    """Journal immuable des transitions de statut."""

    __tablename__ = "order_status_history"
    __table_args__ = (Index("ix_osh_order_created", "order_id", "created_at"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    old_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_by_role: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    order: Mapped[Order] = relationship(back_populates="history")


class DeliveryZone(Base, TimestampMixin):
    """Zone de livraison d'un tenant (communes couvertes + frais de base)."""

    __tablename__ = "delivery_zones"
    __table_args__ = (Index("ix_dz_tenant_active", "tenant_id", "is_active"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    regions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    base_fee_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    estimated_days_min: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    estimated_days_max: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
