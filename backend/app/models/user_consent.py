"""Modèle UserConsent — traçabilité des consentements (CGU, confidentialité...)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDType, new_uuid


class UserConsent(Base):
    """Consentement d'un utilisateur à un document à une version donnée."""

    __tablename__ = "user_consents"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # cgu | privacy | marketing
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    document_version: Mapped[str] = mapped_column(String(30), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
