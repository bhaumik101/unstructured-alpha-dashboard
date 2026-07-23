"""Effective independent signals — the de-correlated conviction read.

The Confluence Score's agreement count treats correlated signals as independent
evidence (VIX + put/call + VIX term structure are one risk-appetite bet counted
three times). These tests pin the effective-signal math and the additive
integration into compute_confluence, and guard that every registered signal is
assigned a factor so nothing silently defaults to "independent".
"""

from __future__ import annotations

import pytest

from utils.signal_independence import (
    RHO_CROSS,
    RHO_WITHIN,
    SIGNAL_FACTOR,
    effective_signal_count,
    factor_of,
    independence,
)


# ── The math ──────────────────────────────────────────────────────────────────

def test_empty_and_single():
    assert effective_signal_count([]) == 0.0
    assert effective_signal_count(["vix"]) == 1.0


def test_all_same_factor_collapses_hard():
    """Four signals all proxying risk appetite are NOT four independent votes."""
    risk = ["vix", "put_call_ratio", "vix_term_structure", "retail_fear_gauge"]
    eff = effective_signal_count(risk)
    assert eff < 2.0, f"4 same-factor signals should be ~1.x effective, got {eff:.2f}"
    # closed form: N/(1+rho_within*(N-1)) = 4/(1+0.55*3) = 1.51
    assert eff == pytest.approx(4 / (1 + RHO_WITHIN * 3), rel=1e-3)


def test_all_distinct_factors_stay_high():
    """One signal from each of several factors keeps most of its evidence."""
    distinct = ["vix", "hy_spread", "yield_curve", "crude_oil", "copper", "jobless_claims"]
    eff = effective_signal_count(distinct)
    # closed form: N/(1+rho_cross*(N-1)) = 6/(1+0.05*5) = 4.8
    assert eff == pytest.approx(6 / (1 + RHO_CROSS * 5), rel=1e-3)
    assert eff > 4.0


def test_correlated_always_below_raw():
    for ids in (
        ["vix", "put_call_ratio"],
        ["hy_spread", "ig_credit", "bank_lending_standards"],
        ["crude_oil", "gas_storage", "natural_gas", "retail_gasoline"],
    ):
        assert effective_signal_count(ids) < len(ids)


def test_mixed_set_between_extremes():
    """3 risk-appetite + 3 distinct factors: effective between 'all one' and 'all distinct'."""
    ids = ["vix", "put_call_ratio", "vix_term_structure", "crude_oil", "yield_curve", "copper"]
    eff = effective_signal_count(ids)
    assert 3.0 < eff < 6.0


def test_unknown_signal_is_its_own_factor():
    """An unmapped signal must not be lumped with others (conservative)."""
    assert factor_of("some_new_signal").startswith("_own::")
    eff = effective_signal_count(["some_new_signal", "another_new_one"])
    # two unknowns = two distinct factors = 2/(1+rho_cross) ~ 1.9
    assert eff == pytest.approx(2 / (1 + RHO_CROSS), rel=1e-3)


def test_more_signals_never_fewer_effective_when_adding_distinct_factor():
    base = ["vix", "put_call_ratio"]
    more = base + ["crude_oil"]
    assert effective_signal_count(more) > effective_signal_count(base)


# ── independence() summary ────────────────────────────────────────────────────

def test_independence_summary_shape():
    s = independence(["vix", "put_call_ratio", "hy_spread"])
    assert s["raw"] == 3
    assert s["effective"] < 3
    assert 0 < s["ratio"] < 1
    assert s["n_factors"] == 2  # risk_appetite + credit
    assert s["factors"]["risk_appetite"] == 2


def test_independence_empty():
    s = independence([])
    assert s["raw"] == 0 and s["effective"] == 0.0


# ── Factor map coverage ───────────────────────────────────────────────────────

def test_every_registered_signal_has_a_factor():
    """A new signal added to config without a factor silently defaults to
    'independent', quietly inflating conviction. Force the map to stay complete."""
    from utils.config import SIGNALS
    unmapped = [sid for sid in SIGNALS if sid not in SIGNAL_FACTOR]
    assert not unmapped, (
        "signals missing from SIGNAL_FACTOR (they'd count as fully independent, "
        f"overstating conviction): {unmapped}"
    )


def test_factor_map_has_no_stale_entries():
    from utils.config import SIGNALS
    stale = [sid for sid in SIGNAL_FACTOR if sid not in SIGNALS]
    assert not stale, f"SIGNAL_FACTOR references signals no longer in config: {stale}"


# ── Integration into compute_confluence ───────────────────────────────────────

def _scores(bull_ids=(), bear_ids=(), neutral_ids=()):
    d = {}
    for i in bull_ids:
        d[i] = {"score": 75, "status": "bullish"}
    for i in bear_ids:
        d[i] = {"score": 25, "status": "bearish"}
    for i in neutral_ids:
        d[i] = {"score": 50, "status": "neutral"}
    return d


def test_confluence_adds_effective_fields():
    from utils.analysis import compute_confluence
    r = compute_confluence(_scores(bull_ids=["vix", "put_call_ratio", "crude_oil"]))
    for k in ("effective_signals", "independence_ratio", "conviction_effective", "independence"):
        assert k in r


def test_confluence_effective_below_raw_for_correlated_bulls():
    """Nine agreeing but heavily-correlated signals: effective conviction must be
    lower than the raw count implies."""
    from utils.analysis import compute_confluence
    correlated = ["vix", "put_call_ratio", "vix_term_structure", "retail_fear_gauge",
                  "hy_spread", "ig_credit", "bank_lending_standards"]
    r = compute_confluence(_scores(bull_ids=correlated))
    assert r["bull_count"] == 7
    assert r["effective_signals"] < 7          # de-correlated
    assert r["effective_signals"] < 4          # really ~2 factors -> low effective
    # raw conviction is "Very High" (100% agree); effective should be lower
    assert r["conviction"] == "Very High"
    assert r["conviction_effective"] in ("Low / Mixed", "Moderate", "High")


def test_confluence_diverse_bulls_keep_high_effective():
    """Signals spanning many distinct factors keep their conviction honestly."""
    from utils.analysis import compute_confluence
    diverse = ["vix", "hy_spread", "yield_curve", "crude_oil", "copper",
               "jobless_claims", "housing_starts", "retail_sales"]
    r = compute_confluence(_scores(bull_ids=diverse))
    assert r["effective_signals"] > 5          # mostly independent
    assert r["conviction_effective"] in ("High", "Very High")


def test_confluence_empty_is_safe():
    from utils.analysis import compute_confluence
    r = compute_confluence({})
    assert r["overall_score"] == 50.0
