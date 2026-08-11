"""Signal tallies must add up, and unavailable signals must not vote.

The Signal Dashboard showed 14 bullish / 7 bearish / 17 neutral beside a TOTAL
of 47. Those three numbers sum to 38. On a product whose pitch is data
integrity, that is the kind of arithmetic the target reader checks.

The cause was one denominator. status can be "bullish", "bearish", "neutral",
"insufficient_data" or "no_data", but the total counted every visible signal
while only the first three were tallied. Worse, the Risk-On/Risk-Off verdict
divided by that same inflated total, so nine unscored signals silently counted
as "not bullish":

    14/38 = 36.8%  ->  Mixed
    14/47 = 29.8%  ->  Risk-Off   (what actually rendered)

which is why the panel said "Risk-Off" while the regime bar 400px above it on
the same screen said "MIXED SIGNALS".

Counting an unavailable signal as evidence of anything is precisely the
synthesis this product promises never to do: a failed signal is excluded, never
given a value.
"""

from __future__ import annotations

import sys
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

UNSCORED_STATUSES = ("insufficient_data", "no_data")


def _tally(statuses: list[str]) -> tuple[int, int, int, int, int]:
    """Mirror of the dashboard's counting, kept in one place to assert on."""
    bull = sum(1 for s in statuses if s == "bullish")
    bear = sum(1 for s in statuses if s == "bearish")
    neut = sum(1 for s in statuses if s == "neutral")
    scored = bull + bear + neut
    unscored = len(statuses) - scored
    return bull, bear, neut, scored, unscored


def _verdict(bull: int, scored: int) -> str:
    if scored <= 0:
        return "No Data"
    pct = bull / scored * 100
    return "Risk-On" if pct >= 60 else ("Risk-Off" if pct <= 35 else "Mixed")


def test_buckets_sum_to_the_displayed_total() -> None:
    statuses = (
        ["bullish"] * 14
        + ["bearish"] * 7
        + ["neutral"] * 17
        + ["insufficient_data"] * 6
        + ["no_data"] * 3
    )
    bull, bear, neut, scored, unscored = _tally(statuses)

    assert bull + bear + neut == scored, "the three buckets must equal the total shown"
    assert scored == 38
    assert unscored == 9
    assert scored + unscored == len(statuses) == 47


def test_unavailable_signals_do_not_drag_the_verdict() -> None:
    """The exact production case that produced two contradictory verdicts."""
    statuses = (
        ["bullish"] * 14
        + ["bearish"] * 7
        + ["neutral"] * 17
        + ["insufficient_data"] * 9
    )
    bull, _bear, _neut, scored, _unscored = _tally(statuses)

    assert _verdict(bull, scored) == "Mixed"
    # The bug: dividing by every visible signal instead of every scored one.
    assert _verdict(bull, len(statuses)) == "Risk-Off"


def test_all_unavailable_reports_no_data_rather_than_bearish() -> None:
    """Zero scored signals must not read as maximally bearish."""
    bull, _b, _n, scored, unscored = _tally(["insufficient_data"] * 12)
    assert scored == 0 and unscored == 12
    assert _verdict(bull, scored) == "No Data"


def test_dashboard_uses_the_scored_denominator() -> None:
    """Pin the source, so the inflated denominator cannot quietly return."""
    source = (DASHBOARD / "pages" / "1_Signal_Dashboard.py").read_text(encoding="utf-8")

    assert "scored_n     = bull_n + bear_n + neut_n" in source, (
        "the scored tally should be derived from the three buckets"
    )
    assert "total_n      = scored_n" in source, (
        "the displayed total must be the scored count, not len(visible_signals)"
    )
    assert "total_n   = len(_vals)" not in source, (
        "the inflated denominator is back: unavailable signals would vote again"
    )
