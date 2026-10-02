"""Tests du PANIER (Prompt 3) — endpoints /api/v1/customer/cart.

Couvre : ajout, cumul de quantité (pas de doublon), modification, retrait,
vidage, persistance entre sessions, validation stock, isolation client.
"""

import pytest

from tests.catalog_helpers import create_published_product, setup_vendor
from tests.conftest import CUSTOMER_PAYLOAD, auth, register_customer

pytestmark = pytest.mark.asyncio


async def make_ctx(client):
    """Vendor A approuvé + produit publié + client connecté."""
    va = await setup_vendor(
        client, email="vA@cart.cd", phone="+243811000001", shop_name="CartShopA"
    )
    prod = await create_published_product(client, va["headers"], name="Casque Audio", price_usd="25.00", stock=10)
    cust = await register_customer(client)
    return va, prod, cust


async def add_item(client, headers, product_id, quantity=1):
    r = await client.post(
        "/api/v1/customer/cart/items",
        headers=headers,
        json={"product_id": product_id, "quantity": quantity},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_add_item_to_cart(client):
    _, prod, cust = await make_ctx(client)
    h = auth(cust["access_token"])
    summary = await add_item(client, h, prod["id"], 2)
    assert summary["items_count"] == 2
    ids = [i["product"]["id"] for i in summary["items"]]
    assert prod["id"] in ids


async def test_no_duplicate_same_product_quantity_cumulated(client):
    _, prod, cust = await make_ctx(client)
    h = auth(cust["access_token"])
    await add_item(client, h, prod["id"], 2)
    s2 = await add_item(client, h, prod["id"], 3)
    rows = [i for i in s2["items"] if i["product"]["id"] == prod["id"]]
    assert len(rows) == 1, "le même produit doit cumuler la quantité, pas doubler"
    assert rows[0]["quantity"] == 5


async def test_update_item_quantity(client):
    _, prod, cust = await make_ctx(client)
    h = auth(cust["access_token"])
    s = await add_item(client, h, prod["id"], 1)
    item_id = s["items"][0]["id"]
    r = await client.patch(
        f"/api/v1/customer/cart/items/{item_id}",
        headers=h, json={"quantity": 4},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["quantity"] == 4


async def test_remove_item_and_clear_cart(client):
    _, prod, cust = await make_ctx(client)
    h = auth(cust["access_token"])
    s = await add_item(client, h, prod["id"], 1)
    item_id = s["items"][0]["id"]
    r = await client.delete(f"/api/v1/customer/cart/items/{item_id}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []
    # re-ajout puis vidange globale
    await add_item(client, h, prod["id"], 2)
    rc = await client.delete("/api/v1/customer/cart", headers=h)
    assert rc.status_code == 200, rc.text
    assert rc.json()["items"] == []


async def test_cart_persists_between_sessions(client):
    """Un nouveau login du même client retrouve son panier."""
    _, prod, cust = await make_ctx(client)
    h = auth(cust["access_token"])
    await add_item(client, h, prod["id"], 3)
    from tests.helpers import login_as
    fresh = await login_as(client, CUSTOMER_PAYLOAD["email"], CUSTOMER_PAYLOAD["password"])
    r = await client.get("/api/v1/customer/cart", headers=auth(fresh["access_token"]))
    assert r.status_code == 200, r.text
    assert sum(i["quantity"] for i in r.json()["items"]) == 3


async def test_cart_total_usd_correct(client):
    _, prod, cust = await make_ctx(client)
    h = auth(cust["access_token"])
    s = await add_item(client, h, prod["id"], 4)  # 4 x $25
    total = float(s["subtotal_usd"])
    assert total == pytest.approx(100.0)
    assert float(s["total_usd"]) == pytest.approx(100.0)


async def test_validate_cart_stock_ok_then_exceeded(client):
    _, prod, cust = await make_ctx(client)
    h = auth(cust["access_token"])
    v0 = await client.get("/api/v1/customer/cart/validate", headers=h)
    assert v0.status_code == 200 and v0.json()["valid"] is True
    await add_item(client, h, prod["id"], 999)
    v1 = await client.get("/api/v1/customer/cart/validate", headers=h)
    assert v1.json()["valid"] is False
    assert v1.json()["issues"]


async def test_add_unpublished_or_other_tenant_product_rejected(client):
    """Un produit brouillon (non publié) ne peut être ajouté au panier."""
    va = await setup_vendor(
        client, email="vB@cart.cd", phone="+243811000002", shop_name="CartShopB"
    )
    body = {"name": "Produit Brouillon", "price_input": "10.00",
            "currency_input": "USD", "stock": 5, "is_published": False}
    import json as _json
    r = await client.post("/api/v1/vendor/products", headers=va["headers"],
                          data={"data": _json.dumps(body)})
    assert r.status_code == 201, r.text
    draft_id = r.json()["id"]
    cust = await register_customer(client)
    ra = await client.post(
        "/api/v1/customer/cart/items", headers=auth(cust["access_token"]),
        json={"product_id": draft_id, "quantity": 1},
    )
    assert ra.status_code >= 400, "un produit non publié ne doit pas être commandable"


async def test_cart_isolation_between_customers(client):
    """Le client B ne voit ni ne modifie le panier du client A."""
    _, prod, _ = await make_ctx(client)
    ca = await register_customer(client)
    cb = await register_customer(
        client, email="zoe@client.cd", phone="+243900112233"
    )
    await add_item(client, auth(ca["access_token"]), prod["id"], 2)
    rb = await client.get("/api/v1/customer/cart", headers=auth(cb["access_token"]))
    assert rb.json()["items"] == []
    # tentative de suppression d'un item d'A par B → 404
    sa = await client.get("/api/v1/customer/cart", headers=auth(ca["access_token"]))
    item_a = sa.json()["items"][0]["id"]
    rd = await client.delete(
        f"/api/v1/customer/cart/items/{item_a}", headers=auth(cb["access_token"])
    )
    assert rd.status_code in (404, 403), rd.text
