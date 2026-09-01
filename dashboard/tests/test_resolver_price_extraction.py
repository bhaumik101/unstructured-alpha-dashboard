"""The resolver read yfinance's columns with the two levels the wrong way round.

yf.download(..., group_by="ticker") produces columns (ticker, field), so "Close"
is the INNER key. Both callers in utils/prediction_log.py indexed
`frame["Close"][ticker]`, which raises KeyError: 'Close'.

It survived because on the pinned yfinance 0.2.x a SINGLE-ticker download drops
the ticker level, so the len(tickers) == 1 branch worked and anything exercised
with one ticker passed. resolve_pending() batches every distinct pending ticker,
so production always took the multi-ticker path and raised on every row.

Observed on 2026-09-01: 202 calls logged since 2026-07-09, zero ever resolved,
the page reporting "no call has reached 4 weeks yet" directly above cards that
said "4w window passed", and the resolver-health panel reading "None stuck"
because its only alarm cannot fire until a call is thirteen weeks old.

utils/quotes.py had the layout right all along and documents it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.prediction_log import close_series_for  # noqa: E402

_IDX = pd.date_range("2026-06-01", periods=40, freq="B")


def _grouped_by_ticker(tickers):
    """Exactly what yf.download(group_by='ticker') returns: (ticker, field)."""
    cols = pd.MultiIndex.from_product([tickers, ["Open", "High", "Low", "Close", "Volume"]])
    data = {}
    for i, t in enumerate(tickers):
        for f in ["Open", "High", "Low", "Close", "Volume"]:
            data[(t, f)] = [100.0 + i * 10 + n for n in range(len(_IDX))]
    return pd.DataFrame(data, index=_IDX, columns=cols)


def test_extracts_close_from_the_real_multi_ticker_layout():
    frame = _grouped_by_ticker(["AAPL", "MSFT"])
    aapl = close_series_for(frame, "AAPL")
    msft = close_series_for(frame, "MSFT")
    assert len(aapl) == len(_IDX) and len(msft) == len(_IDX)
    assert float(aapl.iloc[0]) == 100.0
    assert float(msft.iloc[0]) == 110.0, "must return THIS ticker's column, not another's"


def test_the_old_inverted_indexing_really_does_raise():
    """Guards the premise: if this ever stops raising, the bug was elsewhere."""
    frame = _grouped_by_ticker(["AAPL", "MSFT"])
    with pytest.raises(KeyError):
        frame["Close"]["AAPL"]


def test_extracts_close_when_a_single_ticker_keeps_its_level():
    """yfinance 1.x keeps the ticker level even for one ticker; 0.2.x drops it.
    Both shapes must work -- branching on len(tickers) is what broke this."""
    assert len(close_series_for(_grouped_by_ticker(["AAPL"]), "AAPL")) == len(_IDX)


def test_extracts_close_when_the_ticker_level_was_dropped():
    flat = pd.DataFrame({"Open": 1.0, "Close": [100.0 + n for n in range(len(_IDX))]}, index=_IDX)
    assert len(close_series_for(flat, "AAPL")) == len(_IDX)


def test_extracts_close_from_a_field_first_layout():
    """group_by='column' produces (field, ticker). Support it rather than raise."""
    cols = pd.MultiIndex.from_product([["Open", "Close"], ["AAPL", "MSFT"]])
    frame = pd.DataFrame(
        {(f, t): [100.0 + n for n in range(len(_IDX))] for f in ["Open", "Close"]
         for t in ["AAPL", "MSFT"]},
        index=_IDX, columns=cols,
    )
    assert len(close_series_for(frame, "MSFT")) == len(_IDX)


def test_a_missing_or_empty_frame_yields_an_empty_series_not_an_exception():
    """The caller counts this as a named failure; it must never raise."""
    assert close_series_for(_grouped_by_ticker(["AAPL"]), "ZZZZ").empty
    assert close_series_for(pd.DataFrame(), "AAPL").empty
    assert close_series_for(None, "AAPL").empty


def test_nans_are_dropped_so_asof_cannot_read_a_hole():
    cols = pd.MultiIndex.from_product([["AAPL"], ["Close"]])
    vals = [100.0] * len(_IDX)
    vals[5] = float("nan")
    frame = pd.DataFrame({("AAPL", "Close"): vals}, index=_IDX, columns=cols)
    assert len(close_series_for(frame, "AAPL")) == len(_IDX) - 1


# ── the alarm that should have fired ────────────────────────────────────────

def test_health_counts_calls_past_four_weeks_with_no_outcome():
    """#207 removed the 4-week 'overdue' count, correctly -- a call stays pending
    until twelve weeks by design. But that left no signal able to fire before
    thirteen weeks. This one is different: it counts a missing four-week
    OUTCOME, which is written the moment that window closes."""
    from datetime import datetime, timedelta, timezone
    import utils.prediction_log as pl

    now = datetime.now(timezone.utc)
    old = (now - timedelta(weeks=6)).strftime("%Y-%m-%d")
    recent = (now - timedelta(weeks=1)).strftime("%Y-%m-%d")
    rows = [
        {"status": "pending", "event_date": old,    "correct_4w": None},   # counted
        {"status": "pending", "event_date": old,    "correct_4w": 1},      # written, fine
        {"status": "pending", "event_date": recent, "correct_4w": None},   # too new
    ]

    class _Conn:
        def execute(self, *a, **k):
            class _R:
                def mappings(self_inner): return self_inner
                def all(self_inner): return rows
            return _R()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Engine:
        def begin(self): return _Conn()

    import unittest.mock as _m
    with _m.patch.object(pl.db, "engine", _Engine()):
        health = pl.get_resolver_health()

    assert health["awaiting_4w_outcome"] == 1, (
        "exactly the row past its 4-week window with no result should count"
    )


def test_the_page_does_not_claim_no_call_reached_four_weeks_when_some_have():
    source = (_ROOT / "pages" / "30_Track_Record_Live.py").read_text(encoding="utf-8")
    assert "_acc_4w_note" in source, "the note must be computed, not hardcoded"
    note = source[source.index("_acc_4w_note = ("):]
    note = note[:note.index(")\n") + 1]
    assert "awaiting_4w_outcome" in source
    assert "no call has reached 4 weeks yet" in note and "past 4w with no result" in note, (
        "the missing-accuracy caption must distinguish 'nothing is old enough' "
        "from 'the resolver has not written', which are opposite diagnoses"
    )
    # ...and it must actually BRANCH on the count. Asserting only that both
    # strings appear passes even when the condition is replaced by a constant,
    # which is exactly the reassuring-by-default bug being fixed.
    assert "_await_4w_n == 0" in note, (
        "the caption must choose between the two diagnoses using the real count"
    )
