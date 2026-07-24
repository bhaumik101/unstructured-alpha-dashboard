"""Tests for point-in-time FRED vintages (fetch_fred_asof) and the revision-bias
audit (utils/vintage_audit).

Two layers:
1. Offline unit tests with the network mocked — they lock the ALFRED parsing
   path and the pure divergence math, and prove nothing is ever fabricated.
2. One opt-in live-contract test (skipped without FRED_API_KEY) that asserts the
   real ALFRED API still returns a first-print vintage differing from the
   latest-revised value — the ground truth this whole feature rests on.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from utils.fetchers import fetch_fred, fetch_fred_asof, is_unavailable
from utils.vintage_audit import (
    revision_stats, fred_backed_signals, audit_series_asof,
    audit_series_first_print, audit_all_fred_signals, REVISION_EPS_PCT,
)


def _mock_response(json_body):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = json_body
    return m


VINTAGE_FIXTURE = {
    "observations": [
        {"date": "2020-06-01", "value": "97.4587"},
        {"date": "2020-07-01", "value": "98.1002"},
    ]
}


# ── fetch_fred_asof: parsing, honesty, cache keying ──────────────────────────

def test_asof_parses_vintage_shape_and_tags_attrs():
    fetch_fred_asof.clear()
    with patch("utils.fetchers.resilient_get", return_value=_mock_response(VINTAGE_FIXTURE)):
        s = fetch_fred_asof("INDPRO", "2020-06-01", "2020-07-31", "2020-07-15",
                            api_key="fake-key")
    assert not is_unavailable(s)
    assert len(s) == 2
    assert s.attrs.get("vintage") is True
    assert s.attrs.get("as_of") == "2020-07-15"


def test_asof_sends_realtime_params():
    """The whole point: realtime_start/realtime_end must be the as_of date, or we
    silently fetch the latest revision and the vintage is a lie."""
    fetch_fred_asof.clear()
    captured = {}

    def _spy(url, provider=None, params=None, timeout=None):
        captured.update(params or {})
        return _mock_response(VINTAGE_FIXTURE)

    with patch("utils.fetchers.resilient_get", side_effect=_spy):
        fetch_fred_asof("INDPRO", "2020-06-01", "2020-07-31", "2020-07-15",
                        api_key="fake-key")
    assert captured.get("realtime_start") == "2020-07-15"
    assert captured.get("realtime_end") == "2020-07-15"
    assert captured.get("observation_start") == "2020-06-01"


def test_asof_unavailable_without_key():
    fetch_fred_asof.clear()
    s = fetch_fred_asof("INDPRO", "2020-06-01", "2020-06-01", "2020-07-15", api_key="")
    assert is_unavailable(s) and s.empty


def test_asof_unavailable_without_as_of():
    fetch_fred_asof.clear()
    s = fetch_fred_asof("INDPRO", "2020-06-01", "2020-06-01", "", api_key="k")
    assert is_unavailable(s) and s.empty


def test_asof_unreleased_vintage_is_unavailable_not_invented():
    """If no vintage existed on as_of (series not yet published), the result is
    explicitly unavailable — never a fabricated placeholder."""
    fetch_fred_asof.clear()
    with patch("utils.fetchers.resilient_get",
               return_value=_mock_response({"observations": []})):
        s = fetch_fred_asof("INDPRO", "1900-01-01", "1900-01-01", "1900-02-01",
                            api_key="fake-key")
    assert is_unavailable(s)


def test_asof_unavailable_on_request_exception():
    fetch_fred_asof.clear()
    with patch("utils.fetchers.resilient_get", side_effect=ConnectionError("down")):
        s = fetch_fred_asof("INDPRO", "2020-06-01", "2020-06-01", "2020-07-15",
                            api_key="fake-key")
    assert is_unavailable(s)


def test_asof_cache_keyed_on_as_of():
    """Two different as_of dates must not collide in the shared cache."""
    fetch_fred_asof.clear()
    with patch("utils.fetchers.resilient_get", return_value=_mock_response(VINTAGE_FIXTURE)):
        a = fetch_fred_asof("X", "2020-01-01", "2020-02-01", "2020-02-15", api_key="k")
    with patch("utils.fetchers.resilient_get",
               return_value=_mock_response({"observations": [{"date": "2020-01-01", "value": "1.0"}]})):
        b = fetch_fred_asof("X", "2020-01-01", "2020-02-01", "2021-02-15", api_key="k")
    # Different as_of -> distinct cache entries -> distinct payloads.
    assert len(a) == 2 and len(b) == 1


# ── revision_stats: pure divergence math ─────────────────────────────────────

def test_revision_stats_detects_material_revision():
    idx = pd.to_datetime(["2020-06-01"])
    latest = pd.Series([91.5934], index=idx)
    vintage = pd.Series([97.4587], index=idx)
    r = revision_stats(latest, vintage)
    assert r["available"] and r["n_compared"] == 1
    assert r["is_revised"] is True
    # (91.5934 - 97.4587)/97.4587*100 ≈ -6.018
    assert r["mean_signed_pct"] == pytest.approx(-6.018, abs=0.01)
    assert r["mean_abs_pct"] == pytest.approx(6.018, abs=0.01)


def test_revision_stats_zero_when_no_revision():
    idx = pd.to_datetime(["2020-06-01", "2020-07-01"])
    s = pd.Series([100.0, 101.0], index=idx)
    r = revision_stats(s, s.copy())
    assert r["available"] and r["n_compared"] == 2
    assert r["is_revised"] is False
    assert r["mean_abs_pct"] == 0.0
    assert r["share_revised"] == 0.0


def test_revision_stats_aligns_on_common_dates_only():
    latest = pd.Series([1.0, 2.0, 3.0],
                       index=pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]))
    vintage = pd.Series([1.0, 2.2],
                        index=pd.to_datetime(["2020-02-01", "2020-03-01"]))
    r = revision_stats(latest, vintage)
    # Only Feb and Mar are common; Jan is dropped.
    assert r["n_common"] == 2 and r["n_compared"] == 2


def test_revision_stats_skips_zero_vintage_denominator():
    idx = pd.to_datetime(["2020-01-01", "2020-02-01"])
    latest = pd.Series([5.0, 6.0], index=idx)
    vintage = pd.Series([0.0, 6.0], index=idx)  # first point undefined pct
    r = revision_stats(latest, vintage)
    assert r["n_common"] == 2
    assert r["n_compared"] == 1  # the zero-denominator point is skipped


def test_revision_stats_empty_inputs_safe():
    r = revision_stats(pd.Series(dtype=float), pd.Series(dtype=float))
    assert r["available"] is False and r["n_compared"] == 0
    r2 = revision_stats(None, None)
    assert r2["available"] is False


def test_revision_stats_eps_threshold():
    idx = pd.to_datetime(["2020-01-01"])
    latest = pd.Series([100.02], index=idx)
    vintage = pd.Series([100.0], index=idx)  # 0.02% < eps 0.05% -> noise
    r = revision_stats(latest, vintage)
    assert r["is_revised"] is False
    assert REVISION_EPS_PCT == 0.05


# ── fred_backed_signals ──────────────────────────────────────────────────────

def test_fred_backed_signals_filters_source_fred():
    signals = {
        "a": {"source": "fred", "series_id": "INDPRO"},
        "b": {"source": "eia", "series_id": "WCESTUS1"},
        "c": {"source": "fred"},                # no series_id -> excluded
        "d": {"source": "yfinance", "series_id": "SPY"},
        "e": "not-a-dict",
    }
    out = fred_backed_signals(signals)
    assert out == {"a": "INDPRO"}


def test_fred_backed_signals_over_real_config_is_nonempty():
    out = fred_backed_signals()
    assert len(out) >= 20  # ~28 FRED signals in config
    assert all(isinstance(v, str) and v for v in out.values())


# ── audit_series_asof: honest on unavailability ──────────────────────────────

def test_audit_series_reports_unavailable_without_fabricating():
    with patch("utils.fetchers.resilient_get", side_effect=ConnectionError("down")):
        r = audit_series_asof("INDPRO", "2020-01-01", "2020-12-31", "2021-01-15",
                              api_key="fake-key")
    assert r["error"] == "unavailable"
    assert r["available"] is False
    assert r["series_id"] == "INDPRO"


# ── first-print audit + portfolio aggregate ──────────────────────────────────

def test_audit_series_first_print_reports_revision_magnitude():
    idx = pd.to_datetime(["2020-06-01", "2020-07-01"])
    latest = pd.Series([91.59, 92.0], index=idx, name="INDPRO")
    first = pd.Series([97.46, 92.1], index=idx, name="INDPRO")
    with patch("utils.fetchers.fetch_fred", return_value=latest), \
         patch("utils.fetchers.fetch_fred_first_print", return_value=first):
        r = audit_series_first_print("INDPRO", "2020-01-01", "2020-12-31", api_key="k")
    assert r["error"] is None and r["available"] and r["n_compared"] == 2
    assert r["is_revised"] is True
    assert r["series_id"] == "INDPRO"


def test_audit_series_first_print_unavailable_is_honest():
    empty = pd.Series(dtype=float); empty.attrs["fetch_error"] = True
    with patch("utils.fetchers.fetch_fred", return_value=empty), \
         patch("utils.fetchers.fetch_fred_first_print", return_value=empty):
        r = audit_series_first_print("X", "2020-01-01", "2020-12-31", api_key="k")
    assert r["error"] == "unavailable" and r["available"] is False


def test_audit_all_fred_signals_rolls_up_summary():
    signals = {
        "a": {"source": "fred", "series_id": "INDPRO", "name": "Industrial Production"},
        "b": {"source": "fred", "series_id": "DGS10", "name": "10-Year Treasury"},
        "c": {"source": "yfinance", "series_id": "SPY", "name": "S&P 500"},  # excluded
    }

    def _fake_audit(series_id, start, end, api_key=""):
        if series_id == "INDPRO":
            return {"series_id": "INDPRO", "error": None, "available": True,
                    "n_compared": 78, "mean_abs_pct": 4.26, "is_revised": True}
        if series_id == "DGS10":
            return {"series_id": "DGS10", "error": None, "available": True,
                    "n_compared": 125, "mean_abs_pct": 0.0, "is_revised": False}
        return {"series_id": series_id, "error": "unavailable", "available": False,
                "n_compared": 0, "mean_abs_pct": 0.0, "is_revised": False}

    with patch("utils.vintage_audit.audit_series_first_print", side_effect=_fake_audit):
        res = audit_all_fred_signals("2018-01-01", "2024-06-30", api_key="k", signals=signals)

    s = res["summary"]
    assert s["n_signals"] == 2                 # only FRED-backed
    assert s["n_measured"] == 2
    assert s["n_revised"] == 1                 # only INDPRO exceeded the noise floor
    assert s["worst_series"] == "INDPRO"
    assert s["max_abs_pct"] == 4.26
    assert s["mean_abs_pct"] == pytest.approx((4.26 + 0.0) / 2, abs=1e-6)
    # per_signal is sorted worst-first
    assert res["per_signal"][0]["series_id"] == "INDPRO"


def test_audit_all_fred_signals_counts_unavailable_not_zero_revision():
    signals = {"a": {"source": "fred", "series_id": "INDPRO", "name": "IP"}}

    def _unavail(series_id, start, end, api_key=""):
        return {"series_id": series_id, "error": "unavailable", "available": False,
                "n_compared": 0, "mean_abs_pct": 0.0, "is_revised": False}

    with patch("utils.vintage_audit.audit_series_first_print", side_effect=_unavail):
        res = audit_all_fred_signals("2018-01-01", "2024-06-30", api_key="", signals=signals)
    s = res["summary"]
    assert s["n_measured"] == 0 and s["n_unavailable"] == 1
    assert s["worst_series"] is None  # absence of data is not "no revision"


def test_data_trust_page_wires_the_revision_audit():
    """The Data Trust 'Revision Bias' section must actually call the aggregate —
    keeps the marketed page coupled to the real measurement."""
    page = (Path(__file__).resolve().parent.parent / "pages" / "48_Data_Trust.py").read_text(encoding="utf-8")
    assert "Revision Bias" in page
    assert "audit_all_fred_signals" in page


# ── Live contract (opt-in): ALFRED still revises a known series ───────────────

@pytest.mark.skipif(not os.environ.get("FRED_API_KEY"),
                    reason="live FRED key not set; offline suite covers parsing")
def test_live_alfred_vintage_differs_from_latest_for_indpro():
    fetch_fred.clear(); fetch_fred_asof.clear()
    key = os.environ["FRED_API_KEY"]
    latest = fetch_fred("INDPRO", "2020-06-01", "2020-06-01", api_key=key)
    vintage = fetch_fred_asof("INDPRO", "2020-06-01", "2020-06-01", "2020-07-15",
                              api_key=key)
    assert not is_unavailable(latest) and not is_unavailable(vintage)
    r = revision_stats(latest, vintage)
    assert r["available"] and r["is_revised"]  # INDPRO June-2020 was revised materially
