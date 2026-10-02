"""Tests d'ISOLATION MULTI-TENANT — la règle absolue du projet.

Un vendor A ne doit JAMAIS pouvoir lire ou toucher les données du vendor B :
- tenant_id est déduit du JWT, jamais du body ;
- toutes les requêtes CRUD sont filtrées par le tenant du token ;
- un staff du tenant A ne peut pas modifier les permissions d'un user du
  tenant B (404, pas de fuite d'existence) ;
- un tenant suspendu perd immédiatement l'accès à /vendor/* (403).
"""

import pytest

from tests.conftest import VENDOR_PAYLOAD, auth, register_vendor
from tests.helpers import create_superadmin, login_as

pytestmark = pytest.mark.asyncio


async def activate(client, vendor: dict) -> dict:
    """Approuve le tenant du vendor et retourne ses headers frais."""
    await create_superadmin()
    sa = await login_as(client, "root@kimia.cd", "Sup3rAdmin1")
    r = await client.post(
        f"/api/v1/superadmin/tenants/{vendor['tenant_id']}/approve",
        headers=auth(sa["access_token"]),
    )
    assert r.status_code == 200
    fresh = await login_as(client, vendor_payload_email(vendor), VENDOR_PAYLOAD["password"])
    return {"headers": auth(fresh["access_token"]), "token": fresh["access_token"]}


def vendor_payload_email(vendor: dict) -> str:
    return vendor.get("email", VENDOR_PAYLOAD["email"])


async def register_second_vendor(client):
    """Inscrit un second vendeur (tenant B) avec email/téléphone uniques."""
    return await register_vendor(
        client,
        email="carol@boutique.cd",
        phone="+243820000999",
        shop_name="Boutique Carol",
    )


async def test_staff_creation_uses_jwt_tenant_not_body(client):
    """Même si le body contient un tenant_id, le staff est rattaché au tenant du JWT."""
    vendor_a = await register_vendor(client)
    ctx_a = await activate(client, vendor_a)

    r = await client.post(
        "/api/v1/vendor/staff",
        headers=ctx_a["headers"],
        json={
            "email": "staffa@boutique.cd",
            "phone": "+243810000777",
            "password": "Staff12345",
            "first_name": "S",
            # tentative d'injection : le tenant_id du body DOIT être ignoré
            "tenant_id": "00000000-0000-0000-0000-000000000000",
            "permissions": ["orders.view"],
        },
    )
    # Le schéma Pydantic strict rejette tout champ inconnu → 422 ;
    # s'il passait, on vérifie ci-dessous que le rattachement vient du JWT.
    if r.status_code == 422:
        r = await client.post(
            "/api/v1/vendor/staff",
            headers=ctx_a["headers"],
            json={
                "email": "staffa@boutique.cd",
                "phone": "+243810000777",
                "password": "Staff12345",
                "first_name": "S",
                "permissions": ["orders.view"],
            },
        )
    assert r.status_code == 201, r.text
    staff = r.json()
    assert staff["tenant_id"] == vendor_a["tenant_id"]


async def test_vendor_cannot_see_other_tenant_staff(client):
    """Vendor B (activé) ne voit pas le staff du tenant A via l'API."""
    vendor_a = await register_vendor(client)
    ctx_a = await activate(client, vendor_a)
    r = await client.post(
        "/api/v1/vendor/staff",
        headers=ctx_a["headers"],
        json={
            "email": "secret@boutique.cd",
            "phone": "+243810000888",
            "password": "Staff12345",
            "permissions": [],
        },
    )
    assert r.status_code == 201, r.text
    staff_a = r.json()

    vendor_b = await register_second_vendor(client)
    ctx_b = await activate(client, vendor_b)

    # La liste du staff de B ne contient pas le staff de A.
    r = await client.get("/api/v1/vendor/staff", headers=ctx_b["headers"])
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()]
    assert staff_a["id"] not in ids

    # L'accès direct par id au staff de A → 404 (pas de fuite d'existence).
    r = await client.get(
        f"/api/v1/vendor/staff/{staff_a['id']}", headers=ctx_b["headers"]
    )
    assert r.status_code == 404


async def test_suspended_tenant_blocked_from_vendor_api(client):
    """Tenant suspendu → 403 code tenant_not_active sur /vendor/*."""
    vendor = await register_vendor(client)
    ctx = await activate(client, vendor)

    await create_superadmin()
    sa = await login_as(client, "root@kimia.cd", "Sup3rAdmin1")
    r = await client.post(
        f"/api/v1/superadmin/tenants/{vendor['tenant_id']}/suspend",
        headers=auth(sa["access_token"]),
        json={"reason": "Impayé"},
    )
    assert r.status_code == 200

    r = await client.get("/api/v1/vendor/staff", headers=ctx["headers"])
    assert r.status_code == 403
    assert r.json().get("code") == "tenant_not_active"


async def test_customer_has_no_vendor_access(client):
    """Un client (sans tenant) ne peut pas atteindre /vendor/* → 403/401."""
    from tests.conftest import register_customer

    cust = await register_customer(client)
    headers = auth(cust["access_token"])
    r = await client.get("/api/v1/vendor/staff", headers=headers)
    assert r.status_code in (401, 403)
