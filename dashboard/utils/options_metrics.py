"""Derived options-chain metrics.

The Options Flow page reported contract counts and raw volume but left the
standard positioning metrics off the board entirely: no max pain, no open
interest anywhere (only volume), no dollar premium, no ATM implied volatility,
no days-to-expiration. Contract count also flatters cheap far-OTM lottery
tickets — 10,000 contracts at $0.05 is $50k of conviction, while 200 contracts
at $12 is $240k. Premium is the honest measure of how much money is behind a
position, so it is computed here alongside the rest.

Every function is pure and takes plain DataFrames so it can be tested without a
network call. All of them tolerate missing columns and empty frames, because
yfinance omits fields per-ticker and a missing column must degrade to None
rather than raise on a Pro page.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

# One equity option contract covers 100 shares. Premium figures are meaningless
# without it — omitting it understates dollar flow by two orders of magnitude.
CONTRACT_MULTIPLIER = 100


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """Column as float, or an all-zero series when absent/empty."""
    if df is None or df.empty or name not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[name], errors="coerce").fillna(0.0)


def total_open_interest(df: pd.DataFrame) -> int:
    return int(_col(df, "openInterest").sum())


def total_volume(df: pd.DataFrame) -> int:
    return int(_col(df, "volume").sum())


def net_premium(df: pd.DataFrame) -> float:
    """Dollar premium traded today: volume x last price x 100.

    Uses lastPrice rather than the mid of bid/ask: the mid describes where the
    contract could trade now, while lastPrice describes where it did trade, and
    this metric is about flow that already happened. Falls back to the mid only
    when lastPrice is absent.
    """
    if df is None or df.empty:
        return 0.0
    vol = _col(df, "volume")
    price = _col(df, "lastPrice")
    if price.sum() == 0 and {"bid", "ask"} <= set(df.columns):
        price = (_col(df, "bid") + _col(df, "ask")) / 2.0
    return float((vol * price * CONTRACT_MULTIPLIER).sum())


def put_call_ratio(calls: pd.DataFrame, puts: pd.DataFrame, field: str = "volume") -> float | None:
    """P/C ratio on volume (today's flow) or openInterest (standing position).

    The page previously showed only the volume ratio. They answer different
    questions and routinely disagree: volume is what traders did today, open
    interest is what they are still holding.
    """
    c = _col(calls, field).sum()
    p = _col(puts, field).sum()
    if not c:
        return None
    return float(p / c)


def max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> float | None:
    """Strike at which option buyers collectively lose the most at expiry.

    For each candidate settlement price K, the writers' payout is the total
    intrinsic value of every open contract:

        calls: sum(OI * max(0, K - strike))
        puts:  sum(OI * max(0, strike - K))

    Max pain is the K minimising that sum. It is a positioning statistic, not a
    forecast — it says where the most open contracts expire worthless, which is
    why it is presented on the page as context rather than as a target.

    Returns None when there is no open interest to weigh, rather than returning
    an arbitrary strike from an empty chain.
    """
    if (calls is None or calls.empty) and (puts is None or puts.empty):
        return None

    strikes: set[float] = set()
    for df in (calls, puts):
        if df is not None and not df.empty and "strike" in df.columns:
            strikes.update(pd.to_numeric(df["strike"], errors="coerce").dropna().tolist())
    if not strikes:
        return None

    c_strike, c_oi = _col(calls, "strike"), _col(calls, "openInterest")
    p_strike, p_oi = _col(puts, "strike"), _col(puts, "openInterest")
    if c_oi.sum() + p_oi.sum() <= 0:
        return None

    best_strike, best_pain = None, None
    for k in sorted(strikes):
        pain = 0.0
        if len(c_strike):
            pain += float(((k - c_strike).clip(lower=0) * c_oi).sum())
        if len(p_strike):
            pain += float(((p_strike - k).clip(lower=0) * p_oi).sum())
        if best_pain is None or pain < best_pain:
            best_strike, best_pain = float(k), pain
    return best_strike


def atm_iv(df: pd.DataFrame, spot: float | None) -> float | None:
    """Implied volatility of the contract closest to the money, as a percent.

    Reported for the nearest strike rather than as a chain-wide average: an
    average across a skewed chain is dominated by illiquid far-OTM contracts
    whose IV is an artefact of a wide bid-ask, not a market view.
    """
    if df is None or df.empty or not spot:
        return None
    if "strike" not in df.columns or "impliedVolatility" not in df.columns:
        return None
    sub = df.copy()
    sub["_iv"] = pd.to_numeric(sub["impliedVolatility"], errors="coerce")
    sub["_k"] = pd.to_numeric(sub["strike"], errors="coerce")
    sub = sub[(sub["_iv"] > 0) & sub["_k"].notna()]
    if sub.empty:
        return None
    row = sub.iloc[(sub["_k"] - float(spot)).abs().argsort().iloc[0]]
    return float(row["_iv"]) * 100.0


def itm_fraction(df: pd.DataFrame, spot: float | None, is_call: bool) -> float | None:
    """Share of contracts currently in the money, 0-1.

    Weighted by open interest where available rather than counting rows: an
    unweighted count treats a strike with 4 open contracts the same as one with
    40,000, which says nothing about where positioning actually sits.
    """
    if df is None or df.empty or not spot or "strike" not in df.columns:
        return None
    strike = _col(df, "strike")
    if strike.empty:
        return None
    oi = _col(df, "openInterest")
    weights = oi if oi.sum() > 0 else pd.Series(1.0, index=strike.index)
    itm = (strike <= float(spot)) if is_call else (strike >= float(spot))
    denom = float(weights.sum())
    if denom <= 0:
        return None
    return float(weights[itm].sum() / denom)


def days_to_expiration(expiration: str | date | datetime, today: date | None = None) -> int | None:
    """Calendar days until expiry. Negative values are clamped to 0."""
    if expiration is None:
        return None
    try:
        exp = pd.Timestamp(expiration).date()
    except (ValueError, TypeError):
        return None
    ref = today or datetime.now().date()
    return max((exp - ref).days, 0)


def spread_pct(df: pd.DataFrame) -> float | None:
    """Median bid-ask spread as a percent of the mid — a liquidity read.

    A chain quoting 40% spreads is not tradeable at the prices shown, which is
    material context next to any "unusual activity" claim.
    """
    if df is None or df.empty or not {"bid", "ask"} <= set(df.columns):
        return None
    bid, ask = _col(df, "bid"), _col(df, "ask")
    mid = (bid + ask) / 2.0
    valid = mid > 0
    if not valid.any():
        return None
    return float((((ask - bid) / mid)[valid]).median() * 100.0)


def summarize(
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    spot: float | None,
    nearest_expiration: str | None = None,
) -> dict[str, Any]:
    """Every derived metric in one pass, for the page header."""
    return {
        "call_volume": total_volume(calls),
        "put_volume": total_volume(puts),
        "call_oi": total_open_interest(calls),
        "put_oi": total_open_interest(puts),
        "call_premium": net_premium(calls),
        "put_premium": net_premium(puts),
        "pcr_volume": put_call_ratio(calls, puts, "volume"),
        "pcr_oi": put_call_ratio(calls, puts, "openInterest"),
        "max_pain": max_pain(calls, puts),
        "atm_iv_call": atm_iv(calls, spot),
        "atm_iv_put": atm_iv(puts, spot),
        "itm_calls": itm_fraction(calls, spot, is_call=True),
        "itm_puts": itm_fraction(puts, spot, is_call=False),
        "dte": days_to_expiration(nearest_expiration) if nearest_expiration else None,
        "call_spread_pct": spread_pct(calls),
        "put_spread_pct": spread_pct(puts),
        "net_premium_bias": net_premium(calls) - net_premium(puts),
    }
