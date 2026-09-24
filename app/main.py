"""Point d'entrée FastAPI de l'assistant de veille candidatures."""
import utils.session
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import API_KEY, BASE_DIR, ALLOWED_ORIGINS, FEED_REFRESH_MINUTES
from app.ingest import (
    build_index,
    load_applications,
    add_application,
    update_application as update_app,
    delete_application as delete_app,
    filter_applications,
)
from app.qa import answer as answer_question
from app.scoring import score_job
from app.stats import compute_stats
from app.feeds import (
    load_feeds,
    add_feed,
    delete_feed,
    load_offers,
    FeedError,
)
from app.alerts import (
    run_veille,
    load_alerts,
    ack_alert,
    dismiss_alert,
    apply_alert,
)
from app.opportunities import (
    refresh_opportunities,
    list_opportunities,
    draft_opportunity,
    update_opportunity_status,
)
from app.status import parse_status
from app.schemas import (
    Alert,
    Application,
    AskRequest,
    AskResponse,
    ScoreJobRequest,
    ScoreJobResponse,
    StatsResponse,
    ApplyAlertRequest,
    Opportunity,
    OpportunitiesRefreshResponse,
    OpportunityStatusRequest,
    DraftResponse,
)

_feed_loop: Optional[asyncio.Task] = None


async def _feed_refresh_loop():
    """Rafraîchit les flux puis score les nouvelles offres (génère les alertes)."""
    while True:
        try:
            result = await asyncio.to_thread(run_veille)
            print(f"[veille] {result}")
        except Exception as exc:  # ne doit jamais faire tomber le serveur
            print(f"[veille] error: {exc}")
        await asyncio.sleep(FEED_REFRESH_MINUTES * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Réindexe les candidatures dans Chroma et lance la veille au démarrage."""
    count = build_index()
    print(f"[startup] {count} candidatures indexées dans Chroma.")
    global _feed_loop
    _feed_loop = asyncio.create_task(_feed_refresh_loop())
    yield
    if _feed_loop:
        _feed_loop.cancel()


app = FastAPI(
    title="Assistant de veille candidatures",
    description="Mini-RAG + scoring d'offres, construit sur Chroma et FastAPI.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def check_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Protège les endpoints qui coûtent de la ressource (embeddings, LLM).

    Si API_KEY n'est pas définie côté serveur (cas local par défaut), la
    vérification est désactivée — pratique pour développer sans friction.
    En déploiement public, définis API_KEY dans les variables d'environnement.
    """
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Clé API invalide ou manquante.")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/applications", response_model=list[Application])
def list_applications(
    status: Optional[str] = None,
    remote: Optional[str] = None,
    month: Optional[str] = None,
):
    return filter_applications(status=status, remote=remote, month=month)


@app.get("/stats", response_model=StatsResponse)
def stats():
    return compute_stats()


@app.post("/applications", response_model=Application)
def create_application(application: Application):
    existing = [a["id"] for a in load_applications()]
    if application.id in existing:
        raise HTTPException(status_code=400, detail="Cet id existe déjà.")
    try:
        if application.status:
            application.status = parse_status(application.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    add_application(application)
    return application


@app.put("/applications/{application_id}", response_model=Application)
def edit_application(application_id: str, application: Application):
    application.id = application_id
    if application.status:
        try:
            application.status = parse_status(application.status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    try:
        return update_app(application)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Aucune candidature avec l'id {application_id}.",
        )


@app.delete("/applications/{application_id}")
def remove_application(application_id: str):
    if not delete_app(application_id):
        raise HTTPException(
            status_code=404,
            detail=f"Aucune candidature avec l'id {application_id}.",
        )
    return {"deleted": application_id}


@app.post("/ask", response_model=AskResponse, dependencies=[])
def ask_question(payload: AskRequest, x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    answer, sources = answer_question(payload.question)
    return AskResponse(answer=answer, sources=sources)


@app.post("/score-job", response_model=ScoreJobResponse)
def score_job_endpoint(payload: ScoreJobRequest, x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    return score_job(payload.title, payload.description)


class FeedCreateRequest(BaseModel):
    url: str
    category: str = ""


@app.get("/feeds")
def list_feeds():
    return load_feeds()


@app.post("/feeds", status_code=201)
def create_feed(payload: FeedCreateRequest):
    try:
        return add_feed(payload.url, payload.category)
    except FeedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/feeds")
def remove_feed(url: str):
    if not delete_feed(url):
        raise HTTPException(status_code=404, detail="Flux non suivi.")
    return {"deleted": url}


@app.post("/feeds/refresh")
def refresh_feeds_endpoint(x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    return run_veille()


@app.get("/offers")
def list_offers(
    source: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
    x_api_key: Optional[str] = Header(default=None),
):
    check_api_key(x_api_key)
    offers = load_offers()
    if source:
        offers = [o for o in offers if o.get("source") == source]
    if category:
        offers = [o for o in offers if o.get("category") == category]
    return offers[:limit]


@app.get("/alerts", response_model=list[Alert])
def list_alerts(status: Optional[str] = None, x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    alerts = load_alerts()
    if status:
        alerts = [a for a in alerts if a.get("status") == status]
    return alerts


@app.post("/alerts/{alert_id}/ack", response_model=Alert)
def ack_endpoint(alert_id: str, x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    try:
        return ack_alert(alert_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Alerte introuvable.")


@app.post("/alerts/{alert_id}/dismiss", response_model=Alert)
def dismiss_endpoint(alert_id: str, x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    try:
        return dismiss_alert(alert_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Alerte introuvable.")


@app.post("/alerts/{alert_id}/apply", response_model=Application)
def apply_endpoint(
    alert_id: str,
    payload: ApplyAlertRequest = ApplyAlertRequest(),
    x_api_key: Optional[str] = Header(default=None),
):
    check_api_key(x_api_key)
    try:
        return apply_alert(alert_id, notes=payload.notes)
    except KeyError:
        raise HTTPException(status_code=404, detail="Alerte introuvable.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/opportunities/refresh", response_model=OpportunitiesRefreshResponse)
def opportunities_refresh_endpoint(x_api_key: Optional[str] = Header(default=None)):
    """Collecte les flux, score les nouvelles offres et remonte celles qui
    dépassent le seuil. Résumé : fetched / above_threshold / added."""
    check_api_key(x_api_key)
    return refresh_opportunities()


@app.get("/opportunities", response_model=list[Opportunity])
def opportunities_list_endpoint(x_api_key: Optional[str] = Header(default=None)):
    """Liste les missions retenues, triées par score décroissant."""
    check_api_key(x_api_key)
    return list_opportunities()


@app.post("/opportunities/{opportunity_id}/draft", response_model=DraftResponse)
def opportunity_draft_endpoint(
    opportunity_id: str, x_api_key: Optional[str] = Header(default=None)
):
    """Génère un brouillon {subject, body} à rerelire — aucun envoi ici."""
    check_api_key(x_api_key)
    try:
        return draft_opportunity(opportunity_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Opportunité introuvable.")


@app.post("/opportunities/{opportunity_id}/status", response_model=Opportunity)
def opportunity_status_endpoint(
    opportunity_id: str,
    payload: OpportunityStatusRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    """Met à jour le statut. « postulée » (applied) archive l'entrée dans le
    journal des candidatures."""
    check_api_key(x_api_key)
    try:
        return update_opportunity_status(opportunity_id, payload.status)
    except KeyError:
        raise HTTPException(status_code=404, detail="Opportunité introuvable.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# Frontend statique servi par l'API (monté en dernier pour ne pas écraser les routes API).
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")