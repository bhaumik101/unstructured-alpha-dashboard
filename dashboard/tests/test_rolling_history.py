"""The rolling line reaches back up to ten years; the headline does not move.

What must hold:
  * the headline reading is identical whether ten years of data are fetched or
    only the three it is measured on -- the longer history feeds the rolling
    line and nothing else;
  * the rolling line spans well beyond the old two years, so a relationship
    that changed outside the headline window is visible on it;
  * it starts no earlier than the youngest holding's prices -- earlier weeks
    are left out, never filled in;
  * a long line is drawn with an evidence strip and year labels instead of
    dots that would merge into a bar.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import exposure as ex  # noqa: E402
from utils import report_charts as charts  # noqa: E402

END = date(2026, 9, 11)
FLIP = pd.Timestamp("2021-01-01")   # well before the headline's three years


def _world(days=2700, young_days=None):
    rng = np.random.default_rng(5)
    idx = pd.bdate_range(end=str(END), periods=days)
    n = len(idx)
    mkt = rng.normal(0.04, 1.0, n)
    ch = {"rates": rng.normal(0, .05, n), "inflation": rng.normal(0, .025, n),
          "dollar": rng.normal(0, .4, n), "oil": rng.normal(0, 1.8, n), "credit": rng.normal(0, .02, n)}

    def P(r):
        return pd.Series(100 * np.cumprod(1 + r / 100), idx)

    oil_beta = np.where(idx < FLIP, -0.4, 0.4)
    prices = {"SPY": P(mkt),
              "XOM": P(.8 * mkt + oil_beta * ch["oil"] + rng.normal(0, .6, n)),
              "VTI": P(mkt + rng.normal(0, .2, n))}
    if young_days:
        prices["VTI"] = prices["VTI"].iloc[-young_days:]
    levels = {"DGS10": pd.Series(4 + np.cumsum(ch["rates"]), idx),
              "T10YIE": pd.Series(2.3 + np.cumsum(ch["inflation"]), idx),
              "DTWEXBGS": pd.Series(120 * np.cumprod(1 + ch["dollar"] / 100), idx),
              "DCOILWTICO": pd.Series(80 * np.cumprod(1 + ch["oil"] / 100), idx),
              "BAA10Y": pd.Series(1.8 + np.cumsum(ch["credit"]), idx),
              "INDPRO": pd.Series(100 * np.cumprod(1 + rng.normal(0, .5, 60) / 100),
                                  pd.date_range(end="2026-08-01", periods=60, freq="MS"))}
    return prices, levels


def _report(prices, levels, keep_days=None):
    def pf(tickers, start, end):
        return {t: (prices[t].iloc[-keep_days:] if keep_days else prices[t])
                for t in tickers if t in prices}

    def sf(sid, start, end):
        s = levels[sid]
        return s.iloc[-keep_days:] if keep_days and sid != "INDPRO" else s

    holdings = [{"ticker": "XOM", "weight_pct": 50}, {"ticker": "VTI", "weight_pct": 50}]
    report = ex.build_exposure_report(holdings, pf, sf, end=END)
    assert report["status"] == "ok", report
    return report


def test_the_headline_is_identical_with_three_years_or_ten():
    prices, levels = _world()
    long_, short = _report(prices, levels), _report(prices, levels, keep_days=900)
    assert long_["portfolio"]["readings"] == short["portfolio"]["readings"]
    assert long_["contributions"] == short["contributions"]
    assert long_["series"] == short["series"]


def test_the_rolling_line_reaches_back_past_the_headline_window():
    prices, levels = _world()
    report = _report(prices, levels)
    oil = report["rolling"]["oil"]
    first, last = pd.Timestamp(oil[0]["end"]), pd.Timestamp(oil[-1]["end"])
    assert (last - first).days > 7 * 365          # was ~2 years before
    assert oil[-1]["end"] == report["as_of"]       # the last point is still "now"
    # The flip happened outside the headline window, so only the long line can
    # show it: negative before, positive now. (50% weight x -/+0.4 x 10% oil.)
    before = [p["impact"] for p in oil if pd.Timestamp(p["end"]) < FLIP]
    assert before and np.median(before) < -1.0 < 1.0 < oil[-1]["impact"]
    assert report["portfolio"]["readings"]["oil"]["impact"] > 0
    assert report["method"]["history_weeks"] > ex.WINDOW_WEEKS


def test_the_line_starts_where_the_youngest_holding_has_prices():
    prices, levels = _world(young_days=1300)       # VTI: ~5 years
    report = _report(prices, levels)
    first = pd.Timestamp(report["rolling"]["oil"][0]["end"])
    vti_start = prices["VTI"].index[0]
    assert first >= vti_start + pd.Timedelta(weeks=ex.ROLLING_WEEKS - 1)


def test_a_long_line_has_an_evidence_strip_and_year_labels_not_merged_dots():
    prices, levels = _world()
    report = _report(prices, levels)
    points = report["rolling"]["oil"]
    svg = charts.rolling_panel_svg("oil", "Oil", points)
    assert "<circle" not in svg
    assert 'class="uac-strip"' in svg
    years = {str(y) for y in range(2018, 2027)}
    assert sum(f">{y}<" in svg for y in years) >= 3
    assert "Clear in" in svg                       # the strip is also said in words


def test_a_short_line_keeps_its_dots():
    points = [{"end": f"2026-0{m}-01", "impact": 1.0 + m, "low": 0.5, "high": 2.0 + m,
               "evidence": "clear"} for m in range(1, 8)]
    svg = charts.rolling_panel_svg("oil", "Oil", points)
    assert svg.count("<circle") == 7 and 'class="uac-strip"' not in svg
