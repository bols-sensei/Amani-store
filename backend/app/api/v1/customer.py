"""Endpoints /api/v1/customer — espace client (commandes, annulation).

Isolation : chaque requête est filtrée sur user.id (JWT). Un client ne peut
ni voir ni annuler la commande d'un autre ; l'annulation n'est possible que
sur pending/confirmed (machine à états + libération du stock réservé).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, require_customer
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.db.session import get_db
from app.crud import order as crud_order
from app.schemas.order import OrderCancelRequest
from app.services import order_service
from app.api.v1.orders import _order_out

router = APIRouter(
    prefix="/customer",
    tags=["customer"],
    dependencies=[Depends(require_customer)],
)

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/orders")
async def list_my_orders(db: DbDep, user: CurrentUser, status: str | None = None,
                         page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """Mes commandes, triées par date décroissante."""
    rows, total = await crud_order.list_orders(
        db, customer_id=user.id, status=status, page=page, page_size=page_size
    )
    return {
        "items": [_order_out(o) for o in rows],
        "total": total, "page": page, "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }


@router.get("/orders/{order_id}")
async def get_my_order(order_id: str, db: DbDep, user: CurrentUser) -> dict[str, Any]:
    """Détail d'une de mes commandes (404 si elle appartient à un autre)."""
    order = await crud_order.get_order_for_customer(db, user.id, order_id)
    if order is None:
        raise NotFoundError("Commande introuvable")
    return _order_out(order)


@router.post("/orders/{order_id}/cancel")
async def cancel_my_order(order_id: str, payload: OrderCancelRequest,
                          db: DbDep, user: CurrentUser) -> dict[str, Any]:
    """Annule ma commande si pending/confirmed, libère le stock réservé."""
    order = await crud_order.get_order_for_customer(db, user.id, order_id)
    if order is None:
        raise NotFoundError("Commande introuvable")
    if order.status not in ("pending", "confirmed"):
        raise PermissionDeniedError(
            f"Annulation impossible au statut « {order.status} »"
        )
    order = await order_service.update_order_status(
        db, order.id, "cancelled", user, reason=payload.reason or "client_cancel"
    )
    return _order_out(order)
