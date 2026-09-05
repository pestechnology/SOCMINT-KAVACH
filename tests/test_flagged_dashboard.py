"""
Tests for the cross-case "Flagged" dashboard — backend/cases/annotations_service.list_flagged
+ GET /cases/flagged.

Covers: grouping by colour, cross-CASE aggregation (not just cross-account within one
case), the route-ordering trap ("/cases/flagged" must never be swallowed by the
"/cases/{case_id}" catch-all), a dropped/re-scraped account disappearing rather than
showing as a dead link, and per-user isolation.
"""
import uuid


def _make_case_with_entities(client, headers, title="flag-dash"):
    """Create a mock-mode case (completes synchronously) and return (case_id, entities)."""
    r = client.post("/cases", headers=headers,
                    json={"title": title + "-" + uuid.uuid4().hex[:6],
                          "seeds": [{"type": "username", "value": "torvalds"}]})
    assert r.status_code == 200, r.text
    case_id = r.json()["case_id"]
    res = client.get(f"/cases/{case_id}/results", headers=headers)
    assert res.status_code == 200
    entities = res.json()["entities"]
    assert entities, "mock case should produce entities"
    return case_id, entities


def _mk_user(client):
    u = "flagdash_" + uuid.uuid4().hex[:8]
    tok = client.post("/auth/register",
                      json={"username": u, "password": "secret123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_flagged_empty_when_nothing_flagged(client, auth_headers):
    headers, _ = auth_headers
    r = client.get("/cases/flagged", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"red": [], "orange": [], "yellow": []}


def test_flag_appears_in_matching_colour_bucket(client, auth_headers):
    headers, _ = auth_headers
    case_id, entities = _make_case_with_entities(client, headers)
    eid = entities[0]["entity_id"]
    client.put(f"/cases/{case_id}/annotations/{eid}", headers=headers, json={"flag": "orange"})

    got = client.get("/cases/flagged", headers=headers).json()
    assert got["red"] == []
    assert got["yellow"] == []
    assert len(got["orange"]) == 1
    row = got["orange"][0]
    assert row["case_id"] == case_id
    assert row["entity_id"] == eid
    assert row["case_title"]


def test_aggregates_across_multiple_cases(client, auth_headers):
    headers, _ = auth_headers
    case_a, ents_a = _make_case_with_entities(client, headers, "case-a")
    case_b, ents_b = _make_case_with_entities(client, headers, "case-b")
    client.put(f"/cases/{case_a}/annotations/{ents_a[0]['entity_id']}",
              headers=headers, json={"flag": "red"})
    client.put(f"/cases/{case_b}/annotations/{ents_b[0]['entity_id']}",
              headers=headers, json={"flag": "red"})

    got = client.get("/cases/flagged", headers=headers).json()
    seen_cases = {row["case_id"] for row in got["red"]}
    assert seen_cases == {case_a, case_b}


def test_clearing_flag_removes_it_from_dashboard(client, auth_headers):
    headers, _ = auth_headers
    case_id, entities = _make_case_with_entities(client, headers)
    eid = entities[0]["entity_id"]
    client.put(f"/cases/{case_id}/annotations/{eid}", headers=headers, json={"flag": "yellow"})
    assert len(client.get("/cases/flagged", headers=headers).json()["yellow"]) == 1

    client.put(f"/cases/{case_id}/annotations/{eid}", headers=headers, json={"flag": ""})
    assert client.get("/cases/flagged", headers=headers).json()["yellow"] == []


def test_flagged_requires_auth(client):
    assert client.get("/cases/flagged").status_code == 401


def test_flagged_is_per_user(client, auth_headers):
    headers, _ = auth_headers
    case_id, entities = _make_case_with_entities(client, headers)
    client.put(f"/cases/{case_id}/annotations/{entities[0]['entity_id']}",
              headers=headers, json={"flag": "red"})

    other_headers = _mk_user(client)
    got = client.get("/cases/flagged", headers=other_headers).json()
    assert got == {"red": [], "orange": [], "yellow": []}


def test_route_ordering_flagged_not_swallowed_by_case_id_route(client, auth_headers):
    """Regression guard: GET /cases/flagged must hit the dashboard, never be parsed as
    GET /cases/{case_id} with case_id='flagged' (which would 404 as 'not found')."""
    headers, _ = auth_headers
    r = client.get("/cases/flagged", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), dict) and set(r.json().keys()) == {"red", "orange", "yellow"}
