"""
Unit tests for utils/lead_time_research.py, using SYNTHETIC data with a
KNOWN ground-truth relationship -- the only way to actually verify this
kind of statistical methodology works, rather than just "doesn't crash."
Two properties matter and are both tested directly:

  1. A real, injected lag-N relationship (signal change at lag N drives
     price return, plus noise) must be RECOVERED: correct best_lag, must
     survive the Bonferroni correction, must hold up out-of-sample.
  2. Pure noise (no real relationship at all) must be REJECTED: even if
     one lag happens to clear the uncorrected p<0.05 bar by chance (which,
     with 17 lags tested, will happen reasonably often), it must NOT
     survive correction and must NOT hold out-of-sample. A methodology
     that can't reliably tell these two cases apart is worse than useless
     for this feature -- it would actively manufacture false confidence,
     exactly the failure mode this module exists to avoid.
"""

import numpy as np
import pandas as pd
import pytest

from utils.lead_time_research import (
    build_insider_intensity_series,
    build_short_interest_change_series,
    lag_scan_with_validation,
    pooled_lag_scan_across_sector,
    compute_signal_reliability_score,
    get_sector_peers,
)


def _make_signal_and_lagged_price(seed: int, n: int = 200, true_lag: int = 6, strength: float = 0.04):
    """Builds a signal (random walk) and a price series whose weekly RETURN
    is driven by the signal's CHANGE `true_lag` weeks earlier, plus noise --
    matching what align_series()/pct_change() actually correlates (changes
    in signal vs. changes/returns in price), not raw levels."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-03", periods=n, freq="W")
    signal_diffs = rng.normal(0, 1, n)
    signal = pd.Series(np.cumsum(signal_diffs) + 50, index=dates)

    price_vals = np.zeros(n)
    price_vals[0] = 100.0
    for i in range(1, n):
        driver = signal_diffs[i - true_lag] if i >= true_lag else 0.0
        ret = strength * driver + rng.normal(0, 0.015)
        price_vals[i] = price_vals[i - 1] * (1 + ret)
    price = pd.Series(price_vals, index=dates)
    return signal, price


def _make_pure_noise(seed: int, n: int = 200):
    """Signal and price with NO real relationship to each other at all."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-03", periods=n, freq="W")
    signal = pd.Series(np.cumsum(rng.normal(0, 1, n)) + 50, index=dates)
    price_vals = np.zeros(n)
    price_vals[0] = 100.0
    for i in range(1, n):
        price_vals[i] = price_vals[i - 1] * (1 + rng.normal(0, 0.015))
    price = pd.Series(price_vals, index=dates)
    return signal, price


# ── lag_scan_with_validation: recovering a real relationship ────────────────

def test_recovers_known_lag_with_strong_injected_relationship():
    signal, price = _make_signal_and_lagged_price(seed=7, true_lag=6)
    result = lag_scan_with_validation(signal, price, scan_max_lag=16)

    assert result["error"] is None
    assert result["best_lag"] == 6
    assert result["survives_correction"] is True
    assert result["holds_out_of_sample"] is True
    assert result["out_of_sample"]["same_sign_as_in_sample"] is True


def test_reliability_score_is_high_for_a_validated_relationship():
    signal, price = _make_signal_and_lagged_price(seed=7, true_lag=6)
    result = lag_scan_with_validation(signal, price, scan_max_lag=16)
    rel = compute_signal_reliability_score(result)

    assert rel["score"] >= 70
    assert rel["label"] == "Reasonably well-supported"
    assert rel["components"]["corrected_significance"] > 0
    assert rel["components"]["out_of_sample_validation"] > 0


# ── lag_scan_with_validation: rejecting pure noise ───────────────────────────

def test_pure_noise_does_not_survive_correction_across_multiple_seeds():
    """Run several different random seeds -- a methodology that sometimes
    gets fooled by noise on an unlucky seed is not trustworthy. None of
    these should survive the Bonferroni correction."""
    false_positives = 0
    for seed in range(20, 30):
        signal, price = _make_pure_noise(seed=seed)
        result = lag_scan_with_validation(signal, price, scan_max_lag=16)
        if result.get("error"):
            continue
        if result["survives_correction"]:
            false_positives += 1

    # Some uncorrected lags WILL cross p<0.05 by chance with 17 comparisons
    # per run -- that's expected and is exactly the problem this module
    # exists to correct for. After correction, false positives should be
    # rare to nonexistent across 10 independent noise runs.
    assert false_positives == 0, f"{false_positives}/10 pure-noise runs falsely survived correction"


