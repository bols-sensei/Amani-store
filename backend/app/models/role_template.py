"""Modèle RoleTemplate — templates de rôles staff prédéfinis (config-driven)."""

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDType, new_uuid


class RoleTemplate(Base):
    """Template de rôle (Manager, Comptable...) avec liste de permissions.

    `permissions` peut contenir des wildcards : "products.*".
    """

    __tablename__ = "role_templates"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
