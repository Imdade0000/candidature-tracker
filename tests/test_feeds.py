"""Tests sur la normalisation des offres (sans réseau)."""
from app.feeds import _offer_from_entry, _offer_from_json_item, _clean_html


def test_offer_id_is_stable():
    entry = {"title": "Développeur React", "link": "https://exemple.fr/offre-1", "summary": "<p>Poste remote</p>"}
    a = _offer_from_entry(entry, "https://source.example/feed", "fullstack-remote")
    b = _offer_from_entry(entry, "https://source.example/feed", "fullstack-remote")
    assert a["id"] == b["id"]
    assert len(a["id"]) == 12


def test_offer_title_and_html_are_cleaned():
    entry = {"title": "  <b>Dev</b> React  ", "link": "https://exemple.fr/o", "summary": "<p>Remote &amp; flexible</p>"}
    offer = _offer_from_entry(entry, "https://source.example/feed", "")
    assert offer["title"] == "Dev React"
    assert "<" not in offer["description"]


def test_offer_company_fallback_to_host():
    entry = {"title": "Full Stack Developer - Remote at Xperteez Technology", "link": "https://exemple.fr/o"}
    offer = _offer_from_entry(entry, "https://weworkremotely.com/categories/feed.rss", "")
    assert offer["company"] == "Xperteez Technology"


def test_clean_html_strips_entities():
    assert _clean_html("<p>Hello &amp; bye &nbsp; world</p>") == "Hello & bye world"


def test_json_item_maps_remoteok_fields():
    item = {
        "position": "<b>Frontend Engineer</b>",
        "company": "Bjak",
        "location": "",
        "url": "https://remoteok.com/remote-jobs/bjak-frontend-engineer",
        "apply_url": "https://remoteok.com/l/bjak",
        "description": "<p>Remote React position</p>",
        "tags": ["front end", "react", "typescript"],
        "date": 1790172002,
    }
    offer = _offer_from_json_item(item, "https://remoteok.com/api", "fullstack-remote")
    assert offer["title"] == "Frontend Engineer"
    assert offer["company"] == "Bjak"
    assert offer["location"] == ""
    assert offer["url"].startswith("https://remoteok.com")
    assert "react" in offer["description"].lower()
    assert offer["published"] == "2026-09-23"
    assert len(offer["id"]) == 12


def test_json_item_company_falls_back_to_host():
    item = {"position": "Senior Dev", "url": "https://remoteok.com/job/abc"}
    offer = _offer_from_json_item(item, "https://remoteok.com/api", "")
    assert offer["company"] == "remoteok.com"