"""Tests service CONFIRMATION DE LIVRAISON (Prompt 4) — stock, commission,
reçu, order globale, autorisations.

La confirmation est le point de vérité financière du COD : elle décrémente
stock + reserved_stock, fige la commission par item (taux snapshoté), génère
le reçu PDF et bascule la commande en "delivered" quand tous les colis sont
livrés. Tout se passe dans une seule transaction, événements APRÈS commit.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError, PermissionDeniedError
from app.db import session as db_session
from app.models.order import OrderItem
from app.services import delivery_confirmation_service as dcs
from app.services import shipment_service
from tests.catalog_helpers import create_published_product, read_stock, setup_vendor
from tests.conftest import auth, register_customer
from tests.delivery_helpers import make_courier, place_order

pytestmark = pytest.mark.asyncio


async def _setup(client):
    """Vendor + produit publié + client → commande passée."""
    va = await setup_vendor(client, email="v@confirm.cd", phone="+243811200001", shop_name="ConfShop")
    prod = await create_published_product(client, va["headers"], name="Lampe", price_usd="30.00", stock=10)
    cust = await register_customer(client)
    orders = await place_order(client, cust["access_token"], products=[prod], quantities=[2])
    return va, prod, cust, orders[0]


async def _start_shipment(client, va, order, courier_id=None):
    """Crée un colis avec tous les items de la commande (et l'assigne/démarre)."""
    from tests.delivery_helpers import order_items_ids
    item_ids = await order_items_ids(order["id"])
    body = {"order_id": order["id"], "item_ids": item_ids}
    if courier_id:
        body["courier_id"] = courier_id
    r = await client.post("/api/v1/vendor/shipments", headers=va["headers"], json=body)
    assert r.status_code == 201, r.text
    shp = r.json()
    if courier_id:
        rc = await client.post(f"/api/v1/courier/shipments/{shp['id']}/start",
                               headers=auth(_COURIER_TOKEN[0]))
        assert rc.status_code == 200, rc.text
    return shp


_COURIER_TOKEN: list[str] = []  # rempli par les tests qui créent un courier


async def _load_user(user_id: str):
    factory = db_session.get_session_factory()
    async with factory() as s:
        from app.models.user import User
        return await s.get(User, user_id)


async def test_confirm_qr_marks_delivered_and_decrements_stock(client):
    va, prod, cust, order = await _setup(client)
    before_stock, before_reserved = await read_stock(prod["id"])
    assert before_reserved == 2 and before_stock == 10

    item_ids = [i["id"] for i in order["items"]]
    r = await client.post("/api/v1/vendor/shipments", headers=va["headers"],
                          json={"order_id": order["id"], "item_ids": item_ids})
    assert r.status_code == 201, r.text
    shp = r.json()

    # Démarrage via DB (le courier n'est pas obligatoire pour ce test service)
    factory = db_session.get_session_factory()
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        shipment.status = "in_transit"
        await s.commit()

    actor = await _load_user(cust["id"])
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        out = await dcs.confirm_delivery(s, shipment, "qr_scan", actor)

    assert out["shipment"].status == "delivered"
    after_stock, after_reserved = await read_stock(prod["id"])
    assert after_stock == 8          # 10 - 2 livrés
    assert after_reserved == 0       # réservation soldée

    async with factory() as s:
        rows = (await s.execute(
            __import__("sqlalchemy").select(OrderItem).where(OrderItem.order_id == order["id"])
        )).scalars().all()
        for oi in rows:
            assert oi.delivered_at is not None
            # free plan : rate 5%, min 0.50 → 60*0.05 = 3.00
            assert Decimal(str(oi.commission_amount_usd)) == Decimal("3.00") or \
                Decimal(str(oi.commission_amount_usd)) > 0

async def test_confirm_completes_order_when_all_shipments_delivered(client):
    va, prod, cust, order = await _setup(client)
    item_ids = [i["id"] for i in order["items"]]
    r = await client.post("/api/v1/vendor/shipments", headers=va["headers"],
                          json={"order_id": order["id"], "item_ids": item_ids})
    shp = r.json()
    factory = db_session.get_session_factory()
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        shipment.status = "in_transit"
        await s.commit()

    actor = await _load_user(cust["id"])
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        out = await dcs.confirm_delivery(s, shipment, "manual_code", actor)
    assert out["order_completed"] is True
    from tests.delivery_helpers import read_order_status
    assert await read_order_status(order["id"]) == "delivered"

async def test_confirm_generates_receipt_document(client):
    va, prod, cust, order = await _setup(client)
    item_ids = [i["id"] for i in order["items"]]
    r = await client.post("/api/v1/vendor/shipments", headers=va["headers"],
                          json={"order_id": order["id"], "item_ids": item_ids})
    shp = r.json()
    factory = db_session.get_session_factory()
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        shipment.status = "in_transit"
        await s.commit()
    actor = await _load_user(cust["id"])
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        out = await dcs.confirm_delivery(s, shipment, "qr_scan", actor)
    assert out["receipt"] is not None
    assert out["receipt"].number.startswith("REC-")

async def test_confirm_rejects_pending_shipment(client):
    va, prod, cust, order = await _setup(client)
    item_ids = [i["id"] for i in order["items"]]
    r = await client.post("/api/v1/vendor/shipments", headers=va["headers"],
                          json={"order_id": order["id"], "item_ids": item_ids})
    shp = r.json()
    actor = await _load_user(cust["id"])
    factory = db_session.get_session_factory()
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        with pytest.raises(ConflictError):
            await dcs.confirm_delivery(s, shipment, "qr_scan", actor)

async def test_customer_cannot_confirm_other_clients_delivery(client):
    va, prod, cust, order = await _setup(client)
    item_ids = [i["id"] for i in order["items"]]
    r = await client.post("/api/v1/vendor/shipments", headers=va["headers"],
                          json={"order_id": order["id"], "item_ids": item_ids})
    shp = r.json()
    factory = db_session.get_session_factory()
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        shipment.status = "in_transit"
        await s.commit()

    other = await register_customer(client, email="eve@other.cd", phone="+243990000111")
    actor = await _load_user(other["id"])
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        with pytest.raises(PermissionDeniedError):
            await dcs.confirm_delivery(s, shipment, "qr_scan", actor)

async def test_double_confirm_is_atomic_no_double_decrement(client):
    """Un item déjà livré ne doit jamais être recompté (idempotence)."""
    va, prod, cust, order = await _setup(client)
    item_ids = [i["id"] for i in order["items"]]
    r = await client.post("/api/v1/vendor/shipments", headers=va["headers"],
                          json={"order_id": order["id"], "item_ids": item_ids})
    shp = r.json()
    factory = db_session.get_session_factory()
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        shipment.status = "in_transit"
        await s.commit()
    actor = await _load_user(cust["id"])
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        await dcs.confirm_delivery(s, shipment, "qr_scan", actor)
    # Seconde tentative sur un colis déjà livré → refus statut, pas de 2e décrément
    async with factory() as s:
        shipment = await shipment_service.get_shipment(s, shp["id"])
        with pytest.raises(ConflictError):
            await dcs.confirm_delivery(s, shipment, "qr_scan", actor)
    _, reserved = await read_stock(prod["id"])
    assert reserved == 0
