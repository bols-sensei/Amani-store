"""CRUD Panier — accès par client (isolation stricte côté service)."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cart import Cart, CartItem


async def get_cart_by_customer(db: AsyncSession, customer_id: str) -> Optional[Cart]:
    return (await db.execute(
        select(Cart).where(Cart.customer_id == customer_id).options(selectinload(Cart.items))
    )).scalar_one_or_none()


async def get_cart(db: AsyncSession, cart_id: str) -> Optional[Cart]:
    return (await db.execute(
        select(Cart).where(Cart.id == cart_id).options(selectinload(Cart.items))
    )).scalar_one_or_none()


async def get_item(db: AsyncSession, item_id: str) -> Optional[CartItem]:
    return (await db.execute(
        select(CartItem).where(CartItem.id == item_id)
    )).scalar_one_or_none()
