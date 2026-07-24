# utils/fetchers.py
# Unstructured Alpha — Data Fetching Layer
#
# Data sources (all free, none require a credit card):
#   FRED API       — macro signals (ATA trucking, rail, jobless claims, WTI, etc.) — key required
#   EIA API        — crude oil inventories, natural gas storage — key required
#   openFDA        — drug approval velocity — no key needed
#   yfinance       — stock/commodity prices + live quotes (no key needed)
#   CFTC.gov       — COT positioning data (public CSV downloads)
#   USASpending    — federal contract awards (no key needed)
#   SEC EDGAR      — Form 4 insider transactions, both filing metadata and
#                    actual parsed transaction detail (no key needed)
#   FINRA          — consolidated equity short interest, exchange-listed
#                    securities (no key needed) — verified live 2026-06-21:
#                    despite living under the "otcMarket" API group name,
#                    this dataset genuinely covers NYSE/NASDAQ-listed names
#   SEC EDGAR      — Form 13F institutional holdings (no key needed) — a
#                    curated, hand-verified set of funds only (see
#                    utils/config.CURATED_FUNDS and its docstring for why
#                    this is a whitelist, not algorithmic name-matching)
#   arXiv API      — quantum paper velocity (no key needed)
#
# Provider failures return explicitly unavailable empty results. No fetcher
# fabricates substitute observations.

import os
import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from utils.resilience import resilient_get, resilient_post  # shared session + circuit breakers
from utils.provider_health import (
    canonical_provider,
    get_last_known_good,
    record_provider_event,
    remember_last_known_good,
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_fred_key() -> str:
    key = st.session_state.get("FRED_API_KEY", "")
    if not key:
        key = os.environ.get("FRED_API_KEY", "")
    if not key:
        try:
            key = st.secrets.get("FRED_API_KEY", "")
        except Exception:
            pass
    return key


def _get_eia_key() -> str:
    key = st.session_state.get("EIA_API_KEY", "")
    if not key:
        key = os.environ.get("EIA_API_KEY", "")
    if not key:
        try:
            key = st.secrets.get("EIA_API_KEY", "")
        except Exception:
            pass
    return key


def _tz_strip(s: pd.Series) -> pd.Series:
    """Remove timezone from a DatetimeIndex series."""
    if hasattr(s.index, "tz") and s.index.tz is not None:
        s = s.copy()
        s.index = s.index.tz_localize(None)
    return s


def _empty_frame_with_error(provider: str, exc: Exception) -> pd.DataFrame:
    """Represent an unavailable source without caching the failure."""
    frame = pd.DataFrame()
    frame.attrs["fetch_error"] = True
    frame.attrs["provider"] = provider
    frame.attrs["error_type"] = type(exc).__name__
    return frame


def _empty_series_with_error(name: str, provider: str, error_type: str) -> pd.Series:
    """Represent unavailable real data without inventing observations."""
    series = pd.Series(dtype=float, name=name)
    series.attrs["fetch_error"] = True
    series.attrs["provider"] = provider
    series.attrs["error_type"] = error_type
    return series


# ─────────────────────────────────────────────────────────────────────────────
# FRED — Macro Signal Data
# ─────────────────────────────────────────────────────────────────────────────

def is_unavailable(data: pd.Series | pd.DataFrame) -> bool:
    """True when a provider returned no trustworthy real observations."""
    return bool(getattr(data, "attrs", {}).get("fetch_error", False)) or data.empty


@st.cache_data(ttl=21600, show_spinner=False, max_entries=60)  # 6h — FRED series are daily/weekly/monthly, unchanged intraday
def fetch_fred(series_id: str, start: str, end: str, api_key: str = "") -> pd.Series:
    """
    Fetch a FRED data series. Missing credentials and provider failures return
    an explicitly unavailable empty series; this function never fabricates data.

    IMPORTANT — api_key MUST be passed in by the caller (resolved via
    _get_fred_key()), not read internally from st.session_state here. This
    function is decorated with @st.cache_data, which is a server-wide cache
    shared across every concurrent user, keyed on this function's arguments.
    If api_key were read from session_state INSIDE the cached function
    instead of being part of the cache key, the first user to request a
    given (series_id, start, end) would silently determine what every OTHER
    user sees for that same request for the next hour — a user with no key
    could get served another user's real fetched data, or a user who
    correctly configured a key could get served someone else's synthetic
    fallback. Passing api_key as an explicit argument makes it part of the
    cache key, so each key (or lack of one) gets its own cache entry.
    """
    if api_key:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start,
            "observation_end": end,
        }
        try:
            r = resilient_get(url, provider="fred", params=params, timeout=12)
            r.raise_for_status()
            data = r.json()
            df = pd.DataFrame(data["observations"])
            df["date"] = pd.to_datetime(df["date"])
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            s = df.dropna(subset=["value"]).set_index("date")["value"]
            s.name = series_id
            return s
        except Exception as exc:
            return _empty_series_with_error(series_id, "fred", type(exc).__name__)

    return _empty_series_with_error(series_id, "fred", "MissingAPIKey")


@st.cache_data(ttl=604800, show_spinner=False, max_entries=60)  # 7d — a published vintage is immutable, cache hard
def fetch_fred_asof(series_id: str, start: str, end: str, as_of: str, api_key: str = "") -> pd.Series:
    """Point-in-time FRED fetch: the observations for [start, end] AS THEY WERE
    FIRST KNOWN on `as_of` (ALFRED vintage), NOT today's revised numbers.

    This is the honest input for any backtest or validation. The live scoring
    engine at time T only ever saw the data vintage available at T; fetch_fred()
    (which omits realtime params) returns the LATEST revision, so using it to
    reconstruct history bakes in revision / look-ahead bias. Ground-truth
    example that motivated this: INDPRO for 2020-06 was first printed at 97.46
    but reads 91.59 today — a 6% revision the model could not have known.

    `as_of` is an ISO date (YYYY-MM-DD). FRED's realtime_start/realtime_end are
    set to that single day, so the series returned is exactly the vintage in
    effect then; observations not yet published as of that date are correctly
    ABSENT (you did not know them yet), never invented. Missing key or a
    provider failure returns an explicitly-unavailable empty series — this
    function never fabricates data.
    """
    if not api_key:
        return _empty_series_with_error(series_id, "fred", "MissingAPIKey")
    if not as_of:
        return _empty_series_with_error(series_id, "fred", "MissingAsOf")

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "observation_end": end,
        "realtime_start": as_of,
        "realtime_end": as_of,
    }
    try:
        r = resilient_get(url, provider="fred", params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data.get("observations", []))
        if df.empty:
            # No vintage existed on as_of (series unreleased then) — unavailable,
            # not an error to paper over.
            return _empty_series_with_error(series_id, "fred", "NoVintageAsOf")
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        s = df.dropna(subset=["value"]).set_index("date")["value"]
        s.name = series_id
        s.attrs["as_of"] = as_of
        s.attrs["vintage"] = True
        return s
    except Exception as exc:
        return _empty_series_with_error(series_id, "fred", type(exc).__name__)


@st.cache_data(ttl=604800, show_spinner=False, max_entries=60)  # 7d — first prints are immutable
def fetch_fred_first_print(series_id: str, start: str, end: str, api_key: str = "") -> pd.Series:
    """First-print FRED series over [start, end]: every observation's INITIAL
    release value, in a single call, via ALFRED output_type=4.

    Where fetch_fred_asof() answers "what did the vintage on ONE date look like",
    this answers "for each observation, what was FIRST published" across the
    whole range — which is exactly the real-time series a walk-forward backtest
    should see. It removes revision bias from historical inputs (e.g. INDPRO
    2020-06 stays 97.46, its first print, instead of today's revised 91.59).

    realtime_start/realtime_end are pinned to FRED's full sentinel window so
    output_type=4 returns the initial release for every observation. Missing key
    or provider failure returns an explicitly-unavailable empty series; never
    fabricates.
    """
    if not api_key:
        return _empty_series_with_error(series_id, "fred", "MissingAPIKey")

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "observation_end": end,
        "output_type": 4,                 # initial release only
        "realtime_start": "1776-07-04",
        "realtime_end": "9999-12-31",
    }
    try:
        r = resilient_get(url, provider="fred", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data.get("observations", []))
        if df.empty:
            return _empty_series_with_error(series_id, "fred", "NoFirstPrint")
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        # output_type=4 can emit multiple rows per observation date across
        # revisions; keep the EARLIEST realtime row = the genuine first print.
        if "realtime_start" in df.columns:
            df = df.sort_values(["date", "realtime_start"])
        s = (df.dropna(subset=["value"])
               .drop_duplicates(subset=["date"], keep="first")
               .set_index("date")["value"])
        s.name = series_id
        s.attrs["first_print"] = True
        return s
    except Exception as exc:
        return _empty_series_with_error(series_id, "fred", type(exc).__name__)


