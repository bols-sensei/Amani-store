"""Schémas Pydantic v2 — panier client (multi-tenant)."""

from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class CartItemAdd(BaseModel):
    """Ajout d'un produit au panier."""

    model_config = ConfigDict(strict=True)

    product_id: str
    quantity: int = Field(default=1, ge=1)


class CartItemUpdate(BaseModel):
    """Modification de quantité d'une ligne de panier."""

    model_config = ConfigDict(strict=True)

    quantity: int = Field(ge=0)  # 0 = retirer


class TenantSummary(BaseModel):
    """Résumé vendeur (colonnes réelles du modèle Tenant)."""

    id: str
    name: str
    slug: str
    logo_url: Optional[str] = None


class ProductSummary(BaseModel):
    """Résumé produit dans une ligne de panier."""

    id: str
    name: str
    slug: str
    price_usd: Decimal
    stock: int
    reserved_stock: int
    is_active: bool
    is_published: bool
    image_url: Optional[str] = None


class CartItemOut(BaseModel):
    """Ligne de panier avec sous-totaux USD + affichage."""

    id: str
    product: ProductSummary
    tenant: TenantSummary
    quantity: int
    unit_price_usd: Decimal
    subtotal_usd: Decimal
    subtotal_display: str
    available_stock: int


class TenantGroup(BaseModel):
    """Regroupement des lignes de panier par vendeur (pré-split)."""

    tenant: TenantSummary
    items: list[CartItemOut]
    subtotal_usd: Decimal
    subtotal_display: str
    delivery_fee_usd: Decimal = Decimal("0")
    delivery_fee_display: str = "$0.00"


class CartOut(BaseModel):
    """Panier complet résumé, groupé par tenant."""

    id: str
    currency_display: str
    items: list[CartItemOut]
    tenant_groups: list[TenantGroup]
    subtotal_usd: Decimal
    subtotal_display: str
    delivery_fee_usd: Decimal
    delivery_fee_display: str
    total_usd: Decimal
    total_display: str
    items_count: int
    updated_at: Any


class CartValidateIssue(BaseModel):
    """Anomalie détectée à la validation du panier."""

    item_id: Optional[str] = None
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    code: str
    message: str


class CartValidateResult(BaseModel):
    """Résultat de validation du panier avant commande."""

    valid: bool
    issues: list[CartValidateIssue] = []
