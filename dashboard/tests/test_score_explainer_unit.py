"""
Unit tests for utils/score_explainer.py — the Confluence Score transparency
layer (Point 3: make the score explain itself in <10s, with no fake precision).

HERMETIC BY DESIGN: score_explainer only needs SIGNALS/CATEGORIES for
human-readable names, so we stub utils.config in sys.modules BEFORE importing
the module. That keeps these tests pure-function fast — no 152KB config load,
no DB, no network — and lets the attribution/agreement/confidence MATH be
validated against hand-computed ground truth, which is the whole point.

Every numeric assertion below has a hand-derived expected value in its comment
so a future reader can confirm the math, not just that it "runs".
"""

import sys
import types
import math

import pytest

# ── Stub utils.config with a tiny, known signal universe ─────────────────────
_stub = types.ModuleType("utils.config")
_stub.CATEGORIES = {
    "financials":         {"name": "Financials & Credit"},
    "ai_infrastructure":  {"name": "AI Infrastructure"},
    "macro":              {"name": "Macro & Liquidity"},
    "energy":             {"name": "Energy & Oil"},
}
_stub.SIGNALS = {
    "hy_spread":         {"name": "High-Yield Credit Spread", "category": "financials"},
    "semiconductor_etf": {"name": "Semiconductor Capex",      "category": "ai_infrastructure"},
    "insider_x":         {"name": "Insider Activity",         "category": "financials"},
    "ten_year_yield":    {"name": "10-Year Yield",            "category": "macro"},
    "crude_oil":         {"name": "Crude Oil",                "category": "energy"},
    "vix":               {"name": "VIX",                      "category": "macro"},
}
sys.modules.setdefault("utils.config", _stub)

from utils import score_explainer as se  # noqa: E402


# ── 1. Band labels ───────────────────────────────────────────────────────────
def test_score_bands():
    assert se.score_band(72)["tone"] == "supportive"
    assert se.score_band(65)["tone"] == "supportive"          # boundary inclusive
    assert se.score_band(60)["tone"] == "mildly supportive"
    assert se.score_band(50)["tone"] == "mixed"
    assert se.score_band(40)["tone"] == "mildly challenging"
    assert se.score_band(20)["tone"] == "challenging"


# ── 2. Change summary (real snapshots only, never interpolated) ──────────────
def test_change_summary_needs_two_points():
    assert se.change_summary([], days=7)["available"] is False
    one = [{"snapshot_date": "2026-07-13", "score": 72}]
    assert se.change_summary(one, days=7)["available"] is False


def test_change_summary_basic_delta():
    hist = [
        {"snapshot_date": "2026-07-06", "score": 64},
        {"snapshot_date": "2026-07-13", "score": 72},
    ]
    c = se.change_summary(hist, days=7)
    assert c["available"] and c["delta"] == 8.0     # 72 - 64
    assert c["direction"] == "up"
    assert c["span_days"] == 7
    assert c["sparse"] is False


def test_change_summary_picks_nearest_to_window():
    # 2026-07-05 is 8 days before 07-13 (nearest to a 7-day compare); 06-01 is far.
    hist = [
        {"snapshot_date": "2026-06-01", "score": 50},
        {"snapshot_date": "2026-07-05", "score": 60},
        {"snapshot_date": "2026-07-13", "score": 70},
    ]
    c = se.change_summary(hist, days=7)
    assert c["from_score"] == 60.0    # nearest-to-7d baseline, not the oldest
    assert c["delta"] == 10.0         # 70 - 60


# ── 3. Attribution: contribution = weight * delta / Σweight ──────────────────
def _corr():
    return {
        "hy_spread":         {"weight": 2.0, "significant": True, "n": 90},
        "semiconductor_etf": {"weight": 1.0, "significant": True, "n": 90},
        "insider_x":         {"weight": 1.0, "significant": True, "n": 90},
    }  # Σweight = 4.0


def test_attribution_math_and_filtering():
    trends = {
        "hy_spread":         {"trend": "up",   "delta": 16.0},  # 2*16/4 = +8.0
        "semiconductor_etf": {"trend": "up",   "delta": 4.0},   # 1*4/4  = +1.0
        "insider_x":         {"trend": "down", "delta": -1.0},  # 1*-1/4 = -0.25 (below min_points)
    }
    a = se.attribute_change(_corr(), trends)
    assert a["available"] is True
    movers = {m["sig_id"]: m["contribution"] for m in a["movers"]}
    assert math.isclose(movers["hy_spread"], 8.0, abs_tol=0.05)
    assert math.isclose(movers["semiconductor_etf"], 1.0, abs_tol=0.05)
    assert "insider_x" not in movers                 # |−0.25| < 0.3 min_points → filtered
    assert a["movers"][0]["sig_id"] == "hy_spread"   # sorted by |contribution|
    assert a["covered"] == 3


def test_attribution_unavailable_paths():
    assert se.attribute_change(_corr(), {})["available"] is False
    new_only = {"hy_spread": {"trend": "new", "delta": 0.0}}
    assert se.attribute_change({"hy_spread": {"weight": 1.0}}, new_only)["available"] is False