# ─────────────────────────────────────────────────────────────────────────────
# EIA — Energy Information Administration (crude stocks, gas storage)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=21600, show_spinner=False, max_entries=15)  # 6h — EIA series are weekly, unchanged intraday
def fetch_eia(series_id: str, start: str, end: str, api_key: str = "") -> pd.Series:
    """
    Fetch an EIA data series via the API v2 backward-compatibility endpoint
    (api.eia.gov/v2/seriesid/{id}), which accepts legacy v1-style series IDs
    such as WCESTUS1 (weekly crude stocks ex-SPR) and NW2_EPG0_SWO_R48_BCF
    (weekly Lower-48 working gas in underground storage) — both confirmed
    live on EIA's own dnav pages as of 2026.

    Missing credentials and provider failures return an explicitly unavailable
    empty series; this function never fabricates data.

    api_key MUST be passed in by the caller (resolved via _get_eia_key()) for
    the same reason documented on fetch_fred() — this is a server-wide cache
    shared across every concurrent user, and the key needs to be part of the
    cache key so one user's key (or lack of one) can't leak into what
    another user sees for the same series/date-range request.
    """
    if api_key:
        url = f"https://api.eia.gov/v2/seriesid/{series_id}"
        params = {"api_key": api_key}
        try:
            r = resilient_get(url, provider="eia", params=params, timeout=12)
            r.raise_for_status()
            data = r.json()
            rows = data.get("response", {}).get("data", [])
            if rows:
                df = pd.DataFrame(rows)
                df["date"] = pd.to_datetime(df["period"])
                df["value"] = pd.to_numeric(df["value"], errors="coerce")
                s = df.dropna(subset=["value"]).set_index("date")["value"].sort_index()
                s = s.loc[(s.index >= pd.to_datetime(start)) & (s.index <= pd.to_datetime(end))]
                s.name = series_id
                return s
        except Exception as exc:
            return _empty_series_with_error(series_id, "eia", type(exc).__name__)

    return _empty_series_with_error(series_id, "eia", "MissingAPIKey")


# ─────────────────────────────────────────────────────────────────────────────
# NY Fed Global Supply Chain Pressure Index (GSCPI)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False, max_entries=1)
def fetch_ny_fed_gscpi(start: str, end: str) -> pd.Series:
    """
    Fetch the NY Fed Global Supply Chain Pressure Index (GSCPI).

    The GSCPI is published monthly as an Excel file at:
      https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx

    The file has a sheet called 'Monthly' with two columns:
      - Column 0: date (e.g. "Jan-1997")
      - Column 1: GSCPI value (standard deviations from zero)

    Positive values = above-average global supply chain stress.
    Negative values = below-average stress (smooth conditions).

    Provider or parser failures return an explicitly unavailable empty series.
    """
    _URL = (
        "https://www.newyorkfed.org/medialibrary/research/"
        "interactives/gscpi/downloads/gscpi_data.xlsx"
    )
    try:
        r = resilient_get(_URL, provider="ny_fed", timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        raw = io.BytesIO(r.content)
        # openpyxl is required for .xlsx; if absent this raises ImportError
        # which falls through to synthetic below.
        df = pd.read_excel(raw, sheet_name="Monthly", header=0, engine="openpyxl")
        # Column layout: first col = date string, second col = GSCPI value.
        df.columns = ["date", "gscpi"]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["gscpi"] = pd.to_numeric(df["gscpi"], errors="coerce")
        df = df.dropna(subset=["date", "gscpi"]).set_index("date")
        s = df["gscpi"].sort_index()
        # Filter to requested window
        s = s.loc[
            (s.index >= pd.to_datetime(start))
            & (s.index <= pd.to_datetime(end))
        ]
        s.name = "gscpi"
        return s
    except Exception as exc:
        return _empty_series_with_error("gscpi", "ny_fed", type(exc).__name__)



# ─────────────────────────────────────────────────────────────────────────────
# yfinance — Stock & Commodity Prices
# ─────────────────────────────────────────────────────────────────────────────

# Explicit yfinance network deadline. Without it, a slow Yahoo response holds
# the (single) Streamlit worker thread far longer than yfinance's loose default,
# and during a 280-ticker scan those waits stack up and starve the whole app.
# Kept short: a stale cached value or a skipped ticker beats a frozen worker.
_YF_TIMEOUT = 8  # seconds per yfinance HTTP call


@st.cache_data(ttl=7200, show_spinner=False, max_entries=150)  # 2h — daily close series only gains one bar/day; TradingView is the live chart
def _fetch_price_cached(ticker: str, start: str, end: str) -> pd.Series:
    """Fetch daily closing price. No API key required."""
    try:
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True, timeout=_YF_TIMEOUT)
        if hist.empty:
            raise RuntimeError("price source returned no rows")
        s = hist["Close"].rename(ticker)
        return _tz_strip(s)
    except Exception:
        raise


def fetch_price(ticker: str, start: str, end: str) -> pd.Series:
    ticker = str(ticker).upper().strip()
    try:
        return _fetch_price_cached(ticker, str(start)[:10], str(end)[:10])
    except Exception as exc:
        series = pd.Series(dtype=float, name=ticker)
        series.attrs.update(fetch_error=True, provider="yfinance", error_type=type(exc).__name__)
        return series


fetch_price.clear = _fetch_price_cached.clear


@st.cache_data(ttl=7200, show_spinner=False, max_entries=80)  # 2h — daily volume series, matches fetch_price
def fetch_volume(ticker: str, start: str, end: str) -> pd.Series:
    """
    Fetch daily trading volume -- a separate function from fetch_price()
    above rather than returning a DataFrame with both columns, since
    fetch_price() is already called throughout this codebase expecting a
    plain Series; changing its return shape would mean auditing and
    updating every existing call site. A second yfinance .history() call
    for the same ticker/date range is a real, small redundant cost, but
    it's cached the same 30 minutes as fetch_price(), and far lower risk
    than reshaping an already-widely-used function.
    """
    try:
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True, timeout=_YF_TIMEOUT)
        if hist.empty or "Volume" not in hist.columns:
            return pd.Series(dtype=float, name=ticker)
        s = hist["Volume"].rename(ticker)
        return _tz_strip(s)
    except Exception:
        return pd.Series(dtype=float, name=ticker)


@st.cache_data(ttl=300, show_spinner=False, max_entries=100)  # 5min — live-ish quote; ample for a macro product, cuts yfinance quote calls 5x
def fetch_live_quote(ticker: str) -> dict:
    """
    Fetch current price, day change, and pre/post-market data for a ticker.

    Uses fast_info for the main price (cheap), then pulls preMarketPrice /
    postMarketPrice from Ticker.info where available. Both are cached for
    60 seconds — the pre/post prices are volatile but not sub-minute signals.

    Returns dict with keys:
        price, prev_close, pct_change         — regular session
        pre_price, pre_change_pct             — pre-market (None if unavailable)
        post_price, post_change_pct           — post-market (None if unavailable)
        market_state                          — "PRE", "REGULAR", "POST", "CLOSED", None

    All None on failure — callers must treat as "unavailable", never crash.
    """
    try:
        t = yf.Ticker(ticker)
        # yfinance normally exposes FastInfo as an object, but some versions
        # and test adapters provide the same fields as a mapping.
        fi = t.fast_info
        if isinstance(fi, dict):
            price = fi.get("lastPrice") or fi.get("last_price")
            prev_close = (fi.get("previousClose") or fi.get("previous_close") or
                          fi.get("regularMarketPreviousClose"))
        else:
            price = getattr(fi, "last_price", None)
            prev_close = (
                getattr(fi, "previous_close", None)
                or getattr(fi, "regular_market_previous_close", None)
            )
        # Fallback to .info dict if fast_info didn't give us a price
        if price is None:
            try:
                info = t.info or {}
                price = info.get("regularMarketPrice") or info.get("currentPrice")
                prev_close = prev_close or info.get("regularMarketPreviousClose") or info.get("previousClose")
            except Exception:
                pass
        if price is None:
            return {
                "price": None, "prev_close": None, "pct_change": None,
                "pre_price": None, "pre_change_pct": None,
                "post_price": None, "post_change_pct": None,
                "market_state": None,
            }
        pct_change = ((price - prev_close) / prev_close * 100) if prev_close else None

        # Pre/post market — from .info (heavier but cached 60s, acceptable)
        pre_price = pre_chg = post_price = post_chg = market_state = None
        try:
            info = t.info or {}
            market_state_raw = info.get("marketState")  # "PRE", "REGULAR", "POST", "CLOSED"
            market_state = market_state_raw if isinstance(market_state_raw, str) else None
            pre_price_raw  = info.get("preMarketPrice")
            post_price_raw = info.get("postMarketPrice")
            if pre_price_raw and prev_close:
                pre_price = float(pre_price_raw)
                pre_chg   = (pre_price - float(prev_close)) / float(prev_close) * 100
            if post_price_raw and prev_close:
                post_price = float(post_price_raw)
                post_chg   = (post_price - float(prev_close)) / float(prev_close) * 100
        except Exception:
            pass  # Pre/post market failure must never crash the main price display

        return {
            "price":          float(price),
            "prev_close":     float(prev_close) if prev_close else None,
            "pct_change":     float(pct_change) if pct_change is not None else None,
            "pre_price":      pre_price,
            "pre_change_pct": float(pre_chg) if pre_chg is not None else None,
            "post_price":     post_price,
            "post_change_pct": float(post_chg) if post_chg is not None else None,
            "market_state":   market_state,
        }
    except Exception:
        return {
            "price": None, "prev_close": None, "pct_change": None,
            "pre_price": None, "pre_change_pct": None,
            "post_price": None, "post_change_pct": None,
            "market_state": None,
        }


