# Veille // candidatures

Assistant personnel de veille de candidatures : il centralise l'historique,
répond à des questions dessus (RAG local), score de nouvelles offres contre
ton profil et **t'alerte** quand une offre correspond.

## Fonctionnalités

- **Journal** : centralise les candidatures (`data/applications.json`) avec ajout / modification / suppression — l'index RAG suit automatiquement.
- **Interroger** : questions en français sur ton historique (ex. « à combien d'offres remote ai-je postulé ce mois ? »), servies par ChromaDB. Mode *extractif* gratuit par défaut ; un LLM (OpenAI) reformule si `OPENAI_API_KEY` est fournie.
- **Scorer une offre** : score hybride 0–100 (similarité sémantique + matching de skills + règles métier remote/séniorité), avec flags et recommandation.
- **Stats** : répartition par mois / remote / statut / séniorité (`/stats`).
- **Veille RSS** : collecte d'offres depuis des flux RSS/Atom dans `data/offers.json`, en arrière-plan (`FEED_REFRESH_MINUTES`).
- **Alertes** : chaque nouvelle offre est scorée ; celles qui dépassent `ALERT_THRESHOLD` apparaissent dans l'onglet **Alertes** du frontend (badge compteur). Actions : marquer comme lue, ignorer, ou **postuler** (transforme l'offre en candidature).

## Démarrage rapide

Prérequis : Python 3.10+ (le Dockerfile utilise 3.11). Le premier lancement télécharge le petit modèle d'embedding local ONNX (connexion Internet une seule fois).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
vim .env   # facultatif, sur la base de .env.example
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ouvre ensuite **http://localhost:8000** : le frontend est servi par l'API.

### Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

## Variables d'environnement

Voir `.env.example`. Les principales :

| Variable | Défaut | Rôle |
|---|---|---|
| `OPENAI_API_KEY` | *(vide)* | Reformulation des réponses RAG par LLM. Vide = mode extractif gratuit |
| `OPENAI_MODEL` | `gpt-4o-mini` | Modèle utilisé si clé fournie |
| `CHROMA_PATH` | `./chroma_db` | Persistance de la base vectorielle |
| `FEED_REFRESH_MINUTES` | `60` | Intervalle du rafraîchissement des flux |
| `ALERT_THRESHOLD` | `45` | Score minimal pour générer une alerte (70 = très bons matches seulement) |
| `API_KEY` | *(vide)* | Protège `/ask`, `/score-job`, `/feeds/refresh`, `/alerts`. Vide = désactivé (local) |
| `ALLOWED_ORIGINS` | `*` | Origines CORS (virgule-séparées) — à restreindre en déploiement |
| `PORT` | `8000` | Port d'écoute (injecté automatiquement par Render/Railway/Fly) |

## Configurer la veille

Le fichier `data/feeds.json` liste les flux suivis :
`{"url": "https://exemple.com/feed.xml", "category": "fullstack-remote"}`.

À ajouter via l'API (`POST /feeds`), l'UI n'a pas encore de gestion de flux — ou directement en éditant le fichier puis en appelant `POST /feeds/refresh`.

Flux de départ testés et fonctionnels : **DevRemotely** (`https://devremotely.com/feeds/fullstack.xml`, `.../engineer.xml`, `.../devops.xml`) et **We Work Remotely** full-stack (`https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss`).

> Note : de nombreux flux publics (Remotive, RemoteOK…) purgent vers du HTML ou sont mal formés pour `feedparser`. Vérifie un nouveau flux avec `curl -L <url>` avant de l'ajouter.

## Architecture

```
app/
  main.py      FastAPI : routes API + boucle de veille (lifespan)
  config.py    Chemins, clés, seuils
  schemas.py   Modèles Pydantic
  store.py     Client Chroma (persistant)
  ingest.py    applications.json <-> index RAG (ajout/maj/suppression/filtres)
  rag.py       Retrieval + génération (LLM ou extractif)
  scoring.py   Score hybride d'une offre contre le profil
  stats.py     Statistiques agrégées
  feeds.py     Collecte/déduplication des offres RSS/Atom
  alerts.py    Scoring des nouvelles offres + cycle de vie des alertes
data/
  profil.json        Ton profil (source du scoring)
  applications.json  L'historique des candidatures
  feeds.json         Flux suivis
  offers.json        Offres brutes collectées (runtime)
  alerts.json        Alertes de matching (runtime)
frontend/index.html  UI monopage (vanilla JS)
```

### API principale

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/health` | État |
| GET/POST/PUT/DELETE | `/applications` | CRUD candidatures (+ filtres `?status=&remote=&month=`) |
| GET | `/stats` | Statistiques agrégées |
| POST | `/ask` | Question sur l'historique (RAG) |
| POST | `/score-job` | Score d'une offre |
| GET/POST/DELETE | `/feeds` | Gestion des flux |
| POST | `/feeds/refresh` | Collecte + scoring → nouvelles alertes |
| GET | `/alerts` | Alertes (filtre `?status=new`) |
| POST | `/alerts/{id}/ack` · `/dismiss` · `/apply` | Cycle de vie d'une alerte |
| GET | `/offers` | Offres brutes collectées |

La documentation interactive OpenAPI est disponible sur `/docs`.

## Déploiement

Docker (voir `Dockerfile`), prévu pour Render / Railway / Fly `$PORT`.

```bash
docker build -t veille-candidatures .
docker run -p 8000:8000 veille-candidatures
```

En déploiement public, définir au minimum `API_KEY` et `ALLOWED_ORIGINS`.