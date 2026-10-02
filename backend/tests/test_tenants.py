"""Tests du module superadmin/tenants : file d'attente, validation,
rejet, suspension, réactivation, modification plan/commission, RBAC."""

import pytest

from tests.conftest import auth, register_vendor
from tests.helpers import create_superadmin, login_as

pytestmark = pytest.mark.asyncio

SA_EMAIL = "root@kimia.cd"
SA_PASSWORD = "Sup3rAdmin1"


async def sa_headers(client):
    """Crée le superadmin (idempotent) et retourne ses headers d'auth."""
    await create_superadmin(SA_EMAIL, SA_PASSWORD)
    data = await login_as(client, SA_EMAIL, SA_PASSWORD)
    return auth(data["access_token"])


async def test_pending_queue_lists_new_vendor(client):
    """Inscription vendeur → visible dans GET /superadmin/tenants/pending."""
    vendor = await register_vendor(client)
    headers = await sa_headers(client)

    r = await client.get("/api/v1/superadmin/tenants/pending", headers=headers)
    assert r.status_code == 200
    page = r.json()
    ids = [t["id"] for t in page["items"]]
    assert vendor["tenant_id"] in ids
    assert page["items"][0]["status"] == "pending"


async def test_approve_reject_flow(client):
    """pending → active (approve), puis suspend → reactivate."""
    vendor = await register_vendor(client)
    tid = vendor["tenant_id"]
    headers = await sa_headers(client)

    r = await client.post(f"/api/v1/superadmin/tenants/{tid}/approve", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    r = await client.post(
        f"/api/v1/superadmin/tenants/{tid}/suspend",
        json={"reason": "impayé"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "suspended"

    r = await client.post(
        f"/api/v1/superadmin/tenants/{tid}/reactivate", headers=headers
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"


async def test_reject_with_reason(client):
    """Rejet avec raison : statut rejected + raison enregistrée."""
    vendor = await register_vendor(client, email="carol@boutique.cd",
                                   phone="+243811112233", shop_name="Boutique Carol")
    tid = vendor["tenant_id"]
    headers = await sa_headers(client)

    r = await client.post(
        f"/api/v1/superadmin/tenants/{tid}/reject",
        json={"reason": "documents manquants"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    detail = await client.get(f"/api/v1/superadmin/tenants/{tid}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["rejection_reason"] == "documents manquants"


async def test_update_plan_and_commission(client):
    """PATCH superadmin : changement de plan + commission_rate."""
    vendor = await register_vendor(client, email="dave@boutique.cd",
                                   phone="+243811112244", shop_name="Boutique Dave")
    tid = vendor["tenant_id"]
    headers = await sa_headers(client)

    r = await client.patch(
        f"/api/v1/superadmin/tenants/{tid}",
        json={"plan_name": "pro", "commission_rate": 0.02},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["plan_name"] == "pro"
    assert float(body["commission_rate"]) == 0.02


async def test_list_filters_status_plan_search(client):
    """GET liste : filtres status, plan et recherche nom/slug."""
    vendor = await register_vendor(client, email="erin@boutique.cd",
                                   phone="+243811112255", shop_name="Erin Shop")
    headers = await sa_headers(client)
    tid = vendor["tenant_id"]
    await client.post(f"/api/v1/superadmin/tenants/{tid}/approve", headers=headers)
    await client.patch(f"/api/v1/superadmin/tenants/{tid}",
                       json={"plan_name": "business"}, headers=headers)

    r = await client.get("/api/v1/superadmin/tenants?status=active&plan=business",
                         headers=headers)
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["items"]]
    assert tid in ids

    r = await client.get("/api/v1/superadmin/tenants?search=Erin", headers=headers)
    assert r.json()["total"] >= 1

    r = await client.get("/api/v1/superadmin/tenants?status=pending", headers=headers)
    assert tid not in [t["id"] for t in r.json()["items"]]


async def test_non_superadmin_forbidden(client):
    """Un vendor ou un customer n'a PAS accès aux endpoints superadmin."""
    await sa_headers(client)
    vendor = await register_vendor(client, email="frank@boutique.cd",
                                   phone="+243811112266", shop_name="Boutique Frank")
    r = await client.get("/api/v1/superadmin/tenants",
                         headers=auth(vendor["access_token"]))
    assert r.status_code == 403

    from tests.conftest import register_customer

    cust = await register_customer(client, email="gina@client.cd",
                                   phone="+243998765000")
    r = await client.get("/api/v1/superadmin/tenants",
                         headers=auth(cust["access_token"]))
    assert r.status_code == 403


async def test_anonymous_unauthorized(client):
    """Sans token → 401 sur la liste des tenants."""
    r = await client.get("/api/v1/superadmin/tenants")
    assert r.status_code == 401


async def test_audit_log_written_on_approve(client):
    """Les actions superadmin sont tracées dans audit_logs (vérifié via DB)."""
    from sqlalchemy import select

    from app.db import session as db_session
    from app.models.audit_log import AuditLog

    vendor = await register_vendor(client, email="henry@boutique.cd",
                                   phone="+243811112277", shop_name="Boutique Henry")
    headers = await sa_headers(client)
    r = await client.post(
        f"/api/v1/superadmin/tenants/{vendor['tenant_id']}/approve", headers=headers
    )
    assert r.status_code == 200

    factory = db_session.get_session_factory()
    async with factory() as s:
        rows = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.action == "tenant.approve",
                    AuditLog.target_id == vendor["tenant_id"],
                )
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor_role == "superadmin"
    assert rows[0].after == {"status": "active"}
