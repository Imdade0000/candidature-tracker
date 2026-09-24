"""Vocabulaire unique des statuts, partagé par Missions, Alertes et Journal.

Toutes les sources (offres/alertes/candidatures) utilisent désormais les
mêmes slugs fermés. Les libellés français servent à l'affichage et à la
saisie ; les anciens statuts libres (ex. « candidature envoyée ») sont
reconnus et normalisés par parse_status / normalize_status.
"""
from typing import Dict, Optional

STATUSES: Dict[str, str] = {
    "new": "nouvelle",
    "seen": "vue",
    "to_apply": "à postuler",
    "applied": "postulée",
    "pending": "en attente",
    "rejected": "refusée",
    "dropped": "abandonnée",
}

DEFAULT_STATUS = "new"

# Statuts proposés dans le formulaire du journal (les outcomes pertinents).
JOURNAL_STATUSES = [
    "new", "to_apply", "applied", "pending", "rejected", "dropped",
]

_ALIASES: Dict[str, str] = {
    # valeurs historiques en français
    "candidature envoyée": "applied",
    "candidature envoyee": "applied",
    "candidature envoyé": "applied",
    "envoyée": "applied",
    "envoyee": "applied",
    "envoyé": "applied",
    "envoye": "applied",
    "postulée": "applied",
    "postulee": "applied",
    "postulé": "applied",
    "postule": "applied",
    "poursuivie": "applied",
    "non postulé": "to_apply",
    "non postule": "to_apply",
    "à postuler": "to_apply",
    "a postuler": "to_apply",
    "à candidater": "to_apply",
    "à candidater sur": "to_apply",
    "décision en attente": "pending",
    "decision en attente": "pending",
    "en attente": "pending",
    "en attente de réponse": "pending",
    "en cours": "pending",
    "attente": "pending",
    "relancée": "pending",
    "relancee": "pending",
    "refusé": "rejected",
    "refuse": "rejected",
    "refusée": "rejected",
    "refusee": "rejected",
    "écarté": "dropped",
    "ecarte": "dropped",
    "écartée": "dropped",
    "ecartee": "dropped",
    "abandonné": "dropped",
    "abandonne": "dropped",
    "abandonnée": "dropped",
    "abandonnee": "dropped",
    "abandonné - lien suspect": "dropped",
    "abandonnée - lien suspect": "dropped",
    "lien suspect": "dropped",
    "ignorée": "dropped",
    "ignoree": "dropped",
    "ignoré": "dropped",
    "ignore": "dropped",
    "nouvelle": "new",
    "nouveau": "new",
    "nouvel": "new",
    "vue": "seen",
    "vu": "seen",
    "lue": "seen",
    "lu": "seen",
    # slugs eux-mêmes
    "new": "new",
    "seen": "seen",
    "to_apply": "to_apply",
    "applied": "applied",
    "pending": "pending",
    "rejected": "rejected",
    "dropped": "dropped",
    # ancien slug d'alerte « dismissed » fusionné avec « dropped »
    "dismissed": "dropped",
}


def label(status: str) -> str:
    """Libellé français affichable pour un slug canonique."""
    return STATUSES.get(status, status or "non précisé")


def normalize_status(status: Optional[str]) -> Optional[str]:
    """Retourne le slug canonique pour une valeur libre, sinon None si inconnue."""
    if not status:
        return None
    key = str(status).strip().lower()
    return _ALIASES.get(key)


def parse_status(status: Optional[str]) -> str:
    """Version stricte : lève ValueError si le statut est inconnu."""
    slug = normalize_status(status)
    if slug is None:
        raise ValueError(f"Statut invalide : « {status} ». Valeurs acceptées : "
                         + ", ".join(f"{k} ({v})" for k, v in STATUSES.items()))
    return slug


def coerce_or_default(status: Optional[str]) -> str:
    """Version permissive : normalise, sinon retombe sur le statut par défaut."""
    slug = normalize_status(status)
    if slug is None:
        return DEFAULT_STATUS
    return slug


def status_from_question(question: str) -> Optional[str]:
    """Déduit un statut canonique d'une question posée à l'assistant.

    « envoyées », « postulé », « refus », « en attente », « abandon »,
    « non postulé »… retournent le slug correspondant, sinon None.
    """
    q = " " + (question or "").lower().replace("’", "'").strip() + " "
    if "non postul" in q:
        return "to_apply"
    if "envoy" in q or "postul" in q:
        return "applied"
    if "refus" in q:
        return "rejected"
    if "abandon" in q or "lien suspect" in q:
        return "dropped"
    if "attente" in q or "décision" in q or "decision" in q:
        return "pending"
    if " nouvelle" in q or "nouvelles" in q:
        return "new"
    if " vu" in q or " vue" in q or "lue" in q:
        return "seen"
    return None