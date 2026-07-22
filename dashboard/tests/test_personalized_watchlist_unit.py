"""Persisted-data Watchlist personalization stays honest and deterministic."""

from utils.personalized_watchlist import build_watchlist_score_views
from utils.risk_profile import DEFAULT_PROFILE


def _evidence():
    return [{
        "ticker": "CCJ",
        "snapshot": {
            "score": 62.0,
            "score_kind": "full",
            "snapshot_date": "2026-07-22",
        },
        "components": {
            "final_score": 62.0,
            "momentum_score": 50.0,
            "snapshot_date": "2026-07-22",
            "signals": [
                {"id": "uranium_proxy", "score": 80.0, "weight": 1.0, "significant": True},
                {"id": "vix", "score": 35.0, "weight": 0.5, "significant": True},
            ],
            "components": [],
        },
    }]


def test_default_profile_keeps_standard_score_basis():
    view = build_watchlist_score_views(_evidence(), DEFAULT_PROFILE)["CCJ"]

    assert view["score"] == 62.0
    assert view["canonical_score"] == 62.0
    assert view["personal_applied"] is False
    assert view["alert_basis_label"] == "Confluence Score"


def test_default_profile_does_not_replace_fresh_snapshot_with_older_components():
    evidence = _evidence()
    evidence[0]["snapshot"].update({
        "score": 71.0,
        "score_kind": "macro_momentum",
        "snapshot_date": "2026-07-23",
    })
    evidence[0]["components"].update({
        "final_score": 42.0,
        "snapshot_date": "2026-07-20",
    })

    view = build_watchlist_score_views(evidence, DEFAULT_PROFILE)["CCJ"]

    assert view["score"] == 71.0
    assert view["canonical_score"] == 71.0
    assert view["score_kind"] == "macro_momentum"
    assert view["as_of"] == "2026-07-23"


def test_non_default_profile_exposes_your_score_and_standard_comparison():
    profile = {"tolerance": "aggressive", "horizon": "short", "emphasis": "macro"}
    view = build_watchlist_score_views(_evidence(), profile)["CCJ"]

    assert view["personal_applied"] is True
    assert view["basis_label"] == "Your Score"
    assert view["alert_basis_label"] == "Your Score"
    assert view["canonical_score"] == 62.0
    assert view["score"] != view["canonical_score"]
    assert view["peer_score"] == 62.0
    assert view["peer_score_kind"] == "full"


def test_missing_real_score_is_not_estimated():
    views = build_watchlist_score_views([
        {"ticker": "NEW", "snapshot": None, "components": None}
    ], {"tolerance": "aggressive"})

    assert views == {}
