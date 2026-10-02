"""Schémas Pydantic v2 — produits du catalogue.

Rappel règle d'or : le prix est SAISI dans la devise du vendeur
(`price_input` + `currency_input`) mais TOUJOURS stocké/converti en USD.
Le `tenant_id` n'existe JAMAIS dans un schéma d'entrée : il vient du JWT.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CURRENCY_INPUTS = ("USD", "CDF")
SORT_OPTIONS = (
    "created_at",
    "-created_at",
    "price_usd",
    "-price_usd",
    "sales_count",
    "-sales_count",
    "views_count",
    "-views_count",
    "relevance",
)


class ProductImageOut(BaseModel):
    """Image produit sérialisée (URLs déjà servies par /static)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    thumb_url: str | None = None
    medium_url: str | None = None
    alt_text: str | None = None
    display_order: int
    is_primary: bool


class ProductCreate(BaseModel):
    """Création produit (multipart : les images arrivent séparément)."""

    name: str = Field(min_length=3, max_length=200)
    description: str | None = None
    short_description: str | None = Field(default=None, max_length=200)
    category_id: str | None = None
    price_input: Decimal = Field(gt=0)
    currency_input: str = "CDF"
    stock: int = Field(default=0, ge=0)
    sku: str | None = Field(default=None, max_length=80)
    weight_kg: Decimal | None = Field(default=None, gt=0)
    is_published: bool = False

    @field_validator("currency_input")
    @classmethod
    def _check_currency(cls, v: str) -> str:
        if v not in CURRENCY_INPUTS:
            raise ValueError(f"currency_input doit être l'une de {CURRENCY_INPUTS}")
        return v


class ProductUpdate(BaseModel):
    """Modification partielle d'un produit."""

    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    short_description: str | None = Field(default=None, max_length=200)
    category_id: str | None = None
    price_input: Decimal | None = Field(default=None, gt=0)
    currency_input: str | None = None
    stock: int | None = Field(default=None, ge=0)
    sku: str | None = None
    weight_kg: Decimal | None = None
    is_active: bool | None = None

    @field_validator("currency_input")
    @classmethod
    def _check_currency(cls, v: str | None) -> str | None:
        if v is not None and v not in CURRENCY_INPUTS:
            raise ValueError(f"currency_input doit être l'une de {CURRENCY_INPUTS}")
        return v


class ProductOut(BaseModel):
    """Produit complet + champs calculés (prix affiché selon devise)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    category_id: str | None
    name: str
    slug: str
    description: str | None
    short_description: str | None
    price_usd: Decimal
    price_display: str = ""          # ex: "$20.00" ou "50 000 FC"
    price_value_display: Decimal = Decimal("0")
    currency_display: str = "USD"
    currency_input: str
    stock: int
    reserved_stock: int
    available_stock: int = 0
    sku: str | None
    weight_kg: Decimal | None
    is_active: bool
    is_published: bool
    views_count: int
    sales_count: int
    rating_avg: Decimal
    rating_count: int
    images: list[ProductImageOut] = []
    category: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ProductListOut(BaseModel):
    """Version allégée pour les listes."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    price_usd: Decimal
    price_display: str = ""
    stock: int
    available_stock: int = 0
    is_active: bool
    is_published: bool
    views_count: int
    sales_count: int
    rating_avg: Decimal
    primary_image_url: str | None = None


class PaginatedProducts(BaseModel):
    """Pagination standard du catalogue."""

    items: list[ProductListOut]
    total: int
    page: int
    per_page: int
    pages: int


class StockAdjust(BaseModel):
    """Ajustement de stock (+/- delta)."""

    delta: int = Field(..., description="Écart à appliquer (peut être négatif)")
    reason: str | None = Field(default=None, max_length=200)

    @field_validator("delta")
    @classmethod
    def _non_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("delta doit être non nul")
        return v


class BulkAction(BaseModel):
    """Action groupée sur des produits (publish / unpublish / delete)."""

    product_ids: list[str] = Field(min_length=1, max_length=200)
    action: str = Field(pattern="^(publish|unpublish|deactivate)$")


class ProductSearchFilters(BaseModel):
    """Filtres de recherche publics (shop) et vendeurs."""

    q: str | None = Field(default=None, max_length=200)
    category_id: str | None = None
    tenant_slug: str | None = None
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    in_stock_only: bool = False
    sort: str = "-created_at"

    @field_validator("sort")
    @classmethod
    def _check_sort(cls, v: str) -> str:
        if v not in SORT_OPTIONS:
            raise ValueError(f"sort invalide. Options : {', '.join(SORT_OPTIONS)}")
        return v


class SearchSuggestions(BaseModel):
    """Réponses d'autocomplete."""

    products: list[dict] = []
    categories: list[dict] = []


class ProductStatsSummary(BaseModel):
    """Statistiques agrégées du catalogue d'un tenant."""

    total: int
    active: int
    published: int
    drafts: int
    low_stock: int
    out_of_stock: int


class ImageAdd(BaseModel):
    """Résultat d'upload d'image(s)."""

    added: list[ProductImageOut]
    remaining_quota: int | None = None
