"""Connexion à la base vectorielle Chroma.

Chroma utilise par défaut un modèle d'embedding local (MiniLM, via ONNX) :
aucune clé API n'est nécessaire pour vectoriser le texte. Le modèle est
téléchargé automatiquement au premier lancement (connexion internet requise
une seule fois).
"""
import os

# Chroma embarque une télémétrie PostHog dont l'appel plante avec la version
# de posthog installée (warning à chaque démarrage, aucune donnée utile).
# On la neutralise avant toute instanciation du client.
import posthog

posthog.disabled = True
posthog.capture = lambda *args, **kwargs: None

import chromadb
from chromadb.config import Settings

from app.config import CHROMA_PATH, COLLECTION_NAME

_client = None
_collection = None


def get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_collection():
    """Retourne la collection Chroma, en la créant si besoin (distance cosinus)."""
    global _collection
    if _collection is None:
        client = get_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def reset_collection():
    """Supprime puis recrée la collection (utile pour réindexer proprement)."""
    global _collection
    client = get_client()
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass
    _collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection