"""Alertes de matching : scores les nouvelles offres collectées et conserve
celles qui dépassent le seuil configuré (ALERT_THRESHOLD, défaut 70).

Chaque alerte suit un cycle de vie :
  new -> seen (ack) | dropped (dismiss) | applied
« Appliquée » transforme l'offre en candidature dans applications.json
et aliène l'alerte (elle cesse d'apparaître dans le compteur).
"""
import json
import threading
from datetime import date, timedelta
from typing import Dict, List, Optional

from app.config import ALERTS_PATH, ALERT_THRESHOLD
from app.ingest import add_application
from app.schemas import Alert, Application, ScoreJobResponse
from app.scoring import score_job

_lock = threading.Lock()


def load_alerts() -> List[Dict]:
    if not ALERTS_PATH.exists():
        return []
    with open(ALERTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_alerts(alerts: List[Dict]) -> None:
    with open(ALERTS_PATH, "w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)


def _alert_from_offer(offer: Dict, result: ScoreJobResponse) -> Dict:
    return {
        "id": offer["id"],
        "score": result.score,
        "title": offer.get("title", ""),
        "company": offer.get("company", ""),
        "url": offer.get("url", ""),
        "source": offer.get("source", ""),
        "category": offer.get("category", ""),
        "published": offer.get("published", ""),
        "matched_skills": result.matched_skills,
        "missing_skills": result.missing_skills,
        "flags": result.flags,
        "recommendation": result.recommendation,
        "explanation": result.explanation,
        "status": "new",
        "created": date.today().isoformat(),
    }


def score_new_offers(offers: List[Dict]) -> int:
    """Score les offres neuves et ajoute celles >= seuil. Retourne le nb d'alertes créées."""
    with _lock:
        alerts = load_alerts()
        known_ids = {a["id"] for a in alerts}
        added = 0
        for offer in offers:
            if offer["id"] in known_ids:
                continue
            result = score_job(offer.get("title", ""), offer.get("description", ""))
            if result.score >= ALERT_THRESHOLD:
                alerts.insert(0, _alert_from_offer(offer, result))
                known_ids.add(offer["id"])
                added += 1
        if added:
            save_alerts(alerts)
        return added


def run_veille() -> Dict:
    """Ordonnanceur : collecte les flux PUIS génère les alertes de matching."""
    from app.feeds import load_offers, refresh_feeds

    summary = refresh_feeds()
    index = {o["id"]: o for o in load_offers()}
    new_offers = [index[i] for i in summary.get("new_ids", []) if i in index]
    summary["new_offers"] = len(new_offers)
    summary["alerts_added"] = score_new_offers(new_offers)
    return summary


def expire_stale_alerts(days: int = 30) -> int:
    """Archive comme « abandonnée » les alertes new/seen inchangées depuis +de
    `days` jours. Retourne le nombre d'alertes expirées."""
    cutoff = date.today() - timedelta(days=days)
    with _lock:
        alerts = load_alerts()
        changed = 0
        for a in alerts:
            created = (a.get("created") or "").strip()
            if a.get("status") not in ("new", "seen") or not created:
                continue
            try:
                created_date = date.fromisoformat(created)
            except ValueError:
                continue
            if created_date < cutoff:
                a["status"] = "dropped"
                changed += 1
        if changed:
            save_alerts(alerts)
    return changed


def rescore_alerts() -> int:
    """Re-score toutes les alertes à partir de leur offre (nouveau scoring,
    incl. le filtre géographique) et purge celles passées sous le seuil et
    jamais traitées (new/seen). Retourne le nombre d'alertes sorties."""
    from app.feeds import load_offers

    offers = {o["id"]: o for o in load_offers()}
    with _lock:
        alerts = load_alerts()
        kept = []
        removed = 0
        for a in alerts:
            offer = offers.get(a["id"])
            if offer is None:
                kept.append(a)
                continue
            result = score_job(offer.get("title", ""), offer.get("description", ""))
            a["score"] = result.score
            a["matched_skills"] = result.matched_skills
            a["missing_skills"] = result.missing_skills
            a["flags"] = result.flags
            a["recommendation"] = result.recommendation
            a["explanation"] = result.explanation
            if result.score < ALERT_THRESHOLD and a.get("status") in ("new", "seen"):
                removed += 1
                continue
            kept.append(a)
        save_alerts(kept)
    return removed


def _find_alert(alert_id: str) -> tuple[Dict, List[Dict]]:
    alerts = load_alerts()
    alert = next((a for a in alerts if a["id"] == alert_id), None)
    if alert is None:
        raise KeyError(alert_id)
    return alert, alerts


def ack_alert(alert_id: str) -> Dict:
    with _lock:
        alert, alerts = _find_alert(alert_id)
        if alert["status"] == "new":
            alert["status"] = "seen"
        save_alerts(alerts)
        return alert


def dismiss_alert(alert_id: str) -> Dict:
    with _lock:
        alert, alerts = _find_alert(alert_id)
        alert["status"] = "dropped"
        save_alerts(alerts)
        return alert


def apply_alert(alert_id: str, notes: str = "") -> Application:
    """Transforme une alerte en candidature (applications.json + index RAG)."""
    with _lock:
        alert, alerts = _find_alert(alert_id)
        if alert["status"] == "applied":
            raise ValueError("Cette offre a déjà été transformée en candidature.")

        for a in alerts:
            if a["id"] == alert_id:
                a["status"] = "applied"
                break

        application = Application(
            id=alert_id,
            company=alert["company"] or alert["source"],
            title=alert["title"],
            stack=[s for s in alert.get("matched_skills", [])],
            location="",
            remote="100% télétravail" if "remote" in alert.get("category", "").lower() else "",
            seniority_required="",
            status="applied",
            date=date.today().isoformat(),
            notes=(alert.get("url", "") and f"Offre repérée via la veille : {alert['url']}\n") + notes,
        )
        add_application(application)
        save_alerts(alerts)
        return application