"""Réponses structurées aux questions sur l'historique de candidatures.

Beaucoup de questions sont « chiffrables » ou « listables » directement depuis
applications.json (mois, télétravail, statut, stack…). Plutôt que de laisser le
RAG recracher des passages bruts — inexploitable pour « combien de postes
remote ce mois ? » — on répond d'abord par le calcul, et on retombe sur le RAG
uniquement pour les questions libres.
"""
import re
from datetime import date as _date
from typing import Dict, List, Optional, Tuple

from app.ingest import load_applications, classify_remote
from app.rag import ask as rag_ask
from app.status import label, normalize_status, status_from_question

_MONTH_NUM = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
_MONTH_NAMES = ["janvier", "février", "mars", "avril", "mai", "juin",
                "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
_REMOTE_WORDS = ("remote", "télétravail", "teletravail", "à distance", "a distance")
_ONSITE_WORDS = ("présentiel", "presentiel", "sur site", "sur place")
_COUNT_WORDS = ("combien", "nombre de")
_LIST_WORDS = ("lesquelles", "lesquels", "quelles sont", "quels sont", "quelle est",
               "quel est", "liste", "donne-moi", "donne moi", "qui sont",
               "quelles", "quels", "quelle", "quel")


def _normalize(question: str) -> str:
    return " " + question.lower().replace("’", "'").strip() + " "


def _parse_filters(question: str, today: _date) -> Dict:
    q = _normalize(question)
    filters: Dict = {"month": None, "year": None, "remote_cat": None, "status": None, "stack": None}

    if "ce mois-ci" in q or "ce mois" in q:
        filters["month"] = f"{today.year:04d}-{today.month:02d}"
    else:
        for name, num in _MONTH_NUM.items():
            if name in q:
                year = today.year
                match_year = re.search(r"\b(20\d{2})\b", q)
                if match_year:
                    year = int(match_year.group(1))
                filters["month"] = f"{year:04d}-{num:02d}"
                break
        else:
            match = re.search(r"\b(20\d{2})\s*[-/_]\s*(\d{1,2})\b", q)
            if match:
                filters["month"] = f"{match.group(1)}-{int(match.group(2)):02d}"
    if "cette année" in q or "cette annee" in q:
        filters["year"] = today.year

    if "hybride" in q:
        filters["remote_cat"] = "hybride"
    elif any(w in q for w in _ONSITE_WORDS):
        filters["remote_cat"] = "présentiel"
    elif any(w in q for w in _REMOTE_WORDS):
        filters["remote_cat"] = "remote"

    filters["status"] = status_from_question(question)

    filters["stack"] = _stack_token(q, load_applications())
    return filters


def _stack_token(question: str, apps: List[dict]) -> Optional[str]:
    """Trouve un mot de la question qui correspond à une compétence d'une candidature."""
    found = set()
    for app in apps:
        for skill in app.get("stack", []):
            token = skill.lower()
            if len(token) >= 2 and token in question:
                found.add(token)
    return max(found, key=len) if found else None


def _apply_filters(apps: List[dict], filters: Dict) -> List[dict]:
    if filters["month"]:
        apps = [a for a in apps if (a.get("date") or "")[:7] == filters["month"]]
    elif filters["year"]:
        apps = [a for a in apps if (a.get("date") or "")[:4] == str(filters["year"])]
    if filters["remote_cat"]:
        apps = [a for a in apps if classify_remote(a.get("remote")) == filters["remote_cat"]]
    if filters["status"]:
        slug = normalize_status(filters["status"])
        apps = [a for a in apps if normalize_status(a.get("status")) == slug]
    if filters["stack"]:
        needle = filters["stack"]
        apps = [a for a in apps if any(needle in s.lower() for s in a.get("stack", []))]
    return apps


def _month_label(month: str) -> str:
    try:
        year, num = month.split("-")
        return f"{_MONTH_NAMES[int(num) - 1]} {year}"
    except Exception:
        return month


def _scope(filters: Dict) -> str:
    if filters["month"]:
        return f"en {_month_label(filters['month'])}"
    if filters["year"]:
        return f"en {filters['year']}"
    return "au total"


def _count_answer(apps: List[dict], filters: Dict) -> str:
    n = len(apps)
    if n == 0:
        return "Je n'ai trouvé aucune candidature correspondant à ces critères."
    noun = "candidature" if n == 1 else "candidatures"
    scope = _scope(filters)

    if filters["remote_cat"]:
        cat = {"remote": "remote", "hybride": "hybride", "présentiel": "en présentiel"}[filters["remote_cat"]]
        return f"Tu as {n} {noun} {cat} {scope}."
    if filters["status"]:
        return f"Tu as {n} {noun} au statut « {label(filters['status'])} » {scope}."
    if filters["stack"]:
        return f"Tu as {n} {noun} mentionnant « {filters['stack']} » {scope}."
    return f"Tu as {n} {noun} {scope}."


def _list_answer(apps: List[dict]) -> str:
    if not apps:
        return "Je n'ai trouvé aucune candidature correspondant à ces critères."
    header = "Voici les candidatures qui correspondent :"
    lines = [header]
    for a in apps:
        meta = ", ".join(x for x in [label(a.get("status")), a.get("date")] if x)
        lines.append(f"- {a.get('company')} : {a.get('title')} ({meta})")
    lines.append("Détaille avec une question si tu veux plus d'infos sur l'une d'elles.")
    return "\n".join(lines)


def _company_match(question: str) -> Optional[dict]:
    """Si la question cite une entreprise connue, on la retrouve par sous-chaîne
    (nom complet, nom sans domaine type « .net », ou un mot du nom)."""
    q = _normalize(question)
    hits = []
    for a in load_applications():
        name = (a.get("company") or "").lower().strip()
        if len(name) < 3:
            continue
        base = re.sub(r"\.(net|com|io|fr|dev|co)$", "", name)
        words = [w for w in re.split(r"[\s\.\-,/]+", base) if len(w) >= 3]
        if name in q or base in q or any(w in q for w in words):
            hits.append(a)
    if not hits:
        return None
    hits.sort(key=lambda a: -len(a.get("company") or ""))
    return hits[0]


def _detail_answer(app: dict) -> str:
    stack = ", ".join(app.get("stack", [])) or "non renseignée"
    lines = [
        f"Candidature chez {app.get('company')} pour le poste « {app.get('title')} ».",
        f"Statut : {label(app.get('status')).capitalize()} (date : {app.get('date') or 'inconnue'}).",
        f"Séniorité demandée : {app.get('seniority_required') or 'non précisée'}.",
        f"Télétravail : {app.get('remote') or 'non précisé'}.",
        f"Stack : {stack}.",
    ]
    if app.get("notes"):
        lines.append(f"Notes : {app['notes']}")
    return "\n".join(lines)


def try_structured_answer(question: str) -> Optional[Tuple[str, List[str]]]:
    """Tente une réponse chiffrée/listée/détaillée. Retourne None si ce n'est
    pas une question structurée (dans ce cas, le RAG prend le relais)."""
    company = _company_match(question)
    if company:
        return _detail_answer(company), [company["id"]]

    q = _normalize(question)
    is_count = any(w in q for w in _COUNT_WORDS)
    is_list = any(w in q for w in _LIST_WORDS) and not is_count
    if not (is_count or is_list):
        return None

    filters = _parse_filters(question, _date.today())
    apps = _apply_filters(load_applications(), filters)
    sources = [a["id"] for a in apps]

    if is_count:
        return _count_answer(apps, filters), sources
    return _list_answer(apps), sources


def answer(question: str) -> Tuple[str, List[str]]:
    structured = try_structured_answer(question)
    if structured:
        return structured
    return rag_ask(question)