"""Schémas Pydantic v2 — catégories (globales + tenant)."""

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    """Création d'une catégorie par un tenant (ou globales par superadmin)."""

    name: str = Field(min_length=2, max_length=120)
    parent_id: str | None = None
    description: str | None = None
    icon_url: str | None = None
    display_order: int = 0


class CategoryUpdate(BaseModel):
    """Modification partielle d'une catégorie."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    parent_id: str | None = None
    description: str | None = None
    icon_url: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class CategoryOut(BaseModel):
    """Catégorie sérialisée (arborescence optionnelle via `children`)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None
    parent_id: str | None
    name: str
    slug: str
    description: str | None = None
    icon_url: str | None = None
    display_order: int
    is_active: bool
    children: list["CategoryOut"] = []


class CategoryListOut(BaseModel):
    """Liste à plat + version arbre."""

    items: list[CategoryOut]
    tree: list[CategoryOut]
