"""Collecte d'offres d'emploi depuis des flux RSS/Atom.

Les offres brutes sont stockées dans data/offers.json, séparées des
candidatures. Chaque flux est décrit dans data/feeds.json (url + catégorie
facultative). Le rafraîchissement déduplique les offres par URL, puis met les
nouvelles en tête de file — c'est elles que la phase d'alerte (scoring)
examinera.
"""
import hashlib
import html
import json
import re
import time
import urllib.request
from typing import Dict, List, Optional
from urllib.parse import urlparse

import feedparser

from app.config import FEEDS_PATH, OFFERS_PATH

_MAX_OFFERS = 500


class FeedError(Exception):
    pass


def load_feeds() -> List[Dict]:
    if not FEEDS_PATH.exists():
        return []
    with open(FEEDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_feeds(feeds: List[Dict]) -> None:
    with open(FEEDS_PATH, "w", encoding="utf-8") as f:
        json.dump(feeds, f, ensure_ascii=False, indent=2)


def add_feed(url: str, category: str = "") -> Dict:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise FeedError("URL invalide : attendu http(s)://")
    feeds = load_feeds()
    if any(f["url"] == url for f in feeds):
        raise FeedError("Ce flux est déjà suivi.")
    feed = {"url": url, "category": category.strip()}
    feeds.append(feed)
    save_feeds(feeds)
    return feed


def delete_feed(url: str) -> bool:
    feeds = load_feeds()
    remaining = [f for f in feeds if f["url"] != url]
    if len(remaining) == len(feeds):
        return False
    save_feeds(remaining)
    return True


def load_offers() -> List[Dict]:
    if not OFFERS_PATH.exists():
        return []
    with open(OFFERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_offers(offers: List[Dict]) -> None:
    with open(OFFERS_PATH, "w", encoding="utf-8") as f:
        json.dump(offers, f, ensure_ascii=False, indent=2)


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _company_from_entry(entry: Dict, source: str) -> str:
    """Tente d'extraire l'entreprise : auteur du flux, mention 'at Company',
    préfixe 'Company: Poste' ou 'Company - Poste' dans le titre, sinon l'hôte."""
    author = _clean_html(entry.get("author", "")).strip()
    if author:
        return author
    title = _clean_html(entry.get("title", "")).strip()
    match = re.search(r"\bat\s+([A-Za-z0-9][A-Za-z0-9 .&\-]{1,60})$", title)
    if match:
        return match.group(1).strip()
    for sep in (":", " - "):
        if sep in title:
            prefix = title.split(sep, 1)[0].strip()
            if 2 <= len(prefix) <= 60:
                return prefix
    host = urlparse(source).netloc.replace("www.", "")
    return host or source


def _offer_from_entry(entry: Dict, source: str, category: str) -> Dict:
    title = _clean_html(entry.get("title", "")).strip()
    url = (entry.get("link") or "").strip()
    summary = _clean_html(entry.get("summary") or entry.get("description") or "")[:4000]

    published = entry.get("published_parsed") or entry.get("updated_parsed")
    date = time.strftime("%Y-%m-%d", published) if published else ""

    seed = url or title
    offer_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

    return {
        "id": offer_id,
        "source": source,
        "category": category,
        "title": title,
        "company": _company_from_entry(entry, source),
        "location": "",
        "remote": "",
        "url": url,
        "description": summary,
        "published": date,
        "status": "nouveau",
    }


def _offer_from_json_item(item: Dict, source: str, category: str) -> Dict:
    title = _clean_html(str(item.get("position", ""))).strip()
    link = str(item.get("url") or item.get("apply_url") or "").strip()
    description = _clean_html(str(item.get("description", "")))
    tags = item.get("tags") or []
    if tags:
        description = f"{description} Tags : {', '.join(map(str, tags))}".strip()
    published = item.get("date")
    date = ""
    if isinstance(published, (int, float)):
        date = time.strftime("%Y-%m-%d", time.gmtime(published))

    company = str(item.get("company") or "").strip() or _company_from_entry(item, source)
    location = str(item.get("location") or "").strip()

    seed = link or title
    offer_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

    return {
        "id": offer_id,
        "source": source,
        "category": category,
        "title": title,
        "company": company,
        "location": location,
        "remote": location,
        "url": link,
        "description": description[:4000],
        "published": date,
        "status": "nouveau",
    }


def fetch_json_feed(feed: Dict) -> List[Dict]:
    """Télécharge et parse un flux JSON (ex: RemoteOK) en offres normalisées.

    Chaque item est un objet avec au moins `position` ; les champs
    `company`, `location`, `url`, `apply_url`, `description`, `tags` et
    `date` (epoch) sont reconnus.
    """
    url = feed["url"]
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "veille-candidatures/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise FeedError(f"Impossible de contacter {url}: {exc}") from exc

    if not isinstance(data, list):
        raise FeedError(f"Format JSON inattendu (liste attendue) : {url}")

    category = feed.get("category", "")
    offers = []
    for item in data:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        if not _clean_html(str(item.get("position", ""))).strip():
            continue
        offers.append(_offer_from_json_item(item, url, category))
    return offers


def fetch_feed(feed: Dict) -> List[Dict]:
    """Télécharge et parse un flux (JSON si type='json', RSS/Atom sinon)."""
    if feed.get("type") == "json":
        return fetch_json_feed(feed)

    url = feed["url"]
    try:
        parsed = feedparser.parse(url)
    except Exception as exc:  # urllib peut lever pour un réseau/cert inattendu
        raise FeedError(f"Impossible de contacter {url}: {exc}") from exc

    if getattr(parsed, "bozo", False) and not parsed.entries:
        raise FeedError(f"Flux illisible ou vide : {url} (erreur de parsing)")

    source = feed.get("url", url)
    category = feed.get("category", "")
    return [
        _offer_from_entry(entry, source, category)
        for entry in parsed.entries
        if _clean_html(entry.get("title", "")).strip()
    ]


def refresh_feeds() -> Dict:
    """Parcourt tous les flux, ajoute les offres inconnues, purge les doublons.

    Retourne un résumé : {feeds, fetched, new, new_ids, errors}.
    `new_ids` permet à la couche d'alerte de scorer uniquement les offres neuves.
    """
    feeds = load_feeds()
    offers = load_offers()
    known_ids = {o["id"] for o in offers}
    known_urls = {o["url"] for o in offers if o.get("url")}

    summary = {"feeds": len(feeds), "fetched": 0, "new": 0, "new_ids": [], "errors": []}

    for feed in feeds:
        try:
            entries = fetch_feed(feed)
        except FeedError as exc:
            summary["errors"].append(str(exc))
            continue

        for offer in entries:
            summary["fetched"] += 1
            duplicate = offer["id"] in known_ids or (offer["url"] and offer["url"] in known_urls)
            if duplicate:
                continue
            known_ids.add(offer["id"])
            if offer["url"]:
                known_urls.add(offer["url"])
            offers.insert(0, offer)
            summary["new"] += 1
            summary["new_ids"].append(offer["id"])

    if summary["new"]:
        save_offers(offers[:_MAX_OFFERS])
    elif not OFFERS_PATH.exists():
        save_offers(offers[: _MAX_OFFERS])

    return summary