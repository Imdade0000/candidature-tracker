"""Configuration centrale du projet : chemins et clés optionnelles."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

PROFILE_PATH = DATA_DIR / "profil.json"
APPLICATIONS_PATH = DATA_DIR / "applications.json"

# Veille d'offres : liste des flux RSS/Atom et offres collectées
FEEDS_PATH = DATA_DIR / "feeds.json"
OFFERS_PATH = DATA_DIR / "offers.json"
ALERTS_PATH = DATA_DIR / "alerts.json"

# Intervalle (minutes) du rafraîchissement automatique des flux en arrière-plan
FEED_REFRESH_MINUTES = int(os.getenv("FEED_REFRESH_MINUTES", "60"))

# Score minimal à partir duquel une nouvelle offre génère une alerte.
# 45 = à partir d'un "match partiel" (postule en étant transparent sur les écarts).
# Monter à 70 réserve les alertes aux très bons matches.
ALERT_THRESHOLD = int(os.getenv("ALERT_THRESHOLD", "45"))

CHROMA_PATH = os.getenv("CHROMA_PATH", str(BASE_DIR / "chroma_db"))
COLLECTION_NAME = "applications"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Clé optionnelle pour protéger l'API en déploiement public.
# En local, si elle n'est pas définie, aucune vérification n'est appliquée.
API_KEY = os.getenv("API_KEY", "").strip()

# Origines autorisées pour le CORS (virgule-séparées). "*" = tout (local).
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if o.strip()
]

# Nombre de chunks récupérés lors d'une recherche RAG
TOP_K = 4