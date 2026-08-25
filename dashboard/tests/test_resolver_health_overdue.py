""""Overdue" must mean stuck, not maturing.

resolve_pending() fills 4w/8w/12w independently but flips status to "resolved"
only once ALL THREE have expired. A prediction therefore cannot leave the
pending pool until it is twelve weeks old.

get_resolver_health() counted pending rows older than FOUR weeks as overdue and
the Track Record page told the operator that any non-zero value was "typically a
cron failure". In steady state that number is never zero: it counts every call
in the eight-week stretch where it is maturing exactly as designed. It reported
56 stuck predictions on a working pipeline, and the remedy that suggests --
resolve them by hand -- would mean inventing outcomes for windows that have not
closed.

This is the same defect already fixed once in get_track_record(); see
tests/test_track_record_counts_partial_outcomes.py.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import utils.prediction_log as pl  # noqa: E402


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


def _row(id_, status, days_old):
    return {
        "id": id_, "status": status, "event_type": "convergence",
        "direction": "bull", "event_date": _days_ago(days_old),
        "ticker": "NVDA", "signals_triggered": None,
        "correct_4w": None, "return_4w": None,
        "correct_8w": None, "return_8w": None,
        "correct_12w": None, "return_12w": None,
    }


@pytest.fixture
def health(monkeypatch):
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
        return pl.get_resolver_health()
    return _make


def test_a_call_inside_its_window_is_maturing_not_overdue(health):
    """Six weeks old: past 4w, nowhere near able to resolve."""
    rh = health([_row(1, "pending", 42)])
    assert rh["pending_total"] == 1
    assert rh["maturing_pending"] == 1
    assert rh["overdue_pending"] == 0, (
        "a six-week-old call was flagged overdue; it cannot resolve until its "
        "12-week window closes, so this is the metric misreading the design"
    )


def test_the_whole_four_to_twelve_week_band_is_healthy(health):
    """This band is what produced the phantom backlog."""
    rows = [_row(i, "pending", d) for i, d in enumerate((30, 45, 60, 75, 83), start=1)]
    rh = health(rows)
    assert rh["overdue_pending"] == 0, (
        f"{rh['overdue_pending']} of 5 in-flight calls counted as overdue"
    )
    assert rh["maturing_pending"] == 5


def test_a_call_past_the_horizon_and_grace_is_genuinely_stuck(health):
    """14 weeks: 12-week window closed two weeks ago and it never resolved."""
    rh = health([_row(1, "pending", 98)])
    assert rh["overdue_pending"] == 1, (
        "a call two weeks past its full horizon is stuck and must be surfaced"
    )
    assert rh["maturing_pending"] == 0


def test_the_grace_period_covers_the_cron_cadence(health):
    """Exactly 12 weeks old is not yet late: the cron runs Mon/Thu."""
    rh = health([_row(1, "pending", 12 * 7)])
    assert rh["overdue_pending"] == 0, (
        "a call that hit its horizon today is flagged before the resolver has "
        "had a scheduled run to pick it up"
    )


def test_resolved_rows_are_never_counted_either_way(health):
    rh = health([_row(1, "resolved", 200), _row(2, "resolved", 30)])
    assert rh["pending_total"] == 0
    assert rh["overdue_pending"] == 0
    assert rh["maturing_pending"] == 0


def test_the_horizon_constant_matches_the_longest_window():
    """If a 24w horizon is ever added, this metric has to move with it."""
    import inspect
    src = inspect.getsource(pl.resolve_pending)
    assert "(12, \"price_12w\"" in src, (
        "the longest resolution window changed; RESOLUTION_HORIZON_WEEKS must "
        "track it or 'overdue' goes back to measuring the design"
    )
    assert pl.RESOLUTION_HORIZON_WEEKS == 12


def test_a_database_error_returns_the_full_zero_filled_shape(monkeypatch):
    """Callers index these keys directly; a partial dict would KeyError."""
    class _Engine:
        def begin(self): raise RuntimeError("db down")
    monkeypatch.setattr(pl.db, "engine", _Engine())
    rh = pl.get_resolver_health()
    for key in ("pending_total", "maturing_pending", "overdue_pending",
                "last_resolved_date", "recently_resolved_7d"):
        assert key in rh
