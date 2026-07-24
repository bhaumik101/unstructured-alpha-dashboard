"""First-print (initial-release) FRED history and its wiring into the validation
pipeline.

The validation/backtest surfaces must only ever see data as it was known at the
time. fetch_fred_first_print() supplies each observation's INITIAL release
(ALFRED output_type=4); fetch_signal_series(..., point_in_time=True) routes FRED
signals through it while leaving non-revisable sources untouched; and
utils/validation_status.py consumes the point-in-time path so revised-in-hindsight
values can't inflate a signal's measured skill.

Offline unit tests mock the network; one opt-in live-contract test (skipped
without FRED_API_KEY) proves the real API still returns first prints that differ
from today's revisions.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from utils.fetchers import (
    fetch_fred, fetch_fred_first_print, fetch_signal_series, is_unavailable,
)

DASHBOARD = Path(__file__).resolve().parent.parent


def _mock_response(json_body):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = json_body
    return m


# output_type=4 rows carry realtime_start; a series can appear once (clean) or,
# defensively, more than once — we must keep the earliest realtime row.
FIRST_PRINT_FIXTURE = {
    "observations": [
        {"date": "2020-03-01", "value": "103.6635", "realtime_start": "2020-04-15"},
        {"date": "2020-06-01", "value": "97.4587", "realtime_start": "2020-07-15"},
        {"date": "2020-09-01", "value": "101.5055", "realtime_start": "2020-10-15"},
    ]
}


def test_first_print_parses_output_type_4_shape():
    fetch_fred_first_print.clear()
    with patch("utils.fetchers.resilient_get", return_value=_mock_response(FIRST_PRINT_FIXTURE)):
        s = fetch_fred_first_print("INDPRO", "2020-01-01", "2020-12-31", api_key="k")
    assert not is_unavailable(s)
    assert len(s) == 3
    assert s.attrs.get("first_print") is True
    assert float(s.loc["2020-06-01"]) == pytest.approx(97.4587)


def test_first_print_sends_initial_release_params():
    fetch_fred_first_print.clear()
    captured = {}

    def _spy(url, provider=None, params=None, timeout=None):
        captured.update(params or {})
        return _mock_response(FIRST_PRINT_FIXTURE)

    with patch("utils.fetchers.resilient_get", side_effect=_spy):
        fetch_fred_first_print("INDPRO", "2020-01-01", "2020-12-31", api_key="k")
    assert captured.get("output_type") == 4
    assert captured.get("realtime_start") == "1776-07-04"
    assert captured.get("realtime_end") == "9999-12-31"


def test_first_print_keeps_earliest_realtime_row_per_date():
    """If a date appears multiple times, the genuine first print is the earliest
    realtime_start — never a later revision."""
    fetch_fred_first_print.clear()
    dup = {"observations": [
        {"date": "2020-06-01", "value": "97.4587", "realtime_start": "2020-07-15"},
        {"date": "2020-06-01", "value": "91.5934", "realtime_start": "2021-03-01"},  # a revision
    ]}
    with patch("utils.fetchers.resilient_get", return_value=_mock_response(dup)):
        s = fetch_fred_first_print("INDPRO", "2020-06-01", "2020-06-30", api_key="k")
    assert len(s) == 1
    assert float(s.iloc[0]) == pytest.approx(97.4587)  # first print, not the revision


def test_first_print_unavailable_without_key():
    fetch_fred_first_print.clear()
    s = fetch_fred_first_print("INDPRO", "2020-01-01", "2020-12-31", api_key="")
    assert is_unavailable(s) and s.empty


def test_first_print_unavailable_on_empty_and_exception():
    fetch_fred_first_print.clear()
    with patch("utils.fetchers.resilient_get", return_value=_mock_response({"observations": []})):
        s = fetch_fred_first_print("INDPRO", "2020-01-01", "2020-12-31", api_key="k")
    assert is_unavailable(s)
    fetch_fred_first_print.clear()
    with patch("utils.fetchers.resilient_get", side_effect=ConnectionError("down")):
        s2 = fetch_fred_first_print("INDPRO", "2020-01-01", "2020-12-31", api_key="k")
    assert is_unavailable(s2)


# ── fetch_signal_series routing ──────────────────────────────────────────────

def test_signal_series_pit_routes_fred_to_first_print():
    cfg = {"source": "fred", "series_id": "INDPRO"}
    with patch("utils.fetchers.fetch_fred_first_print") as fp, \
         patch("utils.fetchers.fetch_fred") as latest, \
         patch("utils.fetchers._get_fred_key", return_value="k"):
        fp.return_value = pd.Series([1.0], index=pd.to_datetime(["2020-06-01"]), name="INDPRO")
        fetch_signal_series(cfg, "2020-01-01", "2020-12-31", point_in_time=True)
        fp.assert_called_once()
        latest.assert_not_called()


def test_signal_series_live_routes_fred_to_latest_revised():
    cfg = {"source": "fred", "series_id": "INDPRO"}
    with patch("utils.fetchers.fetch_fred_first_print") as fp, \
         patch("utils.fetchers.fetch_fred") as latest, \
         patch("utils.fetchers._get_fred_key", return_value="k"):
        latest.return_value = pd.Series([1.0], index=pd.to_datetime(["2020-06-01"]), name="INDPRO")
        fetch_signal_series(cfg, "2020-01-01", "2020-12-31", point_in_time=False)
        latest.assert_called_once()
        fp.assert_not_called()


def test_signal_series_pit_is_noop_for_non_fred_source():
    """point_in_time must NOT change or falsely claim vintage for prices, which
    aren't revised — it routes through the normal price path unchanged."""
    cfg = {"source": "yfinance", "series_id": "SPY"}
    with patch("utils.fetchers.fetch_price") as price, \
         patch("utils.fetchers.fetch_fred_first_print") as fp:
        price.return_value = pd.Series([100.0], index=pd.to_datetime(["2020-06-01"]), name="SPY")
        fetch_signal_series(cfg, "2020-01-01", "2020-12-31", point_in_time=True)
        price.assert_called_once()
        fp.assert_not_called()