# ── 4. Level drivers: contribution = weight * (score-50) / Σweight ────────────
def test_level_drivers():
    scores = {
        "hy_spread":         {"score": 70, "status": "bullish"},  # 2*20/4 = +10.0
        "semiconductor_etf": {"score": 60, "status": "bullish"},  # 1*10/4 = +2.5
        "insider_x":         {"score": 45, "status": "bearish"},  # 1*-5/4 = -1.25
    }
    ld = se.level_drivers(_corr(), scores)
    d = {x["sig_id"]: x["contribution"] for x in ld["drivers"]}
    assert math.isclose(d["hy_spread"], 10.0, abs_tol=0.05)
    assert d["insider_x"] < 0
    assert ld["drivers"][0]["sig_id"] == "hy_spread"


# ── 5. Agreement: only statistically-significant, directional signals count ──
def test_agreement_excludes_nonsignificant_and_neutral():
    corr = {
        "hy_spread":         {"weight": 2.0, "significant": True,  "n": 90},
        "semiconductor_etf": {"weight": 1.0, "significant": True,  "n": 90},
        "ten_year_yield":    {"weight": 1.0, "significant": True,  "n": 90},
        "crude_oil":         {"weight": 1.0, "significant": False, "n": 90},  # excluded
        "vix":               {"weight": 1.0, "significant": True,  "n": 90},
    }
    scores = {
        "hy_spread":         {"score": 70},   # supportive
        "semiconductor_etf": {"score": 66},   # supportive
        "ten_year_yield":    {"score": 40},   # challenging
        "crude_oil":         {"score": 80},   # supportive but NOT significant → ignored
        "vix":               {"score": 50.0}, # neutral → not directional
    }
    ag = se.agreement(scores, corr)
    assert ag["relevant"] == 3         # hy, semi, ten (crude excluded, vix neutral)
    assert ag["supportive"] == 2
    assert ag["challenging"] == 1
    assert ag["direction"] == "supportive"
    assert ag["agree"] == 2


# ── 6. Confidence tiers ──────────────────────────────────────────────────────
def test_confidence_tiers():
    hi = se.confidence({f"s{i}": {"significant": True, "n": 90} for i in range(6)}, [{"score": 1}] * 3)
    assert hi["level"] == "High"
    mod = se.confidence({f"s{i}": {"significant": True, "n": 90} for i in range(4)}, [])
    assert mod["level"] == "Moderate"
    lim = se.confidence({"a": {"significant": True, "n": 5}, "b": {"significant": False, "n": 90}}, [])
    assert lim["level"] == "Limited"
    assert lim["reasons"]


# ── 7. Factor breakdown shares sum to ~100% ──────────────────────────────────
def test_factor_breakdown_shares():
    scores = {
        "hy_spread":         {"score": 70},
        "semiconductor_etf": {"score": 60},
        "insider_x":         {"score": 45},
    }
    fb = se.factor_breakdown(_corr(), scores)
    assert fb
    assert math.isclose(sum(f["share"] for f in fb), 100, abs_tol=1.5)
    assert all("name" in f for f in fb)


# ── 8. Integration: build + render, and the always-on honesty caveat ─────────
def test_build_and_render():
    corr = {
        "hy_spread":         {"weight": 2.0, "significant": True, "n": 90},
        "semiconductor_etf": {"weight": 1.0, "significant": True, "n": 90},
        "ten_year_yield":    {"weight": 1.0, "significant": True, "n": 90},
    }
    scores = {"hy_spread": {"score": 70}, "semiconductor_etf": {"score": 66},
              "ten_year_yield": {"score": 40}}
    hist = [{"snapshot_date": "2026-07-06", "score": 64},
            {"snapshot_date": "2026-07-13", "score": 72}]
    trends = {"hy_spread": {"trend": "up", "delta": 16.0}}
    result = {"ticker": "NVDA", "confluence": {"overall_score": 72.0},
              "corr_info": corr, "signal_scores": scores}
    payload = se.build_explainer(result, score_history=hist, signal_trends=trends, change_days=7)
    assert payload["score"] == 72.0
    assert payload["band"]["tone"] == "supportive"
    # The non-negotiable honesty caveat must always be present.
    assert any("predictive accuracy" in l for l in payload["limitations"])
    html = se.render_explainer_html(payload)
    assert isinstance(html, str) and len(html) > 200
    assert "72" in html and "Confidence" in html
    assert html.count("<div") >= html.count("</div")   # not wildly unbalanced


# ── 9. Edge cases never crash ────────────────────────────────────────────────
def test_empty_inputs_never_crash():
    empty = se.build_explainer(
        {"ticker": "X", "confluence": {"overall_score": 50}, "corr_info": {}, "signal_scores": {}},
        [], {},
    )
    assert empty["confidence"]["level"] == "Limited"
    assert isinstance(se.render_explainer_html(empty), str)


def test_pt_formatting():
    assert se._pt(8) == "+8"
    assert se._pt(-1) == "-1"
    assert se._pt(0) == "+0"
