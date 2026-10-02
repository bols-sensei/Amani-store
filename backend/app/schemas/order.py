"""Schémas Pydantic v2 — commandes, suivi, zones de livraison."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeliveryAddress(BaseModel):
    """Adresse de livraison (stockée en JSON sur l'order)."""

    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=6, max_length=30)
    commune: str = Field(min_length=1, max_length=120)
    city: str = Field(default="Kinshasa", max_length=120)
    details: Optional[str] = Field(default=None, max_length=500)
    coordinates: Optional[dict[str, float]] = None


class OrderCreate(BaseModel):
    """Création de commande(s) depuis le panier (split auto multi-vendeurs).

    ⚠️ Pas de tenant_id ici : JAMAIS depuis le body (règle absolue).
    """

    model_config = ConfigDict(strict=True)

    delivery_address: DeliveryAddress
    delivery_zone_id: Optional[str] = None
    delivery_notes: Optional[str] = Field(default=None, max_length=1000)


class OrderStatusUpdate(BaseModel):
    """Changement de statut générique (vendor/superadmin)."""

    model_config = ConfigDict(strict=True)

    status: str = Field(min_length=2, max_length=30)
    reason: Optional[str] = Field(default=None, max_length=300)


class OrderCancelRequest(BaseModel):
    """Annulation avec raison optionnelle."""

    model_config = ConfigDict(strict=True)

    reason: Optional[str] = Field(default=None, max_length=300)


class OrderItemOut(BaseModel):
    """Ligne de commande (snapshots)."""

    id: str
    product_id: Optional[str]
    product_name: str
    product_short_description: Optional[str]
    product_image_url: Optional[str]
    sku: Optional[str]
    unit_price_usd: Decimal
    quantity: int
    subtotal_usd: Decimal
    commission_rate: Decimal
    commission_amount_usd: Decimal
    delivered_at: Optional[datetime]


class OrderTimelineEvent(BaseModel):
    """Événement de suivi (historique des statuts)."""

    status: str
    label: str
    at: datetime
    by_role: Optional[str] = None
    note: Optional[str] = None


class OrderOut(BaseModel):
    """Commande complète avec timeline et totaux affichés."""

    id: str
    reference: str
    tenant: dict[str, Any]
    customer: Optional[dict[str, Any]] = None
    status: str
    status_label: str
    subtotal_usd: Decimal
    delivery_fee_usd: Decimal
    total_usd: Decimal
    subtotal_display: str
    delivery_fee_display: str
    total_display: str
    currency_at_creation: str
    exchange_rate_used: Optional[Decimal]
    delivery_address: dict[str, Any]
    delivery_zone_id: Optional[str]
    delivery_notes: Optional[str]
    items: list[OrderItemOut]
    timeline: list[OrderTimelineEvent] = []
    created_at: datetime
    confirmed_at: Optional[datetime]
    delivered_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    cancel_reason: Optional[str]


class OrderListItem(BaseModel):
    """Version allégée pour les listes."""

    id: str
    reference: str
    status: str
    status_label: str
    total_usd: Decimal
    total_display: str
    items_count: int
    created_at: datetime
    tenant: Optional[dict[str, Any]] = None
    customer: Optional[dict[str, Any]] = None


class PaginatedOrders(BaseModel):
    """Pagination standard des listes de commandes."""

    items: list[OrderListItem]
    total: int
    page: int
    page_size: int
    pages: int


class DeliveryZoneCreate(BaseModel):
    """Création d'une zone de livraison (tenant via JWT)."""

    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=2, max_length=120)
    regions: list[str] = Field(min_length=1)
    base_fee_usd: Decimal = Field(ge=0)
    estimated_days_min: int = Field(default=1, ge=0, le=60)
    estimated_days_max: int = Field(default=3, ge=0, le=90)

    @field_validator("estimated_days_max")
    @classmethod
    def _check_range(cls, v: int, info) -> int:
        lo = info.data.get("estimated_days_min")
        if lo is not None and v < lo:
            raise ValueError("estimated_days_max doit être >= estimated_days_min")
        return v


class DeliveryZoneUpdate(BaseModel):
    """Modification partielle d'une zone."""

    model_config = ConfigDict(strict=True)

    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    regions: Optional[list[str]] = None
    base_fee_usd: Optional[Decimal] = Field(default=None, ge=0)
    estimated_days_min: Optional[int] = Field(default=None, ge=0, le=60)
    estimated_days_max: Optional[int] = Field(default=None, ge=0, le=90)
    is_active: Optional[bool] = None


class DeliveryZoneOut(BaseModel):
    """Zone de livraison complète."""

    id: str
    tenant_id: str
    name: str
    regions: list[str]
    base_fee_usd: Decimal
    base_fee_display: str
    estimated_days_min: int
    estimated_days_max: int
    is_active: bool
    created_at: datetime


class OrdersStatsSummary(BaseModel):
    """ Compteurs par statut pour le dashboard vendeur/superadmin."""

    pending: int = 0
    confirmed: int = 0
    preparing: int = 0
    shipped: int = 0
    out_for_delivery: int = 0
    delivered: int = 0
    delivered_today: int = 0
    rescheduled: int = 0
    failed: int = 0
    returned: int = 0
    cancelled: int = 0
    cancelled_today: int = 0
    total: int = 0
