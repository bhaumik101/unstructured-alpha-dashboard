"""The chrome's snapshot read must stay bounded.

get_latest_signal_states() used to SELECT the entire signal_snapshots table,
sort it, ship every row to Python and keep only the newest per signal.
Production PERF logs had page.home.persisted_snapshot at ~472ms average, and
the table grows 47 rows a day — so the read got slower every single day
(~17k rows after a year to return 47).

It now uses a ROW_NUMBER window function. These tests exist because that
rewrite is only safe if it returns EXACTLY what the old one did, so the
centrepiece is a differential test against the retained full-scan version.

Same in-memory SQLite pattern as tests/test_score_history_unit.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from utils import db
from utils.score_history import (
    _get_latest_signal_states_fullscan,
    get_latest_signal_states,
)


@pytest.fixture(autouse=True)
def _in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    db.metadata.create_all(engine)
    yield


def _insert(signal_id: str, date: str, score: float, status: str, created_at: str):
    """Write directly: record_all_signal_snapshots upserts on (signal_id, date),
    which is exactly the collision these tests need to control by hand."""
    with db.engine.begin() as conn:
        conn.execute(db.signal_snapshots.insert().values(
            signal_id=signal_id, snapshot_date=date, score=score,
            status=status, created_at=created_at,
        ))


def test_returns_the_newest_row_per_signal():
    _insert("hy_spread", "2026-07-01", 10.0, "bearish", "2026-07-01T00:00:00Z")
    _insert("hy_spread", "2026-08-01", 90.0, "bullish", "2026-08-01T00:00:00Z")
    _insert("vix_term",  "2026-07-15", 50.0, "neutral", "2026-07-15T00:00:00Z")

    states = get_latest_signal_states()

    assert set(states) == {"hy_spread", "vix_term"}
    assert states["hy_spread"]["score"] == 90.0
    assert states["hy_spread"]["status"] == "bullish"
    assert states["vix_term"]["score"] == 50.0


def test_one_row_per_signal_per_day_is_enforced_by_the_schema():
    """Why the window function needs no tie-break in practice.

    signal_snapshots has UNIQUE(signal_id, snapshot_date), so a same-date tie
    cannot exist — the original query's created_at secondary sort was
    unreachable. It is preserved in the new ORDER BY anyway so the two
    implementations stay literally equivalent, but this pins the reason it
    never fires. (I wrote a tie test first; the database rejected it.)
    """
    from sqlalchemy.exc import IntegrityError

    _insert("hy_spread", "2026-08-01", 11.0, "bearish", "2026-08-01T01:00:00Z")
    with pytest.raises(IntegrityError):
        _insert("hy_spread", "2026-08-01", 99.0, "bullish", "2026-08-01T09:00:00Z")


def test_matches_the_full_scan_implementation_exactly():
    """The differential test: same input, byte-identical output.

    A window function is only a safe swap for "sort everything and keep the
    first of each" if it agrees on every row, including ties and ordering.
    """
    for day in range(1, 12):
        for sig in ("hy_spread", "vix_term", "net_liquidity", "ten_year_yield"):
            _insert(sig, f"2026-07-{day:02d}", float(day * 7 % 100), "neutral",
                    f"2026-07-{day:02d}T0{day % 10}:00:00Z")
    # plus a signal with exactly one row, and one whose latest is an old date
    _insert("lonely_signal", "2026-06-01", 5.0, "bearish", "2026-06-01T00:00:00Z")
    _insert("stale_signal", "2025-01-01", 1.0, "neutral", "2025-01-01T00:00:00Z")

    assert get_latest_signal_states() == _get_latest_signal_states_fullscan()


def test_internal_rank_column_is_not_leaked_to_callers():
    """_rn is an implementation detail. Chrome spreads these dicts into the
    snapshot it renders, so a stray key would travel a long way."""
    _insert("hy_spread", "2026-08-01", 90.0, "bullish", "2026-08-01T00:00:00Z")
    row = get_latest_signal_states()["hy_spread"]
    assert "_rn" not in row
    assert set(row) == {"id", "signal_id", "snapshot_date", "score", "status", "created_at"}


def test_empty_table_returns_empty_dict():
    assert get_latest_signal_states() == {}


def test_falls_back_rather_than_returning_nothing(monkeypatch):
    """If the window query cannot run, chrome must still get its data.

    A blank regime bar is a visible product defect; a slow one is merely slow.
    """
    _insert("hy_spread", "2026-08-01", 90.0, "bullish", "2026-08-01T00:00:00Z")

    real_execute = db.engine.connect
    class Boom(Exception): pass
    import utils.score_history as sh
    calls = []
    orig = sh._get_latest_signal_states_fullscan
    def spy():
        calls.append(1)
        return orig()
    monkeypatch.setattr(sh, "_get_latest_signal_states_fullscan", spy)
    monkeypatch.setattr(sh, "func", None)          # break the window construction

    states = sh.get_latest_signal_states()
    assert calls == [1], "fallback was not used"
    assert states["hy_spread"]["score"] == 90.0
