"""A persisting convergence is re-logged daily; those rows are one call.

log_prediction() is idempotent per (ticker, event_date, event_type), which means
one row PER DAY for as long as the condition holds -- not one row per call. On
2026-09-01 the 25 most recent rows covered just 10 distinct tickers: TDG and TMO
logged four days running, CSX/F/IWM three each.

Scoring those as separate observations inflates the sample a track record's
confidence rests on. "202 calls" was really a few dozen positions. Every horizon
statistic is therefore computed per EPISODE -- a run of consecutive daily rows
for the same ticker, event type and direction -- represented by its FIRST row,
the day the signal actually fired.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import utils.prediction_log as pl  # noqa: E402


def _r(ticker, date, direction="bull", event_type="convergence", **extra):
    base = {"ticker": ticker, "event_date": date, "direction": direction,
            "event_type": event_type, "status": "pending",
            "correct_4w": None, "return_4w": None, "correct_8w": None,
            "return_8w": None, "correct_12w": None, "return_12w": None,
            "signals_triggered": None}
    base.update(extra)
    return base


def test_a_run_of_daily_rows_is_one_episode():
    rows = [_r("TDG", f"2026-08-{d}") for d in (29, 30, 31)] + [_r("TDG", "2026-09-01")]
    eps = pl.group_into_episodes(rows)
    assert len(eps) == 1, f"four daily rows for one position must be one call, got {len(eps)}"
    assert eps[0]["call_count"] == 4
    assert eps[0]["event_date"] == "2026-08-29", (
        "the episode must be dated when the signal FIRED; a later date would mean "
        "choosing an entry after part of the outcome was observable"
    )
    assert eps[0]["episode_last_date"] == "2026-09-01"


def test_a_gap_starts_a_genuinely_new_episode():
    rows = [_r("TDG", "2026-07-01"), _r("TDG", "2026-08-29"), _r("TDG", "2026-08-30")]
    eps = pl.group_into_episodes(rows)
    assert len(eps) == 2, "a call months later is a new call, not a continuation"
    assert sorted(e["call_count"] for e in eps) == [1, 2]


def test_a_weekend_or_missed_cron_does_not_split_an_episode():
    """Calls are logged daily including weekends; a short outage must not
    manufacture extra observations out of one position."""
    rows = [_r("CSX", "2026-08-28"), _r("CSX", "2026-09-01")]  # 4-day gap
    assert len(pl.group_into_episodes(rows)) == 1


def test_opposite_directions_are_never_merged():
    rows = [_r("NVDA", "2026-08-29", "bull"), _r("NVDA", "2026-08-30", "bear")]
    assert len(pl.group_into_episodes(rows)) == 2, (
        "a flip from bull to bear is a different call, not the same one continuing"
    )


def test_non_canonical_direction_labels_group_together():
    """The #209 bug wrote "bullish" where the schema stores "bull". Grouping on
    the raw string would split one episode into two."""
    rows = [_r("NVDA", "2026-08-29", "bullish"), _r("NVDA", "2026-08-30", "bull")]
    assert len(pl.group_into_episodes(rows)) == 1


def test_different_tickers_and_event_types_stay_separate():
    rows = [_r("TDG", "2026-08-29"), _r("TMO", "2026-08-29"),
            _r("TDG", "2026-08-29", event_type="score_cross_bull")]
    assert len(pl.group_into_episodes(rows)) == 3


def test_unusable_rows_are_kept_not_silently_dropped():
    """Over-counting a logged call is bad; losing one from the audit trail is worse."""
    rows = [_r("TDG", "2026-08-29"), _r(None, "2026-08-29"), _r("TMO", "not-a-date")]
    eps = pl.group_into_episodes(rows)
    assert len(eps) == 3
    assert all(e.get("call_count") == 1 for e in eps if not e.get("ticker") or
               e.get("event_date") == "not-a-date")


# ── the statistic that was being overstated ─────────────────────────────────

def _track(monkeypatch, rows):
    class _Res:
        def mappings(self): return self
        def all(self): return rows
    class _Conn:
        def execute(self, *a, **k): return _Res()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Engine:
        def begin(self): return _Conn()
    monkeypatch.setattr(pl.db, "engine", _Engine())
    return pl.get_track_record()


def test_accuracy_counts_each_position_once_not_once_per_day(monkeypatch):
    """One winning position logged four days plus one losing position logged once
    is 50% accuracy over two calls -- not 80% over five rows."""
    rows = [_r("TDG", f"2026-08-{d}", correct_4w=1, return_4w=5.0) for d in (28, 29, 30, 31)]
    rows += [_r("TMO", "2026-08-28", correct_4w=0, return_4w=-3.0)]

    tr = _track(monkeypatch, rows)
    assert tr["total_calls"] == 5, "the raw log is untouched"
    assert tr["total_episodes"] == 2
    assert tr["n_4w"] == 2, "two independent calls have a 4-week outcome"
    assert tr["n_calls_4w"] == 5, "the row count stays available for comparison"
    assert tr["accuracy_4w"] == 50.0, (
        f"got {tr['accuracy_4w']}% -- row-based scoring would report 80%, weighting "
        f"the winner by how many days it happened to persist"
    )


def test_pnl_is_not_weighted_by_how_long_a_call_persisted(monkeypatch):
    rows = [_r("TDG", f"2026-08-{d}", correct_4w=1, return_4w=10.0) for d in (28, 29, 30)]
    rows += [_r("TMO", "2026-08-28", correct_4w=0, return_4w=-10.0)]
    tr = _track(monkeypatch, rows)
    assert tr["mean_pnl_4w"] == pytest.approx(0.0), (
        f"two equal-and-opposite calls must average to zero; got {tr['mean_pnl_4w']} "
        f"-- row weighting would give +5.0"
    )


def test_the_empty_contract_carries_the_episode_keys():
    empty = pl._empty_track_record()
    assert empty["total_episodes"] == 0 and empty["total_calls"] == 0
    for h in ("4w", "8w", "12w"):
        assert f"n_calls_{h}" in empty


def test_the_page_shows_distinct_calls_not_the_row_count():
    source = (_ROOT / "pages" / "30_Track_Record_Live.py").read_text(encoding="utf-8")
    assert "total_episodes" in source
    assert "Distinct Calls" in source, (
        "the headline figure must be the number of independent calls; labelling "
        "the daily row count 'Calls Logged' overstates the sample by ~4x"
    )