def test_pure_noise_does_not_hold_out_of_sample():
    signal, price = _make_pure_noise(seed=99)
    result = lag_scan_with_validation(signal, price, scan_max_lag=16)
    assert result["error"] is None
    assert result["holds_out_of_sample"] is False


def test_reliability_score_is_low_for_pure_noise():
    signal, price = _make_pure_noise(seed=99)
    result = lag_scan_with_validation(signal, price, scan_max_lag=16)
    rel = compute_signal_reliability_score(result)
    assert rel["score"] < 40
    assert rel["label"] in ("Weak — likely noise", "Suggestive, not yet well-supported")


# ── insufficient data handling ───────────────────────────────────────────────

def test_lag_scan_reports_error_on_too_little_data():
    dates = pd.date_range("2024-01-01", periods=10, freq="W")
    signal = pd.Series(np.random.normal(0, 1, 10), index=dates)
    price = pd.Series(100 + np.cumsum(np.random.normal(0, 1, 10)), index=dates)

    result = lag_scan_with_validation(signal, price, scan_max_lag=16)
    assert result["error"] is not None


def test_reliability_score_zero_when_validation_errored():
    rel = compute_signal_reliability_score({"error": "Insufficient overlapping data (3 weeks)"})
    assert rel["score"] == 0
    assert rel["components"] == {}


# ── event-data → weekly series adapters ──────────────────────────────────────

def test_build_insider_intensity_series_counts_buys_minus_sells():
    tx_df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-05", "2026-01-05", "2026-01-05", "2026-01-12"]),
        "code": ["P", "P", "S", "S"],
    })
    series = build_insider_intensity_series(tx_df)
    assert series[pd.Timestamp("2026-01-05")] == 1  # 2 buys - 1 sell
    assert series[pd.Timestamp("2026-01-12")] == -1  # 0 buys - 1 sell


def test_build_insider_intensity_series_empty_input():
    assert build_insider_intensity_series(pd.DataFrame()).empty


def test_build_short_interest_change_series_indexes_by_date():
    si_df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-15", "2026-01-31"]),
        "change_pct": [5.2, -3.1],
        "short_shares": [1000, 950],
    })
    series = build_short_interest_change_series(si_df)
    assert series[pd.Timestamp("2026-01-15")] == 5.2
    assert series[pd.Timestamp("2026-01-31")] == -3.1


def test_build_short_interest_change_series_empty_input():
    assert build_short_interest_change_series(pd.DataFrame()).empty


# ── cross-ticker pooling ──────────────────────────────────────────────────────

def test_pooled_lag_scan_aggregates_across_tickers():
    sig_a, price_a = _make_signal_and_lagged_price(seed=1, true_lag=6)
    sig_b, price_b = _make_signal_and_lagged_price(seed=2, true_lag=6)
    sig_c, price_c = _make_pure_noise(seed=3)  # one ticker with no real relationship

    pooled = pooled_lag_scan_across_sector(
        signal_per_ticker={"AAA": sig_a, "BBB": sig_b, "CCC": sig_c},
        price_per_ticker={"AAA": price_a, "BBB": price_b, "CCC": price_c},
    )

    assert pooled["n_tickers"] == 3
    # 2 of 3 tickers have a real, validated relationship -- significance_rate
    # should reflect that, not be 0 or 1.
    assert 0.5 <= pooled["significance_rate"] <= 0.8


def test_pooled_lag_scan_handles_no_data():
    pooled = pooled_lag_scan_across_sector(signal_per_ticker={}, price_per_ticker={})
    assert pooled == {"n_tickers": 0, "significance_rate": 0.0, "avg_abs_r": 0.0, "details": []}


# ── sector peers ──────────────────────────────────────────────────────────────

def test_get_sector_peers_excludes_self_and_etfs():
    peers = get_sector_peers("UNP")  # Union Pacific, sector="Transportation"
    assert "UNP" not in peers
    assert all(p != "SPY" for p in peers)  # SPY is an ETF, must never appear as a "peer"


def test_get_sector_peers_unknown_ticker_returns_empty():
    assert get_sector_peers("NOT_A_REAL_TICKER_XYZ") == []
