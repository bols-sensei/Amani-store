"""Modèle ExchangeRate — taux de change snapshotables (config-driven)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base, UUIDType, new_uuid, utcnow


class ExchangeRate(Base):
    """Taux de change entre deux devises, valable à partir de `effective_at`."""

    __tablename__ = "exchange_rates"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    from_currency: Mapped[str] = mapped_column(
        String(8), ForeignKey("currencies.code"), nullable=False
    )
    to_currency: Mapped[str] = mapped_column(
        String(8), ForeignKey("currencies.code"), nullable=False
    )
    rate: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    # "manual" | "api"
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")
    created_by: Mapped[str | None] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