def fetch_signal_series(cfg: dict, start: str, end: str,
                        point_in_time: bool = False) -> pd.Series:
    """
    Single dispatch point for fetching a signal's raw data series, used by
    every page that scores signals from SIGNALS config entries. Keeping this
    in one place means adding a new source type (like "arxiv") only has to
    happen once instead of being duplicated across five page-level loops.

    `point_in_time=True` returns the REAL-TIME (first-print) history for
    revisable sources instead of today's latest-revised values — the honest
    input for backtests/validation, which must only see data as it was known at
    the time. Today only FRED supports this (via fetch_fred_first_print); prices
    are not revised, and the other providers have no clean vintage API, so those
    sources are returned unchanged and the flag makes NO false point-in-time
    claim about them. Live scoring must keep point_in_time=False: the current
    reading IS the latest revision.
    """
    src = str(cfg.get("source") or "unknown")
    ids = cfg.get("series_ids") or [cfg.get("series_id", "")]
    if isinstance(ids, str):
        ids = [ids]
    pit_tag = "pit" if point_in_time else "live"
    cache_key = f"{src}:{'|'.join(str(item) for item in ids)}:{start}:{end}:{pit_tag}"
    # Most sources report transport health in resilient_get/post. These two
    # clients manage their own HTTP internally, so dispatch is their only
    # privacy-safe telemetry boundary. Avoid double-counting other providers.
    records_dispatch_health = src.startswith("yfinance") or src == "google_trends"
    try:
        if src == "fred":
            if point_in_time:
                result = fetch_fred_first_print(cfg["series_id"], start, end, api_key=_get_fred_key())
            else:
                result = fetch_fred(cfg["series_id"], start, end, api_key=_get_fred_key())
        elif src == "eia":
            result = fetch_eia(cfg["series_id"], start, end, api_key=_get_eia_key())
        elif src == "yfinance":
            result = fetch_price(cfg["series_id"], start, end)
        elif src in ("yfinance_basket", "yfinance_multi"):
            result = fetch_basket(cfg.get("series_ids", [cfg.get("series_id", "SPY")]), start, end)
        elif src == "yfinance_ratio":
            ids = cfg.get("series_ids", [])
            if len(ids) < 2:
                result = pd.Series(dtype=float)
            else:
                s1 = fetch_price(ids[0], start, end)
                s2 = fetch_price(ids[1], start, end)
                combined = pd.concat([s1, s2], axis=1, join="inner").dropna()
                if s1.empty or s2.empty or combined.empty or (combined.iloc[:, 1] == 0).any():
                    result = pd.Series(dtype=float)
                else:
                    result = (combined.iloc[:, 0] / combined.iloc[:, 1])
                    result.name = "ratio"
        elif src == "arxiv":
            result = fetch_arxiv_velocity(query=cfg.get("series_id", "quantum computing"))
        elif src == "fda":
            result = fetch_fda_approval_velocity()
        elif src == "google_trends":
            result = fetch_google_trends_fear(terms=cfg.get("series_id", "market crash,recession"))
        elif src == "fedspeaks":
            result = fetch_fedspeaks_hawkishness(series_id=cfg.get("series_id", "fomc_hawkishness"))
        elif src == "ny_fed_gscpi":
            result = fetch_ny_fed_gscpi(start, end)
        else:
            result = pd.Series(dtype=float)

        attrs = getattr(result, "attrs", {})
        failed = result is None or result.empty or bool(attrs.get("fetch_error"))
        if not failed:
            result = result.copy()
            result.attrs.update({
                "provider": canonical_provider(src),
                "data_state": "live",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "stale": False,
            })
            remember_last_known_good(cache_key, result, provider=src)
            if records_dispatch_health:
                record_provider_event(src, success=True)
            return result

        if records_dispatch_health:
            record_provider_event(src, success=False, error_type=attrs.get("error_type", "EmptyResponse"))
        cached = get_last_known_good(cache_key)
        if cached is not None:
            return cached
        if result is None:
            result = pd.Series(dtype=float)
        result.attrs.setdefault("provider", canonical_provider(src))
        result.attrs.setdefault("fetch_error", True)
        result.attrs.setdefault("error_type", "EmptyResponse")
        return result
    except Exception as exc:
        if records_dispatch_health:
            record_provider_event(src, success=False, error_type=type(exc).__name__)
        cached = get_last_known_good(cache_key)
        if cached is not None:
            return cached
        result = pd.Series(dtype=float)
        result.attrs.update({
            "provider": canonical_provider(src),
            "fetch_error": True,
            "error_type": type(exc).__name__,
        })
        return result


@st.cache_data(ttl=7200, show_spinner=False, max_entries=40)
def fetch_prices_batch(tickers: tuple, start: str, end: str) -> dict:
    """
    Batch-fetch daily close prices for many tickers in ONE yfinance request
    (yf.download) instead of a separate .history() call per ticker. Verified to
    return prices byte-identical to fetch_price(). Returns {ticker: pd.Series}
    (empty Series for a ticker with no data). Falls back to per-ticker fetch_price
    on any batch failure so callers always get complete, correct data.

    `tickers` is a tuple so the result is cacheable.
    """
    tickers = tuple(dict.fromkeys(t for t in tickers if t))  # dedupe, preserve order
    out = {t: pd.Series(dtype=float, name=t) for t in tickers}
    if not tickers:
        return out
    if len(tickers) == 1:
        out[tickers[0]] = fetch_price(tickers[0], start, end)
        return out
    try:
        df = yf.download(list(tickers), start=start, end=end, auto_adjust=True,
                         progress=False, group_by="ticker", threads=True, timeout=_YF_TIMEOUT)
        lvl0 = set(df.columns.get_level_values(0)) if hasattr(df.columns, "get_level_values") else set()
        for t in tickers:
            try:
                if t in lvl0:
                    col = df[t]["Close"]
                else:
                    col = df["Close"][t]
                s = col.dropna().rename(t)
                out[t] = _tz_strip(s) if not s.empty else pd.Series(dtype=float, name=t)
            except Exception:
                out[t] = fetch_price(t, start, end)   # per-ticker fallback
        return out
    except Exception:
        return {t: fetch_price(t, start, end) for t in tickers}


@st.cache_data(ttl=1800, show_spinner=False, max_entries=10)
def fetch_basket(tickers: list, start: str, end: str) -> pd.Series:
    """Fetch an equal-weight composite index of multiple tickers (one batched
    yfinance request; output identical to the prior per-ticker loop)."""
    prices = fetch_prices_batch(tuple(tickers), start, end)
    series_list = []
    for t in tickers:
        s = prices.get(t, pd.Series(dtype=float))
        if not s.empty:
            # Normalize each to 100 at start
            s_norm = s / s.dropna().iloc[0] * 100
            series_list.append(s_norm)
    if not series_list:
        return pd.Series(dtype=float, name="basket")
    df = pd.concat(series_list, axis=1).mean(axis=1)
    df.name = "basket"
    return df


# ─────────────────────────────────────────────────────────────────────────────
# CFTC — Commitments of Traders (COT)
# ─────────────────────────────────────────────────────────────────────────────

# Maps our signal names → substrings that appear in CFTC market names
_COT_MARKET_MAP = {
    "copper":      "COPPER",
    "gold":        "GOLD",
    "crude_oil":   "CRUDE OIL, LIGHT SWEET",
    "natural_gas": "NAT GAS",
    "corn":        "CORN",
    "soybeans":    "SOYBEANS",
    "wheat":       "WHEAT-SRW",
    "silver":      "SILVER",
}

