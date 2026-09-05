"""
Tests for case-level triage priority flags — backend/cases/case_service.set_priority
+ the PUT /cases/{id}/flag route.

Distinct from test_annotations.py: that covers PER-ACCOUNT red/orange/yellow flags
inside one case's results; this covers the red/orange/green flag on the CASE itself,
used to bucket/filter the case list ("show me every red-flagged case").
"""
import uuid


def _new_case(client, headers, title="prio-case"):
    r = client.post("/cases", headers=headers,
                    json={"title": title + "-" + uuid.uuid4().hex[:6],
                          "seeds": [{"type": "username", "value": "torvalds"}]})
    assert r.status_code == 200, r.text
    return r.json()["case_id"]


def _mk_user(client):
    u = "prio_" + uuid.uuid4().hex[:8]
    tok = client.post("/auth/register",
                      json={"username": u, "password": "secret123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_new_case_has_no_priority_by_default(client, auth_headers):
    headers, _ = auth_headers
    case_id = _new_case(client, headers)
    r = client.get(f"/cases/{case_id}", headers=headers)
    assert r.json()["priority_flag"] == ""


def test_set_and_read_back_priority(client, auth_headers):
    headers, _ = auth_headers
    case_id = _new_case(client, headers)

    r = client.put(f"/cases/{case_id}/flag", headers=headers, json={"flag": "red"})
    assert r.status_code == 200
    assert r.json() == {"priority_flag": "red"}

    assert client.get(f"/cases/{case_id}", headers=headers).json()["priority_flag"] == "red"
    mine = [c for c in client.get("/cases", headers=headers).json()["cases"]
            if c["case_id"] == case_id][0]
    assert mine["priority_flag"] == "red"


def test_priority_can_be_changed_and_cleared(client, auth_headers):
    headers, _ = auth_headers
    case_id = _new_case(client, headers)
    client.put(f"/cases/{case_id}/flag", headers=headers, json={"flag": "orange"})
    assert client.get(f"/cases/{case_id}", headers=headers).json()["priority_flag"] == "orange"

    client.put(f"/cases/{case_id}/flag", headers=headers, json={"flag": "green"})
    assert client.get(f"/cases/{case_id}", headers=headers).json()["priority_flag"] == "green"

    client.put(f"/cases/{case_id}/flag", headers=headers, json={"flag": ""})
    assert client.get(f"/cases/{case_id}", headers=headers).json()["priority_flag"] == ""


def test_invalid_flag_rejected(client, auth_headers):
    headers, _ = auth_headers
    case_id = _new_case(client, headers)
    r = client.put(f"/cases/{case_id}/flag", headers=headers, json={"flag": "purple"})
    assert r.status_code == 422
    # untouched by the rejected write
    assert client.get(f"/cases/{case_id}", headers=headers).json()["priority_flag"] == ""


def test_flag_requires_auth(client, auth_headers):
    headers, _ = auth_headers
    case_id = _new_case(client, headers)
    assert client.put(f"/cases/{case_id}/flag", json={"flag": "red"}).status_code == 401


def test_cannot_flag_another_users_case(client, auth_headers):
    owner_headers, _ = auth_headers
    case_id = _new_case(client, owner_headers)
    other_headers = _mk_user(client)
    r = client.put(f"/cases/{case_id}/flag", headers=other_headers, json={"flag": "red"})
    assert r.status_code == 404
    # owner's case is unaffected
    assert client.get(f"/cases/{case_id}", headers=owner_headers).json()["priority_flag"] == ""


def test_flag_on_nonexistent_case(client, auth_headers):
    headers, _ = auth_headers
    r = client.put(f"/cases/{uuid.uuid4().hex}/flag", headers=headers, json={"flag": "red"})
    assert r.status_code == 404
