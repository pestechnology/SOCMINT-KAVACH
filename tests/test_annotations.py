"""
Tests for per-user bookmarks + severity flags (backend/cases/annotations_service.py
and the /cases/{id}/annotations routes).

The stability test is the important one: annotations are keyed on account content, not
entity_id, so they must survive the entity_id churn a re-scrape/pivot causes.
"""
import uuid

from backend.cases.annotations_service import (get_annotations, set_annotation,
                                               target_key_for)


def _make_case_with_entities(client, headers):
    """Create a mock-mode case (completes synchronously) and return (case_id, entity)."""
    r = client.post("/cases", headers=headers,
                    json={"title": "ann-" + uuid.uuid4().hex[:6],
                          "seeds": [{"type": "username", "value": "torvalds"}]})
    assert r.status_code == 200, r.text
    case_id = r.json()["case_id"]
    res = client.get(f"/cases/{case_id}/results", headers=headers)
    assert res.status_code == 200
    entities = res.json()["entities"]
    assert entities, "mock case should produce entities"
    return case_id, entities[0]


def test_set_and_read_bookmark_and_flag(client, auth_headers):
    headers, _ = auth_headers
    case_id, ent = _make_case_with_entities(client, headers)
    eid = ent["entity_id"]

    r = client.put(f"/cases/{case_id}/annotations/{eid}", headers=headers,
                   json={"bookmarked": True, "flag": "red", "note": "prime suspect"})
    assert r.status_code == 200
    assert r.json() == {"bookmarked": True, "flag": "red", "note": "prime suspect"}

    got = client.get(f"/cases/{case_id}/annotations", headers=headers).json()
    assert got["by_entity"][eid]["flag"] == "red"
    assert got["by_entity"][eid]["bookmarked"] is True


def test_partial_update_leaves_other_fields(client, auth_headers):
    headers, _ = auth_headers
    case_id, ent = _make_case_with_entities(client, headers)
    eid = ent["entity_id"]
    client.put(f"/cases/{case_id}/annotations/{eid}", headers=headers,
               json={"bookmarked": True, "flag": "orange"})
    # change only the flag; bookmark must persist
    r = client.put(f"/cases/{case_id}/annotations/{eid}", headers=headers,
                   json={"flag": "yellow"})
    assert r.json() == {"bookmarked": True, "flag": "yellow", "note": ""}


def test_clearing_everything_removes_the_row(client, auth_headers):
    headers, _ = auth_headers
    case_id, ent = _make_case_with_entities(client, headers)
    eid = ent["entity_id"]
    client.put(f"/cases/{case_id}/annotations/{eid}", headers=headers,
               json={"bookmarked": True, "flag": "red"})
    client.put(f"/cases/{case_id}/annotations/{eid}", headers=headers,
               json={"bookmarked": False, "flag": "", "note": ""})
    got = client.get(f"/cases/{case_id}/annotations", headers=headers).json()
    assert eid not in got["by_entity"]


def test_invalid_flag_rejected(client, auth_headers):
    headers, _ = auth_headers
    case_id, ent = _make_case_with_entities(client, headers)
    r = client.put(f"/cases/{case_id}/annotations/{ent['entity_id']}", headers=headers,
                   json={"flag": "purple"})
    assert r.status_code == 422


def test_annotations_require_auth(client):
    assert client.get("/cases/whatever/annotations").status_code == 401
    assert client.put("/cases/whatever/annotations/x", json={"flag": "red"}).status_code == 401


def test_cannot_annotate_another_users_case(client, auth_headers):
    owner_headers, _ = auth_headers
    case_id, ent = _make_case_with_entities(client, owner_headers)

    other = "other_" + uuid.uuid4().hex[:8]
    tok = client.post("/auth/register",
                      json={"username": other, "password": "secret123"}).json()["token"]
    other_headers = {"Authorization": f"Bearer {tok}"}

    assert client.get(f"/cases/{case_id}/annotations", headers=other_headers).status_code == 404
    assert client.put(f"/cases/{case_id}/annotations/{ent['entity_id']}",
                      headers=other_headers, json={"flag": "red"}).status_code == 404


def test_unknown_entity_is_404(client, auth_headers):
    headers, _ = auth_headers
    case_id, _ = _make_case_with_entities(client, headers)
    r = client.put(f"/cases/{case_id}/annotations/nonexistent-id", headers=headers,
                   json={"flag": "red"})
    assert r.status_code == 404


def test_annotation_survives_entity_id_change(client, auth_headers):
    """The core reason annotations are content-keyed: entity_id is a fresh uuid on every
    re-run, so an annotation set now must still resolve after the entity_id changes."""
    from backend.database import get_db
    headers, user = auth_headers
    case_id, ent = _make_case_with_entities(client, headers)
    eid = ent["entity_id"]
    client.put(f"/cases/{case_id}/annotations/{eid}", headers=headers,
               json={"bookmarked": True, "flag": "red"})

    # Simulate a pivot: give this entity a brand-new entity_id (same content).
    new_eid = uuid.uuid4().hex
    conn = get_db()
    try:
        conn.execute("UPDATE entities SET entity_id = ? WHERE entity_id = ?", (new_eid, eid))
        conn.commit()
    finally:
        conn.close()

    got = client.get(f"/cases/{case_id}/annotations", headers=headers).json()
    assert eid not in got["by_entity"]           # old id is gone
    assert got["by_entity"][new_eid]["flag"] == "red"   # annotation re-mapped onto the new id


def test_target_key_is_normalized():
    assert target_key_for("social_account", "GitHub", "TorValds") == \
        target_key_for("social_account", "github", "torvalds")
