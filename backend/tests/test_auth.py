"""Tests du module auth : inscription, login, refresh (rotation), logout,
vérification téléphone, reset mdp, politique mot de passe, rate limiting."""

import pytest

from tests.conftest import auth, register_customer, register_vendor

pytestmark = pytest.mark.asyncio


async def test_register_vendor_creates_pending_tenant(client):
    """Inscription vendeur → user vendor + tenant en 'pending'."""
    data = await register_vendor(client)
    assert data["role"] == "vendor"
    assert data["tenant_id"] is not None

    # Le tenant créé est bien en attente de validation (règle base seedée).
    me = await client.get("/api/v1/auth/me", headers=auth(data["access_token"]))
    assert me.status_code == 200
    body = me.json()
    assert body["role"] == "vendor"
    assert body["tenant_id"] == data["tenant_id"]
    assert body["is_verified"] is False


async def test_register_customer_no_tenant(client):
    """Inscription client → user créé, JAMAIS de tenant."""
    data = await register_customer(client)
    assert data["role"] == "customer"
    assert data["tenant_id"] is None


async def test_weak_password_rejected(client):
    """Politique mot de passe : trop faible → 422."""
    r = await client.post(
        "/api/v1/auth/register/customer",
        json={"phone": "+243800000001", "password": "short", "accept_cgu": True},
    )
    assert r.status_code == 422

    r2 = await client.post(
        "/api/v1/auth/register/customer",
        json={"phone": "+243800000002", "password": "nouveau_pass_1", "accept_cgu": True},
    )
    assert r2.status_code == 422  # pas de majuscule


async def test_duplicate_email_conflict(client):
    await register_vendor(client)
    r = await client.post(
        "/api/v1/auth/register/customer",
        json={"email": "alice@boutique.cd", "phone": "+243800000003",
              "password": "Other1Pass", "accept_cgu": True},
    )
    assert r.status_code == 409


async def test_login_by_email(client):
    await register_vendor(client)
    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "alice@boutique.cd", "password": "Passw0rd123"},
    )
    assert r.status_code == 200
    assert r.json()["access_token"]
    # Refresh token dans un cookie httpOnly, jamais dans le body.
    assert "kimia_refresh=" in r.headers.get("set-cookie", "")
    assert "HttpOnly" in r.headers["set-cookie"]
    assert "refresh_token" not in r.json()


async def test_login_by_phone(client):
    await register_customer(client)
    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "+243998765432", "password": "Cust0mer123"},
    )
    assert r.status_code == 200


async def test_login_wrong_password(client):
    await register_customer(client)
    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "bob@client.cd", "password": "Wrong1Password"},
    )
    assert r.status_code == 401


async def test_refresh_rotation(client):
    """Refresh → nouvel access + cookie ROTÉ ; l'ancien refresh est mort."""
    await register_customer(client)
    login = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "bob@client.cd", "password": "Cust0mer123"},
    )
    old_cookie = login.headers["set-cookie"]

    ref1 = await client.post("/api/v1/auth/refresh", headers={"Cookie": old_cookie})
    assert ref1.status_code == 200
    new_cookie = ref1.headers["set-cookie"]
    assert new_cookie != old_cookie  # rotation

    # L'ancien token réutilisé doit échouer (session déjà rotée).
    ref_old = await client.post("/api/v1/auth/refresh", headers={"Cookie": old_cookie})
    assert ref_old.status_code == 401

    # Le nouveau fonctionne.
    ref2 = await client.post("/api/v1/auth/refresh", headers={"Cookie": new_cookie})
    assert ref2.status_code == 200


