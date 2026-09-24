"""Score une offre d'emploi par rapport au profil du candidat.

Combine :
1. Une similarité sémantique (embeddings) entre l'offre et le profil.
2. Un matching de mots-clés explicite (skills maîtrisées vs manquantes).
3. Des "flags" métier basés sur des règles simples (séniorité, remote, localisation),
   directement inspirés des leçons de cette conversation (ex: Wise Associates).
"""
import json
import math
import re
from typing import List, Tuple

from chromadb.utils import embedding_functions

from app.config import PROFILE_PATH
from app.schemas import ScoreJobResponse

_embedder = embedding_functions.DefaultEmbeddingFunction()

# --- Analyse géographique : détecte les offres réservées (local-US/UK/EU…) ---
# Seuls des motifs « contextuels » sont pris en compte, pour éviter les faux
# positifs (« Headquarters: United States » n'est pas une contrainte de résidence).
_REGION_RESTRICTIONS = [
    (r"\bus\s+only\b", "États-Unis", "US"),
    (r"\bu\.?s\.?\s+citizen", "États-Unis", "US"),
    (r"\bu\.?s\.?\s+(?:work\s+authorization|residenc\w*)", "États-Unis", "US"),
    (r"\bw-?2\b", "États-Unis (contrat W2)", "US"),
    (r"\bremote\s*[·,ː\-–—]\s*(?:the\s+)?(?:us|usa)\b", "États-Unis", "US"),
    (r"\bremote\s*[·,ː\-–—]\s*(?:the\s+)?united\s+states\b", "États-Unis", "US"),
    (r"(?:us|usa)\b[·,]\s*[a-z]{2,}", "États-Unis", "US"),
    (r"within\s+(?:the\s+)?(?:united\s+states|us)\b", "États-Unis", "US"),
    (r"(?:based|located|residing|must\s+(?:live|be|reside)).{0,40}\bus\b", "États-Unis", "US"),
    (r"\buk\s+only\b", "Royaume-Uni", "UK"),
    (r"\buk\s+(?:based|resident|citizen)", "Royaume-Uni", "UK"),
    (r"united\s+kingdom\s+only", "Royaume-Uni", "UK"),
    (r"\beu\s+only\b", "Union européenne", "EU"),
    (r"\beu\s+(?:based|resident|citizen)", "Union européenne", "EU"),
    (r"european\s+union\s+only", "Union européenne", "EU"),
    (r"based\s+in\s+europe\b", "Union européenne", "EU"),
    (r"canada\s+(?:only|based|resident)", "Canada", "local"),
    (r"australia\s+(?:only|based|resident)", "Australie", "local"),
]

# Signaux d'ouverture mondiale (aucune pénalité ; on n'y recourt que
# lorsqu'aucune restriction explicite n'est détectée).
_INCLUSIVE_SIGNALS = (
    "worldwide", "anywhere", "anywhere in the world", "work from anywhere",
    "open to applicants worldwide", "all over the world", "global remote",
    "distributed across the world", "emea", "africa", "remote-first",
)


def _geo_analysis(title: str, description: str) -> Tuple[List[str], int]:
    """Détecte une contrainte géographique incompatible avec le profil.

    Retourne (flags, pénalité). Pénalité 30 pour un contrat US (W2 /
    citoyenneté), 25 pour une restriction régionale, 0 sinon.
    """
    text = f"{title}\n{description}".lower()
    keys = []
    for pattern, label, key in _REGION_RESTRICTIONS:
        if re.search(pattern, text) and key not in keys:
            keys.append(key)

    if not keys and any(sig in text for sig in _INCLUSIVE_SIGNALS):
        return [], 0

    if not keys:
        return [], 0

    labels = []
    for key in keys:
        if key == "US":
            if "w2" in text:
                labels.append("États-Unis (contrat W2)")
            elif "citizen" in text:
                labels.append("États-Unis (citoyenneté exigée)")
            else:
                labels.append("États-Unis")
        elif key == "UK":
            labels.append("Royaume-Uni")
        elif key == "EU":
            labels.append("Union européenne")
        else:
            labels.append("pays/région spécifique")
    labels = ", ".join(dict.fromkeys(labels))

    hard = any("w2" in text or "citizen" in text for k in keys if k == "US")
    penalty = 30 if hard else 25
    flag = (
        f"⚠️ Localisation : offre réservée à {labels} — inéligible "
        f"depuis {load_profile().get('location', 'ta localisation')}."
    )
    return [flag], penalty


def load_profile() -> dict:
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _profile_text(profile: dict) -> str:
    return (
        f"Développeur avec {profile['years_experience']} ans d'expérience, "
        f"niveau {profile['seniority']}. Compétences : {', '.join(profile['skills'])}. "
        f"Préférence : {profile['remote_preference']}."
    )


def score_job(title: str, description: str) -> ScoreJobResponse:
    profile = load_profile()
    full_text = f"{title}\n{description}"
    lower_text = full_text.lower()

    # 1. Similarité sémantique
    embeddings = _embedder([full_text, _profile_text(profile)])
    similarity = _cosine_similarity(embeddings[0], embeddings[1])  # entre -1 et 1
    similarity_score = max(0.0, similarity) * 60  # jusqu'à 60 points

    # 2. Matching de mots-clés
    matched_skills = [s for s in profile["skills"] if s.lower() in lower_text]
    missing_skills = [s for s in profile["weak_or_missing_skills"] if s.lower() in lower_text]

    skill_ratio = len(matched_skills) / max(1, len(matched_skills) + len(missing_skills))
    skill_score = skill_ratio * 30  # jusqu'à 30 points

    # 3. Flags métier
    flags = []
    penalty = 0

    geo_flags, geo_penalty = _geo_analysis(title, description)
    penalty += geo_penalty

    if "senior" in lower_text and profile["seniority"] != "senior":
        flags.append("⚠️ 'Senior' explicitement demandé — décalage probable avec ton niveau actuel.")
        penalty += 15

    remote_keywords = ["remote", "télétravail", "distance"]
    onsite_keywords = ["sur site", "présentiel", "présence"]
    mentions_remote = any(k in lower_text for k in remote_keywords)
    mentions_onsite = any(k in lower_text for k in onsite_keywords)

    if mentions_onsite:
        flags.append("⚠️ Présence sur site mentionnée — vérifie la compatibilité avec ta recherche 100% remote.")
        penalty += 20
    elif mentions_remote and not geo_flags:
        flags.append("ℹ️ Remote mentionné — vérifie si c'est du remote local ou international (cf. cas Wise Associates).")

    if missing_skills:
        flags.append(f"⚠️ Compétences demandées non maîtrisées : {', '.join(missing_skills)}.")

    flags.extend(geo_flags)

    raw_score = similarity_score + skill_score - penalty
    score = max(0, min(100, round(raw_score)))

    if score >= 70:
        recommendation = "Bon match — vaut la peine de postuler."
        explanation = "Le profil colle bien à l'offre sur la stack et les critères clés."
    elif score >= 45:
        recommendation = "Match partiel — postule en étant transparent sur les écarts."
        explanation = "Certains éléments correspondent, mais des écarts significatifs existent (niveau, compétences ou modalités)."
    else:
        recommendation = "Match faible — probablement à éviter ou à fort risque de refus."
        explanation = "Trop d'écarts entre le profil et les exigences de l'offre."

    return ScoreJobResponse(
        score=score,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        flags=flags,
        recommendation=recommendation,
        explanation=explanation,
    )