"""
Unit tests for utils/score_history.py -- the foundation for the Score
History chart on Ticker Deep Dive (2026-06-22 roadmap, step 2 of the
agreed sequence: search bar -> score history -> sector percentile).

Run against an in-memory SQLite database for full isolation, same
pattern as tests/test_auth_and_multitenancy_unit.py.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine

from utils import db
from utils.score_history import (
    compute_sector_percentile,
    compute_sector_percentiles,
    get_latest_signal_states,
    get_score_history,
    record_all_signal_snapshots,
    record_score_snapshot,
)


@pytest.fixture(autouse=True)
def _in_memory_db(monkeypatch):
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db, "engine", test_engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    db.metadata.create_all(test_engine)
    yield


def test_record_and_retrieve_a_snapshot():
    record_score_snapshot("CCJ", 72.5, "BULL", "High")
    history = get_score_history("CCJ")
    assert len(history) == 1
    assert history[0]["ticker"] == "CCJ"
    assert history[0]["score"] == 72.5
    assert history[0]["case"] == "BULL"
    assert history[0]["conviction"] == "High"


def test_unknown_ticker_returns_empty_history():
    assert get_score_history("NEVER_VIEWED_XYZ") == []


def test_recording_twice_same_day_overwrites_not_duplicates():
    """A user revisiting the same ticker later the same day must update
    that day's row, not create a second one -- the unique (ticker,
    snapshot_date) constraint is what makes this an upsert, not a
    plain insert."""
    record_score_snapshot("NVDA", 60.0, "NEUTRAL", "Mixed")
    record_score_snapshot("NVDA", 64.0, "NEUTRAL", "Mixed")  # later visit, same day

    history = get_score_history("NVDA")
    assert len(history) == 1
    assert history[0]["score"] == 64.0  # the LATER value, not the first


def test_history_is_ticker_scoped():
    record_score_snapshot("AAA", 80.0, "BULL", "High")
    record_score_snapshot("BBB", 20.0, "BEAR", "High")
    assert [r["ticker"] for r in get_score_history("AAA")] == ["AAA"]
    assert [r["ticker"] for r in get_score_history("BBB")] == ["BBB"]


def test_latest_signal_states_uses_persisted_batch_without_provider_fetch():
    record_all_signal_snapshots({
        "hy_spread": {"score": 28.0, "status": "bearish", "error": False},
        "vix_term": {"score": 72.0, "status": "bullish", "error": False},
    })

    states = get_latest_signal_states()

    assert states["hy_spread"]["score"] == 28.0
    assert states["hy_spread"]["status"] == "bearish"
    assert states["vix_term"]["status"] == "bullish"


# ── compute_sector_percentile() ──────────────────────────────────────────────
# UNP (Union Pacific, sector="Transportation") and its real peers CSX/NSC/CP/
# CNI/ODFL -- same sector group already used by
# test_get_sector_peers_excludes_self_and_etfs in
# tests/test_lead_time_research_unit.py, reused here rather than inventing a
# fake ticker, since compute_sector_percentile genuinely depends on
# utils.config.TICKERS' real sector groupings via get_sector_peers().

def test_sector_percentile_ranks_against_recorded_peer_scores():
    record_score_snapshot("CSX", 40.0, "BEAR", "Mixed")
    record_score_snapshot("NSC", 50.0, "NEUTRAL", "Mixed")
    record_score_snapshot("CP", 60.0, "NEUTRAL", "Mixed")

    result = compute_sector_percentile("UNP", score=70.0)

    assert result["error"] is None
    assert result["n_peers"] >= 3  # at least CSX/NSC/CP recorded
    # 70 is higher than all 3 recorded peers -- should rank at or near the top.
    assert result["percentile"] == 100.0
    assert result["sector_avg"] < 70.0


def test_sector_percentile_handles_no_peer_data_recorded():
    """If no sector peer has ever been viewed/snapshotted, this must
    return a clean, honest error -- never a fabricated 50th-percentile
    placeholder."""
    result = compute_sector_percentile("UNP", score=55.0)
    assert result["error"] is not None
    assert result["n_peers"] == 0


def test_sector_percentile_unknown_ticker_returns_clean_error():
    result = compute_sector_percentile("NOT_A_REAL_TICKER_XYZ", score=50.0)
    assert result["error"] is not None
    assert result["n_peers"] == 0


def test_sector_percentile_peer_scores_include_as_of_date():
    record_score_snapshot("CSX", 45.0, "NEUTRAL", "Mixed")
    result = compute_sector_percentile("UNP", score=80.0)
    assert result["error"] is None
    assert all("as_of" in p and "ticker" in p and "score" in p for p in result["peer_scores"])


def test_sector_context_reports_rank_median_and_coverage():
    record_score_snapshot("CSX", 40.0, "BEAR", "Mixed")
    record_score_snapshot("NSC", 50.0, "NEUTRAL", "Mixed")
    record_score_snapshot("CP", 60.0, "NEUTRAL", "Mixed")

    result = compute_sector_percentile("UNP", score=55.0)

    assert result["rank"] == 2
    assert result["universe_size"] >= 4
    assert result["sector_median"] == 50.0
    assert result["delta_vs_median"] == 5.0
    assert result["n_possible_peers"] >= result["n_peers"]


def test_sector_context_never_mixes_score_kinds():
    record_score_snapshot("CSX", 80.0, "BULL", "High", kind="macro_momentum")
    record_score_snapshot("NSC", 45.0, "NEUTRAL", "Mixed", kind="full")

    contexts = compute_sector_percentiles([
        {"ticker": "UNP", "score": 55.0, "score_kind": "full"},
    ])

    peers = contexts["UNP"]["peer_scores"]
    assert {row["ticker"] for row in peers} == {"NSC"}
    assert all(row["score_kind"] == "full" for row in peers)


def test_sector_context_excludes_stale_peer_scores():
    old_day = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%d")
    with db.engine.begin() as conn:
        conn.execute(db.score_snapshots.insert().values(
            ticker="CSX",
            snapshot_date=old_day,
            score=90.0,
            case="BULL",
            conviction="High",
            created_at=datetime.now(timezone.utc).isoformat(),
            score_kind="full",
        ))

    result = compute_sector_percentile("UNP", score=50.0, max_age_days=30)

    assert result["error"] is not None
    assert result["n_peers"] == 0


def test_score_history_can_be_filtered_to_one_score_kind():
    now = datetime.now(timezone.utc)
    with db.engine.begin() as conn:
        for offset, kind, score in ((2, "full", 45.0), (1, "macro_momentum", 75.0)):
            conn.execute(db.score_snapshots.insert().values(
                ticker="MIXEDKIND",
                snapshot_date=(now - timedelta(days=offset)).strftime("%Y-%m-%d"),
                score=score,
                case="NEUTRAL",
                conviction="Mixed",
                created_at=now.isoformat(),
                score_kind=kind,
            ))

    full_rows = get_score_history("MIXEDKIND", kind="full")
    macro_rows = get_score_history("MIXEDKIND", kind="macro_momentum")

    assert [row["score"] for row in full_rows] == [45.0]
    assert [row["score"] for row in macro_rows] == [75.0]


def test_history_returned_oldest_first_and_respects_days_limit():
    """Inserts snapshots across several distinct dates directly (bypassing
    record_score_snapshot's "today only" behavior, which can't simulate
    multiple days in one test run) to verify get_score_history's
    ordering and limit, exactly as a real multi-day history would look."""
    base = datetime.now(timezone.utc)
    with db.engine.begin() as conn:
        for i in range(5):
            day = (base - timedelta(days=4 - i)).strftime("%Y-%m-%d")  # oldest to newest
            conn.execute(db.score_snapshots.insert().values(
                ticker="MULTI", snapshot_date=day, score=50.0 + i,
                case="NEUTRAL", conviction="Mixed", created_at=base.isoformat(),
            ))

    full_history = get_score_history("MULTI", days=180)
    assert [r["score"] for r in full_history] == [50.0, 51.0, 52.0, 53.0, 54.0]  # oldest first

    limited = get_score_history("MULTI", days=2)
    assert len(limited) == 2
    assert [r["score"] for r in limited] == [53.0, 54.0]  # the 2 MOST RECENT, still oldest-first
