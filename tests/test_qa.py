"""Tests du moteur de réponse structurée (app/qa.py), sans toucher aux données."""
from app.ingest import classify_remote, load_applications
from app.qa import answer, try_structured_answer
from app.status import normalize_status


def _apps():
    return load_applications()


def test_count_by_status():
    expected = len([a for a in _apps() if normalize_status(a.get("status")) == "pending"])
    resp, sources = answer("combien d offres sont en attente de décision")
    assert str(expected) in resp
    assert len(sources) == expected


def test_count_remote_current_month():
    today_month = "2026-09"
    expected = len([a for a in _apps()
                    if (a.get("date") or "")[:7] == today_month
                    and classify_remote(a.get("remote")) == "remote"])
    resp, sources = answer("combien de candidatures remote ce mois")
    assert str(expected) in resp
    assert len(sources) == expected


def test_list_by_stack_react():
    expected = {a["id"] for a in _apps()
                if any("react" in s.lower() for s in a.get("stack", []))}
    resp, sources = answer("quelles candidatures avec une stack React")
    assert set(sources) == expected
    assert "Visibl" in resp


def test_company_mention_goes_structured():
    resp, sources = answer("parle moi du poste chez elbahi")
    assert sources == ["elbahi"]
    assert "ELBAHI.NET" in resp


def test_abandon_list_targets_dropped_only():
    _, sources = answer("quelles candidatures j ai abandonnées")
    assert set(sources) == {a["id"] for a in _apps()
                            if normalize_status(a.get("status")) == "dropped"}


def test_non_structured_question_falls_back_to_rag():
    resp, sources = answer("parle moi du projet professionnel")
    assert isinstance(sources, list)
    assert resp and isinstance(resp, str)


def test_unsupported_question_returns_none_from_structured():
    assert try_structured_answer("salut") is None