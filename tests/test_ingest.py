"""Tests sur l'ingestion et la classification des candidatures."""
from app.ingest import classify_remote, application_to_text, filter_applications, load_applications


def test_classify_remote():
    assert classify_remote("100% télétravail confirmé") == "remote"
    assert classify_remote("100% remote") == "remote"
    assert classify_remote("4 jours sur site, 1 jour télétravail") == "hybride"
    assert classify_remote("100% présentiel") == "présentiel"
    assert classify_remote("3 jours par semaine sur site") == "présentiel"
    assert classify_remote("Non précisé") == "inconnu"
    assert classify_remote("") == "inconnu"


def test_application_to_text_is_plain_text():
    app = load_applications()[0]
    text = application_to_text(app)
    assert "Candidature chez" in text
    assert app["company"] in text
    assert "Stack technique" in text


def test_filter_applications_by_month():
    apps = filter_applications(month="2026-09")
    assert apps
    assert all(a["date"].startswith("2026-09") for a in apps)


def test_filter_applications_by_remote():
    apps = filter_applications(remote="remote")
    assert apps
    assert all(classify_remote(a["remote"]) == "remote" for a in apps)


def test_filter_applications_by_status():
    apps = filter_applications(status="applied")
    assert apps
    assert all(a["status"] == "applied" for a in apps)


def test_filter_applications_by_status_accepts_legacy_label():
    apps = filter_applications(status="candidature envoyée")
    assert {a["id"] for a in apps} == {a["id"] for a in filter_applications(status="applied")}