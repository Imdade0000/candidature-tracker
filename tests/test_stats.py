"""Tests sur les statistiques agrégées, sans toucher aux données."""
from app.ingest import load_applications, classify_remote
from app.stats import compute_stats


def test_stats_total_matches_store():
    stats = compute_stats()
    assert stats.total == len(load_applications())
    assert stats.total > 0


def test_stats_breakdowns_are_consistent():
    stats = compute_stats()
    assert sum(stats.by_status.values()) == stats.total
    assert sum(stats.by_remote.values()) == stats.total
    assert set(stats.by_remote.keys()).issubset({"remote", "hybride", "présentiel", "inconnu"})
    assert "2026-09" in stats.by_month


def test_stats_month_remote_counts():
    stats = compute_stats()
    month = stats.by_month["2026-09"]
    apps_month = [a for a in load_applications() if (a.get("date") or "")[:7] == "2026-09"]
    expected_remote = sum(1 for a in apps_month if classify_remote(a.get("remote")) == "remote")
    expected_hybrid = sum(1 for a in apps_month if classify_remote(a.get("remote")) == "hybride")
    expected_onsite = sum(1 for a in apps_month if classify_remote(a.get("remote")) == "présentiel")
    assert month.total == len(apps_month)
    assert (month.remote, month.hybrid, month.onsite) == (expected_remote, expected_hybrid, expected_onsite)