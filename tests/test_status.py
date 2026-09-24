"""Tests du vocabulaire unique des statuts (app/status.py)."""
import pytest

from app.status import (
    JOURNAL_STATUSES,
    STATUSES,
    label,
    normalize_status,
    parse_status,
    status_from_question,
    coerce_or_default,
)


def test_closed_vocabulary():
    assert set(STATUSES) == {"new", "seen", "to_apply", "applied",
                             "pending", "rejected", "dropped"}
    assert len(JOURNAL_STATUSES) == 6


def test_normalize_legacy_labels():
    assert normalize_status("candidature envoyée") == "applied"
    assert normalize_status("CANDIDATURE ENVOYEE") == "applied"
    assert normalize_status("non postulé") == "to_apply"
    assert normalize_status("décision en attente") == "pending"
    assert normalize_status("abandonné - lien suspect") == "dropped"
    assert normalize_status("refusé") == "rejected"
    assert normalize_status("ignorée") == "dropped"
    assert normalize_status("dismissed") == "dropped"


def test_normalize_unknown_returns_none():
    assert normalize_status("statut bizarre") is None
    assert normalize_status("") is None
    assert normalize_status(None) is None


def test_parse_status_strict():
    assert parse_status("envoyée") == "applied"
    with pytest.raises(ValueError):
        parse_status("statut inconnu")


def test_coerce_or_default_falls_back():
    assert coerce_or_default("") == "new"
    assert coerce_or_default("refusé") == "rejected"


def test_label():
    assert label("applied") == "postulée"
    assert label("dropped") == "abandonnée"
    assert label("noop") == "noop"
    assert label("") == "non précisé"


def test_status_from_question():
    assert status_from_question("combien j'ai envoyé") == "applied"
    assert status_from_question("parle moi des non postulées") == "to_apply"
    assert status_from_question("quelles offres refusées") == "rejected"
    assert status_from_question("quelles candidatures abandonnées") == "dropped"
    assert status_from_question("quelles offres en attente") == "pending"
    assert status_from_question("c'est quoi le remote") is None