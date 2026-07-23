"""Tests for the Conviction Curve (lead-time term structure).

Pins the horizon-bucketing, the sign-restricted aggregation, the de-correlated
per-bucket confidence, the peak/trend logic, and — because honesty is
load-bearing — that a DISCLAIMER always travels with the object.
"""

from __future__ import annotations

import pytest

from utils.conviction_curve import (
    BUCKETS,
    DISCLAIMER,
    ConvictionCurve,
    conviction_curve,
    summary_sentence,
)


def _sig(score, status=None):
    return {"score": score, "status": status or ("bullish" if score > 55 else
                                                  "bearish" if score < 45 else "neutral")}


# ── Bucketing by lead time ────────────────────────────────────────────────────

def test_signals_land_in_lead_time_buckets(monkeypatch):
    import utils.conviction_curve as cc
    monkeypatch.setattr(cc, "SIGNALS", {
        "fast": {"lag_weeks": 1}, "mid": {"lag_weeks": 4}, "slow": {"lag_weeks": 8},
        "verylong": {"lag_weeks": 52},
    })
    scores = {"fast": _sig(80), "mid": _sig(80), "slow": _sig(80), "verylong": _sig(80)}
    curve = conviction_curve(scores)
    by_label = {p.label: p for p in curve.points}
    assert by_label["~1 wk"].n_signals == 1
    assert by_label["4-5 wk"].n_signals == 1
    assert by_label["6-8 wk"].n_signals == 1
    assert by_label["14 wk+"].n_signals == 1


def test_unknown_lead_defaults_to_modal_bucket(monkeypatch):
    import utils.conviction_curve as cc
    monkeypatch.setattr(cc, "SIGNALS", {"x": {}})  # no lag_weeks
    curve = conviction_curve({"x": _sig(80)})
    filled = [p for p in curve.points if p.n_signals]
    assert len(filled) == 1
    assert filled[0].label == "4-5 wk"


# ── Sign-restricted aggregation ───────────────────────────────────────────────

def test_bullish_readings_give_positive_conviction(monkeypatch):
    import utils.conviction_curve as cc
    monkeypatch.setattr(cc, "SIGNALS", {"a": {"lag_weeks": 4}, "b": {"lag_weeks": 4}})
    curve = conviction_curve({"a": _sig(90), "b": _sig(80)})
    b = next(p for p in curve.points if p.label == "4-5 wk")
    assert b.conviction > 0 and b.direction == "bullish"


def test_bearish_readings_give_negative_conviction(monkeypatch):
    import utils.conviction_curve as cc
    monkeypatch.setattr(cc, "SIGNALS", {"a": {"lag_weeks": 4}, "b": {"lag_weeks": 4}})
    curve = conviction_curve({"a": _sig(10), "b": _sig(20)})
    b = next(p for p in curve.points if p.label == "4-5 wk")
    assert b.conviction < 0 and b.direction == "bearish"


def test_neutral_reading_contributes_near_zero(monkeypatch):
    import utils.conviction_curve as cc
    monkeypatch.setattr(cc, "SIGNALS", {"a": {"lag_weeks": 4}})
    b = next(p for p in conviction_curve({"a": _sig(50)}).points if p.label == "4-5 wk")
    assert abs(b.conviction) < 0.05 and b.direction == "neutral"


# ── De-correlated confidence ──────────────────────────────────────────────────

def test_bucket_reports_effective_below_raw_for_correlated_signals():
    """Three risk-appetite signals in one bucket are ~1 independent read."""
    # vix / put_call_ratio / vix_term_structure are all risk_appetite and default
    # to the 0-1wk or 2-3wk buckets; place them together by real config leads.
    scores = {"vix": _sig(80), "put_call_ratio": _sig(80), "vix_term_structure": _sig(80)}
    curve = conviction_curve(scores)
    filled = [p for p in curve.points if p.n_signals >= 2]
    assert filled, "expected the correlated signals to share a bucket"
    for p in filled:
        assert p.effective_signals < p.n_signals


# ── Peak & trend ──────────────────────────────────────────────────────────────

def test_peak_is_the_strongest_supported_horizon(monkeypatch):
    import utils.conviction_curve as cc
    monkeypatch.setattr(cc, "SIGNALS", {
        "n1": {"lag_weeks": 1}, "n2": {"lag_weeks": 1},   # weak near
        "f1": {"lag_weeks": 8}, "f2": {"lag_weeks": 8}, "f3": {"lag_weeks": 8},  # strong far
    })
    scores = {"n1": _sig(58), "n2": _sig(58), "f1": _sig(95), "f2": _sig(92), "f3": _sig(90)}
    curve = conviction_curve(scores)
    assert curve.peak_label == "6-8 wk"
    assert curve.peak_direction == "bullish"


def test_trend_building_when_far_stronger(monkeypatch):
    import utils.conviction_curve as cc
    monkeypatch.setattr(cc, "SIGNALS", {
        "n": {"lag_weeks": 1}, "f1": {"lag_weeks": 8}, "f2": {"lag_weeks": 12},
    })
    curve = conviction_curve({"n": _sig(55), "f1": _sig(95), "f2": _sig(93)})
    assert curve.trend == "building"


def test_trend_front_loaded_when_near_stronger(monkeypatch):
    import utils.conviction_curve as cc
    monkeypatch.setattr(cc, "SIGNALS", {
        "n1": {"lag_weeks": 1}, "n2": {"lag_weeks": 2}, "f": {"lag_weeks": 12},
    })
    curve = conviction_curve({"n1": _sig(95), "n2": _sig(93), "f": _sig(55)})
    assert curve.trend == "front-loaded"


# ── Honesty invariants ────────────────────────────────────────────────────────

def test_disclaimer_always_present():
    curve = conviction_curve({})
    assert curve.disclaimer == DISCLAIMER
    assert "not a validated forecast" in curve.disclaimer.lower()
    assert "trade trigger" in curve.disclaimer.lower()


def test_empty_input_is_safe_and_flagged():
    curve = conviction_curve({})
    assert isinstance(curve, ConvictionCurve)
    assert not curve.has_signal
    assert "No macro signals" in summary_sentence(curve)


def test_errored_signals_excluded(monkeypatch):
    import utils.conviction_curve as cc
    monkeypatch.setattr(cc, "SIGNALS", {"a": {"lag_weeks": 4}, "b": {"lag_weeks": 4}})
    scores = {"a": _sig(90), "b": {"score": 90, "error": "fetch failed"}}
    b = next(p for p in conviction_curve(scores).points if p.label == "4-5 wk")
    assert b.n_signals == 1


def test_summary_sentence_is_directional_and_honest(monkeypatch):
    import utils.conviction_curve as cc
    monkeypatch.setattr(cc, "SIGNALS", {"f1": {"lag_weeks": 8}, "f2": {"lag_weeks": 8}})
    curve = conviction_curve({"f1": _sig(95), "f2": _sig(92)})
    s = summary_sentence(curve)
    assert "bullish" in s and "6-8 wk" in s


def test_all_buckets_present_even_when_empty():
    curve = conviction_curve({})
    assert len(curve.points) == len(BUCKETS)
    assert all(p.n_signals == 0 for p in curve.points)
