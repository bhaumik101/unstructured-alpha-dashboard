"""
Unit tests for utils/portfolio_xray.py — the Portfolio Macro X-Ray engine
(Point 2). HERMETIC: stubs utils.config so the aggregation math is validated in
isolation against hand-computed ground truth (no DB, no network, no yfinance).
"""

import sys
import types
import math

import pytest

_stub = types.ModuleType("utils.config")
_stub.CATEGORIES = {
    "macro": {"name": "Macro & Liquidity"},
    "financials": {"name": "Financials & Credit"},
    "energy": {"name": "Energy & Oil"},
    "ai_infrastructure": {"name": "AI Infrastructure"},
}
_stub.SIGNALS = {
    "ten_year_yield":    {"category": "macro", "name": "10-Year Yield"},
    "vix":               {"category": "macro", "name": "VIX"},
    "hy_spread":         {"category": "financials", "name": "High-Yield Spread"},
    "ig_credit":         {"category": "financials", "name": "IG Credit"},
    "crude_oil":         {"category": "energy", "name": "Crude Oil"},
    "semiconductor_etf": {"category": "ai_infrastructure", "name": "Semiconductor Capex"},
}
sys.modules.setdefault("utils.config", _stub)

from utils import portfolio_xray as px  # noqa: E402


def _H(t, sec, corr, scr, score):
    return {"ticker": t, "sector": sec, "corr_info": corr, "signal_scores": scr, "score": score}


def test_holding_factor_profile():
    corr = {"ten_year_yield": {"weight": 2.0, "significant": True},
            "hy_spread": {"weight": 1.0, "significant": True},
            "crude_oil": {"weight": 5.0, "significant": False}}   # excluded (not significant)
    scr = {"ten_year_yield": {"score": 40}, "hy_spread": {"score": 60}, "crude_oil": {"score": 90}}
    prof = px.holding_factor_profile(corr, scr)
    assert math.isclose(prof["macro"]["exposure"], 2 / 3, abs_tol=0.001)
    assert math.isclose(prof["financials"]["exposure"], 1 / 3, abs_tol=0.001)
    assert "energy" not in prof                       # insignificant signal excluded
    assert prof["macro"]["direction"] == 40.0
    assert math.isclose(sum(v["exposure"] for v in prof.values()), 1.0, abs_tol=0.01)


def _portfolio():
    c_tech = {"semiconductor_etf": {"weight": 2.0, "significant": True},
              "ten_year_yield": {"weight": 2.0, "significant": True}}
    s_tech = {"semiconductor_etf": {"score": 70}, "ten_year_yield": {"score": 40}}
    c_fin = {"hy_spread": {"weight": 3.0, "significant": True},
             "ig_credit": {"weight": 1.0, "significant": True}}
    s_fin = {"hy_spread": {"score": 40}, "ig_credit": {"score": 42}}
    return [_H("NVDA", "Technology", c_tech, s_tech, 62),
            _H("AMZN", "Consumer", c_tech, s_tech, 60),   # identical macro profile, different sector
            _H("JPM", "Financials", c_fin, s_fin, 41)]


def test_portfolio_aggregation():
    pl = px.build_portfolio_xray(_portfolio(), prior_portfolio_score=50)
    assert pl["n_holdings"] == 3
    assert pl["portfolio_score"] == 54.3          # (62+60+41)/3
    assert pl["score_delta"] == 4.3               # 54.3 - 50
    fac = {r["factor"]: r for r in pl["factors"]}
    assert fac["ai_infrastructure"]["pct_holdings"] == 67 and fac["ai_infrastructure"]["kind"] == "tailwind"
    assert fac["macro"]["pct_holdings"] == 67 and fac["macro"]["kind"] == "risk"          # dir 40
    assert fac["financials"]["pct_holdings"] == 33 and fac["financials"]["kind"] == "risk"
    assert "ai_infrastructure" in [r["factor"] for r in pl["tailwinds"]]
    assert {"macro", "financials"} <= set(r["factor"] for r in pl["risks"])


def test_most_exposed_and_hidden_correlations():
    pl = px.build_portfolio_xray(_portfolio())
    assert pl["most_vulnerable"]["ticker"] == "JPM"
    assert pl["most_vulnerable"]["driver"] == "Financials & Credit"
    assert pl["most_supported"]["ticker"] == "NVDA"
    hc = pl["hidden_correlations"]
    assert any(set(h["pair"]) == {"NVDA", "AMZN"} for h in hc)
    assert hc[0]["similarity"] >= 0.99            # identical profiles
    assert set(hc[0]["sectors"]) == {"Technology", "Consumer"}


def test_exposure_threshold():
    c_thin = {"hy_spread": {"weight": 10.0, "significant": True},
              "crude_oil": {"weight": 1.0, "significant": True}}   # energy ~9% share < 12%
    s_thin = {"hy_spread": {"score": 45}, "crude_oil": {"score": 80}}
    pl = px.build_portfolio_xray([_H("X", "Fin", c_thin, s_thin, 46)])
    fac = {r["factor"]: r for r in pl["factors"]}
    assert fac["energy"]["n_exposed"] == 0        # below EXPOSURE_THRESHOLD
    assert fac["financials"]["n_exposed"] == 1


def test_empty_and_render():
    e = px.build_portfolio_xray([])
    assert e["empty"] is True and e["portfolio_score"] is None
    assert "Add a few holdings" in px.render_portfolio_xray_html(e)
    html = px.render_portfolio_xray_html(px.build_portfolio_xray(_portfolio()))
    assert "54.3" in html and "Portfolio Macro Score" in html
    assert "Hidden correlations" in html
    assert "not advice" in html.lower()
    assert html.count("<div") >= html.count("</div")
