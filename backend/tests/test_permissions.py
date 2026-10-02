"""Tests du module permissions : seed, vendor owner, staff sans permission,
wildcards de role_templates, dépendance require_permission (403)."""

import pytest

from tests.conftest import VENDOR_PAYLOAD, auth, register_vendor
from tests.helpers import login_as

pytestmark = pytest.mark.asyncio

VENDOR_EMAIL = VENDOR_PAYLOAD["email"]
VENDOR_PASSWORD = VENDOR_PAYLOAD["password"]


async def activate_tenant(client, vendor: dict) -> dict:
    """Approuve le tenant du vendor puis re-login pour rafraîchir les claims.

    Retourne les headers du vendor (JWT frais avec tenant_id + statut actif).
    """
    from tests.helpers import create_superadmin

    await create_superadmin()
    sa = await login_as(client, "root@kimia.cd", "Sup3rAdmin1")
    r = await client.post(
        f"/api/v1/superadmin/tenants/{vendor['tenant_id']}/approve",
        headers=auth(sa["access_token"]),
    )
    assert r.status_code == 200
    fresh = await login_as(client, VENDOR_EMAIL, VENDOR_PASSWORD)
    vendor["access_token"] = fresh["access_token"]
    return auth(fresh["access_token"])


async def make_staff(client, vendor_headers: dict, keys: list[str],
                     email: str = "s1@boutique.cd",
                     phone: str = "+243810000001") -> dict:
    """Crée un staff avec les permissions données (via l'API vendor)."""
    r = await client.post(
        "/api/v1/vendor/staff",
        headers=vendor_headers,
        json={
            "email": email,
            "phone": phone,
            "password": "Staff12345",
            "first_name": "Staf",
            "permissions": keys,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def staff_headers(login_payload: dict) -> dict:
    """Headers Bearer depuis un payload TokenResponse."""
    return auth(login_payload["access_token"])


async def test_vendor_owner_has_all_permissions(client):
    """Le propriétaire vendor dispose de TOUTES les permissions seedées."""
    vendor = await register_vendor(client)
    headers = await activate_tenant(client, vendor)

    r = await client.get("/api/v1/vendor/me/permissions", headers=headers)
    assert r.status_code == 200
    perms = r.json()
    assert "staff.manage" in perms
    assert "products.create" in perms
    assert len(perms) >= 26  # toutes les permissions seedées


async def test_staff_without_permission_gets_403(client):
    """Staff sans permission → 403 sur une route require_permission."""
    vendor = await register_vendor(client)
    vheaders = await activate_tenant(client, vendor)

    staff = await make_staff(client, vheaders, [], "s1@boutique.cd", "+243810000001")
    slogin = await login_as(client, "s1@boutique.cd", "Staff12345")
    sheaders = staff_headers(slogin)

    # Liste vide côté permissions effectives.
    r = await client.get("/api/v1/vendor/me/permissions", headers=sheaders)
    assert r.json() == []

    # Et le staff ne peut pas créer un autre staff (staff.manage requis).
    r = await client.post(
        "/api/v1/vendor/staff",
        headers=sheaders,
        json={"email": "s2@boutique.cd", "phone": "+243810000002",
              "password": "Staff12345", "permissions": []},
    )
    assert r.status_code == 403


async def test_staff_with_permission_succeeds(client):
    """Staff AVEC staff.manage → la même action passe (201)."""
    vendor = await register_vendor(client)
    vheaders = await activate_tenant(client, vendor)

    manager = await make_staff(
        client, vheaders, ["staff.manage", "products.view"],
        "boss@boutique.cd", "+243810000010",
    )
    assert manager["role"] == "staff"
    blogin = await login_as(client, "boss@boutique.cd", "Staff12345")
    bheaders = staff_headers(blogin)

    r = await client.get("/api/v1/vendor/me/permissions", headers=bheaders)
    assert set(r.json()) == {"staff.manage", "products.view"}

    r = await client.post(
        "/api/v1/vendor/staff",
        headers=bheaders,
        json={"email": "s3@boutique.cd", "phone": "+243810000011",
              "password": "Staff12345", "permissions": ["orders.view"]},
    )
    assert r.status_code == 201, r.text


async def test_role_template_wildcard_expansion(client):
    """expand_template_permissions développe 'products.*' en clés concrètes."""
    from app.db import session as db_session
    from app.services.permission_service import expand_template_permissions

    factory = db_session.get_session_factory()
    async with factory() as s:
        expanded = await expand_template_permissions(s, ["products.*", "finances.view"])
    assert {"products.view", "products.create", "products.edit",
            "products.delete", "products.stock", "finances.view"} <= set(expanded)
    assert "orders.view" not in expanded


async def test_role_templates_seeded(client):
    """Les 6 templates système sont présents en base (config-driven)."""
    from sqlalchemy import select

    from app.db import session as db_session
    from app.models.role_template import RoleTemplate

    factory = db_session.get_session_factory()
    async with factory() as s:
        rows = (await s.execute(select(RoleTemplate))).scalars().all()
    keys = {t.key for t in rows}
    assert {"manager", "stock_manager", "order_manager", "accountant",
            "marketing", "support"} <= keys
    manager = next(t for t in rows if t.key == "manager")
    # Le template manager n'inclut PAS staff.manage (règle métier du seed).
    assert "staff.manage" not in manager.permissions


async def test_update_staff_permissions_replaces(client):
    """PUT /vendor/staff/{id}/permissions remplace la liste (isolation incluse)."""
    vendor = await register_vendor(client)
    vheaders = await activate_tenant(client, vendor)

    staff = await make_staff(
        client, vheaders, ["products.view"], "updater@boutique.cd", "+243810000020"
    )
    r = await client.put(
        f"/api/v1/vendor/staff/{staff['id']}/permissions",
        headers=vheaders,
        json=["orders.view", "orders.confirm"],
    )
    assert r.status_code == 200
    assert r.json()["granted"] == 2

    slogin = await login_as(client, "updater@boutique.cd", "Staff12345")
    r = await client.get("/api/v1/vendor/me/permissions",
                         headers=auth(slogin["access_token"]))
    assert sorted(r.json()) == ["orders.confirm", "orders.view"]
