"""Ranking, honesty, and rendering checks for the fast personal brief."""

from utils.personalized_brief import build_priority_brief, render_priority_card_html
from utils.risk_profile import DEFAULT_PROFILE


def _evidence(ticker, score=55.0, components=None, weight=0.0, source="portfolio"):
    return {
        "ticker": ticker,
        "snapshot": {"score": score, "case": "BULL" if score >= 65 else "NEUTRAL", "snapshot_date": "2026-07-21"},
        "components": components,
        "weight_pct": weight,
        "source": source,
    }


def test_watchlist_specific_change_ranks_ahead_of_static_extreme():
    evidence = [_evidence("SPY", 52), _evidence("NVDA", 80)]
    changes = {
        "changes": [{
            "headline": "Credit spreads weakened",
            "delta": -9,
            "watchlist_hits": ["SPY"],
        }]
    }

    out = build_priority_brief(evidence, DEFAULT_PROFILE, changes)

    assert [row["ticker"] for row in out["priorities"]] == ["SPY", "NVDA"]
    assert out["priorities"][0]["status"] == "Changed"
    assert "Credit spreads" in out["priorities"][0]["reason"]


def test_strong_canonical_backdrop_is_prioritized_without_invented_change():
    out = build_priority_brief([_evidence("XOM", 72), _evidence("SPY", 51)], DEFAULT_PROFILE)

    assert out["priorities"][0]["ticker"] == "XOM"
    assert out["priorities"][0]["status"] == "Strong backdrop"
    assert out["priorities"][1]["status"] == "Monitor"


def test_missing_real_score_is_disclosed_not_estimated():
    out = build_priority_brief(
        [{"ticker": "AAPL", "snapshot": None, "components": None}], DEFAULT_PROFILE
    )

    assert out["priorities"] == []
    assert out["missing"] == ["AAPL"]
    assert out["n_total"] == 1


def test_priority_view_caps_primary_cards_at_three():
    evidence = [_evidence(ticker, 50 + idx * 5) for idx, ticker in enumerate(("A", "B", "C", "D", "E"))]
    out = build_priority_brief(evidence, DEFAULT_PROFILE)

    assert len(out["top_priorities"]) == 3
    assert len(out["remaining"]) == 2


def test_card_renderer_escapes_account_evidence_text():
    item = {
        "ticker": "<script>",
        "case": "NEUTRAL",
        "status": "Monitor",
        "reason": "<b>not trusted</b>",
        "personal_score": 50,
        "canonical_score": 50,
        "profile_delta": 0,
    }

    html = render_priority_card_html(item, 1)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>not trusted</b>" not in html


def test_weighted_portfolio_score_and_position_size_influence_priority():
    evidence = [
        _evidence("A", 70, weight=10),
        _evidence("B", 68, weight=90),
    ]

    out = build_priority_brief(evidence, DEFAULT_PROFILE)

    assert [row["ticker"] for row in out["priorities"]] == ["B", "A"]
    assert out["weighted_personal_score"] == 68.2
    assert out["scored_weight_pct"] == 100.0
    assert out["source"] == "portfolio"
    assert "90.0% weight" in render_priority_card_html(out["priorities"][0], 1)
