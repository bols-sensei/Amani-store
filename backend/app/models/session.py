"""Modèle Session — sessions utilisateurs (refresh tokens rotatifs)."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDType, new_uuid


class Session(Base):
    """Session active : refresh token haché + infos appareil. Multi-session supportée."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    device_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {os, browser, type}
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="sessions")  # noqa: F821
