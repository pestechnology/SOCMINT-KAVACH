"""
Tests for case collections (named folders/watchlists) — backend/cases/collections_*.

The cross-user isolation tests are the important ones: a case must never leak into
another investigator's collection, and one user's collections must be invisible to
another.
"""
import uuid


def _new_case(client, headers, title="col-case"):
    r = client.post("/cases", headers=headers,
                    json={"title": title + "-" + uuid.uuid4().hex[:6],
                          "seeds": [{"type": "username", "value": "torvalds"}]})
    assert r.status_code == 200, r.text
    return r.json()["case_id"]


def _mk_user(client):
    u = "col_" + uuid.uuid4().hex[:8]
    tok = client.post("/auth/register",
                      json={"username": u, "password": "secret123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_create_list_and_delete_collection(client, auth_headers):
    headers, _ = auth_headers
    r = client.post("/collections", headers=headers, json={"name": "Priority", "color": "#ff3366"})
    assert r.status_code == 200
    cid = r.json()["collection_id"]

    got = client.get("/collections", headers=headers).json()
    assert any(c["collection_id"] == cid and c["name"] == "Priority"
               for c in got["collections"])

    assert client.delete(f"/collections/{cid}", headers=headers).status_code == 200
    got2 = client.get("/collections", headers=headers).json()
    assert all(c["collection_id"] != cid for c in got2["collections"])


def test_duplicate_name_returns_existing(client, auth_headers):
    headers, _ = auth_headers
    name = "Dupes-" + uuid.uuid4().hex[:6]
    a = client.post("/collections", headers=headers, json={"name": name}).json()
    b = client.post("/collections", headers=headers, json={"name": name}).json()
    assert a["collection_id"] == b["collection_id"]


def test_blank_name_rejected(client, auth_headers):
    headers, _ = auth_headers
    assert client.post("/collections", headers=headers, json={"name": "   "}).status_code == 422


def test_file_case_into_collections_and_count(client, auth_headers):
    headers, _ = auth_headers
    case_id = _new_case(client, headers)
    c1 = client.post("/collections", headers=headers, json={"name": "A-" + uuid.uuid4().hex[:5]}).json()
    c2 = client.post("/collections", headers=headers, json={"name": "B-" + uuid.uuid4().hex[:5]}).json()

    r = client.put(f"/cases/{case_id}/collections", headers=headers,
                   json={"collection_ids": [c1["collection_id"], c2["collection_id"]]})
    assert r.status_code == 200
    assert set(r.json()["collection_ids"]) == {c1["collection_id"], c2["collection_id"]}

    got = client.get("/collections", headers=headers).json()
    assert set(got["memberships"][case_id]) == {c1["collection_id"], c2["collection_id"]}
    counts = {c["collection_id"]: c["case_count"] for c in got["collections"]}
    assert counts[c1["collection_id"]] == 1 and counts[c2["collection_id"]] == 1


def test_set_collections_replaces_not_appends(client, auth_headers):
    headers, _ = auth_headers
    case_id = _new_case(client, headers)
    c1 = client.post("/collections", headers=headers, json={"name": "X-" + uuid.uuid4().hex[:5]}).json()
    c2 = client.post("/collections", headers=headers, json={"name": "Y-" + uuid.uuid4().hex[:5]}).json()
    client.put(f"/cases/{case_id}/collections", headers=headers,
               json={"collection_ids": [c1["collection_id"]]})
    client.put(f"/cases/{case_id}/collections", headers=headers,
               json={"collection_ids": [c2["collection_id"]]})   # replace
    got = client.get("/collections", headers=headers).json()
    assert got["memberships"].get(case_id) == [c2["collection_id"]]


def test_clearing_collections_empties_membership(client, auth_headers):
    headers, _ = auth_headers
    case_id = _new_case(client, headers)
    c1 = client.post("/collections", headers=headers, json={"name": "Z-" + uuid.uuid4().hex[:5]}).json()
    client.put(f"/cases/{case_id}/collections", headers=headers,
               json={"collection_ids": [c1["collection_id"]]})
    client.put(f"/cases/{case_id}/collections", headers=headers, json={"collection_ids": []})
    got = client.get("/collections", headers=headers).json()
    assert case_id not in got["memberships"]


def test_collections_require_auth(client):
    assert client.get("/collections").status_code == 401
    assert client.post("/collections", json={"name": "x"}).status_code == 401


def test_cannot_file_case_into_another_users_collection(client, auth_headers):
    owner_headers, _ = auth_headers
    case_id = _new_case(client, owner_headers)
    other_headers = _mk_user(client)
    other_col = client.post("/collections", headers=other_headers,
                            json={"name": "theirs-" + uuid.uuid4().hex[:5]}).json()
    # owner tries to file THEIR case into ANOTHER user's collection -> silently ignored
    r = client.put(f"/cases/{case_id}/collections", headers=owner_headers,
                   json={"collection_ids": [other_col["collection_id"]]})
    assert r.status_code == 200
    assert r.json()["collection_ids"] == []          # not accepted


def test_cannot_touch_another_users_case(client, auth_headers):
    owner_headers, _ = auth_headers
    case_id = _new_case(client, owner_headers)
    other_headers = _mk_user(client)
    col = client.post("/collections", headers=other_headers,
                      json={"name": "mine-" + uuid.uuid4().hex[:5]}).json()
    r = client.put(f"/cases/{case_id}/collections", headers=other_headers,
                   json={"collection_ids": [col["collection_id"]]})
    assert r.status_code == 404                       # not their case


def test_another_users_collections_are_invisible(client, auth_headers):
    headers, _ = auth_headers
    mine = client.post("/collections", headers=headers,
                       json={"name": "private-" + uuid.uuid4().hex[:5]}).json()
    other_headers = _mk_user(client)
    got = client.get("/collections", headers=other_headers).json()
    assert all(c["collection_id"] != mine["collection_id"] for c in got["collections"])
