"""SEC EDGAR XBRL fundamentals.

Fixtures below are trimmed from the LIVE companyconcept payload for MSFT
(CIK 0000789019, PaymentsToAcquirePropertyPlantAndEquipment) captured
2026-08-02, including its real values and real filed dates. They are not
invented shapes — the two failure modes these guard against are exactly the
ones the live data produces.
"""

from __future__ import annotations

import pandas as pd
import pytest

from utils import sec_xbrl


class _Resp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


# Real MSFT rows. Note CY2026Q1 (discrete) sits alongside a 9-month YTD span
# carrying the SAME accession and NO frame key — that is the double-count trap.
_MSFT = {"units": {"USD": [
    {"start": "2025-01-01", "end": "2025-03-31", "val": 16745000000,
     "accn": "0000950170-25-061046", "filed": "2025-04-30", "frame": "CY2025Q1"},
    {"start": "2025-01-01", "end": "2025-03-31", "val": 16745000000,
     "accn": "0001193125-26-191507", "filed": "2026-04-29", "frame": "CY2025Q1"},
    {"start": "2025-07-01", "end": "2026-03-31", "val": 80146000000,
     "accn": "0001193125-26-191507", "filed": "2026-04-29"},               # YTD, no frame
    {"start": "2024-07-01", "end": "2025-06-30", "val": 64551000000,
     "accn": "0000950170-25-100235", "filed": "2025-07-30", "frame": "CY2025"},  # full year
    {"start": "2026-01-01", "end": "2026-03-31", "val": 30876000000,
     "accn": "0001193125-26-191507", "filed": "2026-04-29", "frame": "CY2026Q1"},
]}}


@pytest.fixture(autouse=True)
def _clear_caches():
    for fn in (sec_xbrl.fetch_sec_concept, sec_xbrl._ticker_to_cik):
        try: fn.clear()
        except Exception: pass
    yield


def _patch(monkeypatch, payload):
    monkeypatch.setattr(sec_xbrl, "resilient_get", lambda *a, **k: _Resp(payload))


def test_only_discrete_quarters_are_kept(monkeypatch):
    """YTD and full-year facts must not enter a quarterly series.

    Without the frame filter this sums to ~192bn for a company that spent
    ~30.9bn in the quarter — a 6x overstatement that would look like an
    AI-capex explosion rather than a parsing bug.
    """
    _patch(monkeypatch, _MSFT)
    s = sec_xbrl.fetch_sec_concept("0000789019", "PaymentsToAcquirePropertyPlantAndEquipment")
    assert list(s.index.strftime("%Y-%m-%d")) == ["2025-03-31", "2026-03-31"]
    assert s.loc["2026-03-31"] == 30876000000
    assert 80146000000 not in set(s.values)   # the YTD span
    assert 64551000000 not in set(s.values)   # the full year


def test_restatement_collapses_to_one_row_per_period(monkeypatch):
    _patch(monkeypatch, _MSFT)
    s = sec_xbrl.fetch_sec_concept("0000789019", "PaymentsToAcquirePropertyPlantAndEquipment")
    assert s.index.is_unique


def test_first_print_takes_the_earliest_filing(monkeypatch):
    """CY2025Q1 was filed 2025-04-30 and re-filed 2026-04-29.

    A backtest must see the 2025-04-30 vintage; using the later refiling leaks
    a year of hindsight, the same trap fetch_fred_first_print exists to avoid.
    """
    payload = {"units": {"USD": [
        {"end": "2025-03-31", "val": 111, "filed": "2025-04-30", "frame": "CY2025Q1"},
        {"end": "2025-03-31", "val": 999, "filed": "2026-04-29", "frame": "CY2025Q1"},
    ]}}
    _patch(monkeypatch, payload)
    first = sec_xbrl.fetch_sec_concept("0000789019", "X", first_print=True)
    assert first.loc["2025-03-31"] == 111
    sec_xbrl.fetch_sec_concept.clear()
    latest = sec_xbrl.fetch_sec_concept("0000789019", "X", first_print=False)
    assert latest.loc["2025-03-31"] == 999


def test_network_failure_degrades_to_empty_not_exception(monkeypatch):
    def boom(*a, **k): raise RuntimeError("SEC unreachable")
    monkeypatch.setattr(sec_xbrl, "resilient_get", boom)
    assert sec_xbrl.fetch_sec_concept("0000789019", "X").empty


def test_sum_drops_quarters_a_filer_has_not_reported(monkeypatch):
    """A partial sum reads as demand collapsing, not as a late filer."""
    monkeypatch.setattr(sec_xbrl, "_ticker_to_cik", lambda: {"AAA": "1", "BBB": "2"})
    def fake(cik, tag, taxonomy="us-gaap", unit="USD", first_print=False):
        idx = pd.to_datetime(["2025-03-31", "2025-06-30"])
        if cik == "1":
            return pd.Series([10.0, 20.0], index=idx)
        return pd.Series([5.0], index=idx[:1])          # BBB has not filed Q2
    monkeypatch.setattr(sec_xbrl, "fetch_sec_concept", fake)
    out = sec_xbrl.fetch_sec_concept_sum(["AAA", "BBB"], "TAG")
    assert list(out.index.strftime("%Y-%m-%d")) == ["2025-03-31"]
    assert out.iloc[0] == 15.0


def test_no_signal_cites_sec_while_reading_prices():
    """Regression guard for the actual bug this module was written to fix.

    hyperscaler_capex was named CapEx, cited to sec.gov, and computed an
    equal-weight share-price index. Nothing caught it because nothing checked
    that a signal's claimed source matches the source it reads.
    """
    from utils.config import SIGNALS
    offenders = [
        k for k, c in SIGNALS.items()
        if "sec.gov" in str(c.get("source_url", ""))
        and str(c.get("source", "")).startswith("yfinance")
    ]
    assert not offenders, f"signals citing SEC but reading prices: {offenders}"