@st.cache_data(ttl=86400, show_spinner=False, max_entries=10)
def fetch_cot(market: str = "copper") -> pd.DataFrame:
    """
    Fetch CFTC Commitments of Traders data.
    Downloads the current-year legacy futures CSV from cftc.gov.
    Returns an explicitly unavailable empty frame when live data cannot be used.
    """
    year = datetime.now().year
    # CFTC legacy futures-only report
    url = f"https://www.cftc.gov/files/dea/history/fut_disagg_xls_{year}.zip"

    try:
        r = resilient_get(url, provider="cftc", timeout=30)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            fname = next(n for n in z.namelist() if n.lower().endswith((".csv", ".txt")))
            with z.open(fname) as f:
                df = pd.read_csv(f, encoding="latin1", low_memory=False)

        market_substr = _COT_MARKET_MAP.get(market, market.upper())
        col = next((c for c in df.columns if "market" in c.lower()), df.columns[0])
        mask = df[col].str.upper().str.contains(market_substr, na=False)
        sub = df[mask].copy()

        if sub.empty:
            return _empty_frame_with_error("cftc", LookupError("market not found"))

        date_col = next((c for c in sub.columns if "date" in c.lower()), None)
        if date_col:
            sub["date"] = pd.to_datetime(sub[date_col], errors="coerce")

        # Try to find positioning columns (column names vary by report type)
        def _find_col(df, *fragments):
            for frag in fragments:
                matches = [c for c in df.columns if frag.lower() in c.lower()]
                if matches:
                    return matches[0]
            return None

        spec_long_col  = _find_col(sub, "noncommercial long", "managed money long")
        spec_short_col = _find_col(sub, "noncommercial short", "managed money short")
        comm_long_col  = _find_col(sub, "commercial long")
        comm_short_col = _find_col(sub, "commercial short")
        oi_col         = _find_col(sub, "open interest")

        if not all([spec_long_col, spec_short_col, comm_long_col, comm_short_col]):
            return _empty_frame_with_error("cftc", ValueError("required columns missing"))

        result = pd.DataFrame({
            "date":          sub["date"],
            "spec_long":     pd.to_numeric(sub[spec_long_col],  errors="coerce"),
            "spec_short":    pd.to_numeric(sub[spec_short_col], errors="coerce"),
            "comm_long":     pd.to_numeric(sub[comm_long_col],  errors="coerce"),
            "comm_short":    pd.to_numeric(sub[comm_short_col], errors="coerce"),
            "open_interest": pd.to_numeric(sub[oi_col],         errors="coerce") if oi_col else np.nan,
        }).dropna(subset=["date", "spec_long"]).sort_values("date")

        return result.reset_index(drop=True)

    except Exception as exc:
        return _empty_frame_with_error("cftc", exc)


# ─────────────────────────────────────────────────────────────────────────────
# USASpending.gov — Federal Contract Award Velocity
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False, max_entries=128)
def _fetch_federal_contracts_cached(company_name: str, years: int = 2) -> pd.DataFrame:
    """
    Fetch federal contract awards for a company from USASpending.gov.
    No API key required. Free public endpoint.

    This is a UNIQUE signal: DoE/DoD contract award spikes give
    6-12 months of revenue visibility before earnings disclosures.
    """
    start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
    end   = datetime.now().strftime("%Y-%m-%d")

    url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    payload = {
        "filters": {
            "time_period": [{"start_date": start, "end_date": end}],
            "award_type_codes": ["A", "B", "C", "D"],
            "recipient_search_text": [company_name],
        },
        "fields": [
            "Award ID", "Recipient Name", "Award Amount",
            "Start Date", "Awarding Agency", "Description",
        ],
        "sort": "Start Date",
        "order": "desc",
        "limit": 100,
        "page": 1,
    }

    try:
        r = resilient_post(url, provider="usaspending", json=payload, timeout=20,
                          headers={"Content-Type": "application/json"})
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        rename_map = {
            "Award ID":       "award_id",
            "Recipient Name": "recipient",
            "Award Amount":   "amount",
            "Start Date":     "date",
            "Awarding Agency":"agency",
            "Description":    "description",
        }
        df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
        df["date"]   = pd.to_datetime(df.get("date",   pd.NaT), errors="coerce")
        df["amount"] = pd.to_numeric(df.get("amount", np.nan), errors="coerce")
        return df.sort_values("date").reset_index(drop=True)

    except Exception:
        raise


def fetch_federal_contracts(company_name: str, years: int = 2) -> pd.DataFrame:
    company_name = " ".join(str(company_name).split()).upper()
    try:
        return _fetch_federal_contracts_cached(company_name, int(years))
    except Exception as exc:
        return _empty_frame_with_error("usaspending", exc)


fetch_federal_contracts.clear = _fetch_federal_contracts_cached.clear


# ─────────────────────────────────────────────────────────────────────────────
# SEC EDGAR — Form 4 Insider Transactions
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False, max_entries=50)
def fetch_insider_trades(ticker: str, days: int = 180) -> pd.DataFrame:
    """
    Fetch recent Form 4 insider transactions from SEC EDGAR full-text search.
    No API key required. Returns filings mentioning the ticker.
    """
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end   = datetime.now().strftime("%Y-%m-%d")

    url = (
        "https://efts.sec.gov/LATEST/search-index"
        f"?q=%22{ticker}%22"
        f"&forms=4"
        f"&dateRange=custom&startdt={start}&enddt={end}"
        f"&hits.hits.total.value=true"
    )

    headers = {"User-Agent": "UnstructuredAlpha/1.0 research@unstructuredalpha.com"}

    try:
        r = resilient_get(url, provider="sec_edgar", headers=headers, timeout=12)
        r.raise_for_status()
        data = r.json()
        hits = data.get("hits", {}).get("hits", [])

        records = []
        for hit in hits[:30]:
            src = hit.get("_source", {})
            names = src.get("display_names", [])
            records.append({
                "date":      src.get("file_date", ""),
                "filer":     names[0] if names else "Unknown",
                "form":      src.get("form_type", "4"),
                "entity":    src.get("entity_name", ticker),
                "accession": src.get("period_of_report", ""),
            })

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df.sort_values("date", ascending=False).reset_index(drop=True)

    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=21600, show_spinner=False, max_entries=128)
def _fetch_insider_transactions_detail_cached(ticker: str, days: int = 180, max_filings: int = 20) -> pd.DataFrame:
    """
    Fetch and parse ACTUAL Form 4 transaction detail (buy/sell direction,
    shares, price) -- not just filing metadata.

    fetch_insider_trades() above only returns who-filed-when via EDGAR's
    full-text search INDEX; the search index does not include parsed
    transaction content. That content only exists in each filing's
    underlying XML, which is what this function fetches and parses.

    URL pattern verified live against real filings before writing this
    (not assumed from memory): EDGAR full-text search hits include an
    "_id" field shaped "{accession-no-dashes-with-dash}:{filename}" and a
    "ciks" list whose first entry is the FILER's (insider's) CIK, not the
    issuer's. The filing's XML lives at:
        https://www.sec.gov/Archives/edgar/data/{filer_cik}/{accession_no_no_dashes}/{filename}
    Confirmed the filename varies by filing agent (e.g. "doc4.xml" for one
    company's agent, "form4.xml" for another's) -- this is why the filename
    must come from the search hit's own "_id" field, not be assumed/hardcoded.

    Only counts genuine open-market transactions: transactionCode "P"
    (purchase) or "S" (sale) inside <nonDerivativeTransaction> -- NOT
    <nonDerivativeHolding> (no transaction, just a position snapshot), and
    NOT <derivativeTransaction> codes like "A" (grant/award) or "M"
    (option exercise) or "F" (shares withheld for taxes on vesting), none
    of which reflect a genuine buy/sell decision by the insider.

    Returns columns: date, insider, role, code (P/S), shares, price, value
    (shares * price, signed: + for P, - for S), accession, filer_cik,
    source_url (the exact filing XML each row came from -- the audit-trail
    feature links back to this directly rather than a generic search page).
    """
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end   = datetime.now().strftime("%Y-%m-%d")
    headers = {"User-Agent": "UnstructuredAlpha/1.0 research@unstructuredalpha.com"}

    search_url = (
        "https://efts.sec.gov/LATEST/search-index"
        f"?q=%22{ticker}%22&forms=4"
        f"&dateRange=custom&startdt={start}&enddt={end}"
    )

    try:
        r = resilient_get(search_url, provider="sec_edgar", headers=headers, timeout=12)
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
    except Exception:
        raise

    records = []
    for hit in hits[:max_filings]:
        src = hit.get("_source", {})
        hit_id = hit.get("_id", "")
        ciks = src.get("ciks", [])
        if ":" not in hit_id or not ciks:
            continue
        accession, filename = hit_id.split(":", 1)
        filer_cik = ciks[0].lstrip("0") or "0"
        accession_nodash = accession.replace("-", "")
        xml_url = f"https://www.sec.gov/Archives/edgar/data/{filer_cik}/{accession_nodash}/{filename}"
        # filed_date: when SEC received the filing — this is the "known as of" date,
        # i.e., the earliest point a market participant could have acted on this
        # information. The transaction_date (below) is when the trade occurred,
        # which is typically weeks earlier. Using filed_date for lead-time scoring
        # prevents the signal from appearing more predictive than it actually is.
        filed_date_raw = src.get("file_date") or src.get("filedAt", "")
        filed_date = filed_date_raw[:10] if filed_date_raw else ""

        try:
            xr = resilient_get(xml_url, provider="sec_edgar", headers=headers, timeout=12)
            xr.raise_for_status()
            root = ET.fromstring(xr.content)
        except Exception:
            continue

        insider_name = ""
        owner_el = root.find("reportingOwner/reportingOwnerId/rptOwnerName")
        if owner_el is not None and owner_el.text:
            insider_name = owner_el.text

        rel = root.find("reportingOwner/reportingOwnerRelationship")
        role_parts = []
        if rel is not None:
            if (rel.findtext("isOfficer") or "0") == "1":
                title = rel.findtext("officerTitle") or "Officer"
                role_parts.append(title)
            if (rel.findtext("isDirector") or "0") == "1":
                role_parts.append("Director")
            if (rel.findtext("isTenPercentOwner") or "0") == "1":
                role_parts.append("10%+ Owner")
        role = ", ".join(role_parts) if role_parts else "Unknown"

        for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
            code = tx.findtext("transactionCoding/transactionCode", default="")
            if code not in ("P", "S"):
                continue
            try:
                shares = float(tx.findtext("transactionAmounts/transactionShares/value", default="0"))
                price  = float(tx.findtext("transactionAmounts/transactionPricePerShare/value", default="0"))
            except (ValueError, TypeError):
                continue
            tx_date = tx.findtext("transactionDate/value", default="")
            value = shares * price
            records.append({
                "date":    tx_date,
                "insider": insider_name,
                "role":    role,
                "code":    code,
                "shares":  shares,
                "price":   price,
                "value":   value if code == "P" else -value,
                # Kept for the audit-trail feature: this is the exact filing
                # each transaction came from, already built above to fetch
                # the XML in the first place -- previously computed and then
                # discarded once parsing was done, even though every row
                # legitimately needs its own source link (a single filing
                # can contain multiple transactions, each potentially from
                # a different filer for joint-filer forms).
                "accession":  accession,
                "filer_cik":  filer_cik,
                "source_url": xml_url,
                "filed_date": filed_date,
            })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date", ascending=False).reset_index(drop=True)


