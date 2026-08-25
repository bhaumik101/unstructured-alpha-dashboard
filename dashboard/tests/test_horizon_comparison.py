""""Which holding period is best" has to be asked of the same calls.

The Track Record hero shows 4-week and 12-week accuracy. The 8-week column was
computed by get_track_record() and never displayed, so the three horizons could
not be compared at all.

Adding the third number is not enough on its own. Horizons mature at different
times: the 4-week figure is drawn from recent calls, the 12-week figure from
calls made three months earlier. Ranking horizons on those samples compares two
different market regimes and calls the difference "timing".

get_horizon_comparison() therefore returns both views -- every row that has an
outcome at each horizon, and the matched subset with ALL THREE -- and draws
best_horizon only from the matched one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import utils.prediction_log as pl  # noqa: E402


def _row(id_, direction="bull", **outcomes):
    base = {
        "id": id_, "status": "pending", "event_type": "convergence",
        "direction": direction, "event_date": f"2026-06-{id_:02d}",
        "ticker": "NVDA", "signals_triggered": None,
        "correct_4w": None, "return_4w": None,
        "correct_8w": None, "return_8w": None,
        "correct_12w": None, "return_12w": None,
    }
    base.update(outcomes)
    return base


@pytest.fixture
def compare(monkeypatch):
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
        return pl.get_horizon_comparison()
    return _make


def test_no_outcomes_yields_an_honest_empty_shape(compare):
    """The live state today: 129 calls logged, none matured."""
    hz = compare([_row(i) for i in range(1, 6)])
    assert hz["matched_n"] == 0
    assert hz["best_horizon"] is None
    for h in ("4w", "8w", "12w"):
        assert hz["all"][h]["accuracy"] is None
        assert hz["matched"][h]["accuracy"] is None


def test_a_partly_matured_call_counts_only_where_it_has_an_outcome(compare):
    hz = compare([_row(1, correct_4w=1, return_4w=5.0)])
    assert hz["all"]["4w"]["n"] == 1
    assert hz["all"]["8w"]["n"] == 0
    assert hz["matched_n"] == 0, (
        "a call with only its 4-week outcome must not enter the matched sample"
    )


def test_the_matched_sample_requires_all_three_outcomes(compare):
    full = _row(1, correct_4w=1, return_4w=4.0,
                correct_8w=1, return_8w=6.0,
                correct_12w=0, return_12w=-2.0)
    partial = _row(2, correct_4w=0, return_4w=-3.0)
    hz = compare([full, partial])

    assert hz["matched_n"] == 1
    assert hz["all"]["4w"]["n"] == 2, "the all view keeps every 4-week outcome"
    assert hz["matched"]["4w"]["n"] == 1
    assert hz["matched"]["4w"]["accuracy"] == 100.0
    assert hz["matched"]["12w"]["accuracy"] == 0.0


def test_best_horizon_is_drawn_from_the_matched_sample_only(compare):
    """The trap this exists to avoid.

    12w looks perfect across all rows, but only because its single data point
    comes from a different call than the 4w ones. On the matched sample -- the
    one call scored at every horizon -- 4w is the winner.
    """
    matched = _row(1, correct_4w=1, return_4w=8.0,
                   correct_8w=0, return_8w=-1.0,
                   correct_12w=0, return_12w=-4.0)
    only_12w = _row(2, correct_12w=1, return_12w=20.0)
    hz = compare([matched, only_12w])

    assert hz["all"]["12w"]["accuracy"] == 50.0
    assert hz["best_horizon"] == "4w", (
        f"best_horizon={hz['best_horizon']}; it must come from the matched "
        "sample, where the same call is scored at every horizon"
    )
    assert hz["best_accuracy"] == 100.0


def test_a_tie_goes_to_the_shorter_horizon(compare):
    """Same accuracy for less time at risk is strictly better."""
    rows = [
        _row(1, correct_4w=1, return_4w=3.0, correct_8w=1, return_8w=3.0,
             correct_12w=1, return_12w=3.0),
        _row(2, correct_4w=0, return_4w=-3.0, correct_8w=0, return_8w=-3.0,
             correct_12w=0, return_12w=-3.0),
    ]
    hz = compare(rows)
    assert hz["matched"]["4w"]["accuracy"] == hz["matched"]["12w"]["accuracy"] == 50.0
    assert hz["best_horizon"] == "4w"


def test_pnl_is_direction_adjusted_so_a_correct_bear_call_is_a_gain(compare):
    """A bear call on a stock that fell 8% made +8%."""
    hz = compare([_row(1, direction="bear",
                       correct_4w=1, return_4w=-8.0,
                       correct_8w=1, return_8w=-8.0,
                       correct_12w=1, return_12w=-8.0)])
    assert hz["matched"]["4w"]["median_pnl"] == 8.0, (
        "a winning short was counted as a loss; raw price move is not P&L"
    )


def test_a_database_error_returns_the_full_zero_filled_shape(monkeypatch):
    class _Engine:
        def begin(self): raise RuntimeError("db down")
    monkeypatch.setattr(pl.db, "engine", _Engine())
    hz = pl.get_horizon_comparison()
    assert hz["matched_n"] == 0 and hz["best_horizon"] is None
    for view in ("all", "matched"):
        for h in ("4w", "8w", "12w"):
            assert hz[view][h]["n"] == 0


def test_the_page_renders_all_three_horizons():
    """The 8-week number existed in the data and not on the page."""
    page = (_ROOT / "pages" / "30_Track_Record_Live.py").read_text(encoding="utf-8")
    assert "get_horizon_comparison" in page
    assert 'for _i, _h in enumerate(("4w", "8w", "12w"))' in page, (
        "the comparison must cover all three horizons, not just 4w and 12w"
    )
