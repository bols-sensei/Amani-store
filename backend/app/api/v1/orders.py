"""Endpoints /api/v1/orders — création client + suivi public.

- POST /orders : crée la/les commande(s) depuis le panier (split auto).
  ⚠️ tenant_id JAMAIS dans le body (déduit des produits du panier).
- GET /orders/track/{reference} : SUIVI PUBLIC sans JWT (cahier des charges) ;
  exposition minimale (statut + timeline + ville), jamais d'identité complète.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, require_customer
from app.core.exceptions import NotFoundError, ValidationError_
from app.db.session import get_db
from app.crud import order as crud_order
from app.schemas.order import OrderCreate
from app.services import order_service
from app.services.order_state_machine import status_label

router = APIRouter(prefix="/orders", tags=["orders"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _order_out(o) -> dict[str, Any]:
    """Sérialise une commande avec libellés FR et timeline ordonnée."""
    return {
        "id": o.id,
        "reference": o.reference,
        "status": o.status,
        "status_label": status_label(o.status),
        "subtotal_usd": str(o.subtotal_usd),
        "delivery_fee_usd": str(o.delivery_fee_usd),
        "total_usd": str(o.total_usd),
        "currency_at_creation": o.currency_at_creation,
        "exchange_rate_used": str(o.exchange_rate_used) if o.exchange_rate_used else None,
        "delivery_notes": o.delivery_notes,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "confirmed_at": o.confirmed_at.isoformat() if o.confirmed_at else None,
        "delivered_at": o.delivered_at.isoformat() if o.delivered_at else None,
        "cancelled_at": o.cancelled_at.isoformat() if o.cancelled_at else None,
        "cancel_reason": o.cancel_reason,
        "items": [
            {
                "id": i.id, "product_id": i.product_id, "product_name": i.product_name,
                "product_short_description": i.product_short_description,
                "product_image_url": i.product_image_url, "sku": i.sku,
                "unit_price_usd": str(i.unit_price_usd), "quantity": i.quantity,
                "subtotal_usd": str(i.subtotal_usd),
            } for i in o.items
        ],
        "timeline": [
            {
                "status": h.new_status,
                "label": status_label(h.new_status),
                "at": h.created_at.isoformat() if h.created_at else None,
                "by_role": h.changed_by_role,
                "note": h.reason,
            } for h in sorted(o.history, key=lambda x: x.created_at)
        ],
    }


@router.post("", status_code=201)
async def create_orders(payload: OrderCreate, db: DbDep, user: CurrentUser
                        ) -> dict[str, Any]:
    """Commande le panier → N commandes (une par vendeur). Tout ou rien."""
    from app.services import cart_service

    check = await cart_service.validate_cart(db, user)
    if not check["valid"]:
        # 409 sémantique via ValidationError_ : messages clients clairs.
        raise ValidationError_(
            "Panier non commandable", details=check["issues"]
        )
    orders = await order_service.create_orders_from_cart(
        db, user,
        delivery_address=payload.delivery_address.model_dump(),
        delivery_zone_id=payload.delivery_zone_id,
        notes=payload.delivery_notes,
    )
    return {
        "orders": [_order_out(o) for o in orders],
        "count": len(orders),
        "message": ("Votre commande a été enregistrée. Paiement à la livraison."
                    if len(orders) == 1 else
                    f"Votre panier a été réparti en {len(orders)} commandes. "
                    "Paiement à la livraison."),
    }


@router.get("/track/{reference}")
async def track_public(reference: str, db: DbDep) -> dict[str, Any]:
    """Suivi de commande PUBLIC (sans JWT) par référence."""
    order = (await db.execute(
        crud_order._with_rel(select(crud_order.Order))
        .where(crud_order.Order.reference == reference)
    )).scalar_one_or_none()
    if order is None:
        raise NotFoundError("Commande introuvable")
    out = _order_out(order)
    addr = order.delivery_address or {}
    # Exposition minimale pour le suivi public (jamais identité complète).
    out["delivery_city"] = addr.get("city")
    out["delivery_commune"] = addr.get("commune")
    out.pop("delivery_notes", None)
    return out
