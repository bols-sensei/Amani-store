"""Endpoints /api/v1/cart — panier client (tenant JAMAIS depuis le body).

Isolation : toutes les opérations sont filtrées sur l'utilisateur JWT.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, require_customer
from app.db.session import get_db
from app.schemas.cart import CartItemAdd, CartItemUpdate

router = APIRouter(
    prefix="/cart",
    tags=["cart"],
    dependencies=[Depends(require_customer)],
)

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("")
async def get_cart(db: DbDep, user: CurrentUser) -> dict[str, Any]:
    """Panier courant groupé par vendeur avec totaux USD + devise."""
    from app.services import cart_service

    return await cart_service.get_cart_summary(db, user)


@router.post("/items", status_code=201)
async def add_item(payload: CartItemAdd, db: DbDep, user: CurrentUser) -> dict[str, Any]:
    """Ajoute un produit publié d'importe quel vendeur (prix snapshoté USD)."""
    from app.services import cart_service

    await cart_service.add_item(db, user, payload.product_id, payload.quantity)
    await db.commit()
    return await cart_service.get_cart_summary(db, user)


@router.patch("/items/{item_id}")
async def update_item(item_id: str, payload: CartItemUpdate, db: DbDep,
                      user: CurrentUser) -> dict[str, Any]:
    """Met à jour la quantité (0 = retrait)."""
    from app.services import cart_service

    await cart_service.update_item_quantity(db, user, item_id, payload.quantity)
    await db.commit()
    return await cart_service.get_cart_summary(db, user)


@router.delete("/items/{item_id}")
async def remove_item(item_id: str, db: DbDep, user: CurrentUser) -> dict[str, Any]:
    """Retire une ligne du panier."""
    from app.services import cart_service

    await cart_service.remove_item(db, user, item_id)
    await db.commit()
    return await cart_service.get_cart_summary(db, user)


@router.delete("")
async def clear_cart(db: DbDep, user: CurrentUser) -> dict[str, Any]:
    """Vide entièrement le panier."""
    from app.services import cart_service

    await cart_service.clear_cart(db, user)
    await db.commit()
    return await cart_service.get_cart_summary(db, user)


@router.get("/validate")
async def validate_cart(db: DbDep, user: CurrentUser) -> dict[str, Any]:
    """Vérifie stock/disponibilité de chaque ligne avant commande."""
    from app.services import cart_service

    return await cart_service.validate_cart(db, user)
