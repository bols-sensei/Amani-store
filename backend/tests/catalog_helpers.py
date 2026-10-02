"""Helpers partagés pour les tests des prompts 3 & 4 (panier/commandes/livraison).

Conventions :
- tenant_id JAMAIS depuis le body : tout passe par le JWT ;
- un vendor doit être APPROUVÉ (superadmin) avant d'accéder à /vendor/*
  (TenantStatusMiddleware renvoie 403 sinon) ;
- produits créés PUBLIÉS pour être commandables.
"""

import json

from app.db import session as db_session
from app.models.product import Product
from tests.conftest import VENDOR_PAYLOAD, auth, register_vendor
from tests.helpers import create_superadmin, login_as


async def activate(client, vendor: dict, *, email: str, password: str) -> dict:
    """Approuve le tenant du vendor et retourne headers/token frais."""
    await create_superadmin()
    sa = await login_as(client, "root@kimia.cd", "Sup3rAdmin1")
    r = await client.post(
        f"/api/v1/superadmin/tenants/{vendor['tenant_id']}/approve",
        headers=auth(sa["access_token"]),
    )
    assert r.status_code == 200, r.text
    fresh = await login_as(client, email, password)
    return {"headers": auth(fresh["access_token"]), "token": fresh["access_token"]}


async def setup_vendor(client, *, email: str, phone: str, shop_name: str,
                      password: str = "Passw0rd123") -> dict:
    """Inscrit + approuve un vendeur, retourne {vendor, headers, token}."""
    payload_over = {"email": email, "phone": phone, "shop_name": shop_name}
    # on réutilise le mot de passe standard pour le re-login
    vendor = await register_vendor(client, **payload_over)
    ctx = await activate(client, vendor, email=email, password=password)
    return {"vendor": vendor, **ctx}


async def create_published_product(client, headers: dict, *, name: str,
                                   price_usd: float | str = "20.00",
                                   stock: int = 50) -> dict:
    """Crée un produit via l'API vendor puis le publie. Retourne le produit."""
    body = {
        "name": name,
        "description": f"{name} — test",
        "short_description": name[:100],
        "price_input": str(price_usd),
        "currency_input": "USD",
        "stock": stock,
        "is_published": False,
    }
    r = await client.post(
        "/api/v1/vendor/products",
        headers=headers,
        data={"data": json.dumps(body)},
    )
    assert r.status_code == 201, r.text
    prod = r.json()
    rp = await client.post(
        f"/api/v1/vendor/products/{prod['id']}/publish", headers=headers
    )
    assert rp.status_code == 200, rp.text
    return prod


async def read_stock(product_id: str) -> tuple[int, int]:
    """Retourne (stock, reserved_stock) du produit, lu directement en base."""
    factory = db_session.get_session_factory()
    async with factory() as s:
        p = await s.get(Product, product_id)
        return (int(p.stock), int(p.reserved_stock)) if p else (None, None)