async def test_logout_revokes_session_and_blacklists_token(client):
    await register_customer(client)
    login = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "bob@client.cd", "password": "Cust0mer123"},
    )
    token = login.json()["access_token"]
    cookie = login.headers["set-cookie"]

    out = await client.post(
        "/api/v1/auth/logout", headers={**auth(token), "Cookie": cookie}
    )
    assert out.status_code == 200

    # Access token blackliqué → 401.
    me = await client.get("/api/v1/auth/me", headers=auth(token))
    assert me.status_code == 401

    # Session révoquée → refresh impossible.
    ref = await client.post("/api/v1/auth/refresh", headers={"Cookie": cookie})
    assert ref.status_code == 401


async def test_verify_phone_flow(client):
    """Vérification par lien (stub SMS renvoie debug_link en dev)."""
    await register_customer(client)
    resend = await client.post(
        "/api/v1/auth/resend-verification",
        json={"identifier": "bob@client.cd"},
    )
    assert resend.status_code == 200
    link = resend.json()["debug_link"]
    assert link is not None
    raw_token = link.split("token=")[1]

    v = await client.post("/api/v1/auth/verify-phone", json={"token": raw_token})
    assert v.status_code == 200

    # Token à usage unique → réutilisation refusée.
    v2 = await client.post("/api/v1/auth/verify-phone", json={"token": raw_token})
    assert v2.status_code == 422


async def test_forgot_reset_password_flow(client):
    await register_customer(client)
    forgot = await client.post(
        "/api/v1/auth/forgot-password", json={"identifier": "bob@client.cd"}
    )
    assert forgot.status_code == 200
    link = forgot.json()["debug_link"]
    raw_token = link.split("token=")[1]

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "password": "NewPass123"},
    )
    assert reset.status_code == 200

    # Ancien mdp mort, nouveau valide.
    old = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "bob@client.cd", "password": "Cust0mer123"},
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "bob@client.cd", "password": "NewPass123"},
    )
    assert new.status_code == 200


async def test_me_requires_auth(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_update_preferences(client):
    data = await register_customer(client)
    r = await client.patch(
        "/api/v1/auth/me",
        headers=auth(data["access_token"]),
        json={"currency_display": "CDF", "language": "fr"},
    )
    assert r.status_code == 200
    assert r.json()["currency_display"] == "CDF"


async def test_sessions_list_and_revoke(client):
    data = await register_customer(client)
    lst = await client.get("/api/v1/auth/sessions", headers=auth(data["access_token"]))
    assert lst.status_code == 200
    sessions = lst.json()
    assert len(sessions) >= 1
    sid = sessions[0]["id"]
    rev = await client.delete(f"/api/v1/auth/sessions/{sid}", headers=auth(data["access_token"]))
    assert rev.status_code == 200
    lst2 = await client.get("/api/v1/auth/sessions", headers=auth(data["access_token"]))
    assert all(s["id"] != sid for s in lst2.json())


async def test_rate_limit_login_6th_request_429(client):
    """Rate limiting /login : 5/min (business_rule) → 6e requête → 429.

    X-Test-No-Lockout neutralise le verrou DB pour isoler le middleware.
    """
    headers = {"X-Test-No-Lockout": "1"}
    for i in range(5):
        r = await client.post(
            "/api/v1/auth/login",
            json={"identifier": "nobody@x.cd", "password": "Whatever123"},
            headers=headers,
        )
        assert r.status_code == 401, f"req {i + 1}: {r.status_code}"
    r6 = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "nobody@x.cd", "password": "Whatever123"},
        headers=headers,
    )
    assert r6.status_code == 429


async def test_bruteforce_lockout_db_config_driven(client):
    """Lockout anti-brute-force lu depuis business_rules.login.max_attempts."""
    await register_customer(client)
    for _ in range(5):
        r = await client.post(
            "/api/v1/auth/login",
            json={"identifier": "bob@client.cd", "password": "WrongPass1"},
        )
        assert r.status_code in (401, 429)
    # Même avec un bon mot de passe, le lockout DB frappe avant la limite réseau.
    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "bob@client.cd", "password": "Cust0mer123"},
    )
    assert r.status_code == 429