def test_signal_series_pit_cache_key_distinct_from_live():
    """PIT and live results must not collide in the last-known-good cache."""
    import utils.fetchers as F
    cfg = {"source": "fred", "series_id": "INDPRO"}
    keys = []
    real_remember = F.remember_last_known_good

    def _spy_remember(cache_key, *a, **k):
        keys.append(cache_key)
        return None  # skip real caching side effects

    with patch.object(F, "remember_last_known_good", side_effect=_spy_remember), \
         patch.object(F, "_get_fred_key", return_value="k"), \
         patch.object(F, "fetch_fred",
                      return_value=pd.Series([1.0], index=pd.to_datetime(["2020-06-01"]), name="INDPRO")), \
         patch.object(F, "fetch_fred_first_print",
                      return_value=pd.Series([2.0], index=pd.to_datetime(["2020-06-01"]), name="INDPRO")):
        F.fetch_signal_series(cfg, "2020-01-01", "2020-12-31", point_in_time=False)
        F.fetch_signal_series(cfg, "2020-01-01", "2020-12-31", point_in_time=True)
    assert len(keys) == 2 and keys[0] != keys[1]
    assert keys[0].endswith(":live") and keys[1].endswith(":pit")


# ── validation pipeline actually consumes the point-in-time path ─────────────

def test_validation_status_requests_point_in_time():
    src = (DASHBOARD / "utils" / "validation_status.py").read_text(encoding="utf-8")
    assert src.count("point_in_time=True") >= 2, (
        "both backtest_all_macro_signals and the OOS validation must fetch "
        "first-print data, or the Model Validation numbers keep look-ahead bias"
    )
    assert "fetch_signal_series(cfg, start, end)\n" not in src, (
        "a bare latest-revised fetch_signal_series remains in the validation path"
    )


def test_model_validation_page_discloses_point_in_time():
    """The honesty claim on the page must stay coupled to the behavior: if the
    page advertises point-in-time/first-print, the pipeline must deliver it."""
    page = (DASHBOARD / "pages" / "11_Model_Validation.py").read_text(encoding="utf-8")
    assert "Point-in-time" in page and "first-print" in page.lower()


# ── Live contract: first print really differs from latest ────────────────────

@pytest.mark.skipif(not os.environ.get("FRED_API_KEY"),
                    reason="live FRED key not set; offline suite covers parsing")
def test_live_first_print_history_differs_from_latest():
    fetch_fred.clear(); fetch_fred_first_print.clear()
    key = os.environ["FRED_API_KEY"]
    fp = fetch_fred_first_print("INDPRO", "2020-01-01", "2020-12-31", api_key=key)
    lr = fetch_fred("INDPRO", "2020-01-01", "2020-12-31", api_key=key)
    assert not is_unavailable(fp) and not is_unavailable(lr)
    # June-2020 initial release ≈ 97.46; latest revised ≈ 91.59.
    assert float(fp.loc["2020-06-01"]) == pytest.approx(97.4587, abs=0.5)
    assert abs(float(fp.loc["2020-06-01"]) - float(lr.loc["2020-06-01"])) > 1.0
