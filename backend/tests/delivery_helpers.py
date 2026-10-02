"""Helpers partagés pour les tests du Prompt 4 (cycle de livraison COD).

Flux type d'un test :
    vendor + produit publié → client ajoute au panier → POST /orders
    (split multi-vendeurs) → vendor crée un shipment → assigne un courier
    → courier démarre → QR token → client confirme → stock/commission/reçu.

Conventions : tenant_id jamais depuis le body ; vendor approuvé avant
d'accéder à /vendor/* ; produits publiés pour être commandables.
"""

from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.db import session as db_session
from app.models.order import Order, OrderItem
from app.models.user import User
from tests.catalog_helpers import auth, create_published_product, setup_vendor
from tests.conftest import register_customer

DELIVERY_PASSWORD = "Deliv3ry123"


async def make_courier(client, vendor_ctx: dict, *, email: str,
                       phone: str) -> dict:
    """Crée directement un user courier du tenant vendeur (DB) + login.

    Le rôle courier n'a pas d'inscription publique dans le MVP : il est
    créé par le vendeur. On insère donc en base comme fait helpers.py
    pour le superadmin, puis on authentifie via /auth/login.
    """
    factory = db_session.get_session_factory()
    async with factory() as s:
        courier = User(
            email=email,
            phone=phone,
            hashed_password=hash_password(DELIVERY_PASSWORD),
            role="courier",
            tenant_id=vendor_ctx["vendor"]["tenant_id"],
            is_active=True,
            is_verified=True,
            first_name="Liv",
            last_name="reur",
        )
        s.add(courier)
        await s.commit()
        await s.refresh(courier)
        cid = courier.id
    r = await client.post("/api/v1/auth/login",
                          json={"identifier": email, "password": DELIVERY_PASSWORD})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    return {"id": cid, "token": tok, "headers": auth(tok)}


async def order_payload(*, commune: str = "Gombe") -> dict:
    return {
        "delivery_address": {
            "name": "Bob Kabasele",
            "phone": "+243998765432",
            "commune": commune,
            "city": "Kinshasa",
            "details": "Avenue de la Testerie, n°42",
        },
        "delivery_notes": "Appeler avant de passer",
    }


async def place_order(client, customer_token: str, *,
                      products: list[dict], quantities: list[int] | None = None):
    """Remplit le panier puis POST /orders. Retourne la liste des commandes."""
    h = auth(customer_token)
    qty = quantities or [1] * len(products)
    for p, q in zip(products, qty):
        r = await client.post("/api/v1/customer/cart/items", headers=h,
                              json={"product_id": p["id"], "quantity": q})
        assert r.status_code == 201, r.text
    ro = await client.post("/api/v1/orders", headers=h, json=order_payload())
    assert ro.status_code == 201, ro.text
    return ro.json()


async def order_items_ids(order_id: str) -> list[str]:
    factory = db_session.get_session_factory()
    async with factory() as s:
        rows = (await s.execute(
            select(OrderItem.id).where(OrderItem.order_id == order_id)
        )).scalars().all()
        return list(rows)


async def read_order_status(order_id: str) -> str:
    factory = db_session.get_session_factory()
    async with factory() as s:
        o = await s.get(Order, order_id)
        return o.status if o else None


async def shift_order_created_at(order_id: str, hours_ago: float) -> None:
    """Recule created_at d'une commande (mock du temps pour auto-cancel)."""
    factory = db_session.get_session_factory()
    async with factory() as s:
        o = await s.get(Order, order_id)
        o.created_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        await s.commit()
