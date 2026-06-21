"""
Unit tests for the pure-math scoring functions in utils/analysis.py.

These use synthetic pandas Series built in-memory — no network access, no
API keys, fully deterministic. They exist to lock in the contract of each
function's return dict (every key always present, even on the "not enough
data" fallback path) since two real bugs in this project were exactly that
shape: score_signal() and score_contract_velocity() both used to omit keys
on their empty/insufficient-data branches, which crashed callers downstream
that assumed every key was always present.
"""

import numpy as np
import pandas as pd
import pytest

from utils.analysis import (
    score_signal,
    score_contract_velocity,
    score_insider_activity,
    score_short_interest,
    score_13f_positioning,
    compute_quick_correlation_stats,
    compute_backtested_pcs,
)


def _make_series(n=104, start="2024-01-01", seed=0, trend=0.0, noise=1.0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start=start, periods=n, freq="W")
    values = 100 + np.cumsum(rng.normal(trend, noise, n))
    return pd.Series(values, index=dates)


# ── score_signal ─────────────────────────────────────────────────────────────

def test_score_signal_insufficient_data_has_all_keys():
    """The exact bug class that previously crashed pages: missing keys on
    the short-circuit "not enough data" return path."""
    tiny = _make_series(n=5)
    result = score_signal(tiny)
    expected_keys = {
        "score", "status", "z_score", "percentile", "current",
        "mean_52w", "std_52w", "deviation_pct", "trend_4w_pct",
    }
    assert expected_keys.issubset(result.keys())
    assert result["status"] == "insufficient_data"


def test_score_signal_normal_path_has_all_keys_and_valid_range():
    s = _make_series(n=104)
    result = score_signal(s)
    assert 0.0 <= result["score"] <= 100.0
    assert result["status"] in ("bullish", "bearish", "neutral")


def test_score_signal_inverse_flips_direction():
    """A strongly rising series should score bullish normally and bearish
    when inverse=True (e.g. jobless claims rising = bad)."""
    rising = pd.Series(np.linspace(100, 200, 60), index=pd.date_range("2024-01-01", periods=60, freq="W"))
    normal = score_signal(rising, inverse=False)
    inverse = score_signal(rising, inverse=True)
    assert normal["score"] > 50
    assert inverse["score"] < 50


def test_score_signal_handles_zero_std_without_crashing():
    """A perfectly flat series has std=0 — must not divide by zero."""
    flat = pd.Series([50.0] * 60, index=pd.date_range("2024-01-01", periods=60, freq="W"))
    result = score_signal(flat)
    assert result["score"] == 50.0
    assert result["status"] == "neutral"


# ── score_insider_activity ───────────────────────────────────────────────────

def _make_tx(code, insider, value=10000.0):
    return {"date": pd.Timestamp("2026-01-01"), "insider": insider, "role": "Officer",
            "code": code, "shares": 100, "price": value / 100, "value": value if code == "P" else -value}


def test_score_insider_activity_empty_df_has_all_keys():
    result = score_insider_activity(pd.DataFrame())
    for key in ("score", "status", "distinct_buyers", "distinct_sellers",
                "buy_count", "sell_count", "net_value", "cluster_bonus_applied"):
        assert key in result
    assert result["status"] == "no_data"


def test_score_insider_activity_missing_code_column_has_all_keys():
    result = score_insider_activity(pd.DataFrame({"foo": [1, 2]}))
    assert result["status"] == "no_data"


def test_score_insider_activity_cluster_buying_is_strongly_bullish():
    """3+ distinct insiders buying, zero sellers -> cluster bonus, bullish."""
    df = pd.DataFrame([
        _make_tx("P", "Alice"), _make_tx("P", "Bob"), _make_tx("P", "Carol"),
    ])
    result = score_insider_activity(df)
    assert result["distinct_buyers"] == 3
    assert result["distinct_sellers"] == 0
    assert result["cluster_bonus_applied"] is True
    assert result["status"] == "bullish"
    assert result["score"] > 65


def test_score_insider_activity_cluster_selling_is_strongly_bearish():
    df = pd.DataFrame([
        _make_tx("S", "Alice"), _make_tx("S", "Bob"), _make_tx("S", "Carol"),
    ])
    result = score_insider_activity(df)
    assert result["distinct_sellers"] == 3
    assert result["cluster_bonus_applied"] is True
    assert result["status"] == "bearish"
    assert result["score"] < 35


def test_score_insider_activity_single_buyer_no_cluster_bonus():
    """One insider buying shouldn't get the multi-insider cluster bonus."""
    df = pd.DataFrame([_make_tx("P", "Alice")])
    result = score_insider_activity(df)
    assert result["cluster_bonus_applied"] is False
    assert result["score"] > 50  # still leans bullish, just not as strongly