def fetch_insider_transactions_detail(ticker: str, days: int = 180, max_filings: int = 20) -> pd.DataFrame:
    ticker = str(ticker).upper().strip()
    try:
        return _fetch_insider_transactions_detail_cached(ticker, int(days), int(max_filings))
    except Exception as exc:
        return _empty_frame_with_error("sec_edgar", exc)


fetch_insider_transactions_detail.clear = _fetch_insider_transactions_detail_cached.clear


# ─────────────────────────────────────────────────────────────────────────────
# FINRA — Consolidated Equity Short Interest
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False, max_entries=128)
def _fetch_short_interest_cached(ticker: str, years: float = 1.5) -> pd.DataFrame:
    """
    Fetch real, exchange-listed short interest history from FINRA's free,
    keyless public API.

    Endpoint and schema verified live before writing this (not assumed):
    despite living under the API group name "otcMarket", the
    "consolidatedShortInterest" dataset genuinely includes NYSE/NASDAQ-listed
    names (confirmed directly against real Microsoft, Agilent, and Alcoa
    records) — a DIFFERENT FINRA dataset ("EquityShortInterest", same
    "otcMarket" group) returns nothing for those same tickers and only
    covers genuinely OTC securities, which is why that one was rejected in
    favor of this one.

    FINRA's short interest reporting is bi-monthly (settlement dates near
    the 15th and last business day of each month, published with a ~2-3
    week lag), NOT daily or weekly — this is real, but the slowest-moving
    of this product's signals, similar in spirit to 13F filings.

    Returns columns: date (settlementDate), short_shares
    (currentShortPositionQuantity), prev_short_shares, change_pct
    (FINRA's own period-over-period calculation), days_to_cover,
    avg_daily_volume.
    """
    cutoff = (datetime.now() - timedelta(days=int(years * 365))).strftime("%Y-%m-%d")
    url = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
    payload = {
        "compareFilters": [
            {"compareType": "EQUAL", "fieldName": "symbolCode", "fieldValue": ticker},
            {"compareType": "GTE", "fieldName": "settlementDate", "fieldValue": cutoff},
        ],
        "limit": 50,
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        r = resilient_post(url, provider="finra", json=payload, headers=headers, timeout=15)
        if r.status_code == 204:  # FINRA's "no rows matched" response, not an error
            return pd.DataFrame()
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        rename_map = {
            "settlementDate": "date",
            "currentShortPositionQuantity": "short_shares",
            "previousShortPositionQuantity": "prev_short_shares",
            "changePercent": "change_pct",
            "daysToCoverQuantity": "days_to_cover",
            "averageDailyVolumeQuantity": "avg_daily_volume",
        }
        df = df.rename(columns=rename_map)
        keep = [c for c in rename_map.values() if c in df.columns]
        df = df[keep].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for c in ("short_shares", "prev_short_shares", "change_pct", "days_to_cover", "avg_daily_volume"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    except Exception:
        raise


def fetch_short_interest(ticker: str, years: float = 1.5) -> pd.DataFrame:
    ticker = str(ticker).upper().strip()
    try:
        return _fetch_short_interest_cached(ticker, float(years))
    except Exception as exc:
        return _empty_frame_with_error("finra", exc)


fetch_short_interest.clear = _fetch_short_interest_cached.clear


# ─────────────────────────────────────────────────────────────────────────────
# SEC EDGAR — Form 13F institutional holdings (curated funds only)
# ─────────────────────────────────────────────────────────────────────────────

_THIRTEENF_NS = {"t": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}
_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


@st.cache_data(ttl=86400, show_spinner=False, max_entries=32)
def _fetch_13f_holdings_cached(cik: str, fund_name: str, max_filings: int = 2) -> pd.DataFrame:
    """
    Fetch a fund's most recent Form 13F-HR holdings, real and live, for the
    curated funds in utils/config.CURATED_FUNDS.

    Endpoint chain verified live against Berkshire Hathaway (CIK 1067983),
    Pershing Square (CIK 1336528), Scion Asset Management (CIK 1649339),
    Tiger Global Management (CIK 1167483), and Duquesne Family Office
    (CIK 1536411) before any of this was written:
      1. data.sec.gov/submissions/CIK{10-digit}.json -> the real filing
         history: accession numbers, form types, AND reportDate (the real
         period the holdings are as of, e.g. "2026-03-31") all in one
         response. Originally this used the legacy cgi-bin/browse-edgar
         atom feed plus a separate primary_doc.xml fetch per filing to get
         the period -- switched after that atom feed returned empty
         responses on several CIK lookups during live testing (intermittent,
         not a real absence of data: data.sec.gov returned correct results
         for the exact same CIKs moments later). This is also simply fewer
         requests: one JSON call instead of one atom-feed call plus one
         primary_doc.xml call per filing.
         13F-HR/A amendments are explicitly excluded by exact form-type
         match -- a re-filed amendment is not a new quarter's positioning,
         and including it would double-count or misdate a period.
      2. Each filing's /index.json -> the information table's actual XML
         filename. This is NOT a fixed convention (seen in the wild:
         "53405.xml", "infotable.xml", "form13f_20251231.xml") -- same
         lesson as Form 4's filename variability, solved the same way:
         read the real directory listing, don't assume a name.
      3. The information table XML itself -- infoTable entries with fields
         nameOfIssuer, cusip, value, shrsOrPrnAmt/sshPrnamt, and an OPTIONAL
         putCall field. putCall is the field that makes this non-trivial:
         a "Put" position is a BEARISH bet (or hedge), not bullish share
         ownership, even though it appears in the same information table
         alongside plain long stock positions -- confirmed live in Scion's
         actual filing (their NVIDIA position is a Put, their Halliburton
         position is a Call) and Duquesne's (their Amazon position is split
         across a plain share line AND a separate Call-option line on the
         same CUSIP). Treating every line as "the fund owns this stock"
         would have been wrong.

    Returns one row per (filing period x holding), with columns: fund,
    period (the real reportDate, not the filing date), filed_date,
    cusip, issuer, shares, value, direction ("long" for a plain share
    position or a Call option, "short" for a Put option).
    """
    headers = {"User-Agent": "Unstructured Alpha research dashboard (contact: research@unstructuredalpha.example)"}
    rows = []
    try:
        cik_padded = f"{int(cik):010d}"
        sub_r = resilient_get(f"https://data.sec.gov/submissions/CIK{cik_padded}.json", provider="sec_edgar", headers=headers, timeout=15)
        sub_r.raise_for_status()
        recent = sub_r.json().get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        report_dates = recent.get("reportDate", [])

        filings = []  # list of (accession, report_date_str)
        for form, accession, report_date in zip(forms, accessions, report_dates):
            if form != "13F-HR":  # excludes 13F-HR/A amendments on purpose
                continue
            filings.append((accession, report_date))
            if len(filings) >= max_filings:
                break

        for accession, report_date_str in filings:
            accession_nodash = accession.replace("-", "")
            base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}"

            idx_r = resilient_get(f"{base}/index.json", provider="sec_edgar", headers=headers, timeout=15)
            idx_r.raise_for_status()
            items = idx_r.json().get("directory", {}).get("item", [])
            info_table_name = next(
                (it["name"] for it in items
                 if it["name"].lower().endswith(".xml") and it["name"].lower() != "primary_doc.xml"),
                None,
            )
            if not info_table_name:
                continue

            period = pd.to_datetime(report_date_str, errors="coerce") if report_date_str else None

            tbl_r = resilient_get(f"{base}/{info_table_name}", provider="sec_edgar", headers=headers, timeout=20)
            tbl_r.raise_for_status()
            tbl_root = ET.fromstring(tbl_r.content)

            # Filing agents inconsistently use a namespace prefix (e.g.
            # Bridgewater's filings use "ns1:infoTable") vs. the bare,
            # default-namespace tag every curated fund here actually uses.
            # iterate over all elements and match by LOCAL tag name (after
            # the "}") so this works regardless of prefix.
            for info_table in tbl_root.iter():
                if not info_table.tag.endswith("}infoTable") and info_table.tag != "infoTable":
                    continue
                fields = {}
                for child in info_table.iter():
                    local = child.tag.split("}")[-1]
                    if local in ("nameOfIssuer", "cusip", "value", "putCall", "sshPrnamt"):
                        fields[local] = (child.text or "").strip()
                if "cusip" not in fields:
                    continue
                direction = "short" if fields.get("putCall", "").lower() == "put" else "long"
                rows.append({
                    "fund": fund_name,
                    "period": period,
                    "filed_date": accession,  # kept for traceability, not displayed as the AS-OF date
                    "cusip": fields.get("cusip", ""),
                    "issuer": fields.get("nameOfIssuer", ""),
                    "shares": pd.to_numeric(fields.get("sshPrnamt", ""), errors="coerce"),
                    "value": pd.to_numeric(fields.get("value", ""), errors="coerce"),
                    "direction": direction,
                    # Audit-trail field: the exact information-table XML this
                    # row came from. `base`/`info_table_name` were already
                    # being computed above to fetch the filing in the first
                    # place -- same pattern as the insider-transaction fetch,
                    # previously discarded once parsing was done.
                    "source_url": f"{base}/{info_table_name}",
                })
    except Exception:
        raise

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def fetch_13f_holdings(cik: str, fund_name: str, max_filings: int = 2) -> pd.DataFrame:
    try:
        cik = str(int(str(cik)))
        fund_name = " ".join(str(fund_name).split())
        return _fetch_13f_holdings_cached(cik, fund_name, int(max_filings))
    except Exception as exc:
        return _empty_frame_with_error("sec_edgar", exc)


fetch_13f_holdings.clear = _fetch_13f_holdings_cached.clear


# NOTE: a Google Trends fetcher (via the unofficial "pytrends" scraper) used
# to live here. Removed — confirmed via a full-codebase audit that it was
# never called from anywhere (no page, no signal config, dead since it was
# written). Not worth reviving as-is either: pytrends scrapes Google Trends'
# internal endpoints with no official API or key, and is well documented to
# break under CAPTCHA/rate-limit blocks for periods at a time — the same
# fragility class as yfinance, but for a signal that wasn't wired to
# anything in the first place. If search-velocity-as-signal is wanted later,
# it should be re-evaluated with that fragility in mind, not just restored.


# ─────────────────────────────────────────────────────────────────────────────
# arXiv — Quantum Computing Paper Velocity
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False, max_entries=5)
def fetch_arxiv_velocity(
    query: str = "qubit error correction fault tolerant quantum computing",
    max_results: int = 300,
) -> pd.Series:
    """
    Fetch arXiv quantum paper publication velocity.
    Peer-reviewed papers appear 2-6 weeks before press releases;
    a velocity spike often precedes equity rotation into quantum stocks.
    No API key required.
    """
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"cat:quant-ph AND ({query})",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        r = resilient_get(url, provider="arxiv", params=params, timeout=25)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"a": "http://www.w3.org/2005/Atom"}

        dates = []
        for entry in root.findall("a:entry", ns):
            pub = entry.find("a:published", ns)
            if pub is not None and pub.text:
                dates.append(pd.to_datetime(pub.text[:10]))

        if not dates:
            return pd.Series(dtype=float, name="arxiv_papers_per_week")

        s = pd.Series(1, index=dates)
        weekly = s.resample("W").sum()
        weekly.name = "arxiv_papers_per_week"
        return weekly

    except Exception:
        return pd.Series(dtype=float, name="arxiv_papers_per_week")


