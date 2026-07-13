"""
Unit tests for utils/what_changed.py — the "What Changed" compression engine
(Point 4: decision compression, holdings-first, honest noise bucketing).

HERMETIC: what_changed only needs SIGNALS/TICKERS/CATEGORIES for names and the
signal↔ticker impact map, so we stub utils.config in sys.modules before import.
Every numeric assertion has a hand-derived expected value in its comment.
"""

import sys
import types

import pytest

_stub = types.ModuleType("utils.config")
_stub.CATEGORIES = {
    "financials": {"name": "Financials & Credit"},
    "energy":     {"name": "Energy & Oil"},
    "macro":      {"name": "Macro & Liquidity"},
    "ai_infrastructure": {"name": "AI Infrastructure"},
}
_stub.SIGNALS = {
    "hy_spread":         {"name": "High-Yield Credit Spread", "category": "financials",
                          "relevant_tickers": ["JPM", "XLF"], "description": "Credit stress gauge; wider spreads signal risk-off."},
    "crude_inventories": {"name": "Crude Inventories", "category": "energy",
                          "relevant_tickers": ["XOM", "CVX"], "description": "Oil supply glut gauge."},
    "insider_x":         {"name": "Insider Activity", "category": "financials",
                          "relevant_tickers": [], "description": "Insider buying clusters."},
    "vix":               {"name": "VIX", "category": "macro",
                          "relevant_tickers": ["SPY"], "description": "Equity volatility."},
    "semiconductor_etf": {"name": "Semiconductor Capex", "category": "ai_infrastructure",
                          "relevant_tickers": ["NVDA"], "description": "Chip capex."},
}
_stub.TICKERS = {
    "JPM":  {"sector": "Financial Services", "signals": ["hy_spread"]},
    "XLF":  {"sector": "Financials ETF",     "signals": ["hy_spread"]},
    "XOM":  {"sector": "Energy",             "signals": ["crude_inventories"]},
    "SPY":  {"sector": "ETF",                "signals": ["vix", "hy_spread"]},
    "NVDA": {"sector": "Technology",         "signals": ["semiconductor_etf"]},
}
sys.modules.setdefault("utils.config", _stub)

from utils import what_changed as wc  # noqa: E402


def _diff():
    return {
        "days_back": 1,
        "regime_shift": "RISK-ON → MIXED",
        "flipped_bullish": [
            {"signal_id": "hy_spread", "name": "High-Yield Credit Spread",
             "from_score": 41, "to_score": 57, "to_status": "bullish"},
        ],
        "flipped_bearish": [],
        "biggest_movers": [
            {"signal_id": "crude_inventories", "name": "Crude Inventories", "delta": -23,
             "direction": "down", "from_score": 71, "to_score": 48, "category": "energy"},
            {"signal_id": "insider_x", "name": "Insider Activity", "delta": 9,
             "direction": "up", "from_score": 50, "to_score": 59, "category": "financials"},
            {"signal_id": "vix", "name": "VIX", "delta": 4, "direction": "up",
             "from_score": 50, "to_score": 54, "category": "macro"},  # below threshold → noise
            {"signal_id": "hy_spread", "name": "dup", "delta": 16, "direction": "up"},  # dup of flip
        ],
    }


WL = ["JPM", "XOM", "NVDA"]


def test_impact_mapping_both_directions():
    assert wc.affects_ticker("hy_spread", "JPM")            # via TICKERS[JPM].signals
    assert wc.affects_ticker("crude_inventories", "XOM")    # via SIGNALS.relevant_tickers
    assert not wc.affects_ticker("hy_spread", "NVDA")       # unrelated
    assert wc.affected_watchlist("hy_spread", WL) == ["JPM"]
    assert wc.affected_watchlist("insider_x", WL) == []     # hits nobody
    assert wc.affected_sectors("hy_spread")                 # non-empty sector list


def test_threshold_dedupe_and_ranking():
    p = wc.build_what_changed(_diff(), watchlist=WL, total_signals=47)
    ids = [c["sig_id"] for c in p["changes"]]
    assert p["meaningful_total"] == 3            # flip + 2 movers ≥8; vix(4) excluded
    assert "vix" not in ids                      # |4| < 8 → noise
    assert ids.count("hy_spread") == 1           # mover-dup collapsed into the flip
    assert next(c for c in p["changes"] if c["sig_id"] == "hy_spread")["kind"] == "flip"
    # holdings-first, then |delta|: crude (hit,23) > hy (hit,16) > insider (no hit,9)
    assert ids == ["crude_inventories", "hy_spread", "insider_x"]
    assert p["noise_count"] == 44                # 47 - 3
    assert p["most_exposed"] in {"JPM", "XOM"}
    assert p["regime_shift"] == "RISK-ON → MIXED"
    assert p["has_watchlist"] is True


def test_framing():
    p = wc.build_what_changed(_diff(), watchlist=WL, total_signals=47)
    hy = next(c for c in p["changes"] if c["sig_id"] == "hy_spread")
    assert "turned supportive" in hy["headline"] and hy["direction"] == "up"
    assert hy["from_score"] == 41 and hy["to_score"] == 57
    cr = next(c for c in p["changes"] if c["sig_id"] == "crude_inventories")
    assert "weakened" in cr["headline"] and cr["direction"] == "down"
    assert "glut" in cr["why"]                   # why = real config description
    assert cr["watchlist_hits"] == ["XOM"]


def test_threshold_boundary():
    d8 = {"days_back": 1, "flipped_bullish": [], "flipped_bearish": [],
          "biggest_movers": [{"signal_id": "insider_x", "name": "Insider Activity",
                              "delta": 8, "direction": "up", "from_score": 50, "to_score": 58}]}
    assert wc.build_what_changed(d8)["meaningful_total"] == 1   # exactly 8 counts
    d7 = {"days_back": 1, "flipped_bullish": [], "flipped_bearish": [],
          "biggest_movers": [{"signal_id": "insider_x", "name": "Insider Activity",
                              "delta": 7, "direction": "up", "from_score": 50, "to_score": 57}]}
    assert wc.build_what_changed(d7)["meaningful_total"] == 0   # 7 is noise


def test_no_watchlist_path():
    p = wc.build_what_changed(_diff(), watchlist=None, total_signals=47)
    assert p["most_exposed"] is None and p["has_watchlist"] is False
    # falls back to pure |delta| ranking → crude (23) first
    assert [c["sig_id"] for c in p["changes"]][0] == "crude_inventories"


def test_empty_and_render():
    empty = wc.build_what_changed(
        {"days_back": 1, "flipped_bullish": [], "flipped_bearish": [], "biggest_movers": []},
        watchlist=WL, total_signals=47,
    )
    assert empty["meaningful_total"] == 0
    assert "held steady" in wc.render_what_changed_html(empty)
    html = wc.render_what_changed_html(wc.build_what_changed(_diff(), watchlist=WL, total_signals=47))
    assert "3 meaningful change" in html
    assert "Your holdings" in html
    assert "treated as noise" in html
    assert "RISK-ON → MIXED" in html
    assert html.count("<div") >= html.count("</div")
