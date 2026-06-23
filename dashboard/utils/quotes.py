# utils/quotes.py
# Unstructured Alpha — Shared Price Quote + Sparkline Helpers
#
# Extracted 2026-06-22 from pages/5_Market_Overview.py, which had its own
# page-local get_quote()/get_batch_quotes()/mini_sparkline() -- Stock
# Screener and Watchlist now need the EXACT same "price + % change +
# small chart" building blocks (per explicit user request: show price/
# daily % change next to tickers there too, plus a mini chart on
# Watchlist), and duplicating this logic a second and third time would
# risk the three pages' price displays silently drifting out of sync
# with each other -- the same reasoning already applied to
# utils/validation_status.py and utils/score_history.py elsewhere in
# this codebase. Market Overview now imports from here instead of
# defining its own copy.

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# CBOE treasury "yield index" tickers quote the yield × 10 (e.g. a 4.30%
# yield shows as 43.00) -- must be divided by 10 to get the real
# percentage. Only relevant if a caller ever passes one of these in;
# Stock Screener/Watchlist tickers won't, but kept here since get_quote()
# needs to know about it regardless of caller.
CBOE_YIELD_TICKERS = {"^TNX", "^TYX", "^FVX", "^IRX"}

PERIODS = ["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "2Y", "ALL"]
PERIOD_DAYS = {
    "1D": 1, "5D": 5, "1M": 22, "3M": 66, "6M": 132,
    "YTD": None, "1Y": 252, "2Y": 504, "ALL": 0,
}


def _pct_change(close: pd.Series, period: str) -> float | None:
    """Return % change for the selected period using daily close data."""
    try:
        n = PERIOD_DAYS[period]
        last = float(close.iloc[-1])

        if n is None:           # YTD: from Jan 1 of current year
            yr_start = pd.Timestamp(datetime.now().year, 1, 1, tz=close.index.tz)
            ytd = close[close.index >= yr_start]
            if len(ytd) < 2:
                yr_start_naive = pd.Timestamp(datetime.now().year, 1, 1)
                ytd = close[close.index.normalize() >= yr_start_naive]
            if len(ytd) < 1:
                return None
            start = float(ytd.iloc[0])
        elif n == 0:            # ALL: from first available data point
            start = float(close.iloc[0])
        else:
            idx = max(0, len(close) - n - 1)
            start = float(close.iloc[idx])

        return (last - start) / start * 100 if start and start != 0 else None
    except Exception:
        return None


@st.cache_data(ttl=900, show_spinner=False)
def get_quote(ticker: str, _v: int = 5) -> dict:
    """
    Fetch full available daily history for `ticker` and pre-compute
    returns for every period in PERIODS, plus the close-price series
    itself (so a caller can build a sparkline without a second fetch).
    Cached 15 minutes -- this is a "how's it doing today and historically"
    snapshot, not a sub-minute live tick (see fetch_live_quote() in
    utils/fetchers.py for that, a different, much-shorter-cache tool).

    Returns {} on any failure (empty/missing history, bad ticker, etc.)
    -- callers must treat that as "quote unavailable," never crash or
    fabricate a placeholder price.
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="max", interval="1d")
        if hist.empty:
            for fallback_period in ("5y", "2y", "1y", "6mo"):
                hist = t.history(period=fallback_period, interval="1d")
                if not hist.empty:
                    break
        if hist.empty:
            return {}
        close = hist["Close"].dropna()
        if len(close) < 5:
            return {}

        if ticker in CBOE_YIELD_TICKERS:
            close = close / 10.0

        last = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else last
        if not (all(pd.notna([last, prev])) and prev != 0):
            return {}

        chg_1d_abs = last - prev
        chg_1d_pct = (chg_1d_abs / prev * 100) if prev else None

        returns = {p: _pct_change(close, p) for p in PERIODS}

        return {
            "last":      last,
            "chg_1d":    chg_1d_abs,
            "chg_1d_pct": chg_1d_pct,
            "returns":   returns,
            "series":    close,
        }
    except Exception:
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def get_batch_quotes(tickers: list, _v: int = 8) -> dict:
    """
    {ticker: get_quote(ticker) result} for every ticker in `tickers`.

    REWRITTEN 2026-06-23 to use yf.download() instead of a sequential
    per-ticker loop. The prior ThreadPoolExecutor attempt (reverted on
    2026-06-22) crashed production because we wrapped yfinance's single-
    ticker API in external threads -- curl_cffi, yfinance's HTTP client,
    doesn't tolerate that. yf.download() is different: it uses yfinance's
    OWN internal thread pool, specifically designed and tested for multi-
    ticker fetching. This is the correct, library-sanctioned approach.

    Performance: ~80 screener tickers go from ~30s (sequential) to ~3s
    (yf.download single request). Each ticker's data is extracted from the
    multi-ticker DataFrame and converted to the same {last, chg_1d_pct,
    returns, series} dict shape that get_quote() returns, so every
    downstream caller (Watchlist, Stock Screener, Market Overview) works
    identically -- no interface change.

    Falls back to the sequential loop for a single ticker (yf.download
    with one ticker drops the ticker level from the column MultiIndex,
    which requires special handling; single-ticker callers are better
    served by get_quote() directly anyway).
    """
    if not tickers:
        return {}

    # Single ticker: yf.download drops the ticker level — delegate to get_quote
    if len(tickers) == 1:
        return {tickers[0]: get_quote(tickers[0])}

    try:
        raw = yf.download(
            tickers,
            period="max",
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="ticker",  # MultiIndex: (ticker, OHLCV field)
        )
    except Exception:
        # Network error: fall back to sequential so the page degrades
        # gracefully rather than returning an empty dict for all tickers.
        return {t: get_quote(t) for t in tickers}

    if raw is None or raw.empty:
        return {t: get_quote(t) for t in tickers}

    results = {}
    for t in tickers:
        try:
            # Extract this ticker's Close column from the MultiIndex DataFrame.
            # yf.download with group_by="ticker" produces columns like
            # (ticker, "Close"), (ticker, "Open"), etc.
            if isinstance(raw.columns, pd.MultiIndex):
                close = raw[t]["Close"].dropna() if t in raw.columns.get_level_values(0) else pd.Series(dtype=float)
            else:
                # Shouldn't happen with 2+ tickers and group_by="ticker", but handle it
                close = raw.get("Close", pd.Series(dtype=float)).dropna()

            if t in CBOE_YIELD_TICKERS:
                close = close / 10.0

            if len(close) < 5:
                results[t] = {}
                continue

            last = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) > 1 else last
            if not (pd.notna(last) and pd.notna(prev) and prev != 0):
                results[t] = {}
                continue

            chg_1d_abs = last - prev
            chg_1d_pct = (chg_1d_abs / prev * 100)
            returns = {p: _pct_change(close, p) for p in PERIODS}

            results[t] = {
                "last":       last,
                "chg_1d":     chg_1d_abs,
                "chg_1d_pct": chg_1d_pct,
                "returns":    returns,
                "series":     close,
            }
        except Exception:
            results[t] = {}

    # Fill any tickers missing from the download (delisted, bad symbol, etc.)
    for t in tickers:
        if t not in results:
            results[t] = {}

    return results


def get_return(q: dict, period: str) -> float | None:
    """Safe accessor for a period return from a get_quote() result."""
    if not q:
        return None
    return q.get("returns", {}).get(period)


def period_label(period: str) -> str:
    labels = {
        "1D": "Today", "5D": "5-Day", "1M": "1-Month", "3M": "3-Month",
        "6M": "6-Month", "YTD": "YTD", "1Y": "1-Year", "2Y": "2-Year", "ALL": "All-Time",
    }
    return labels.get(period, period)


def mini_sparkline(series: pd.Series, color: str, period: str, show_axes: bool = False) -> go.Figure:
    """
    A small Plotly line chart over the given period window -- built for
    inline use next to a ticker row (Watchlist, Market Overview's index
    cards), not as a standalone full chart.

    `show_axes=False` (the default, unchanged from before) keeps Market
    Overview's existing minimal index-card look exactly as it was --
    axis-free, the classic compact-sparkline style. `show_axes=True`
    (used by Watchlist as of 2026-06-22, per explicit user request to see
    actual prices/times on the watchlist charts, not just a bare shape)
    shows real tick labels on both axes instead.
    """
    n = PERIOD_DAYS.get(period, 22)
    if period == "YTD":
        yr_start = pd.Timestamp(datetime.now().year, 1, 1, tz=series.index.tz)
        spark = series[series.index >= yr_start]
        if len(spark) < 2:
            spark = series.iloc[-252:]
    elif n == 0:               # ALL — full series
        spark = series
    else:
        n = n or 252
        spark = series.iloc[-max(n + 5, 5):]

    fig = go.Figure(go.Scatter(
        x=spark.index, y=spark.values,
        mode="lines", line=dict(color=color, width=1.5, shape="spline", smoothing=0.3),
        fill="tozeroy", fillcolor="rgba(28,43,74,0.09)",
        hovertemplate="%{x|%b %d}: $%{y:,.2f}<extra></extra>",
    ))
    if show_axes:
        fig.update_layout(
            height=90, margin=dict(l=0, r=0, t=4, b=18),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=True, showgrid=False, tickfont=dict(color="#8B7355", size=8), nticks=4),
            yaxis=dict(visible=True, showgrid=True, gridcolor="rgba(0,0,0,0.06)",
                       tickfont=dict(color="#8B7355", size=8), tickprefix="$", nticks=3),
            showlegend=False,
        )
    else:
        fig.update_layout(
            height=55, margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            showlegend=False,
        )
    return fig
