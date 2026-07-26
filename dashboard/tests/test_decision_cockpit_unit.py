"""Decision Cockpit composition, freshness, honesty, and rendering guards."""

from datetime import date

from utils.decision_cockpit import (
    build_decision_cockpit,
    render_attention_card_html,
    render_cockpit_summary_html,
    render_portfolio_impact_html,
)


def _evidence(ticker: str, score: float | None, weight: float, snapshot_date: str):
    return {
        "ticker": ticker,
        "weight_pct": weight,
        "source": "portfolio",
        "snapshot": (
            {
                "score": score,
                "score_kind": "full",
                "case": "BULL" if (score or 0) >= 65 else "NEUTRAL",
                "snapshot_date": snapshot_date,
            }
            if score is not None else None
        ),
    }


def _priority(ticker: str, score: float, weight: float, priority: float):
    return {
        "ticker": ticker,
        "personal_score": score,
        "canonical_score": score,
        "priority_score": priority,
        "weight_pct": weight,
        "status": "Strong backdrop",
        "reason": "Recorded evidence is outside the neutral range",
        "snapshot_date": "2026-07-26",
    }


def test_cockpit_ranks_queue_exceptions_before_monitoring_priorities():
    evidence = [
        _evidence("AAPL", 70, 60, "2026-07-26"),
        _evidence("MSFT", 42, 40, "2026-07-25"),
    ]
    brief = {
        "priorities": [
            _priority("AAPL", 70, 60, 80),
            _priority("MSFT", 42, 40, 40),
        ],
        "source": "portfolio",
        "weighted_personal_score": 58.8,
        "scored_weight_pct": 100,
        "n_evidence": 2,
        "n_total": 2,
        "material_changes": 0,
    }
    queue = [{
        "ticker": "MSFT",
        "status": "open",
        "severity": "urgent",
        "priority": 98,
        "headline": "Earnings event risk",
        "why_now": "Earnings are expected in two days.",
        "next_action": "Prepare the pre-earnings thesis review",
        "route": "thesis",
        "score": 42,
        "weight_pct": 40,
        "snapshot_date": "2026-07-25",
        "evidence_hash": "abc",
        "triggers": [{
            "kind": "earnings",
            "title": "Earnings event risk",
            "detail": "Earnings are expected in two days.",
        }],
    }]

    out = build_decision_cockpit(
        evidence,
        priority_brief=brief,
        queue_items=queue,
        theses=[{"ticker": "MSFT", "status": "active"}],
        today=date(2026, 7, 26),
    )

    assert out["headline"] == "1 urgent review item"
    assert [row["ticker"] for row in out["attention"]] == ["MSFT", "AAPL"]
    assert "company update" in out["attention"][0]["guided_reason"]
    assert out["portfolio"]["largest"] == {"ticker": "AAPL", "weight_pct": 60.0}
    assert out["portfolio"]["strongest"]["ticker"] == "AAPL"
    assert out["portfolio"]["challenged"]["ticker"] == "MSFT"
    assert out["freshness"]["state"] == "current"
    assert out["no_synthetic"] is True


def test_stale_and_missing_evidence_are_disclosed_not_neutralized():
    evidence = [
        _evidence("OLD", 55, 50, "2026-07-01"),
        _evidence("MISS", None, 50, "2026-07-26"),
    ]
    brief = {
        "priorities": [_priority("OLD", 55, 50, 20)],
        "missing": ["MISS"],
        "source": "portfolio",
        "weighted_personal_score": 55,
        "scored_weight_pct": 50,
        "n_evidence": 1,
        "n_total": 2,
        "material_changes": 0,
    }

    out = build_decision_cockpit(
        evidence,
        priority_brief=brief,
        today=date(2026, 7, 26),
    )

    assert out["freshness"]["state"] == "partial"
    assert out["freshness"]["stale"] == 1
    assert out["freshness"]["unavailable"] == 1
    assert out["portfolio"]["covered_weight_pct"] == 50


def test_renderers_escape_user_derived_content_and_expose_both_modes():
    payload = {
        "headline": "<script>alert(1)</script>",
        "queue": {"open": 1},
        "portfolio": {
            "weighted_score": 55,
            "covered_weight_pct": 80,
            "strongest": {"ticker": "A", "personal_score": 70},
            "challenged": {"ticker": "B", "personal_score": 30},
            "largest": {"ticker": "A", "weight_pct": 60},
        },
        "freshness": {"label": "Current recorded evidence"},
    }
    item = {
        "ticker": "<A>",
        "severity": "high",
        "headline": "<b>Review</b>",
        "guided_reason": "Plain explanation",
        "professional_reason": "Recorded trigger",
        "score": 55,
        "weight_pct": 20,
        "snapshot_date": "2026-07-26",
    }

    summary = render_cockpit_summary_html(payload, mode="Guided")
    guided = render_attention_card_html(item, 1, mode="Guided")
    professional = render_attention_card_html(item, 1, mode="Professional")
    impact = render_portfolio_impact_html(payload, mode="Professional")

    assert "<script>" not in summary
    assert "&lt;script&gt;" in summary
    assert "<b>Review</b>" not in guided
    assert "Plain explanation" in guided
    assert "Recorded trigger" in professional
    assert "Most supported" in impact


def test_today_page_wires_lazy_cache_modes_actions_and_marketing():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    page = (root / "pages" / "2_Today_Digest.py").read_text(encoding="utf-8")
    billing = (root / "utils" / "billing.py").read_text(encoding="utf-8")
    upgrade = (root / "pages" / "29_Upgrade.py").read_text(encoding="utf-8")

    assert 'sections=("Decision Cockpit", "Portfolio Impact", "Market Intelligence", "Weekly Research")' in page
    assert "@st.cache_data(ttl=300" in page
    assert '["Guided", "Professional"]' in page
    assert "DECISION_COCKPIT_ACTION" in page
    assert "Professional Decision Cockpit" in billing
    assert "Personalized Decision Cockpit" in upgrade