# ─────────────────────────────────────────────────────────────────────────────
# openFDA — Drug Approval Velocity (healthcare differentiator)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False, max_entries=3)
def fetch_fda_approval_velocity(max_results: int = 1000) -> pd.Series:
    """
    Fetch FDA drug application approval velocity from openFDA's free,
    keyless drug/drugsfda endpoint (api.fda.gov — confirmed live, no key
    required, verified directly against the real endpoint before wiring
    this in: it returned 25,368 total approved-submission records on
    2026-06-20).

    Rather than a single ticker's revenue lagging an approval by quarters,
    a rising rate of FDA approvals across the industry is a real, rarely
    free-shown alternative-data signal of regulatory tailwind/headwind for
    biotech and pharma broadly — most retail platforms don't surface this
    at all; it's normally something analysts track by hand off FDA press
    releases.

    Returns a weekly count of approval-status submissions, same shape as
    fetch_arxiv_velocity, so it slots into the existing scoring pipeline
    without any special-casing.
    """
    url = "https://api.fda.gov/drug/drugsfda.json"
    params = {
        "search": "submissions.submission_status:AP",
        "sort": "submissions.submission_status_date:desc",
        "limit": min(max_results, 1000),
    }
    try:
        r = resilient_get(url, provider="fda", params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])

        dates = []
        for app in results:
            for sub in app.get("submissions", []):
                if sub.get("submission_status") == "AP" and sub.get("submission_status_date"):
                    try:
                        dates.append(pd.to_datetime(sub["submission_status_date"], format="%Y%m%d"))
                    except Exception:
                        continue

        if not dates:
            return pd.Series(dtype=float, name="fda_approvals_per_week")

        s = pd.Series(1, index=dates)
        weekly = s.resample("W").sum()
        weekly.name = "fda_approvals_per_week"
        return weekly

    except Exception:
        return pd.Series(dtype=float, name="fda_approvals_per_week")


# ─────────────────────────────────────────────────────────────────────────────
# yfinance — Earnings Dates + News Headlines
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600 * 6, show_spinner=False, max_entries=50)
def fetch_earnings_dates(ticker: str) -> list[dict]:
    """
    Returns up to ~5 earnings dates (last 4 quarters + next upcoming) for a
    ticker via yfinance.Ticker.earnings_dates.

    Each dict:
      date         — datetime.date
      reported     — bool (False = upcoming/estimated)
      eps_estimate — float or None
      eps_actual   — float or None (None if upcoming)
      surprise_pct — float or None (positive = beat, negative = miss)

    Returns [] on any failure — callers treat this as "no data available" and
    skip the earnings overlay rather than crashing.
    """
    try:
        t = yf.Ticker(ticker)
        df = t.earnings_dates
        if df is None or df.empty:
            return []

        now_utc = pd.Timestamp.now(tz="UTC")
        cutoff_past = now_utc - pd.Timedelta(days=400)   # last ~4 quarters

        results = []
        for dt, row in df.iterrows():
            # Keep only the last ~4 reported quarters + any upcoming dates
            if pd.notna(dt):
                # earnings_dates index is tz-aware (ET); normalise for comparison
                dt_utc = dt.tz_convert("UTC") if dt.tzinfo else dt.tz_localize("UTC")
                if dt_utc < cutoff_past:
                    continue
            else:
                continue

            eps_actual   = row.get("Reported EPS")
            eps_estimate = row.get("EPS Estimate")
            surprise     = row.get("Surprise(%)")

            reported = pd.notna(eps_actual)

            results.append({
                "date":         dt.date() if hasattr(dt, "date") else dt,
                "reported":     reported,
                "eps_estimate": float(eps_estimate) if pd.notna(eps_estimate) else None,
                "eps_actual":   float(eps_actual)   if pd.notna(eps_actual)   else None,
                "surprise_pct": float(surprise)     if pd.notna(surprise)     else None,
            })

        return sorted(results, key=lambda x: x["date"])
    except Exception:
        return []


@st.cache_data(ttl=3600 * 2, show_spinner=False, max_entries=50)
def fetch_ticker_news(ticker: str) -> list[dict]:
    """
    Returns up to 12 recent news items for a ticker via yfinance.Ticker.news.

    Each dict:
      title        — str
      url          — str
      publisher    — str
      published_at — pd.Timestamp (UTC) or pd.NaT

    Handles both yfinance formats:
      - Old (< 1.x): flat dict with uuid/title/link/publisher/providerPublishTime
      - New (1.x+):  dict with id + nested 'content' sub-dict

    Returns [] on any failure.
    """
    try:
        t = yf.Ticker(ticker)
        raw = t.news or []
        results = []
        for item in raw[:15]:
            if "content" in item and isinstance(item.get("content"), dict):
                # New yfinance 1.x format
                c = item["content"]
                title = c.get("title", "")
                url   = (c.get("url")
                         or c.get("canonicalUrl", {}).get("url", "")
                         or "")
                pub   = c.get("provider", {}).get("displayName", "")
                pub_str = c.get("pubDate", "")
                try:
                    pub_dt = pd.Timestamp(pub_str).tz_convert("UTC") if pub_str else pd.NaT
                except Exception:
                    pub_dt = pd.NaT
            else:
                # Old flat format
                title = item.get("title", "")
                url   = item.get("link", "")
                pub   = item.get("publisher", "")
                ts    = item.get("providerPublishTime", 0)
                try:
                    pub_dt = pd.Timestamp(ts, unit="s", tz="UTC") if ts else pd.NaT
                except Exception:
                    pub_dt = pd.NaT

            if title:
                results.append({
                    "title":        title,
                    "url":          url,
                    "publisher":    pub,
                    "published_at": pub_dt,
                })

        return results[:12]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# yfinance — Options Chain (unusual activity detector)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False, max_entries=80)
