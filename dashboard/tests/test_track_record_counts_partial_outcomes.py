"""A call whose 4-week window has closed must count, and count as P&L.

Two defects, both of which made the Track Record page look empty or wrong.

1. HORIZONS RESOLVE INDEPENDENTLY, THE PAGE DID NOT
   resolve_pending() writes return_4w/correct_4w as soon as that window expires,
   but flips status to "resolved" only once ALL THREE of 4w/8w/12w have. Every
   aggregate read `status == "resolved"`, so a call with a known and stored
   4-week outcome stayed invisible for the following EIGHT WEEKS. The page
   reported "0 resolved" and "not enough resolved data yet" while the answer sat
   in the table. get_signal_accuracy_stats() filtered the same way in SQL.

   It also quietly misstated the number it did show: accuracy_4w was computed
   only over calls old enough to have 12-week data, so the "4-week" figure
   excluded every recent call.

2. THE RETURN TILE MEASURED THE WRONG THING
   median_ret_12w is the raw price move, aggregated across a book containing
   both bull and bear calls. A bear call on a stock that fell 8% is a WIN and
   contributed -8%, dragging the median down and painting the tile red for
   calls that were right. Direction-adjusted return is what turns these rows
   into P&L.

   On the fixture below -- three of four calls correct -- the old metric reads
   -4.0% (red) and the new one +5.5% (green). Same rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import utils.prediction_log as pl  # noqa: E402


# Each row is a DIFFERENT ticker. These four are meant to be four independent
# calls, which is what this file tests; they were all "NVDA" on consecutive days
# only incidentally, and once horizon stats became per-episode (2026-09-01) that
# made them one or two episodes rather than four. Distinct tickers keep the
# intended meaning -- four separate calls, partial outcomes, mixed directions.
_TICKERS = {1: "NVDA", 2: "CAT", 3: "MU", 4: "AMD"}


def _row(id_, direction, ret_4w, correct_4w, **extra):
    base = {
        "id": id_, "status": "pending", "event_type": "convergence",
        "direction": direction, "event_date": f"2026-07-{id_:02d}",
        "ticker": _TICKERS.get(id_, f"T{id_}"), "signals_triggered": None,
        "correct_4w": correct_4w, "return_4w": ret_4w,
        "correct_8w": None, "return_8w": None,
        "correct_12w": None, "return_12w": None,
    }
    base.update(extra)
    return base


# Three right, one wrong. Both bear calls were correct, so their negative price
# moves are gains.
_FIXTURE = [
    _row(1, "bear", -8.0, 1),
    _row(2, "bear", -6.0, 1),
    _row(3, "bull",  5.0, 1),
    _row(4, "bull", -2.0, 0),
]


@pytest.fixture
def track(monkeypatch):
    def _make(rows):
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
    return _make


def test_a_four_week_outcome_counts_before_the_call_fully_resolves(track):
    tr = track(_FIXTURE)
    assert tr["resolved"] == 0, "fixture rows are deliberately still pending"
    assert tr["n_4w"] == 4, (
        "calls with a stored 4-week outcome were not counted; the page shows "
        "nothing until all three horizons expire"
    )
    assert tr["accuracy_4w"] == 75.0


def test_the_page_has_something_to_list_before_twelve_weeks(track):
    tr = track(_FIXTURE)
    assert len(tr["recent"]) == 4, (
        "recent listed only fully-resolved calls, so the table read empty for "
        "the first twelve weeks of every call's life"
    )


def test_return_is_direction_adjusted_so_a_correct_short_is_a_gain(track):
    tr = track(_FIXTURE)
    assert tr["median_ret_4w"] == -6.0 or tr["median_ret_4w"] < 0, (
        "sanity: the raw price move across this book is negative"
    )
    assert tr["median_pnl_4w"] > 0, (
        f"three of four calls were right but P&L reads {tr['median_pnl_4w']}%; "
        "correct bear calls are being counted as losses"
    )
    assert tr["mean_pnl_4w"] == pytest.approx(4.25), tr["mean_pnl_4w"]


def test_the_raw_and_adjusted_numbers_disagree_in_sign_here():
    """The whole point of the change, stated as an assertion."""
    import statistics
    raw = statistics.median([r["return_4w"] for r in _FIXTURE])
    adj = statistics.median([pl._signed_return(r, "return_4w") for r in _FIXTURE])
    assert raw < 0 < adj, (
        f"fixture no longer demonstrates the defect (raw={raw}, adjusted={adj})"
    )


def test_no_outcomes_yet_reports_none_not_zero(track):
    """None means "no data"; 0.0% would be a claim of total failure."""
    tr = track([_row(1, "bull", None, None)])
    assert tr["n_4w"] == 0
    assert tr["accuracy_4w"] is None
    assert tr["mean_pnl_4w"] is None


def test_an_empty_table_returns_the_full_shape():
    """Callers index these keys directly; a missing one is an AttributeError."""
    empty = pl._empty_track_record()
    for h in ("4w", "8w", "12w"):
        for k in ("n_", "accuracy_", "median_ret_", "median_pnl_", "mean_pnl_"):
            assert f"{k}{h}" in empty, f"_empty_track_record is missing {k}{h}"
