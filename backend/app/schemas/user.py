"""Schemas Pydantic v2 — utilisateurs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRead(BaseModel):
    """Représentation publique d'un user (aucun champ sensible)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    tenant_id: Optional[str] = None
    is_active: bool
    is_verified: bool
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language: str
    currency_display: str
    last_login_at: Optional[datetime] = None
    created_at: datetime


class UserUpdate(BaseModel):
    """Mise à jour de profil (préférences utilisateur — niveau 3 config)."""

    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    language: Optional[str] = Field(default=None, pattern=r"^[a-z]{2}$")
    currency_display: Optional[str] = Field(default=None, pattern=r"^[A-Z]{2,4}$")
