"""Integrity, cache, and cost controls for Portfolio Review."""

import pytest
from sqlalchemy import delete

from utils import db
from utils.portfolio_review import (
    build_review_input,
    generate_portfolio_review,
    get_cached_review,
    render_portfolio_review_html,
)
from utils.risk_profile import DEFAULT_PROFILE


USER_ID = 9501


@pytest.fixture(autouse=True)
def _clean_reviews():
    db.init_db()
    with db.engine.begin() as conn:
        conn.execute(delete(db.portfolio_reviews).where(db.portfolio_reviews.c.user_id == USER_ID))
    yield
    with db.engine.begin() as conn:
        conn.execute(delete(db.portfolio_reviews).where(db.portfolio_reviews.c.user_id == USER_ID))


def _evidence(ticker, score, weight, *, date="2026-07-22"):
    return {
        "ticker": ticker,
        "weight_pct": weight,
        "source": "portfolio",
        "snapshot": {
            "score": score,
            "case": "BULL" if score >= 65 else ("BEAR" if score <= 35 else "NEUTRAL"),
            "snapshot_date": date,
        },
        "components": None,
    }


def test_input_hash_is_order_stable_and_changes_with_material_evidence():
    a = _evidence("AAPL", 70, 60)
    b = _evidence("XOM", 30, 40)
    first = build_review_input([a, b], DEFAULT_PROFILE)
    reordered = build_review_input([b, a], DEFAULT_PROFILE)
    changed = build_review_input([_evidence("AAPL", 71, 60), b], DEFAULT_PROFILE)

    assert first["input_hash"] == reordered["input_hash"]
    assert first["input_hash"] != changed["input_hash"]
    assert first["summary"]["weighted_your_score"] == 54.0


def test_generation_is_cached_by_evidence_and_model_runs_once(monkeypatch):
    monkeypatch.setattr("utils.portfolio_review.limit_action", lambda actor, action: (True, 0))
    calls = []

    def synth(payload, deterministic):
        calls.append(payload["input_hash"])
        return ("The recorded portfolio evidence is mixed, with concentration and the weakest holding remaining the primary research checks.", "test-model", 100, 20)

    payload = build_review_input(
        [_evidence("AAPL", 70, 60), _evidence("XOM", 30, 40)], DEFAULT_PROFILE
    )
    first = generate_portfolio_review(USER_ID, payload, synthesis=synth)
    second = generate_portfolio_review(USER_ID, payload, synthesis=synth)

    assert len(calls) == 1
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["model"] == "test-model"
    assert get_cached_review(USER_ID, payload["input_hash"])["input_hash"] == payload["input_hash"]


def test_rate_limit_blocks_only_uncached_materially_new_review(monkeypatch):
    payload = build_review_input([_evidence("MSFT", 55, 100)], DEFAULT_PROFILE)
    monkeypatch.setattr("utils.portfolio_review.limit_action", lambda actor, action: (False, 7200))

    result = generate_portfolio_review(USER_ID, payload)

    assert result == {"status": "limited", "retry_after": 7200}
    assert get_cached_review(USER_ID, payload["input_hash"]) is None


def test_deterministic_fallback_discloses_concentration_and_escapes_rendering(monkeypatch):
    monkeypatch.setattr("utils.portfolio_review.limit_action", lambda actor, action: (True, 0))
    payload = build_review_input(
        [_evidence("<SCRIPT>", 25, 80), _evidence("AAPL", 65, 20)], DEFAULT_PROFILE
    )

    result = generate_portfolio_review(
        USER_ID,
        payload,
        synthesis=lambda payload, review: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    html = render_portfolio_review_html(result)

    assert result["model"] == "deterministic-v1"
    assert result["model_synthesis"] is None
    assert any("largest holding is 80.0%" in item for item in result["risk_flags"])
    assert "<SCRIPT>" not in html
    assert "&lt;SCRIPT&gt;" in html
