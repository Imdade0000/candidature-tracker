"""Charge applications.json, transforme chaque candidature en texte, et
l'indexe dans Chroma. C'est l'étape "ingestion" classique d'un pipeline RAG :
source de données -> chunking -> embeddings -> stockage vectoriel.
"""
import json
from typing import List, Dict, Optional

from app.config import APPLICATIONS_PATH
from app.store import reset_collection, get_collection
from app.schemas import Application
from app.status import normalize_status

ONSITE_KEYS = ["sur site", "présentiel", "présence", "sur place"]
REMOTE_KEYS = ["remote", "télétravail", "télé-travail", "full remote"]


def classify_remote(value: Optional[str]) -> str:
    """Classe la mention de télétravail d'un champ libre en catégorie simple."""
    text = (value or "").lower()
    has_remote = any(k in text for k in REMOTE_KEYS)
    has_onsite = any(k in text for k in ONSITE_KEYS)
    if has_onsite and has_remote:
        return "hybride"
    if has_onsite:
        return "présentiel"
    if has_remote:
        return "remote"
    return "inconnu"


def load_applications() -> List[Dict]:
    with open(APPLICATIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def application_to_text(app: Dict) -> str:
    """Transforme une candidature en un chunk de texte lisible pour l'embedding.

    Chaque champ structuré est explicité en langage naturel : ça aide
    beaucoup la qualité du retrieval, plutôt que de vectoriser du JSON brut.
    """
    stack = ", ".join(app.get("stack", [])) or "non précisée"
    return (
        f"Candidature chez {app['company']} pour le poste '{app['title']}'.\n"
        f"Stack technique : {stack}.\n"
        f"Localisation : {app.get('location', 'inconnue')}.\n"
        f"Télétravail : {app.get('remote', 'non précisé')}.\n"
        f"Séniorité demandée : {app.get('seniority_required', 'non précisée')}.\n"
        f"Statut de la candidature : {app.get('status', 'inconnu')} (le {app.get('date', 'date inconnue')}).\n"
        f"Notes : {app.get('notes', '')}"
    )


def build_index() -> int:
    """Réindexe entièrement la collection à partir de applications.json.

    Retourne le nombre de documents indexés.
    """
    applications = load_applications()
    collection = reset_collection()

    ids = [app["id"] for app in applications]
    documents = [application_to_text(app) for app in applications]
    metadatas = [
        {
            "company": app["company"],
            "title": app["title"],
            "status": app.get("status", ""),
        }
        for app in applications
    ]

    if documents:
        collection.add(ids=ids, documents=documents, metadatas=metadatas)

    return len(documents)


def add_application(app: Application) -> None:
    """Ajoute une nouvelle candidature à applications.json ET à l'index vectoriel,
    sans tout réindexer (utile pour l'endpoint POST /applications).
    """
    applications = load_applications()
    applications.append(app.model_dump())
    _write_applications(applications)

    collection = get_collection()
    text = application_to_text(app.model_dump())
    collection.add(
        ids=[app.id],
        documents=[text],
        metadatas=[{"company": app.company, "title": app.title, "status": app.status}],
    )


def update_application(app: Application) -> Application:
    """Met à jour une candidature existante (JSON + index vectoriel)."""
    applications = load_applications()
    idx = next((i for i, a in enumerate(applications) if a["id"] == app.id), None)
    if idx is None:
        raise ValueError(f"Aucune candidature avec l'id {app.id}")
    applications[idx] = app.model_dump()
    _write_applications(applications)

    collection = get_collection()
    text = application_to_text(app.model_dump())
    collection.upsert(
        ids=[app.id],
        documents=[text],
        metadatas=[{"company": app.company, "title": app.title, "status": app.status}],
    )
    return app


def delete_application(application_id: str) -> bool:
    """Supprime une candidature (JSON + index vectoriel). Retourne False si absente."""
    applications = load_applications()
    remaining = [a for a in applications if a["id"] != application_id]
    if len(remaining) == len(applications):
        return False
    _write_applications(remaining)
    get_collection().delete(ids=[application_id])
    return True


def filter_applications(
    status: Optional[str] = None,
    remote: Optional[str] = None,
    month: Optional[str] = None,
) -> List[Dict]:
    """Filtre l'historique par statut, modalité de télétravail (remote/hybride/
    présentiel/inconnu) ou mois (format YYYY-MM)."""
    apps = load_applications()
    if status:
        slug = normalize_status(status)
        apps = [a for a in apps if normalize_status(a.get("status")) == slug]
    if month:
        apps = [a for a in apps if (a.get("date") or "")[:7] == month]
    if remote:
        apps = [a for a in apps if classify_remote(a.get("remote")) == remote.strip().lower()]
    return apps


def _write_applications(applications: List[Dict]) -> None:
    with open(APPLICATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(applications, f, ensure_ascii=False, indent=2)