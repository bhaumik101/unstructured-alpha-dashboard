"""
Integrity tests for utils/score_attribution.py — the "Explain the Move" engine.

The engine is PURE (component-dict in, attribution-dict out), so no config/DB/
taxonomy stubs are needed. Every numeric assertion is hand-derived in a comment.
The governing invariant: Δscore == Σ Δcontribution (reconciliation), and the
product must refuse to show a clean explanation when that fails.
"""

import math

from utils import score_attribution as sa


# ── builders ────────────────────────────────────────────────────────────────
def sig(sid, factor, fname, score, nw, contribution, available=True, name=None):
    return {"id": sid, "name": name or sid, "score": score, "norm_weight": nw,
            "contribution": contribution, "factor": factor, "factor_name": fname,
            "available": available, "significant": True, "weight": nw, "r": 0.3}


def comp(final, signals, components=None, n_available=None,
         generates=True, mv="2026.07.1", reg="sr_aaaa", ticker="NVDA"):
    signals = signals or []
    return {
        "ticker": ticker, "final_score": final, "reconstructed_score": final,
        "macro_score": final, "momentum_score": 50.0, "n_optional": 0, "remaining": 1.0,
        "signals": signals, "components": components or [],
        "coverage": {"n_available": n_available if n_available is not None else len(signals),
                     "tier": "moderate", "generates_score": generates},
        "model_version": mv, "signal_registry_version": reg,
        "calculated_at": "2026-07-14T00:00:00+00:00",
    }


# The spec's NVDA example: 60.9 → 47.1 (Δ -13.8), single signal per factor + momentum.
def _A():
    return comp(60.9, [
        sig("ten_year_yield", "rates", "Real Rates", 60, 0.24, 14.2),
        sig("net_liquidity", "liquidity", "Liquidity", 55, 0.21, 11.4),
        sig("hyperscaler_capex", "capex_tech", "AI Infrastructure", 62, 0.22, 13.1),
        sig("hy_spread", "credit", "Credit", 40, 0.12, 7.2),
    ], components=[{"kind": "momentum", "id": "momentum", "label": "Price Momentum",
                   "score": 50.0, "contribution": 15.0}])


def _B():
    return comp(47.1, [
        sig("ten_year_yield", "rates", "Real Rates", 31, 0.24, 6.1),
        sig("net_liquidity", "liquidity", "Liquidity", 34, 0.21, 7.0),
        sig("hyperscaler_capex", "capex_tech", "AI Infrastructure", 52, 0.22, 11.0),
        sig("hy_spread", "credit", "Credit", 45, 0.12, 8.0),
    ], components=[{"kind": "momentum", "id": "momentum", "label": "Price Momentum",
                   "score": 50.0, "contribution": 15.0}])