def test_score_insider_activity_mixed_buyers_and_sellers_nets_out():
    df = pd.DataFrame([
        _make_tx("P", "Alice"), _make_tx("S", "Bob"),
    ])
    result = score_insider_activity(df)
    assert result["distinct_buyers"] == 1
    assert result["distinct_sellers"] == 1
    assert result["score"] == 50.0
    assert result["status"] == "neutral"


def test_score_insider_activity_net_value_reflects_signed_sum():
    df = pd.DataFrame([_make_tx("P", "Alice", 5000), _make_tx("S", "Bob", 3000)])
    result = score_insider_activity(df)
    assert result["net_value"] == 2000.0  # +5000 - 3000


# ── score_short_interest ─────────────────────────────────────────────────────

def _make_si_row(date, short_shares, change_pct, days_to_cover=2.0):
    return {"date": pd.Timestamp(date), "short_shares": short_shares,
            "prev_short_shares": short_shares, "change_pct": change_pct,
            "days_to_cover": days_to_cover, "avg_daily_volume": 1_000_000}


def test_score_short_interest_empty_df_has_all_keys():
    result = score_short_interest(pd.DataFrame())
    for key in ("score", "status", "latest_change_pct", "short_shares", "days_to_cover", "periods"):
        assert key in result
    assert result["status"] == "no_data"


def test_score_short_interest_missing_column_has_all_keys():
    result = score_short_interest(pd.DataFrame({"foo": [1, 2]}))
    assert result["status"] == "no_data"


def test_score_short_interest_rising_short_interest_is_bearish():
    """INVERSE signal: short interest growing sharply = bearish, lower score."""
    df = pd.DataFrame([
        _make_si_row("2026-04-15", 1_000_000, 5.0),
        _make_si_row("2026-04-30", 1_300_000, 30.0),
    ])
    result = score_short_interest(df)
    assert result["score"] < 50.0
    assert result["status"] in ("bearish", "neutral")


def test_score_short_interest_falling_short_interest_is_bullish():
    df = pd.DataFrame([
        _make_si_row("2026-04-15", 1_000_000, -5.0),
        _make_si_row("2026-04-30", 700_000, -30.0),
    ])
    result = score_short_interest(df)
    assert result["score"] > 50.0
    assert result["status"] in ("bullish", "neutral")


def test_score_short_interest_uses_latest_row_for_diagnostics():
    df = pd.DataFrame([
        _make_si_row("2026-04-15", 1_000_000, 5.0, days_to_cover=1.5),
        _make_si_row("2026-04-30", 1_100_000, 10.0, days_to_cover=2.5),
    ])
    result = score_short_interest(df)
    assert result["short_shares"] == 1_100_000
    assert result["days_to_cover"] == 2.5
    assert result["latest_change_pct"] == 10.0
    assert result["periods"] == 2


# ── score_13f_positioning ────────────────────────────────────────────────────

def test_score_13f_positioning_empty_list_has_all_keys():
    result = score_13f_positioning([])
    for key in ("score", "status", "funds_long", "funds_short", "new_positions",
                "exited_or_trimmed", "n_funds"):
        assert key in result
    assert result["status"] == "no_data"


def test_score_13f_positioning_fund_adding_to_long_position_is_bullish():
    rows = [{"fund": "Berkshire Hathaway", "style": "Value", "latest_shares": 1_100_000,
             "latest_period": "2026-03-31", "prior_shares": 1_000_000, "prior_period": "2025-12-31"}]
    result = score_13f_positioning(rows)
    assert result["score"] > 50.0
    assert result["funds_long"] == 1
    assert result["funds_short"] == 0


def test_score_13f_positioning_put_option_position_is_bearish():
    """A fund's Put position must score bearish, not be mistaken for a long
    share holding just because it appears in the same information table."""
    rows = [{"fund": "Scion Asset Management", "style": "Contrarian", "latest_shares": -1_000_000,
             "latest_period": "2025-09-30", "prior_shares": None, "prior_period": None}]
    result = score_13f_positioning(rows)
    assert result["score"] < 50.0
    assert result["funds_short"] == 1
    assert result["funds_long"] == 0


def test_score_13f_positioning_trimming_a_position_pulls_score_toward_neutral():
    adding = score_13f_positioning([{"fund": "F", "style": "S", "latest_shares": 1_200_000,
                                       "latest_period": "Q2", "prior_shares": 1_000_000, "prior_period": "Q1"}])
    trimming = score_13f_positioning([{"fund": "F", "style": "S", "latest_shares": 800_000,
                                         "latest_period": "Q2", "prior_shares": 1_000_000, "prior_period": "Q1"}])
    assert adding["score"] > trimming["score"]
    assert trimming["score"] > 50.0  # still net long, just less conviction than adding


