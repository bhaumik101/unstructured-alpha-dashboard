"""Portfolio Fit simulation math, evidence integrity, and packaging tests."""

from datetime import date, datetime, timezone
import json

import pytest
from sqlalchemy import delete

from utils import db
from utils.portfolio_fit import load_fit_records, simulate_portfolio_fit


TEST_TICKERS = ("PFBASE", "PFLAB", "PFSTALE")


def _record(ticker: str, weight: float, score: float, signals: dict[str, float]) -> dict:
    return {
        "ticker": ticker,
        "weight": weight,
        "score": score,
        "sector": "Test",
        "corr_info": {
            signal: {"weight": 1.0, "significant": True} for signal in signals
        },
        "signal_scores": {
            signal: {"score": value} for signal, value in signals.items()
        },
        "snapshot_date": "2026-07-22",
        "model_version": "model-v1",
        "signal_registry_version": "signals-v1",
        "ok": True,
    }


@pytest.fixture(autouse=True)
def _clean_fit_rows():
    db.init_db()
    with db.engine.begin() as conn:
        conn.execute(delete(db.score_components).where(db.score_components.c.ticker.in_(TEST_TICKERS)))
        conn.execute(delete(db.score_snapshots).where(db.score_snapshots.c.ticker.in_(TEST_TICKERS)))
    yield
    with db.engine.begin() as conn:
        conn.execute(delete(db.score_components).where(db.score_components.c.ticker.in_(TEST_TICKERS)))
        conn.execute(delete(db.score_snapshots).where(db.score_snapshots.c.ticker.in_(TEST_TICKERS)))


def test_differentiated_candidate_is_funded_pro_rata_and_adds_factor():
    current = [
        _record("AAA", 60, 60, {"ten_year_yield": 42}),
        _record("BBB", 40, 50, {"hy_spread": 45}),
    ]
    candidate = _record("NEW", 0, 70, {"crude_oil": 72})

    result = simulate_portfolio_fit(current, candidate, 20)

    assert result["state"] == "ready"
    assert result["target_weight"] == 20
    weights = {row["ticker"]: row["weight_pct"] for row in result["after"]["holdings"]}
    assert weights == {"AAA": 48.0, "BBB": 32.0, "NEW": 20.0}
    assert result["fit_tone"] == "differentiated"
    assert result["new_factors"]
    assert "reducing every other scored holding pro rata" in result["assumption"]


def test_candidate_that_repeats_existing_factor_is_labeled_as_reinforcing():
    current = [
        _record("AAA", 60, 60, {"ten_year_yield": 42}),
        _record("BBB", 40, 55, {"ten_year_yield": 48}),
    ]
    candidate = _record("NEW", 0, 68, {"ten_year_yield": 55})

    result = simulate_portfolio_fit(current, candidate, 25)

    assert result["fit_tone"] == "reinforces"
    assert result["overlap_similarity"] >= 0.99
    assert result["shared_factors"][0]["candidate_exposure"] == 100.0


def test_existing_holding_can_be_resized_without_duplication():
    current = [
        _record("AAA", 60, 60, {"ten_year_yield": 42}),
        _record("BBB", 40, 55, {"hy_spread": 48}),
    ]

    result = simulate_portfolio_fit(current, dict(current[0]), 30)

    weights = {row["ticker"]: row["weight_pct"] for row in result["after"]["holdings"]}
    assert weights == {"AAA": 30.0, "BBB": 70.0}
    assert len(weights) == 2


def test_unavailable_candidate_never_receives_an_estimated_fit():
    current = [
        _record("AAA", 60, 60, {"ten_year_yield": 42}),
        _record("BBB", 40, 55, {"hy_spread": 48}),
    ]

    result = simulate_portfolio_fit(
        current,
        {"ticker": "MISS", "ok": False, "reason": "No full score."},
        10,
    )

    assert result["state"] == "candidate_unavailable"
    assert "before" not in result and "after" not in result


def test_different_model_versions_are_refused_not_blended():
    current = [
        _record("AAA", 60, 60, {"ten_year_yield": 42}),
        _record("BBB", 40, 55, {"hy_spread": 48}),
    ]
    candidate = _record("NEW", 0, 68, {"crude_oil": 55})
    candidate["model_version"] = "model-v2"

    result = simulate_portfolio_fit(current, candidate, 10)

    assert result["state"] == "evidence_incompatible"
    assert result["model_versions"] == ["model-v1", "model-v2"]
    assert "before" not in result and "after" not in result


def _component_payload(ticker: str, score: float, signal: str) -> str:
    return json.dumps({
        "ticker": ticker,
        "final_score": score,
        "coverage": {"generates_score": True},
        "signals": [{
            "id": signal,
            "score": 55,
            "weight": 1.0,
            "significant": True,
        }],
    })


def test_loader_requires_matched_fresh_reconciled_full_evidence():
    now = datetime.now(timezone.utc).isoformat()
    with db.engine.begin() as conn:
        conn.execute(db.score_snapshots.insert(), [
            {
                "ticker": "PFBASE", "snapshot_date": "2026-07-22", "score": 60,
                "case": "NEUTRAL", "score_kind": "full", "created_at": now,
            },
            {
                "ticker": "PFLAB", "snapshot_date": "2026-07-22", "score": 70,
                "case": "BULL", "score_kind": "full", "created_at": now,
            },
            {
                "ticker": "PFSTALE", "snapshot_date": "2026-07-01", "score": 65,
                "case": "BULL", "score_kind": "full", "created_at": now,
            },
        ])
        conn.execute(db.score_components.insert(), [
            {
                "ticker": "PFBASE", "snapshot_date": "2026-07-22", "final_score": 60,
                "components_json": _component_payload("PFBASE", 60, "ten_year_yield"),
                "created_at": now,
            },
            {
                "ticker": "PFLAB", "snapshot_date": "2026-07-22", "final_score": 70,
                "components_json": _component_payload("PFLAB", 70, "crude_oil"),
                "created_at": now,
            },
            {
                "ticker": "PFSTALE", "snapshot_date": "2026-07-01", "final_score": 65,
                "components_json": _component_payload("PFSTALE", 65, "hy_spread"),
                "created_at": now,
            },
        ])

    current, candidate = load_fit_records(
        [{"ticker": "PFBASE", "weight_pct": 100}],
        "PFLAB",
        as_of=date(2026, 7, 22),
    )
    _, stale = load_fit_records(
        [{"ticker": "PFBASE", "weight_pct": 100}],
        "PFSTALE",
        as_of=date(2026, 7, 22),
    )

    assert current[0]["ok"] is True
    assert candidate["ok"] is True and candidate["score"] == 70
    assert stale["ok"] is False and "stale" in stale["reason"]


def test_loader_rejects_invalid_candidate_symbol_before_querying():
    current, candidate = load_fit_records([], "<script>", as_of=date(2026, 7, 22))

    assert current == []
    assert candidate["ok"] is False
    assert "format is invalid" in candidate["reason"]


def test_fit_lab_is_in_portfolio_navigation_and_pro_marketing():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    portfolio = (root / "pages" / "44_Portfolio_Suite.py").read_text(encoding="utf-8")
    upgrade = (root / "pages" / "29_Upgrade.py").read_text(encoding="utf-8")
    billing = (root / "utils" / "billing.py").read_text(encoding="utf-8")

    assert '"Portfolio Fit Lab"' in portfolio
    assert "simulate_portfolio_fit" in portfolio
    assert "Portfolio Fit Lab — pre-trade factor and concentration simulation" in upgrade
    assert '"Portfolio Fit Lab":' in billing
