"""
Unit tests for utils/fetchers.py's parsing logic, with the network layer
mocked out — these run offline and verify two things:

1. fetch_fred() / fetch_eia() correctly parse a real response shape into a
   clean pandas Series and mark s.attrs["synthetic"] = False.
2. When no API key is configured, both fall back to synthetic data marked
   s.attrs["synthetic"] = True — the contract every page on this site
   depends on to decide whether to show the "DEMO DATA" banner.

The EIA response fixture below is the exact JSON shape captured live from
api.eia.gov/v2/seriesid/PET.WCESTUS1.W with a real key (verified directly
against the live API, not assumed) — this locks that parsing path in so a
future change to fetch_eia() can't silently break it.
"""

from unittest.mock import patch, MagicMock

import pandas as pd
import streamlit as st

from utils.fetchers import (
    fetch_fred, fetch_eia, fetch_fda_approval_velocity, fetch_live_quote,
    is_synthetic, _synthetic_signal,
)


EIA_RESPONSE_FIXTURE = {
    "response": {
        "total": 2,
        "dateFormat": "YYYY-MM-DD",
        "frequency": "weekly",
        "data": [
            {
                "period": "2026-06-12", "duoarea": "NUS", "area-name": "U.S.",
                "product": "EPC0", "product-name": "Crude Oil",
                "process": "SAX", "process-name": "Ending Stocks Excluding SPR",
                "series": "WCESTUS1",
                "series-description": "U.S. Ending Stocks excluding SPR of Crude Oil (Thousand Barrels)",
                "value": 418222, "units": "MBBL",
            },
            {
                "period": "2026-06-05", "duoarea": "NUS", "area-name": "U.S.",
                "product": "EPC0", "product-name": "Crude Oil",
                "process": "SAX", "process-name": "Ending Stocks Excluding SPR",
                "series": "WCESTUS1",
                "series-description": "U.S. Ending Stocks excluding SPR of Crude Oil (Thousand Barrels)",
                "value": 426485, "units": "MBBL",
            },
        ],
    }
}

FRED_RESPONSE_FIXTURE = {
    "observations": [
        {"date": "2026-06-01", "value": "100.5"},
        {"date": "2026-06-08", "value": "101.2"},
    ]
}


def _mock_response(json_body):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = json_body
    return m


def test_fetch_eia_parses_real_response_shape_when_key_present():
    st.session_state["EIA_API_KEY"] = "fake-key-for-test"
    fetch_eia.clear()  # bypass @st.cache_data between test runs
    with patch("utils.fetchers.requests.get", return_value=_mock_response(EIA_RESPONSE_FIXTURE)):
        s = fetch_eia("PET.WCESTUS1.W", "2026-01-01", "2026-12-31")
    assert not is_synthetic(s)
    assert len(s) == 2
    assert float(s.iloc[-1]) == 418222.0  # most recent period, sorted ascending
    del st.session_state["EIA_API_KEY"]


def test_fetch_eia_falls_back_to_synthetic_without_key():
    st.session_state.pop("EIA_API_KEY", None)
    fetch_eia.clear()
    s = fetch_eia("PET.WCESTUS1.W", "2024-01-01", "2024-06-01")
    assert is_synthetic(s)


def test_fetch_eia_falls_back_to_synthetic_on_request_exception():
    st.session_state["EIA_API_KEY"] = "fake-key-for-test"
    fetch_eia.clear()
    with patch("utils.fetchers.requests.get", side_effect=ConnectionError("network down")):
        s = fetch_eia("PET.WCESTUS1.W", "2024-01-01", "2024-06-01")
    assert is_synthetic(s)
    del st.session_state["EIA_API_KEY"]


def test_fetch_fred_parses_real_response_shape_when_key_present():
    st.session_state["FRED_API_KEY"] = "fake-key-for-test"
    fetch_fred.clear()
    with patch("utils.fetchers.requests.get", return_value=_mock_response(FRED_RESPONSE_FIXTURE)):
        s = fetch_fred("SOME_SERIES", "2026-01-01", "2026-12-31")
    assert not is_synthetic(s)
    assert len(s) == 2
    del st.session_state["FRED_API_KEY"]


def test_fetch_fred_falls_back_to_synthetic_without_key():
    st.session_state.pop("FRED_API_KEY", None)
    fetch_fred.clear()
    s = fetch_fred("SOME_SERIES", "2024-01-01", "2024-06-01")
    assert is_synthetic(s)


def test_synthetic_signal_is_marked_synthetic():
    s = _synthetic_signal("ANY_ID", "2024-01-01", "2024-06-01")
    assert is_synthetic(s)
    assert not s.empty


# ── openFDA drug approval velocity ───────────────────────────────────────────

OPENFDA_RESPONSE_FIXTURE = {
    "meta": {"results": {"total": 25368}},
    "results": [
        {
            "submissions": [
                {"submission_type": "ORIG", "submission_status": "AP", "submission_status_date": "20260612"},
            ]
        },
        {
            "submissions": [
                {"submission_type": "ORIG", "submission_status": "AP", "submission_status_date": "20260605"},
                {"submission_type": "SUPPL", "submission_status": "PEND", "submission_status_date": "20260701"},
            ]
        },
    ],
}


def test_fetch_fda_approval_velocity_parses_real_response_shape():
    fetch_fda_approval_velocity.clear()
    with patch("utils.fetchers.requests.get", return_value=_mock_response(OPENFDA_RESPONSE_FIXTURE)):
        s = fetch_fda_approval_velocity()
    assert not s.empty
    assert s.sum() == 2  # two AP-status submissions in the fixture; the PEND one must be excluded


def test_fetch_fda_approval_velocity_falls_back_to_empty_on_request_exception():
    fetch_fda_approval_velocity.clear()
    with patch("utils.fetchers.requests.get", side_effect=ConnectionError("network down")):
        s = fetch_fda_approval_velocity()
    assert s.empty


# ── live quote (st.fragment auto-refresh feature) ────────────────────────────

def test_fetch_live_quote_parses_fast_info():
    fetch_live_quote.clear()
    mock_fast_info = {"lastPrice": 190.5, "previousClose": 188.0}
    mock_ticker = MagicMock()
    mock_ticker.fast_info = mock_fast_info
    with patch("utils.fetchers.yf.Ticker", return_value=mock_ticker):
        q = fetch_live_quote("AAPL")
    assert q["price"] == 190.5
    assert q["prev_close"] == 188.0
    assert round(q["pct_change"], 4) == round((190.5 - 188.0) / 188.0 * 100, 4)


def test_fetch_live_quote_handles_missing_price():
    fetch_live_quote.clear()
    mock_ticker = MagicMock()
    mock_ticker.fast_info = {"previousClose": 188.0}  # no lastPrice
    with patch("utils.fetchers.yf.Ticker", return_value=mock_ticker):
        q = fetch_live_quote("AAPL")
    assert q == {"price": None, "prev_close": None, "pct_change": None}


def test_fetch_live_quote_falls_back_on_exception():
    fetch_live_quote.clear()
    with patch("utils.fetchers.yf.Ticker", side_effect=ConnectionError("network down")):
        q = fetch_live_quote("AAPL")
    assert q == {"price": None, "prev_close": None, "pct_change": None}
