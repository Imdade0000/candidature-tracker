"""Statistiques agrégées sur l'historique de candidatures.

Alerte aussi sur le type de questions que l'assistant doit savoir trancher,
ex : « combien de postes remote ce mois ? ».
"""
from collections import Counter

from app.ingest import load_applications, classify_remote
from app.schemas import StatsResponse, MonthBreakdown


def compute_stats() -> StatsResponse:
    apps = load_applications()

    months: dict[str, MonthBreakdown] = {}
    for app in apps:
        key = (app.get("date") or "")[:7] or "inconnu"
        bucket = months.setdefault(key, MonthBreakdown())
        bucket.total += 1
        cat = classify_remote(app.get("remote"))
        if cat == "remote":
            bucket.remote += 1
        elif cat == "hybride":
            bucket.hybrid += 1
        elif cat == "présentiel":
            bucket.onsite += 1

    by_status = Counter((a.get("status") or "").strip() or "inconnu" for a in apps)
    by_remote = Counter(classify_remote(a.get("remote")) for a in apps)
    by_seniority = Counter((a.get("seniority_required") or "").strip() or "non précisé" for a in apps)

    ordered_months = dict(sorted(months.items(), reverse=True))

    return StatsResponse(
        total=len(apps),
        by_month=ordered_months,
        by_status=dict(by_status),
        by_remote=dict(by_remote),
        by_seniority=dict(by_seniority),
    )