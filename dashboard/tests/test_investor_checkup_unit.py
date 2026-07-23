"""Free checkup normalization, evidence integrity, summaries, and routing."""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete

from utils import db
from utils.investor_checkup import (
    build_investor_checkup,
    load_recent_score_evidence,
    normalize_checkup_tickers,
)


TICKERS = ("CKAAA", "CKBBB", "CKOLD", "CKMAC")


@pytest.fixture(autouse=True)
def _snapshots():
    db.init_db()
    with db.engine.begin() as conn:
        conn.execute(delete(db.score_snapshots).where(db.score_snapshots.c.ticker.in_(TICKERS)))
        conn.execute(db.score_snapshots.insert(), [
            {"ticker": "CKAAA", "snapshot_date": "2026-07-22", "score": 72.0, "case": "BULL",
             "score_kind": "full", "created_at": datetime.now(timezone.utc).isoformat()},
            {"ticker": "CKAAA", "snapshot_date": "2026-07-10", "score": 65.0, "case": "BULL",
             "score_kind": "full", "created_at": datetime.now(timezone.utc).isoformat()},
            {"ticker": "CKBBB", "snapshot_date": "2026-07-21", "score": 28.0, "case": "BEAR",
             "score_kind": "full", "created_at": datetime.now(timezone.utc).isoformat()},
            {"ticker": "CKOLD", "snapshot_date": "2026-06-25", "score": 80.0, "case": "BULL",
             "score_kind": "full", "created_at": datetime.now(timezone.utc).isoformat()},
            {"ticker": "CKMAC", "snapshot_date": "2026-07-22", "score": 90.0, "case": "BULL",
             "score_kind": "macro_momentum", "created_at": datetime.now(timezone.utc).isoformat()},
        ])
    yield
    with db.engine.begin() as conn:
        conn.execute(delete(db.score_snapshots).where(db.score_snapshots.c.ticker.in_(TICKERS)))


def test_ticker_input_is_deduped_capped_and_invalid_text_is_reported():
    valid, invalid = normalize_checkup_tickers("aapl, MSFT $aapl bad! xom nvda meta tsla")
    assert valid == ["AAPL", "MSFT", "XOM", "NVDA", "META"]
    assert invalid == ["bad!"]


def test_loader_excludes_stale_and_non_full_scores_without_imputation():
    rows = load_recent_score_evidence(TICKERS, as_of=date(2026, 7, 23))
    by_ticker = {row["ticker"]: row for row in rows}
    assert by_ticker["CKAAA"]["score"] == 72.0
    assert by_ticker["CKAAA"]["delta_30d"] == 7.0
    assert by_ticker["CKBBB"]["available"] is True
    assert by_ticker["CKOLD"]["available"] is False
    assert by_ticker["CKMAC"]["available"] is False


def test_summary_is_plain_english_and_missing_rows_do_not_become_neutral():
    evidence = load_recent_score_evidence(TICKERS, as_of=date(2026, 7, 23))
    summary = build_investor_checkup(
        evidence,
        {"CKAAA": {"date": date(2026, 7, 28), "days_until": 5, "is_estimate": True}},
    )
    assert summary["covered_count"] == 2
    assert summary["missing_count"] == 2
    assert summary["average_score"] == 50.0
    assert summary["supportive_count"] == 1
    assert summary["challenging_count"] == 1
    assert summary["mixed_count"] == 0
    assert summary["headline"] == "The tracked set has a mixed macro backdrop"
    assert summary["upcoming_earnings"][0]["ticker"] == "CKAAA"


def test_checkup_is_free_routed_and_visible_in_portfolio_navigation():
    root = Path(__file__).resolve().parents[1]
    page = (root / "pages" / "50_Investor_Checkup.py").read_text()
    app = (root / "app.py").read_text()
    header = (root / "utils" / "header.py").read_text()
    assert "require_pro" not in page
    assert "not a weighted portfolio analysis" in page
    assert "No substitute values" in page
    assert 'title="Portfolio Checkup"' in app
    assert 'href="/portfolio-checkup">Portfolio Checkup</a>' in header
