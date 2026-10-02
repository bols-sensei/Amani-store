"""Modèle SearchQuery — historique des recherches (analytics + full-text).

Chaque recherche publique est enregistrée (user/tenant si connus) pour
alimenter l'autocomplétion et les statistiques. tenant_id NULL → recherche
globale marketplace.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDType, new_uuid, utcnow


class SearchQuery(Base):
    """Recherche effectuée sur le shop public."""

    __tablename__ = "search_queries"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    tenant_id: Mapped[str | None] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    query_text: Mapped[str] = mapped_column(String(200), nullable=False)
    results_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicked_product_id: Mapped[str | None] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
