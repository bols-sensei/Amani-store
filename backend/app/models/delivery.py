"""Modèles du cycle de livraison : tokens QR, confirmations, litiges, reports.

- DeliveryToken : JWT court-lived + code manuel 6 chiffres, usage unique (nonce).
- DeliveryConfirmation : journal immuable des confirmations client.
- DeliveryDispute : signalement après livraison (fenêtre configurable).
- DeliveryReschedule : demande de report (client/vendeur/livreur/admin).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDType, new_uuid, utcnow


class DeliveryToken(Base):
    """Token de confirmation (QR JWT ou code manuel) rattaché à un colis."""

    __tablename__ = "delivery_tokens"
    __table_args__ = (Index("ix_dt_shipment_status", "shipment_id", "status"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    shipment_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    manual_code: Mapped[str] = mapped_column(String(6), nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class DeliveryConfirmation(Base):
    """Trace d'une confirmation de livraison (qui, comment, depuis où)."""

    __tablename__ = "delivery_confirmations"
    __table_args__ = (Index("ix_dc_shipment_id", "shipment_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    shipment_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class DeliveryDispute(Base, TimestampMixin):
    """Signalement client sur une livraison (dans la fenêtre configurable)."""

    __tablename__ = "delivery_disputes"
    __table_args__ = (
        Index("ix_dd_shipment_status", "shipment_id", "status"),
        Index("ix_dd_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    shipment_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_urls: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class DeliveryReschedule(Base):
    """Demande de report de livraison avec compteur max config-driven."""

    __tablename__ = "delivery_reschedules"
    __table_args__ = (Index("ix_dr_shipment_status", "shipment_id", "status"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    shipment_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_role: Mapped[str] = mapped_column(String(20), nullable=False)
    old_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    new_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    approved_by: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
