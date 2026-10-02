"""Modèle Shipment (colis) — cycle de livraison COD multi-colis.

1 commande = N colis. Chaque colis regroupe des order_items et suit sa propre
machine à états (app/services/shipment_service.py) :

    pending → in_transit → delivered | failed ; failed → returned | pending

Le point de vérité financière est la confirmation de livraison (QR ou code
manuel), jamais la création du colis.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDType, new_uuid


class Shipment(Base, TimestampMixin):
    """Colis rattaché à une commande, porté par un livreur du même tenant."""

    __tablename__ = "shipments"
    __table_args__ = (
        Index("ix_shipments_order_id", "order_id"),
        Index("ix_shipments_tenant_status", "tenant_id", "status"),
        Index("ix_shipments_courier_status", "courier_id", "status"),
        Index("ix_shipments_reference", "reference"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    order_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    courier_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    delivery_zone_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("delivery_zones.id", ondelete="SET NULL"), nullable=True
    )

    estimated_delivery_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    proof_photo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    confirmed_by_qr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmation_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    receipt_number: Mapped[Optional[str]] = mapped_column(String(40), unique=True, nullable=True)
    receipt_pdf_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    receipt_generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
