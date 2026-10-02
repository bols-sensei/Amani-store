"""Schemas Pydantic v2 — tenants (superadmin)."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    status: str
    plan_name: str
    commission_rate: Decimal
    currency_input: str
    country_code: str
    timezone: str
    language: str
    kimia_tenant_id: Optional[str] = None
    billing_email: Optional[str] = None
    rejection_reason: Optional[str] = None
    suspension_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TenantListPage(BaseModel):
    items: list[TenantRead]
    total: int
    page: int
    page_size: int


class TenantUpdate(BaseModel):
    """Modification superadmin : plan, commission, statut... (jamais le tenant_id)."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    plan_name: Optional[str] = Field(default=None, max_length=20)
    commission_rate: Optional[Decimal] = Field(default=None, ge=0, le=1)
    billing_email: Optional[EmailStr] = None
    currency_input: Optional[str] = Field(default=None, max_length=8)
    language: Optional[str] = Field(default=None, max_length=5)
    kimia_tenant_id: Optional[str] = Field(default=None, max_length=100)


class TenantActionRequest(BaseModel):
    """Raison optionnelle pour reject/suspend."""

    reason: Optional[str] = Field(default=None, max_length=500)
