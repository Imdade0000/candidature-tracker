"""Couche « opportunités » : vue métier par-dessus les alertes scorées.

Une opportunité est une offre d'emploi collectée, scorée et retenue
(l'équivalent « mission » du pipeline alertes). On la manipule sans envoyer
quoi que ce soit : le brouillon généré doit toujours être relu et envoyé par
l'utilisateur lui-même.
"""
from typing import Dict, List
from datetime import date

from app.alerts import (
    _find_alert,
    apply_alert,
    expire_stale_alerts,
    load_alerts,
    rescore_alerts,
    run_veille,
    save_alerts,
)
from app.feeds import load_offers
from app.scoring import load_profile
from app.status import parse_status, label


def _offers_index() -> Dict[str, Dict]:
    return {o["id"]: o for o in load_offers()}


def _to_opportunity(alert: Dict, offers: Dict[str, Dict]) -> Dict:
    offer = offers.get(alert["id"], {})
    discovered = alert.get("created") or alert.get("published") or ""
    age_days = None
    if discovered:
        try:
            days = (date.today() - date.fromisoformat(discovered)).days
            age_days = max(0, days)
        except ValueError:
            pass
    return {
        "id": alert["id"],
        "source": alert.get("source", ""),
        "title": alert.get("title", ""),
        "company": alert.get("company", ""),
        "location": offer.get("location", ""),
        "job_type": alert.get("category", ""),
        "description": offer.get("description", ""),
        "tags": list(alert.get("matched_skills", [])) + list(alert.get("missing_skills", [])),
        "url": alert.get("url", ""),
        "published_at": alert.get("published", ""),
        "score": alert.get("score", 0),
        "matched_skills": list(alert.get("matched_skills", [])),
        "missing_skills": list(alert.get("missing_skills", [])),
        "flags": list(alert.get("flags", [])),
        "recommendation": alert.get("recommendation", ""),
        "status": alert.get("status", "new"),
        "discovered_at": alert.get("created", ""),
        "age_days": age_days,
    }


def refresh_opportunities() -> Dict:
    """Collecte le flux, archive les missions périmées puis re-score et purge
    celles devenues non éligibles (ex: localisation). Vue métier :
    fetched (offres collectées), added (nouvelles stockées), filtered
    (sorties car sous le seuil), expired (archivées pour ancienneté)."""
    summary = run_veille()
    summary["expired"] = expire_stale_alerts()
    summary["filtered"] = rescore_alerts()
    return {
        "fetched": summary.get("fetched", 0),
        "above_threshold": summary.get("alerts_added", 0),
        "added": summary.get("new", 0),
        "expired": summary.get("expired", 0),
        "filtered": summary.get("filtered", 0),
    }


def list_opportunities() -> List[Dict]:
    offers = _offers_index()
    opportunities = [_to_opportunity(a, offers) for a in load_alerts()]
    opportunities.sort(key=lambda o: o["score"], reverse=True)
    return opportunities


def _current_opportunity(opportunity_id: str) -> Dict:
    alert, _ = _find_alert(opportunity_id)
    return _to_opportunity(alert, _offers_index())


def _build_draft(opp: Dict, profile: Dict) -> Dict:
    subject = f"Candidature — {opp['title']} chez {opp['company']}"
    matched = opp["matched_skills"]
    missing = opp["missing_skills"]

    parts = [
        f"Bonjour {opp['company']},",
        "",
        f"Je vous adresse ma candidature pour le poste de {opp['title']}.",
    ]
    if matched:
        parts.append("")
        parts.append(f"Ce qui correspond bien à l'offre : {', '.join(matched)}.")
    if missing:
        parts.append("")
        parts.append(
            f"En toute transparence : {', '.join(missing)} ne font pas encore "
            f"partie de mon socle. Je les monte en compétence rapidement et je "
            f"préfère le signaler plutôt que le maquiller."
        )
    remote_pref = profile.get("remote_preference") or "100% remote"
    payload = [
        "",
        f"Basé à {profile.get('location')}, je recherche un poste {remote_pref}.",
        "Mes réalisations, portfolio et références sont disponibles sur demande.",
        "",
        "Je reste à votre disposition pour échanger.",
        "",
        "Bien cordialement,",
        profile.get("name", ""),
    ]
    parts.extend(payload)
    return {"subject": subject, "body": "\n".join(parts)}


def draft_opportunity(opportunity_id: str) -> Dict:
    """Génère un brouillon {subject, body}. Aucun envoi, jamais."""
    opp = _current_opportunity(opportunity_id)
    return _build_draft(opp, load_profile())


def update_opportunity_status(opportunity_id: str, status: str) -> Dict:
    """Change le statut d'une opportunité. Le cas « postulée » (applied)
    archive aussi l'entrée dans le journal des candidatures (mais l'envoi
    réel — email, tchat — reste interdit du côté backend)."""
    status = parse_status(status)  # ValueError -> 400 si statut inconnu
    if status == "applied":
        apply_alert(opportunity_id)  # archiver dans applications.json
        return _current_opportunity(opportunity_id)

    alert, alerts = _find_alert(opportunity_id)
    for a in alerts:
        if a["id"] == opportunity_id:
            a["status"] = status
            break
    save_alerts(alerts)
    return _to_opportunity(alert, _offers_index())