def fetch_options_chain(ticker: str) -> dict:
    """
    Fetch the full options chain for a ticker via yfinance.

    Returns dict with keys:
        expirations  — list of expiration date strings (closest first)
        calls        — pd.DataFrame (all expirations concatenated, col "expiration" added)
        puts         — pd.DataFrame (same)
        put_call_ratio — float (total put volume / total call volume, NaN on failure)
        current_price  — float or None

    Columns per DataFrame (from yfinance): contractSymbol, strike, lastPrice, bid, ask,
        change, percentChange, volume, openInterest, impliedVolatility, inTheMoney,
        expiration (added).

    "Unusual" contracts are those where volume / max(openInterest, 1) > 1.0 AND
    volume > 100 — the caller can filter for these. A volume-to-OI ratio > 1
    means more contracts traded today than existed yesterday, implying fresh
    positioning rather than exits.

    Returns empty dict on failure — callers must handle gracefully.
    """
    try:
        t = yf.Ticker(ticker)
        expirations = t.options
        if not expirations:
            return {}

        # Pull up to 6 nearest expirations (avoids very far-dated illiquid strikes)
        exp_subset = expirations[:6]

        all_calls, all_puts = [], []
        for exp in exp_subset:
            try:
                chain = t.option_chain(exp)
                c = chain.calls.copy()
                p = chain.puts.copy()
                c["expiration"] = exp
                p["expiration"] = exp
                all_calls.append(c)
                all_puts.append(p)
            except Exception:
                continue

        if not all_calls and not all_puts:
            return {}

        calls_df = pd.concat(all_calls, ignore_index=True) if all_calls else pd.DataFrame()
        puts_df  = pd.concat(all_puts,  ignore_index=True) if all_puts  else pd.DataFrame()

        # Clean: fill NA volume/OI with 0
        for df in (calls_df, puts_df):
            for col in ("volume", "openInterest", "impliedVolatility"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        total_call_vol = float(calls_df["volume"].sum()) if not calls_df.empty else 0
        total_put_vol  = float(puts_df["volume"].sum())  if not puts_df.empty  else 0
        pcr = total_put_vol / total_call_vol if total_call_vol > 0 else float("nan")

        # Current price from fast_info (fast_info is an object, not a dict — use getattr)
        current_price = None
        try:
            fi = t.fast_info
            current_price = getattr(fi, "last_price", None)
        except Exception:
            pass

        return {
            "expirations":    list(expirations),
            "calls":          calls_df,
            "puts":           puts_df,
            "put_call_ratio": pcr,
            "current_price":  float(current_price) if current_price else None,
        }
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Google Trends — Retail Fear Gauge
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False, max_entries=3)
def fetch_google_trends_fear(terms: str = "market crash,recession,stock market crash") -> pd.Series:
    """
    Fetch weekly Google Trends search interest for retail fear terms.
    Returns a pd.Series of weekly values (0–100 relative interest).

    Used as a CONTRARIAN signal: high fear-search intensity has historically
    coincided with market bottoms (capitulation), not tops. Low fear (complacency)
    is the mild bearish read.

    Args:
        terms: comma-separated search terms (from config series_id)

    No API key required — pytrends uses Google Trends' public interface.
    Rate-limited: one request per 24h cache is well within Google's tolerance.
    """
    try:
        from pytrends.request import TrendReq

        term_list = [t.strip() for t in terms.split(",") if t.strip()][:5]

        pt = TrendReq(hl="en-US", tz=360, timeout=(15, 30), retries=2, backoff_factor=0.5)
        pt.build_payload(term_list, cat=0, timeframe="today 3-m", geo="US")
        df = pt.interest_over_time()

        if df.empty:
            return pd.Series(dtype=float, name="retail_fear_index")

        # Average across all queried terms → composite fear index
        available = [t for t in term_list if t in df.columns]
        if not available:
            return pd.Series(dtype=float, name="retail_fear_index")

        fear = df[available].mean(axis=1)
        fear.index = pd.to_datetime(fear.index)
        fear.name = "retail_fear_index"
        return fear.dropna()

    except ImportError:
        return pd.Series(dtype=float, name="retail_fear_index")
    except Exception:
        return pd.Series(dtype=float, name="retail_fear_index")


# ─────────────────────────────────────────────────────────────────────────────
# FedSpeak — FOMC Statement Hawkishness Score
# ─────────────────────────────────────────────────────────────────────────────

# Known FOMC statement dates → used to build time series from historical statements
_FOMC_DATES = [
    # 2023
    "20230201", "20230322", "20230503", "20230614", "20230726", "20230920",
    "20231101", "20231213",
    # 2024
    "20240131", "20240320", "20240501", "20240612", "20240731", "20240918",
    "20241107", "20241218",
    # 2025
    "20250129", "20250319", "20250507", "20250618", "20250730", "20250917",
    "20251029", "20251210",
]

_FOMC_BASE_URL = "https://www.federalreserve.gov/newsevents/pressreleases/monetary{date}a.htm"

_HAWK_PROMPT = """You are a Federal Reserve analyst. Score the following FOMC monetary policy statement on a hawkishness scale from 0 to 100:
- 0-20: Very dovish (explicit easing bias, rate cuts imminent, maximum accommodation language)
- 21-40: Moderately dovish (data-dependent with easing lean, concern about growth/employment)
- 41-59: Neutral (balanced risks, no clear directional bias, truly data-dependent)
- 60-79: Moderately hawkish (inflation focus, rate-hike bias, restrictive stance maintained)
- 80-100: Very hawkish (aggressive tightening language, inflation fight priority, hike imminent)

Respond with ONLY a JSON object: {"score": <integer 0-100>, "rationale": "<one sentence>"}

Statement:
{text}"""


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False, max_entries=1)
def fetch_fedspeaks_hawkishness(series_id: str = "fomc_hawkishness") -> pd.Series:
    """
    Fetch and AI-score recent FOMC monetary policy statements.

    For each known FOMC meeting date (up to 8 most recent), fetches the
    official statement from federalreserve.gov and scores its hawkishness
    0-100 using Claude Haiku (cheap, fast). Returns a pd.Series indexed by
    meeting date — gives the scoring pipeline a real time series to compute
    z-scores and trend against.

    Cached for 7 days — FOMC meets ~8×/year so the series only changes
    after meetings. Haiku API cost: ~$0.002 per statement × 8 = ~$0.016
    per cold-start cache. Acceptable.

    Falls back gracefully:
      - If Anthropic API key missing → returns empty series
      - If a statement fetch fails → skips that date
      - If fewer than 3 dates scored → empty series (not enough for z-score)
    """
    import os, re
    import anthropic as _anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return pd.Series(dtype=float, name="fedspeaks_hawkishness")

    # Score the most recent 8 FOMC meetings (covers ~1 year of data)
    recent_dates = sorted(_FOMC_DATES)[-8:]
    scored: dict[str, float] = {}

    client = _anthropic.Anthropic(api_key=api_key)

    for date_str in recent_dates:
        url = _FOMC_BASE_URL.format(date=date_str)
        try:
            r = resilient_get(url, provider="fed_fomc", timeout=15, headers={"User-Agent": "UnstructuredAlpha/1.0"})
            if r.status_code != 200:
                continue

            # Strip HTML tags
            raw = re.sub(r"<[^>]+>", " ", r.text)
            raw = re.sub(r"\s+", " ", raw).strip()

            # Extract the policy statement portion (first ~2000 chars after "Federal Open Market")
            idx = raw.find("Federal Open Market Committee")
            if idx == -1:
                idx = raw.find("Federal Reserve")
            snippet = raw[max(0, idx):idx + 3000] if idx >= 0 else raw[:3000]

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=120,
                messages=[{"role": "user", "content": _HAWK_PROMPT.format(text=snippet)}],
            )
            raw_resp = response.content[0].text.strip()

            import json as _json
            parsed = _json.loads(raw_resp)
            score_val = float(parsed.get("score", 50))
            if 0 <= score_val <= 100:
                # Parse date string → date object
                dt = pd.to_datetime(
                    f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                )
                scored[dt] = score_val

        except Exception:
            continue  # skip failed dates silently

    if len(scored) < 3:
        return pd.Series(dtype=float, name="fedspeaks_hawkishness")

    series = pd.Series(scored, name="fedspeaks_hawkishness")
    series.index = pd.to_datetime(series.index)
    return series.sort_index()


