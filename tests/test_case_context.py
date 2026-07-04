"""Tests for the case-context guidance layer:
   - le_directory: platform → LE data-request contact resolution
   - next_actions: context playbook + legal_request seeding + digest inclusion
All deterministic paths only (no LLM, no DB)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.analysis.le_directory import data_request_contacts, lookup
from backend.analysis.next_actions import _build_digest, deterministic_actions

ENTITIES = [
    {"entity_id": "e1", "type": "social_account", "platform": "telegram",
     "value": "fraudster_tg", "source_url": "https://t.me/fraudster_tg", "metadata": {}},
    {"entity_id": "e2", "type": "social_account", "platform": "instagram",
     "value": "fraudster_ig", "source_url": "https://instagram.com/fraudster_ig",
     "metadata": {"email": "leak@example.com"}},
    {"entity_id": "e3", "type": "social_account", "platform": "snapchat",
     "value": "fraud_snap", "source_url": "", "metadata": {}},
]
CLUSTERS = [
    {"cluster_id": "c1", "entity_ids": ["e1", "e2"], "tier": "HIGH",
     "match": {"tier": "HIGH", "score": 95}},
    {"cluster_id": "c2", "entity_ids": ["e3"], "tier": "MEDIUM",
     "match": {"tier": "MEDIUM", "score": 60}},
]
CASE = {"case_id": "t1", "case_context": "investment fraud through telegram",
        "seeds": [{"type": "username", "value": "fraudster_tg"}],
        "country_filter": "INDIA"}


def test_directory_resolves_found_platforms_and_appends_i4c():
    contacts = data_request_contacts(ENTITIES, CLUSTERS)
    keys = [c["platform"] for c in contacts]
    assert "telegram" in keys and "meta" in keys and "snapchat" in keys
    assert keys[-1] == "i4c"  # India channel always present, always last
    tg = next(c for c in contacts if c["platform"] == "telegram")
    assert tg["accounts"] == ["telegram/fraudster_tg"]
    assert tg["portal"].startswith("https://")


def test_directory_alias_and_unknown():
    assert lookup("instagram")["platform"] == "meta"
    assert lookup("YouTube")["platform"] == "google"
    assert lookup("unknown_platform_xyz") is None


def test_directory_never_raises_on_junk():
    assert data_request_contacts(None, None)[-1]["platform"] == "i4c"
    assert data_request_contacts([], [])[-1]["platform"] == "i4c"


def test_context_playbook_fires_and_legal_request_prefers_context_platform():
    acts = deterministic_actions(CASE, ENTITIES, CLUSTERS)
    tags = [a["action"] for a in acts]
    assert "records_search" in tags  # NCRP financial-fraud playbook
    lr = [a for a in acts if a["action"] == "legal_request"]
    assert lr, tags
    # context says "telegram" and a telegram account exists → that platform, HIGH priority
    assert "Telegram" in lr[0]["title"]
    assert lr[0]["priority"] == "high"


def test_no_context_no_playbook_and_medium_legal_request():
    case = {"case_id": "t2", "case_context": "", "seeds": CASE["seeds"]}
    acts = deterministic_actions(case, ENTITIES, CLUSTERS)
    assert "NCRP" not in " ".join(a["title"] for a in acts)
    lr = [a for a in acts if a["action"] == "legal_request"]
    assert lr and lr[0]["priority"] == "medium"


def test_digest_carries_case_context():
    acts = deterministic_actions(CASE, ENTITIES, CLUSTERS)
    digest = _build_digest(CASE, ENTITIES, CLUSTERS, acts)
    assert "CASE CONTEXT" in digest
    assert "investment fraud through telegram" in digest


def test_digest_omits_context_line_when_blank():
    case = {"case_id": "t3", "case_context": "   ", "seeds": CASE["seeds"]}
    digest = _build_digest(case, ENTITIES, CLUSTERS, [])
    assert "CASE CONTEXT" not in digest
