"""Pipeline RAG : question -> retrieval (Chroma) -> génération de réponse.

Deux modes de génération :
- Si OPENAI_API_KEY est définie : le LLM reformule une réponse naturelle
  à partir du contexte récupéré.
- Sinon : mode "extractif" gratuit qui présente directement les passages
  les plus pertinents, sans appel API.
"""
from typing import List, Tuple

from app.config import OPENAI_API_KEY, OPENAI_MODEL, TOP_K
from app.store import get_collection


def retrieve(question: str, top_k: int = TOP_K) -> Tuple[List[str], List[str]]:
    """Retourne (documents, ids) des chunks les plus proches de la question."""
    collection = get_collection()
    results = collection.query(query_texts=[question], n_results=top_k)
    documents = results.get("documents", [[]])[0]
    ids = results.get("ids", [[]])[0]
    return documents, ids


def generate_with_openai(question: str, context: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    system_prompt = (
        "Tu es l'assistant personnel de veille candidatures d'un développeur. "
        "Réponds uniquement à partir du contexte fourni, en français, de façon "
        "concise et factuelle. Si le contexte ne permet pas de répondre, dis-le."
    )
    completion = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Contexte :\n{context}\n\nQuestion : {question}"},
        ],
        temperature=0.2,
    )
    return completion.choices[0].message.content.strip()


def generate_extractive(question: str, documents: List[str], ids: List[str]) -> str:
    """Réponse gratuite sans LLM : résumé concis des passages les plus pertinents."""
    if not documents:
        return "Je n'ai trouvé aucune candidature pertinente pour répondre à cette question."

    from app.ingest import load_applications

    by_id = {a["id"]: a for a in load_applications()}
    lines = []
    for doc, id_ in zip(documents, ids):
        app = by_id.get(id_)
        if app:
            meta = ", ".join(x for x in [app.get("status"), app.get("date")] if x)
            stack = ", ".join(app.get("stack", [])) or "stack non renseignée"
            lines.append(
                f"- {app.get('company')} : {app.get('title')}\n"
                f"   {meta}{' | ' if meta else ''}stack : {stack}"
            )
        else:
            lines.append(f"- {doc.splitlines()[0] if doc else ''}")

    return (
        "Voici ce que j'ai trouvé dans ton historique de candidatures :\n\n"
        + "\n".join(lines)
        + "\n\nPose une question plus précise pour creuser l'un de ces dossiers."
    )


def ask(question: str) -> Tuple[str, List[str]]:
    documents, ids = retrieve(question)
    context = "\n\n".join(documents)

    if OPENAI_API_KEY:
        answer = generate_with_openai(question, context)
    else:
        answer = generate_extractive(question, documents, ids)

    return answer, ids