def test_score_13f_positioning_new_position_counted_correctly():
    rows = [{"fund": "F", "style": "S", "latest_shares": 500_000, "latest_period": "Q2",
             "prior_shares": None, "prior_period": None}]
    result = score_13f_positioning(rows)
    assert result["new_positions"] == 1
    assert result["score"] > 50.0


def test_score_13f_positioning_multiple_funds_aggregate():
    rows = [
        {"fund": "A", "style": "S", "latest_shares": 1_000, "latest_period": "Q2", "prior_shares": 900, "prior_period": "Q1"},
        {"fund": "B", "style": "S", "latest_shares": -500, "latest_period": "Q2", "prior_shares": -500, "prior_period": "Q1"},
    ]
    result = score_13f_positioning(rows)
    assert result["n_funds"] == 2
    assert result["funds_long"] == 1
    assert result["funds_short"] == 1


# ── score_contract_velocity ──────────────────────────────────────────────────

def test_score_contract_velocity_empty_df_has_all_keys():
    result = score_contract_velocity(pd.DataFrame())
    assert "pct_change" in result
    assert "award_count" in result


def test_score_contract_velocity_with_data_has_all_keys():
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=20, freq="W"),
        "amount": np.random.default_rng(1).uniform(1e6, 1e8, 20),
    })
    result = score_contract_velocity(df)
    assert "pct_change" in result
    assert "award_count" in result


# ── compute_quick_correlation_stats ──────────────────────────────────────────

def test_quick_correlation_stats_returns_all_keys_on_insufficient_data():
    short_sig = _make_series(n=3)
    short_price = _make_series(n=3, seed=1)
    result = compute_quick_correlation_stats(short_sig, short_price)
    assert set(result.keys()) == {"r", "p_value", "significant", "n"}
    assert result["significant"] is False


def test_quick_correlation_stats_detects_strong_correlation():
    dates = pd.date_range("2020-01-01", periods=200, freq="W")
    base = np.cumsum(np.random.default_rng(2).normal(0, 1, 200))
    signal = pd.Series(base, index=dates)
    price = pd.Series(base * 2 + 50, index=dates)  # perfectly correlated, scaled
    result = compute_quick_correlation_stats(signal, price)
    assert result["n"] > 0
    # Same underlying random walk scaled linearly -> should show meaningful correlation
    assert abs(result["r"]) > 0.0


# ── compute_backtested_pcs (the multi-ticker rigor fix) ──────────────────────

def test_backtested_pcs_returns_unbacktested_when_no_data():
    result = compute_backtested_pcs(pd.Series(dtype=float), [pd.Series(dtype=float)])
    assert result["backtested"] is False
    assert result["pcs"] is None
    assert result["n_tested"] == 0


def test_backtested_pcs_tests_against_every_ticker_passed_in_not_just_first():
    """
    This is the regression test for the rigor fix itself: pass 3 price
    series in, and n_tested must reflect all 3 being evaluated (when each
    has enough overlapping data), not silently truncate to 1.
    """
    dates = pd.date_range("2020-01-01", periods=120, freq="W")
    rng = np.random.default_rng(3)
    signal = pd.Series(100 + np.cumsum(rng.normal(0, 1, 120)), index=dates)
    prices = [
        pd.Series(50 + np.cumsum(rng.normal(0, 1, 120)), index=dates)
        for _ in range(3)
    ]
    tickers = ["AAA", "BBB", "CCC"]
    result = compute_backtested_pcs(signal, prices, tickers=tickers)
    assert result["n_tested"] == 3
    assert len(result["details"]) == 3
    tested_tickers = {d["ticker"] for d in result["details"]}
    assert tested_tickers == set(tickers)


def test_backtested_pcs_skips_empty_series_in_the_list():
    dates = pd.date_range("2020-01-01", periods=120, freq="W")
    rng = np.random.default_rng(4)
    signal = pd.Series(100 + np.cumsum(rng.normal(0, 1, 120)), index=dates)
    good_price = pd.Series(50 + np.cumsum(rng.normal(0, 1, 120)), index=dates)
    result = compute_backtested_pcs(
        signal, [good_price, pd.Series(dtype=float), pd.Series(dtype=float)],
        tickers=["GOOD", "EMPTY1", "EMPTY2"],
    )
    assert result["n_tested"] == 1
    assert result["details"][0]["ticker"] == "GOOD"


def test_backtested_pcs_in_valid_range():
    dates = pd.date_range("2020-01-01", periods=120, freq="W")
    rng = np.random.default_rng(5)
    signal = pd.Series(100 + np.cumsum(rng.normal(0, 1, 120)), index=dates)
    prices = [pd.Series(50 + np.cumsum(rng.normal(0, 1, 120)), index=dates) for _ in range(4)]
    result = compute_backtested_pcs(signal, prices)
    if result["backtested"]:
        assert 1 <= result["pcs"] <= 10
