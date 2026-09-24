"""Tests des endpoints de l'API via le TestClient FastAPI.

Les tests n'écrivent rien : ils ne vérifient que des lectures.
Le TestClient est utilisé sans contexte pour éviter de réindexer Chroma
à chaque exécution (les routes testées ne dépendent pas de l'index).
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_list_applications():
    res = client.get("/applications")
    assert res.status_code == 200
    apps = res.json()
    assert isinstance(apps, list)
    assert len(apps) >= 10


def test_application_filters():
    assert client.get("/applications?month=2026-09").status_code == 200
    assert client.get("/applications?remote=remote").status_code == 200


def test_stats_endpoint():
    res = client.get("/stats")
    assert res.status_code == 200
    assert res.json()["total"] > 0


def test_feeds_list():
    res = client.get("/feeds")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_alerts_list():
    res = client.get("/alerts")
    assert res.status_code == 200
    alerts = res.json()
    assert isinstance(alerts, list)
    assert all(a["status"] in {"new", "seen", "applied", "dropped"} for a in alerts)