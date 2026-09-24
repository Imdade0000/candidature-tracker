"""Tests de la couche /opportunities (lectures + mapping, sans réseau).
Le TestClient est utilisé sans contexte (pas de réindex Chroma au démarrage).
"""
import app.opportunities as opp
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

REQUIRED_FIELDS = {
    "id", "source", "title", "company", "location", "job_type", "description",
    "tags", "url", "published_at", "score", "matched_skills", "missing_skills",
    "flags", "recommendation", "status", "discovered_at",
}


def _first_opportunity():
    res = client.get("/opportunities")
    assert res.status_code == 200
    ops = res.json()
    assert ops, "aucune opportunité dans les données de test"
    return ops[0]


def test_list_sorted_by_score_desc():
    res = client.get("/opportunities")
    assert res.status_code == 200
    ops = res.json()
    assert ops
    scores = [o["score"] for o in ops]
    assert scores == sorted(scores, reverse=True)
    assert all(REQUIRED_FIELDS <= set(o.keys()) for o in ops)
    assert all(0 <= o["score"] <= 100 for o in ops)


def test_first_opportunity_is_built_from_alert():
    first = _first_opportunity()
    assert first["id"]
    assert first["title"]
    assert first["url"].startswith("http")
    assert isinstance(first["matched_skills"], list)
    assert isinstance(first["tags"], list)
    assert first["status"] in {"new", "seen", "applied", "dropped"}


def test_draft_is_readable_and_personalized():
    first = _first_opportunity()
    res = client.post(f"/opportunities/{first['id']}/draft")
    assert res.status_code == 200
    draft = res.json()
    assert draft["subject"]
    assert draft["body"]
    assert first["company"].lower() in draft["body"].lower()
    for skill in first["matched_skills"]:
        assert skill in draft["body"]


def test_status_unknown_id_returns_404():
    res = client.post("/opportunities/introuvable/status",
                      json={"status": "seen"})
    assert res.status_code == 404


def test_status_noop_keeps_value():
    first = _first_opportunity()
    res = client.post(f"/opportunities/{first['id']}/status",
                      json={"status": first["status"]})
    assert res.status_code == 200
    assert res.json()["status"] == first["status"]


def test_status_missing_body_returns_422():
    first = _first_opportunity()
    res = client.post(f"/opportunities/{first['id']}/status", json={})
    assert res.status_code == 422


def test_refresh_mapping_without_network(monkeypatch):
    monkeypatch.setattr(opp, "run_veille",
                        lambda: {"fetched": 7, "alerts_added": 3, "new": 2})
    monkeypatch.setattr(opp, "expire_stale_alerts", lambda: 1)
    monkeypatch.setattr(opp, "rescore_alerts", lambda: 2)
    assert opp.refresh_opportunities() == {
        "fetched": 7, "above_threshold": 3, "added": 2,
        "expired": 1, "filtered": 2,
    }