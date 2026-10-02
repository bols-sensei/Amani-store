"""Modèles Document (reçus/factures PDF) et CourierProfile.

- Document : reçu de livraison (par colis) et facture (par commande), avec
  numéro unique, URL publique temporaire et QR de vérification.
- CourierProfile : infos complémentaires d'un livreur (rattaché user+tenant).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDType, new_uuid, utcnow


class Document(Base):
    """Document PDF généré (receipt | invoice) avec URLs publiques."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_number", "number"),
        Index("ix_documents_owner", "owner_type", "owner_id"),
        Index("ix_documents_reference", "reference_type", "reference_id"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # receipt | invoice
    number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    reference_type: Mapped[str] = mapped_column(String(20), nullable=False)  # shipment | order
    reference_id: Mapped[str] = mapped_column(UUIDType, nullable=False)
    tenant_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_id: Mapped[str] = mapped_column(UUIDType, nullable=False)
    pdf_url: Mapped[str] = mapped_column(Text, nullable=False)
    public_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qr_code_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CourierProfile(Base, TimestampMixin):
    """Profil livreur (1 par user courier), rattaché au tenant de son vendeur."""

    __tablename__ = "courier_profiles"
    __table_args__ = (Index("ix_cp_tenant_available", "tenant_id", "is_available"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    vehicle_type: Mapped[str] = mapped_column(String(20), nullable=False, default="moto")
    vehicle_plate: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    phone_secondary: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