def _finite(x):
    if isinstance(x, float):
        return math.isfinite(x)
    if isinstance(x, dict):
        return all(_finite(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return all(_finite(v) for v in x)
    return True


# ── tests ───────────────────────────────────────────────────────────────────
def test_reconciles_and_is_ok():
    a = sa.attribute_move(_A(), _B())
    assert a["state"] == "ok"
    assert a["total_change"] == -13.8            # 47.1 - 60.9
    assert abs(a["reconciliation_delta"]) < 1e-6  # Σ Δcontribution == Δscore exactly
    # neg movement bucket = -8.1 -4.4 -2.1 = -14.6 ; pos = +0.8
    assert a["neg_total"] == -14.6 and a["pos_total"] == 0.8
    assert a["summary"] and "macro backdrop" in a["summary"]


def test_factors_sorted_and_materiality():
    a = sa.attribute_move(_A(), _B())
    order = [f["factor"] for f in a["factors"]]
    # most negative first: rates(-8.1) liquidity(-4.4) capex(-2.1) momentum(0) credit(+0.8)
    assert order[0] == "rates" and order[1] == "liquidity"
    assert order[-1] == "credit"  # only positive factor => last
    rates = next(f for f in a["factors"] if f["factor"] == "rates")
    liq = next(f for f in a["factors"] if f["factor"] == "liquidity")
    cap = next(f for f in a["factors"] if f["factor"] == "capex_tech")
    assert rates["materiality"] == "primary"        # 8.1/14.6 = 55%
    assert liq["materiality"] == "primary"          # 4.4/14.6 = 30%
    assert cap["materiality"] == "meaningful"       # 2.1/14.6 = 14%
    assert a["n_weakened"] == 3 and a["n_improved"] == 1


def test_factor_delta_equals_signal_sum():
    # rates has TWO signals; factor delta must equal the sum of its signals' deltas.
    a = comp(30.0, [sig("ten_year_yield", "rates", "Real Rates", 60, 0.3, 18.0),
                    sig("yield_curve", "rates", "Real Rates", 55, 0.2, 12.0)])
    b = comp(20.0, [sig("ten_year_yield", "rates", "Real Rates", 40, 0.3, 12.0),
                    sig("yield_curve", "rates", "Real Rates", 45, 0.2, 8.0)])
    r = sa.attribute_move(a, b)
    rates = next(f for f in r["factors"] if f["factor"] == "rates")
    sig_sum = round(sum(s["delta"] for s in rates["signals"]), 3)
    assert rates["delta"] == sig_sum == -10.0        # (12-18)+(8-12) = -10
    assert abs(r["reconciliation_delta"]) < 1e-6


def test_signal_added_and_removed():
    a = comp(20.0, [sig("s1", "rates", "Real Rates", 50, 0.5, 20.0)])
    b = comp(28.0, [sig("s1", "rates", "Real Rates", 50, 0.5, 20.0),
                    sig("s2", "credit", "Credit", 60, 0.2, 8.0)])   # added
    r = sa.attribute_move(a, b)
    causes = {d["id"]: d["cause"] for f in r["factors"] for d in f["signals"]}
    assert causes["s2"] == sa.SIGNAL_ADDED
    r2 = sa.attribute_move(b, a)                                    # reverse => removed
    causes2 = {d["id"]: d["cause"] for f in r2["factors"] for d in f["signals"]}
    assert causes2["s2"] == sa.SIGNAL_REMOVED


def test_data_loss_and_recovery():
    a = comp(20.0, [sig("s1", "rates", "Real Rates", 60, 0.5, 20.0, available=True)])
    b = comp(15.0, [sig("s1", "rates", "Real Rates", 50, 0.5, 15.0, available=False)])
    loss = sa.attribute_move(a, b)["factors"][0]["signals"][0]
    assert loss["cause"] == sa.DATA_LOSS
    rec = sa.attribute_move(b, a)["factors"][0]["signals"][0]
    assert rec["cause"] == sa.DATA_RECOVERY


def test_weight_change_vs_market_input():
    # same score, weight (and thus contribution) moved => WEIGHT_CHANGE
    a = comp(20.0, [sig("s1", "rates", "Real Rates", 50, 0.40, 20.0)])
    b = comp(25.0, [sig("s1", "rates", "Real Rates", 50, 0.50, 25.0)])
    assert sa.attribute_move(a, b)["factors"][0]["signals"][0]["cause"] == sa.WEIGHT_CHANGE
    # score moved => MARKET_INPUT_CHANGE
    c = comp(24.0, [sig("s1", "rates", "Real Rates", 60, 0.40, 24.0)])
    assert sa.attribute_move(a, c)["factors"][0]["signals"][0]["cause"] == sa.MARKET_INPUT_CHANGE


def test_model_version_change_flagged():
    a = _A(); b = _B(); b["model_version"] = "2026.08.0"      # methodology changed
    r = sa.attribute_move(a, b)
    assert r["model_changed"] is True
    assert "methodology changed" in r["summary"]


def test_no_comparison_state():
    assert sa.attribute_move(None, _B())["state"] == "no_comparison"
    assert sa.attribute_move(_A(), None)["state"] == "no_comparison"


def test_insufficient_coverage_honest():
    a = comp(20.0, [sig("s1", "consumer", "Consumer", 60, 1.0, 20.0)], n_available=1)
    b = comp(15.8, [sig("s1", "consumer", "Consumer", 47, 1.0, 15.8)], n_available=1)
    r = sa.attribute_move(a, b)
    assert r["state"] == "insufficient_coverage"
    assert "limited" in r["summary"].lower()
    assert "1 available macro input" in r["summary"]


def test_positive_move_and_offsets():
    a = _B(); b = _A()                       # reverse: +13.8 improvement
    r = sa.attribute_move(a, b)
    assert r["total_change"] == 13.8 and r["direction"] == "up"
    assert r["pos_total"] == 14.6 and r["neg_total"] == -0.8   # credit now the drag
    assert "strengthened" in r["summary"]


def test_unreconciled_is_refused():
    a = _A(); b = _B(); b["final_score"] = 30.0   # break: Σdeltas still -13.8, Δscore now -30.9
    r = sa.attribute_move(a, b)
    assert r["state"] == "unreconciled"
    assert "not available" in r["summary"]


def test_reconstruct_prior_reconciles_and_flagged():
    # Day-1 path: reconstruct Time A from real historical signal scores.
    b = _B()
    hist = {"ten_year_yield": 60, "net_liquidity": 55, "hyperscaler_capex": 62, "hy_spread": 40}
    a = sa.reconstruct_prior(b, hist, as_of_date="2026-07-07")
    assert a is not None and a["reconstructed"] is True
    r = sa.attribute_move(a, b, window_label="this week")
    assert r["state"] == "ok" and r["reconstructed"] is True
    assert abs(r["reconciliation_delta"]) < 0.05         # reconciles within rounding
    assert "historical signal readings" in r["summary"]


def test_reconstruct_prior_needs_enough_history():
    b = _B()
    assert sa.reconstruct_prior(b, {}, "2026-07-07") is None                 # no history
    assert sa.reconstruct_prior(b, {"ten_year_yield": 60}, "2026-07-07") is None  # 1 < min 2


def test_never_nan_or_inf():
    for r in (sa.attribute_move(_A(), _B()), sa.attribute_move(_B(), _A()),
              sa.attribute_move(_A(), _A())):
        assert _finite({k: v for k, v in r.items() if k != "summary"})


def test_what_actually_changed_detail():
    # Wave 4: per-primary-driver detail carries raw value X→Y, weight %, freshness,
    # and a factor-level mechanism; all of it surfaces in the rendered HTML.
    def s2(sid, fac, fn, sc, nw, c, rawv, asof):
        return {"id": sid, "name": fn, "score": sc, "norm_weight": nw, "contribution": c,
                "factor": fac, "factor_name": fn, "available": True, "significant": True,
                "weight": nw, "r": 0.3, "raw_value": rawv, "as_of": asof}
    a = comp(50.0, [s2("ten_year_yield", "rates", "Real Rates", 60, 0.5, 30.0, 2.34, "2026-07-07"),
                    s2("hy_spread", "credit", "Credit", 40, 0.5, 20.0, 3.1, "2026-07-07")])
    b = comp(38.0, [s2("ten_year_yield", "rates", "Real Rates", 31, 0.5, 16.0, 1.98, "2026-07-13"),
                    s2("hy_spread", "credit", "Credit", 45, 0.5, 22.0, 2.9, "2026-07-13")])
    r = sa.attribute_move(a, b)
    assert r["state"] == "ok" and abs(r["reconciliation_delta"]) < 1e-6
    rates_sig = next(f for f in r["factors"] if f["factor"] == "rates")["signals"][0]
    assert rates_sig["raw_from"] == 2.34 and rates_sig["raw_to"] == 1.98
    assert rates_sig["as_of"] == "2026-07-13"
    h = sa.render_attribution_html(r)
    assert "Why it matters" in h                    # factor mechanism
    assert "weight 50%" in h                         # model weight
    assert "raw 2.34" in h and "1.98" in h           # raw series X→Y
    assert "updated 2026-07-13" in h                 # freshness
    assert h.count("<div") == h.count("</div") and "NaN" not in h