# ─────────────────────────────────────────────────────────────────────────────
# Earnings Transcript Sentiment  (SEC EDGAR 8-K Item 2.02 + Loughran-McDonald)
# ─────────────────────────────────────────────────────────────────────────────

# Loughran-McDonald (2011) financial-domain sentiment word lists.
# These lists are preferred over VADER/general-purpose lexicons because
# many words that are negative in everyday English are neutral in a financial
# context (e.g. "liability", "risk", "capital"), and vice-versa.
# Source: https://sraf.nd.edu/loughranmcdonald-master-dictionary/
# This is a representative core subset — sufficient for directional scoring.
_LM_POSITIVE = frozenset({
    "achieve", "achieved", "achievement", "achievements", "advance", "advantage",
    "advantageous", "affirm", "affirmed", "all-time", "attain", "attained",
    "beneficially", "best", "boost", "breakout", "breakthrough", "broad-based",
    "build", "built", "capabilities", "capable", "clarity", "confident",
    "confidence", "consistent", "continued", "deliver", "delivered", "delivering",
    "dynamic", "earnings", "effective", "effectively", "efficiency", "efficient",
    "enhance", "enhanced", "enthusiasm", "excellent", "exceptional", "exceed",
    "exceeded", "exceeds", "exciting", "expand", "expanding", "expansion",
    "exceptional", "exceptional", "favorable", "favorably", "flexibility",
    "gain", "gains", "growth", "high", "higher", "highest", "improve",
    "improved", "improvement", "improvements", "increase", "increased",
    "increasing", "industry-leading", "innovative", "innovation", "leadership",
    "leverage", "leveraging", "maximize", "momentum", "new", "optimistic",
    "organic", "outperform", "outperformed", "outstanding", "positive",
    "positively", "profit", "profitable", "profitability", "progress",
    "progressive", "record", "reiterate", "revenue", "robust", "significant",
    "significantly", "solid", "strength", "strengthen", "strengthened",
    "strong", "stronger", "strongest", "succeed", "succeeded", "success",
    "successful", "successfully", "superior", "support", "supported",
    "sustainable", "upside", "value", "win", "winning",
})

_LM_NEGATIVE = frozenset({
    "adversarial", "adversely", "against", "amend", "amended", "below",
    "breach", "challenged", "challenges", "challenging", "class-action",
    "complaint", "concerned", "concerns", "constrain", "constrained",
    "constraint", "constraints", "contraction", "declined", "declining",
    "decrease", "decreased", "decreasing", "deficit", "delay", "delayed",
    "deteriorate", "deteriorated", "deteriorating", "difficult", "difficulty",
    "disappoint", "disappointed", "disappointing", "disappoints", "disruption",
    "disruptions", "divested", "down", "downgrade", "downward", "elevated",
    "erosion", "error", "errors", "excess", "fail", "failed", "failing",
    "failure", "headwind", "headwinds", "impair", "impaired", "impairment",
    "inadequate", "inflation", "inflationary", "investigation", "lawsuit",
    "layoff", "layoffs", "less", "liabilities", "liability", "litigation",
    "loss", "losses", "lower", "lowest", "material", "miss", "missed",
    "negative", "negatively", "obstacle", "overhang", "penalty", "pressure",
    "pressures", "probe", "problem", "problems", "reduced", "reduction",
    "restatement", "restructuring", "risk", "risks", "setback", "shortfall",
    "slow", "slowed", "slowdown", "softness", "sub-par", "uncertainty",
    "unfavorable", "unfavorably", "volatile", "volatility", "weakness",
    "weaknesses", "write-down", "write-off",
})


def _lm_score(text: str) -> dict:
    """Score text using Loughran-McDonald word lists. Returns pos, neg, total counts."""
    words = [w.lower().strip(".,;:!?\"'()[]") for w in text.split()]
    words = [w for w in words if len(w) > 1]
    total = len(words)
    if total == 0:
        return {"positive": 0, "negative": 0, "total_words": 0, "sentiment_score": 0.0}
    pos = sum(1 for w in words if w in _LM_POSITIVE)
    neg = sum(1 for w in words if w in _LM_NEGATIVE)
    sentiment = (pos - neg) / (pos + neg) if (pos + neg) > 0 else 0.0
    return {"positive": pos, "negative": neg, "total_words": total, "sentiment_score": round(sentiment, 4)}


def _strip_html(html: str) -> str:
    """Strip HTML tags and decode common HTML entities — no lxml/bs4 required."""
    import re, html as _html_module
    text = re.sub(r"<[^>]+>", " ", html)
    text = _html_module.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@st.cache_data(ttl=86400, show_spinner=False, max_entries=50)
def fetch_earnings_transcript_sentiment(ticker: str, n_quarters: int = 8) -> pd.DataFrame:
    """
    Fetch and score the sentiment of earnings press releases for *ticker*
    using SEC EDGAR 8-K filings that contain Item 2.02 (Results of Operations
    and Financial Condition) — these are the actual earnings releases, not
    analyst transcripts.

    Sentiment is scored using the Loughran-McDonald (2011) financial lexicon,
    which is the standard academic word list for financial text and avoids the
    false-positive problem that VADER has with finance-domain vocabulary (e.g.
    VADER incorrectly classifies "liability", "risk", and "capital" as
    negative).

    Returns a DataFrame with columns:
        date            — filing date (datetime)
        positive        — raw positive word count
        negative        — raw negative word count
        sentiment_score — (pos − neg) / (pos + neg), range −1 to +1
        total_words     — total tokenised words in filing
        filing_url      — direct link to the .htm filing on EDGAR

    Returns an empty DataFrame (never synthesises data) if EDGAR is
    unreachable or the ticker has no qualifying 8-K filings.

    API chain (all public, no key required):
        1. https://www.sec.gov/files/company_tickers.json  →  CIK lookup
        2. data.sec.gov/submissions/CIK{10-digit}.json     →  filing list
        3. www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}.htm  →  text
    """
    headers = {
        "User-Agent": "UnstructuredAlpha/1.0 research@unstructuredalpha.com",
        "Accept-Encoding": "gzip, deflate",
    }
    empty = pd.DataFrame(columns=["date", "positive", "negative", "sentiment_score", "total_words", "filing_url"])

    # ── Step 1: CIK lookup ────────────────────────────────────────────────────
    try:
        r = resilient_get(
            "https://www.sec.gov/files/company_tickers.json",
            provider="sec_edgar", headers=headers, timeout=15,
        )
        r.raise_for_status()
        tickers_map = r.json()  # {idx: {"cik_str": int, "ticker": str, "title": str}}
    except Exception:
        return empty

    ticker_upper = ticker.upper()
    cik_int = None
    for entry in tickers_map.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            cik_int = entry["cik_str"]
            break
    if cik_int is None:
        return empty

    cik_padded = str(cik_int).zfill(10)

    # ── Step 2: Submissions feed — filter for 8-K with Item 2.02 ─────────────
    try:
        sub_r = resilient_get(
            f"https://data.sec.gov/submissions/CIK{cik_padded}.json",
            provider="sec_edgar", headers=headers, timeout=15,
        )
        sub_r.raise_for_status()
        sub_data = sub_r.json()
    except Exception:
        return empty

    recent = sub_data.get("filings", {}).get("recent", {})
    forms      = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    items_list = recent.get("items", [])
    primary_docs = recent.get("primaryDocument", [])

    qualifying = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        item_str = items_list[i] if i < len(items_list) else ""
        # items field is comma-separated: "2.02,9.01" or just "2.02"
        if "2.02" not in str(item_str):
            continue
        qualifying.append({
            "date": filing_dates[i] if i < len(filing_dates) else None,
            "accession": accessions[i] if i < len(accessions) else None,
            "primary_doc": primary_docs[i] if i < len(primary_docs) else None,
        })
        if len(qualifying) >= n_quarters:
            break

    if not qualifying:
        return empty

    # ── Step 3: Fetch each filing's primary document and score ───────────────
    records = []
    for filing in qualifying:
        if not filing["accession"] or not filing["date"]:
            continue
        acc_nodash = filing["accession"].replace("-", "")
        doc_name   = filing["primary_doc"] or ""
        if not doc_name:
            continue

        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{cik_int}/{acc_nodash}/{doc_name}"
        )
        try:
            doc_r = resilient_get(filing_url, provider="sec_edgar", headers=headers, timeout=20)
            doc_r.raise_for_status()
            raw_text = _strip_html(doc_r.text)
        except Exception:
            continue

        scored = _lm_score(raw_text)
        records.append({
            "date":            pd.to_datetime(filing["date"]),
            "positive":        scored["positive"],
            "negative":        scored["negative"],
            "sentiment_score": scored["sentiment_score"],
            "total_words":     scored["total_words"],
            "filing_url":      filing_url,
        })

    if not records:
        return empty

    df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    return df
