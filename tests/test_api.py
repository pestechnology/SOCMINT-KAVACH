"""Integration / E2E / security tests for the HTTP API (auth, cases, access control)."""
import uuid


# ---- E2E auth flow ----
def test_register_login_me(client):
    u = "e2e_" + uuid.uuid4().hex[:8]
    r = client.post("/auth/register", json={"username": u, "password": "secret123"})
    assert r.status_code == 200
    tok = r.json()["token"]
    r2 = client.post("/auth/login", json={"username": u, "password": "secret123"})
    assert r2.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


# ---- security: auth required ----
def test_protected_routes_require_auth(client):
    assert client.get("/cases").status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.post("/cases", json={"title": "x", "seeds": []}).status_code == 401


def test_bad_token_rejected(client):
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "not-bearer"}).status_code == 401


def test_wrong_password(client):
    u = "wp_" + uuid.uuid4().hex[:8]
    client.post("/auth/register", json={"username": u, "password": "secret123"})
    assert client.post("/auth/login", json={"username": u, "password": "WRONG"}).status_code == 401


# ---- security: access control (privilege isolation) ----
def test_user_cannot_access_others_case(client):
    a = client.post("/auth/register", json={"username": "iso_a_" + uuid.uuid4().hex[:6], "password": "secret123"}).json()
    b = client.post("/auth/register", json={"username": "iso_b_" + uuid.uuid4().hex[:6], "password": "secret123"}).json()
    ha = {"Authorization": f"Bearer {a['token']}"}
    hb = {"Authorization": f"Bearer {b['token']}"}
    cid = client.post("/cases", json={"title": "secret", "seeds": [{"type": "username", "value": "x"}]}, headers=ha).json()["case_id"]
    assert client.get(f"/cases/{cid}", headers=ha).status_code == 200
    assert client.get(f"/cases/{cid}", headers=hb).status_code == 404
    assert client.get(f"/cases/{cid}/results", headers=hb).status_code == 404
    assert client.get(f"/cases/{cid}/report", headers=hb).status_code == 404


# ---- validation / boundary ----
def test_invalid_seed_type_rejected(client, auth_headers):
    headers, _ = auth_headers
    r = client.post("/cases", json={"title": "x", "seeds": [{"type": "telepathy", "value": "z"}]}, headers=headers)
    assert r.status_code == 400


def test_short_password_rejected(client):
    r = client.post("/auth/register", json={"username": "shortpw_" + uuid.uuid4().hex[:6], "password": "12"})
    assert r.status_code == 409 or r.status_code == 400  # ValueError -> 409 handler


def test_duplicate_username_rejected(client):
    u = "dup_" + uuid.uuid4().hex[:6]
    assert client.post("/auth/register", json={"username": u, "password": "secret123"}).status_code == 200
    assert client.post("/auth/register", json={"username": u, "password": "secret123"}).status_code == 409


# ---- security: SQL injection attempts must not break auth or leak ----
def test_sql_injection_login(client):
    # classic payloads — parameterized queries must treat these as literal strings
    for payload in ("admin' OR '1'='1", "'; DROP TABLE users;--", "' UNION SELECT * FROM users--"):
        r = client.post("/auth/login", json={"username": payload, "password": payload})
        assert r.status_code == 401  # no bypass, no 500


def test_users_table_survives_injection(client):
    # after the DROP attempt above, registration still works => table intact
    u = "intact_" + uuid.uuid4().hex[:6]
    assert client.post("/auth/register", json={"username": u, "password": "secret123"}).status_code == 200
