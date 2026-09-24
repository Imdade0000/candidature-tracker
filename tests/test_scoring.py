"""Tests unitaires sur la logique de scoring d'offres."""
from app.scoring import _geo_analysis, score_job


def test_score_job_returns_bounded_score():
    res = score_job("Développeur React", "100% remote, React, TypeScript")
    assert 0 <= res.score <= 100
    assert res.recommendation
    assert res.explanation
    assert isinstance(res.flags, list)
    assert isinstance(res.matched_skills, list)
    assert isinstance(res.missing_skills, list)


def test_onsite_mentions_are_flagged():
    res = score_job("Développeur", "Poste en présentiel à Paris, présence obligatoire")
    assert any("Présence sur site" in f for f in res.flags)


def test_senior_offers_flag_for_junior_profile():
    res = score_job("Senior Developer", "React")
    assert any("Senior" in f for f in res.flags)


def test_remote_is_informational():
    res = score_job("Développeur", "100% remote, télétravail complet")
    assert any("Remote mentionné" in f for f in res.flags)


def test_geo_analysis_detects_us_restriction():
    flags, penalty = _geo_analysis("Full Stack Dev", "Remote - United States only, React")
    assert flags and penalty == 25
    assert "Localisation" in flags[0]


def test_geo_analysis_detects_remote_local_us_header():
    flags, penalty = _geo_analysis(
        "Frontend Engineer", "Acme · Remote · US, Michigan · 90K USD, TypeScript")
    assert penalty == 25
    assert "États-Unis" in flags[0]


def test_geo_analysis_w2_is_hard_penalty():
    flags, penalty = _geo_analysis("Dev", "100% remote, W2 Only contract, must be based in the US")
    assert penalty >= 30


def test_geo_analysis_uk_eu_ca():
    assert _geo_analysis("Dev", "Remote, UK only")[1] == 25
    assert _geo_analysis("Dev", "EU residents only")[1] >= 25
    assert _geo_analysis("Dev", "Canada based only")[1] == 25


def test_geo_analysis_worldwide_is_penalty_free():
    flags, penalty = _geo_analysis("Dev", "100% remote, work from anywhere in the world, open to worldwide")
    assert penalty == 0
    assert not flags


def test_geo_analysis_hq_us_without_constraint_is_penalty_free():
    flags, penalty = _geo_analysis("Dev", "Headquarters: United States, work globally")
    assert penalty == 0