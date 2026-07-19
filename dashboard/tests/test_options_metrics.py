"""Tests for derived options metrics.

Max pain and premium are checked against figures worked out by hand below
rather than against whatever the implementation happens to return, so the tests
would catch a plausible-but-wrong formula (the usual failure mode here is
forgetting the 100-share multiplier, or minimising the wrong side's payout).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from utils.options_metrics import (
    CONTRACT_MULTIPLIER,
    atm_iv,
    days_to_expiration,
    itm_fraction,
    max_pain,
    net_premium,
    put_call_ratio,
    spread_pct,
    summarize,
    total_open_interest,
    total_volume,
)


@pytest.fixture
def calls() -> pd.DataFrame:
    return pd.DataFrame({
        "strike": [90.0, 100.0, 110.0],
        "openInterest": [100, 200, 50],
        "volume": [10, 400, 25],
        "lastPrice": [12.0, 4.0, 0.50],
        "bid": [11.8, 3.9, 0.45],
        "ask": [12.2, 4.1, 0.55],
        "impliedVolatility": [0.55, 0.40, 0.62],
    })


@pytest.fixture
def puts() -> pd.DataFrame:
    return pd.DataFrame({
        "strike": [90.0, 100.0, 110.0],
        "openInterest": [300, 150, 20],
        "volume": [200, 100, 5],
        "lastPrice": [1.0, 3.5, 11.0],
        "bid": [0.9, 3.4, 10.8],
        "ask": [1.1, 3.6, 11.2],
        "impliedVolatility": [0.70, 0.45, 0.58],
    })


# ── Max pain ──────────────────────────────────────────────────────────────────

def test_max_pain_matches_hand_calculation(calls, puts):
    """Worked by hand across the three candidate strikes.

    Call payout at K = sum(OI * max(0, K - strike)):
      K=90  -> 0
      K=100 -> 100*10 = 1000
      K=110 -> 100*20 + 200*10 = 4000
    Put payout at K = sum(OI * max(0, strike - K)):
      K=90  -> 150*10 + 20*20 = 1900
      K=100 -> 20*10 = 200
      K=110 -> 0
    Totals: K=90 -> 1900, K=100 -> 1200, K=110 -> 4000. Minimum is K=100.
    """
    assert max_pain(calls, puts) == 100.0


def test_max_pain_is_none_without_open_interest():
    """An empty chain must not yield an arbitrary strike."""
    df = pd.DataFrame({"strike": [10.0, 20.0], "openInterest": [0, 0]})
    assert max_pain(df, df) is None


def test_max_pain_handles_one_sided_chain(calls):
    """Puts missing entirely: pain is minimised at the lowest strike, where no
    call has intrinsic value."""
    assert max_pain(calls, pd.DataFrame()) == 90.0


def test_max_pain_on_empty_inputs():
    assert max_pain(pd.DataFrame(), pd.DataFrame()) is None


def test_max_pain_ignores_strikes_with_no_open_contracts():
    calls = pd.DataFrame({"strike": [50.0, 60.0], "openInterest": [0, 1000]})
    puts = pd.DataFrame({"strike": [50.0, 60.0], "openInterest": [1000, 0]})
    # K=50: calls 0, puts 0     -> 0
    # K=60: calls 0, puts 1000*10 = 10000
    assert max_pain(calls, puts) == 50.0


# ── Premium ───────────────────────────────────────────────────────────────────

def test_net_premium_applies_the_contract_multiplier(calls):
    """10*12 + 400*4 + 25*0.5 = 1732.5 contracts-dollars, x100 = 173_250."""
    assert net_premium(calls) == pytest.approx(173_250.0)


def test_net_premium_multiplier_is_not_silently_dropped(calls):
    """The classic bug: reporting per-share premium as dollar flow."""
    assert net_premium(calls) == pytest.approx(1732.5 * CONTRACT_MULTIPLIER)


def test_net_premium_falls_back_to_mid_when_last_price_missing():
    df = pd.DataFrame({
        "volume": [10],
        "lastPrice": [0.0],
        "bid": [2.0],
        "ask": [3.0],
    })
    assert net_premium(df) == pytest.approx(10 * 2.5 * CONTRACT_MULTIPLIER)


def test_net_premium_on_empty():
    assert net_premium(pd.DataFrame()) == 0.0


def test_premium_ranks_conviction_differently_than_contract_count():
    """The reason premium was added: contract count flatters cheap contracts."""
    lottery = pd.DataFrame({"volume": [10_000], "lastPrice": [0.05]})
    serious = pd.DataFrame({"volume": [200], "lastPrice": [12.00]})
    assert total_volume(lottery) > total_volume(serious)
    assert net_premium(serious) > net_premium(lottery)


# ── Ratios ────────────────────────────────────────────────────────────────────

def test_put_call_ratio_on_volume(calls, puts):
    # puts 305 / calls 435
    assert put_call_ratio(calls, puts, "volume") == pytest.approx(305 / 435)


def test_put_call_ratio_on_open_interest(calls, puts):
    # puts 470 / calls 350
    assert put_call_ratio(calls, puts, "openInterest") == pytest.approx(470 / 350)


def test_volume_and_oi_ratios_can_disagree(calls, puts):
    """They answer different questions, which is why both are shown."""
    vol = put_call_ratio(calls, puts, "volume")
    oi = put_call_ratio(calls, puts, "openInterest")
    assert vol < 1 < oi


def test_put_call_ratio_none_on_zero_calls():
    empty = pd.DataFrame({"volume": [0]})
    assert put_call_ratio(empty, pd.DataFrame({"volume": [5]}), "volume") is None


# ── IV / ITM ──────────────────────────────────────────────────────────────────

def test_atm_iv_picks_the_nearest_strike(calls):
    assert atm_iv(calls, 101.0) == pytest.approx(40.0)


def test_atm_iv_prefers_nearest_not_average(calls):
    """A chain-wide mean would be (55+40+62)/3 = 52.3, which is not the ATM read."""
    assert atm_iv(calls, 100.0) == pytest.approx(40.0)


def test_atm_iv_skips_zero_iv_rows():
    df = pd.DataFrame({"strike": [100.0, 101.0], "impliedVolatility": [0.0, 0.33]})
    assert atm_iv(df, 100.0) == pytest.approx(33.0)


def test_atm_iv_none_without_spot(calls):
    assert atm_iv(calls, None) is None


def test_itm_fraction_is_open_interest_weighted(calls):
    """Spot 105: calls at 90 and 100 are ITM -> (100+200)/350."""
    assert itm_fraction(calls, 105.0, is_call=True) == pytest.approx(300 / 350)


def test_itm_fraction_puts_use_the_other_side(puts):
    """Spot 95: puts at 100 and 110 are ITM -> (150+20)/470."""
    assert itm_fraction(puts, 95.0, is_call=False) == pytest.approx(170 / 470)


def test_itm_fraction_falls_back_to_unweighted_count():
    df = pd.DataFrame({"strike": [90.0, 110.0], "openInterest": [0, 0]})
    assert itm_fraction(df, 100.0, is_call=True) == pytest.approx(0.5)


def test_itm_fraction_none_without_spot(calls):
    assert itm_fraction(calls, None, is_call=True) is None


# ── Misc ──────────────────────────────────────────────────────────────────────

def test_days_to_expiration():
    assert days_to_expiration("2026-07-25", today=date(2026, 7, 19)) == 6


def test_days_to_expiration_clamps_the_past():
    assert days_to_expiration("2026-07-01", today=date(2026, 7, 19)) == 0


def test_days_to_expiration_rejects_garbage():
    assert days_to_expiration("not a date") is None
    assert days_to_expiration(None) is None


def test_spread_pct(calls):
    """Spreads: 0.4/12 , 0.2/4 , 0.1/0.5 -> median of 3.33%, 5%, 20% = 5%."""
    assert spread_pct(calls) == pytest.approx(5.0)


def test_spread_pct_none_without_quotes():
    assert spread_pct(pd.DataFrame({"volume": [1]})) is None


# ── Robustness ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fn", [total_volume, total_open_interest, net_premium])
def test_aggregates_tolerate_missing_columns(fn):
    assert fn(pd.DataFrame({"strike": [1.0]})) == 0


def test_summarize_returns_every_key(calls, puts):
    out = summarize(calls, puts, spot=100.0, nearest_expiration="2026-08-21")
    for key in ("call_volume", "put_volume", "call_oi", "put_oi", "call_premium",
                "put_premium", "pcr_volume", "pcr_oi", "max_pain", "atm_iv_call",
                "atm_iv_put", "itm_calls", "itm_puts", "dte", "call_spread_pct",
                "put_spread_pct", "net_premium_bias"):
        assert key in out, f"{key} missing from summary"


def test_summarize_on_empty_chain_does_not_raise():
    out = summarize(pd.DataFrame(), pd.DataFrame(), spot=None)
    assert out["max_pain"] is None
    assert out["call_volume"] == 0


def test_summarize_net_premium_bias_sign(calls, puts):
    out = summarize(calls, puts, spot=100.0)
    assert out["net_premium_bias"] == pytest.approx(
        out["call_premium"] - out["put_premium"]
    )


def test_nan_values_do_not_propagate():
    df = pd.DataFrame({
        "strike": [100.0, float("nan")],
        "openInterest": [10, float("nan")],
        "volume": [5, float("nan")],
        "lastPrice": [2.0, float("nan")],
    })
    assert total_volume(df) == 5
    assert net_premium(df) == pytest.approx(1000.0)
