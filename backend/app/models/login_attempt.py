"""Modèle LoginAttempt — traçabilité des tentatives de connexion (anti-brute-force)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDType, new_uuid


class LoginAttempt(Base):
    """Une tentative de login (réussie ou non), par identifiant + IP."""

    __tablename__ = "login_attempts"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
