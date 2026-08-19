"""
Unit tests for utils/portfolio_xray.py — the Portfolio Macro X-Ray engine.
Now factor grouping is by MACRO-FACTOR FAMILY (Rates / Credit / Capex&Tech / …)
via utils.taxonomy, not the old sector `category`. The taxonomy is stubbed so
the aggregation fixtures stay compact; the real registry coverage is proven
separately in test_foundation_unit.py.
"""

import sys
import types
import math

import pytest

# stub taxonomy — maps the test's signal ids to real macro factor families
_tax = types.ModuleType("utils.taxonomy")
_tax.FACTOR_FAMILIES = {
    "capex_tech": {"name": "Capex & Technology"},
    "rates": {"name": "Rates"},
    "credit": {"name": "Credit"},
    "energy": {"name": "Energy"},
}
_SIGNAL_FACTOR = {
    "semiconductor_etf": "capex_tech", "ten_year_yield": "rates",
    "hy_spread": "credit", "ig_credit": "credit", "crude_oil": "energy",
}
_tax.factor_family_of = lambda s: _SIGNAL_FACTOR.get(s, "growth")
_tax.factor_family_name = lambda f: (_tax.FACTOR_FAMILIES.get(f) or {}).get("name", f.replace("_", " ").title())
import utils as _utils_pkg
_real_tax_mod  = sys.modules.get("utils.taxonomy")
_real_tax_attr = getattr(_utils_pkg, "taxonomy", None)
sys.modules["utils.taxonomy"] = _tax
_utils_pkg.taxonomy = _tax

from utils import portfolio_xray as px  # noqa: E402

# Put the real utils.taxonomy back. px.taxonomy stays bound to the stub
# above -- that is the point of it -- but leaving the stub in sys.modules AND on
# the utils package object poisons every module imported later in the same
# xdist worker. It surfaced as seo/main.py failing to collect with
# "cannot import name 'category_display' from 'utils.taxonomy' (unknown
# location)", which reads like a path bug and is not one.
if _real_tax_mod is not None:
    sys.modules["utils.taxonomy"] = _real_tax_mod
else:
    sys.modules.pop("utils.taxonomy", None)
if _real_tax_attr is not None:
    _utils_pkg.taxonomy = _real_tax_attr
else:
    try:
        del _utils_pkg.taxonomy
    except AttributeError:
        pass



def _H(t, sec, corr, scr, score):
    return {"ticker": t, "sector": sec, "corr_info": corr, "signal_scores": scr, "score": score}


def test_holding_factor_profile_by_family():
    corr = {"ten_year_yield": {"weight": 2.0, "significant": True},
            "hy_spread": {"weight": 1.0, "significant": True},
            "crude_oil": {"weight": 5.0, "significant": False}}   # excluded
    scr = {"ten_year_yield": {"score": 40}, "hy_spread": {"score": 60}, "crude_oil": {"score": 90}}
    prof = px.holding_factor_profile(corr, scr)
    assert math.isclose(prof["rates"]["exposure"], 2 / 3, abs_tol=0.001)
    assert math.isclose(prof["credit"]["exposure"], 1 / 3, abs_tol=0.001)
    assert "energy" not in prof
    assert prof["rates"]["direction"] == 40.0


def _portfolio():
    c_tech = {"semiconductor_etf": {"weight": 2.0, "significant": True},
              "ten_year_yield": {"weight": 2.0, "significant": True}}
    s_tech = {"semiconductor_etf": {"score": 70}, "ten_year_yield": {"score": 40}}
    c_fin = {"hy_spread": {"weight": 3.0, "significant": True},
             "ig_credit": {"weight": 1.0, "significant": True}}
    s_fin = {"hy_spread": {"score": 40}, "ig_credit": {"score": 42}}
    return [_H("NVDA", "Technology", c_tech, s_tech, 62),
            _H("AMZN", "Consumer", c_tech, s_tech, 60),   # identical macro profile
            _H("JPM", "Financials", c_fin, s_fin, 41)]


def test_portfolio_factor_families():
    pl = px.build_portfolio_xray(_portfolio(), prior_portfolio_score=50)
    assert pl["portfolio_score"] == 54.3 and pl["score_delta"] == 4.3
    fac = {r["factor"]: r for r in pl["factors"]}
    assert fac["capex_tech"]["pct_holdings"] == 67 and fac["capex_tech"]["kind"] == "tailwind"
    assert fac["rates"]["pct_holdings"] == 67 and fac["rates"]["kind"] == "risk"
    assert fac["credit"]["pct_holdings"] == 33 and fac["credit"]["kind"] == "risk"
    assert "capex_tech" in [r["factor"] for r in pl["tailwinds"]]
    assert {"rates", "credit"} <= set(r["factor"] for r in pl["risks"])
    # factor names render as real macro families, not sector enums
    assert any(r["name"] == "Rates" for r in pl["factors"])


def test_portfolio_score_and_exposure_respect_position_weights():
    positions = _portfolio()
    positions[0]["weight"] = 80
    positions[1]["weight"] = 10
    positions[2]["weight"] = 10
    pl = px.build_portfolio_xray(positions)
    assert pl["portfolio_score"] == 59.7
    factors = {row["factor"]: row for row in pl["factors"]}
    assert factors["rates"]["pct_portfolio"] == 90
    assert factors["credit"]["pct_portfolio"] == 10
    assert {row["ticker"]: row["weight_pct"] for row in pl["holdings"]} == {
        "AMZN": 10.0, "JPM": 10.0, "NVDA": 80.0,
    }


def test_most_exposed_and_hidden_correlations():
    pl = px.build_portfolio_xray(_portfolio())
    assert pl["most_vulnerable"]["ticker"] == "JPM"
    assert pl["most_vulnerable"]["driver"] == "Credit"          # factor-family name
    assert pl["most_supported"]["ticker"] == "NVDA"
    hc = pl["hidden_correlations"]
    assert any(set(h["pair"]) == {"NVDA", "AMZN"} for h in hc)
    assert hc[0]["similarity"] >= 0.99
    assert set(hc[0]["sectors"]) == {"Technology", "Consumer"}


def test_exposure_threshold():
    c_thin = {"hy_spread": {"weight": 10.0, "significant": True},
              "crude_oil": {"weight": 1.0, "significant": True}}   # energy ~9% < 12%
    s_thin = {"hy_spread": {"score": 45}, "crude_oil": {"score": 80}}
    pl = px.build_portfolio_xray([_H("X", "Fin", c_thin, s_thin, 46)])
    fac = {r["factor"]: r for r in pl["factors"]}
    assert fac["energy"]["n_exposed"] == 0
    assert fac["credit"]["n_exposed"] == 1


def test_empty_and_render():
    e = px.build_portfolio_xray([])
    assert e["empty"] is True and e["portfolio_score"] is None
    assert "Add a few holdings" in px.render_portfolio_xray_html(e)
    html = px.render_portfolio_xray_html(px.build_portfolio_xray(_portfolio()))
    assert "54.3" in html and "Portfolio Macro Score" in html
    assert "not advice" in html.lower()
    assert html.count("<div") >= html.count("</div")
