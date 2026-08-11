"""Recovering an entry price must not quietly improve the track record.

Some calls sat "pending" for over a month with no way to ever resolve: the live
price fetch at logging time has a bare except, so a yfinance blip left
price_at_event NULL, and resolve_pending requires that column. A NULL row is
indistinguishable from a call that is still legitimately maturing.

Backfilling them from the historical close completes the record. It also
introduces two ways to accidentally overstate performance, and both are pinned
here:

  1. picking a price AFTER event_date, which lets the entry drift toward a
     known outcome
  2. presenting a reconstructed entry as though it were observed live

The second is the one that matters most. The close on event_date is a real
price, but it is not the intraday price the call was actually made at, so the
measured return starts somewhere slightly different. Marking it keeps the record
complete without letting it claim more than it knows -- which is the same
distinction the product sells.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

DASHBOARD = Path(__file__).resolve().parent.parent
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))


def _closes(start: str, days: int, start_price: float = 100.0) -> pd.Series:
    idx = pd.date_range(start=start, periods=days, freq="D")
    return pd.Series([start_price + i for i in range(days)], index=idx)


def _pick_entry(closes: pd.Series, event_date: str) -> float | None:
    """Mirror of the selection rule in backfill_missing_entry_prices."""
    eligible = closes[closes.index <= pd.Timestamp(event_date)]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1])


def test_entry_never_comes_from_after_the_event_date() -> None:
    """A later price would let the entry drift toward a known outcome."""
    closes = _closes("2026-07-01", 40, start_price=100.0)
    entry = _pick_entry(closes, "2026-07-10")

    # 2026-07-10 is the 10th point, so 109.0.
    assert entry == 109.0
    later_prices = closes[closes.index > pd.Timestamp("2026-07-10")]
    assert all(entry < p for p in later_prices), (
        "entry must not be taken from a date after the call was made"
    )


def test_uses_last_close_on_or_before_the_event_date() -> None:
    """Weekends and holidays have no close; fall back, never forward."""
    closes = _closes("2026-07-01", 5)          # 1st-5th only
    entry = _pick_entry(closes, "2026-07-12")  # a date with no bar at all
    assert entry == 104.0, "should use the last close BEFORE the gap"


def test_a_call_older_than_all_price_history_stays_unresolved() -> None:
    """Better an honest gap than an invented entry."""
    closes = _closes("2026-07-01", 10)
    assert _pick_entry(closes, "2026-06-01") is None


def test_backfilled_rows_are_marked_and_observed_rows_are_not() -> None:
    from utils.db import prediction_log

    cols = {c.name for c in prediction_log.columns}
    assert "price_source" in cols, (
        "price_source must exist so a reconstructed entry can be told apart "
        "from one observed live"
    )

    source = (DASHBOARD / "utils" / "prediction_log.py").read_text(encoding="utf-8")
    assert 'price_source="backfilled"' in source, "backfilled rows must be tagged"
    assert 'price_source=("observed" if price is not None else None)' in source, (
        "live-fetched prices must be tagged observed"
    )


def test_track_record_discloses_a_reconstructed_entry() -> None:
    """A complete record that cannot be told apart from live data is worse than
    an incomplete one, for this product specifically."""
    page = (DASHBOARD / "pages" / "30_Track_Record_Live.py").read_text(encoding="utf-8")
    assert 'row.get("price_source") == "backfilled"' in page
    assert "est." in page, "the card must visibly mark a reconstructed entry"


def test_resolver_reports_why_it_did_nothing() -> None:
    """Returning 0 on failure looked identical to having nothing to do."""
    source = (DASHBOARD / "utils" / "prediction_log.py").read_text(encoding="utf-8")
    assert "[resolve] could not read pending predictions" in source
    assert "[backfill] price download failed" in source


def test_backfill_runs_before_resolution_selects_work() -> None:
    """Ordering matters: resolve_pending filters on price_at_event, so a row
    fixed after that query would wait another whole cycle."""
    source = (DASHBOARD / "utils" / "prediction_log.py").read_text(encoding="utf-8")
    body = source.split("def resolve_pending", 1)[1]
    backfill_at = body.find("backfill_missing_entry_prices(")
    select_at = body.find("prediction_log.c.price_at_event.isnot(None)")
    assert backfill_at != -1 and select_at != -1
    assert backfill_at < select_at, "backfill must run before pending rows are selected"


def test_the_lookahead_guard_is_actually_in_the_implementation() -> None:
    """The tests above assert the RULE via a local mirror of it.

    A mirror passes happily even if the real selection changes, so pin the
    comparison itself. This is the single line that keeps a reconstructed entry
    from drifting toward an outcome that was already known.
    """
    source = (DASHBOARD / "utils" / "prediction_log.py").read_text(encoding="utf-8")
    body = source.split("def backfill_missing_entry_prices", 1)[1].split("def resolve_pending", 1)[0]

    assert "closes[closes.index <= event_dt]" in body, (
        "entry selection must be bounded at or before event_date"
    )
    assert "closes.index >= event_dt" not in body
    assert "eligible.iloc[-1]" in body, "must take the LAST eligible close, not the first"
