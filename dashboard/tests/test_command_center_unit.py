"""
Unit tests for utils/command_center.py — the signed-in home assembler
(Phase 2). Pure: it only consumes Portfolio X-Ray + What Changed payloads, so
no config/taxonomy/DB stubs are needed. Ground-truth priority: a holding whose
macro backdrop MATERIALLY changed outranks standing exposure concentration.
"""

from utils import command_center as cc


_XRAY = {
    "n_holdings": 3, "empty": False,
    "risks": [{"name": "Rates", "pct_holdings": 67, "n_exposed": 2,
               "exposed_tickers": ["NVDA", "AMZN"], "avg_direction": 40}],
    "most_vulnerable": {"ticker": "JPM", "score": 41, "driver": "Credit"},
}
_WC = {"changes": [
    {"headline": "macro backdrop weakened", "category_name": "Rates", "from_score": 71,
     "to_score": 54, "delta": -17, "direction": "down", "watchlist_hits": ["NVDA"], "why": "real yields"},
    {"headline": "credit improved", "category_name": "Credit", "from_score": 58,
     "to_score": 67, "delta": 9, "direction": "up", "watchlist_hits": ["JPM"]},
    {"headline": "noise", "watchlist_hits": []},   # no holdings hit -> excluded
]}


def test_attention_dominates_biggest_move_first():
    pl = cc.build_command_center(_XRAY, _WC)
    assert pl["state"] == "ready"
    assert pl["dominant"]["kind"] == "attention"
    assert pl["dominant"]["ticker"] == "NVDA" and pl["dominant"]["delta"] == -17
    assert pl["n_attention"] == 2
    kinds = [s["kind"] for s in pl["secondary"]]
    assert "exposure" in kinds and "vulnerable" in kinds
    labels = [e["label"] for e in pl["explore"]]
    assert "Why did NVDA change?" in labels
    assert any("shared Rates" in l for l in labels)


def test_exposure_dominates_when_no_attention():
    pl = cc.build_command_center(_XRAY, {"changes": [{"headline": "x", "watchlist_hits": []}]})
    assert pl["dominant"]["kind"] == "exposure" and pl["dominant"]["factor"] == "Rates"


def test_no_holdings_and_render():
    e = cc.build_command_center({}, {})
    assert e["state"] == "no_holdings"
    assert "add holdings" in cc.render_command_center_html(e).lower()
    html = cc.render_command_center_html(cc.build_command_center(_XRAY, _WC))
    assert "NVDA" in html and "Explore" in html
    assert html.count("<div") >= html.count("</div")
