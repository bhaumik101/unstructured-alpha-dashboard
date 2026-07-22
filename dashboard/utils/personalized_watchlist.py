"""Fast, persisted-data score views for the signed-in Watchlist."""

from __future__ import annotations

from typing import Any

from utils.risk_profile import (
    HORIZON_LABELS,
    compute_personal_score_from_components,
    is_default,
    normalize,
)


def build_watchlist_score_views(evidence: list[dict], profile: Any) -> dict[str, dict]:
    """Return display and alert scores without fetching live market data."""
    normalized_profile = normalize(profile)
    personalize = not is_default(normalized_profile)
    views: dict[str, dict] = {}

    for item in evidence or []:
        ticker = str(item.get("ticker", "")).upper().strip()
        if not ticker:
            continue
        snapshot = item.get("snapshot") or {}
        components = item.get("components") or {}
        snapshot_score = snapshot.get("score")
        component_score = components.get("final_score")
        canonical = snapshot_score if snapshot_score is not None else component_score
        if canonical is None:
            continue
        canonical = float(canonical)
        display_score = canonical
        personal = {}
        personal_applied = False

        if personalize and components:
            personal = compute_personal_score_from_components(components, normalized_profile)
            if personal.get("ok") and personal.get("score") is not None:
                if component_score is not None:
                    canonical = float(component_score)
                display_score = float(personal["score"])
                personal_applied = True

        views[ticker] = {
            "ticker": ticker,
            "score": round(display_score, 1),
            "canonical_score": round(float(canonical), 1),
            "profile_delta": round(display_score - canonical, 1),
            "personal_applied": personal_applied,
            "basis_label": "Your Score" if personal_applied else (
                "Confluence" if str(snapshot.get("score_kind") or "full") == "full"
                else "Macro + momentum"
            ),
            "alert_basis_label": "Your Score" if personal_applied else "Confluence Score",
            "horizon_label": HORIZON_LABELS[normalized_profile["horizon"]],
            "as_of": components.get("snapshot_date") if personal_applied else snapshot.get("snapshot_date"),
            "score_kind": "full" if personal_applied else str(snapshot.get("score_kind") or "full"),
            "peer_score": round(float(canonical), 1),
            "peer_score_kind": "full" if components else str(snapshot.get("score_kind") or "full"),
            "explanation": personal.get("explanation", "") if personal_applied else "",
        }
    return views


def load_watchlist_score_views(user_id: int, profile: Any, limit: int = 50) -> dict[str, dict]:
    """Load all evidence in a bounded batch, then build pure score views."""
    try:
        from utils.personalized_brief import load_watchlist_evidence

        evidence = load_watchlist_evidence(user_id, limit=max(1, int(limit)))
        return build_watchlist_score_views(evidence, profile)
    except Exception:
        return {}
