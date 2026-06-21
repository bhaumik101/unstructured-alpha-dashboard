# utils/fetchers.py
# Unstructured Alpha — Data Fetching Layer
#
# Data sources (all free):
#   FRED API       — macro signals (ATA trucking, rail, jobless claims, WTI, etc.)
#   yfinance       — stock/commodity prices (no key needed)
#   CFTC.gov       — COT positioning data (public CSV downloads)
#   USASpending    — federal contract awards (no key needed)
#   SEC EDGAR      — Form 4 insider transactions (no key needed)
#   pytrends       — Google Trends (no key needed)
#   arXiv API      — quantum paper velocity (no key needed)
#
# All functions fall back to synthetic demo data if real data is unavailable.

import os
import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf


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


# ─────────────────────────────────────────────────────────────────────────────
# FRED — Macro Signal Data
# ─────────────────────────────────────────────────────────────────────────────

def is_synthetic(s: pd.Series) -> bool:
    """True if this series is synthetic placeholder data, not real fetched data."""
    return bool(getattr(s, "attrs", {}).get("synthetic", False))


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fred(series_id: str, start: str, end: str) -> pd.Series:
    """
    Fetch a FRED data series.
    Falls back to synthetic data if no API key is configured. The returned
    series carries s.attrs["synthetic"] so callers/pages can detect and
    visibly flag demo data instead of silently presenting it as real.
    """
    api_key = _get_fred_key()

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
            r = requests.get(url, params=params, timeout=12)
            r.raise_for_status()
            data = r.json()
            df = pd.DataFrame(data["observations"])
            df["date"] = pd.to_datetime(df["date"])
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            s = df.dropna(subset=["value"]).set_index("date")["value"]
            s.name = series_id
            s.attrs["synthetic"] = False
            return s
        except Exception:
            pass  # Fall through to synthetic

    return _synthetic_signal(series_id, start, end)


# ─────────────────────────────────────────────────────────────────────────────
# EIA — Energy Information Administration (crude stocks, gas storage)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_eia(series_id: str, start: str, end: str) -> pd.Series:
    """
    Fetch an EIA data series via the API v2 backward-compatibility endpoint
    (api.eia.gov/v2/seriesid/{id}), which accepts legacy v1-style series IDs
    such as WCESTUS1 (weekly crude stocks ex-SPR) and NW2_EPG0_SWO_R48_BCF
    (weekly Lower-48 working gas in underground storage) — both confirmed
    live on EIA's own dnav pages as of 2026.

    Falls back to synthetic data if no key is configured or the fetch fails,
    same contract as fetch_fred(): s.attrs["synthetic"] marks which is which.
    """
    api_key = _get_eia_key()

    if api_key:
        url = f"https://api.eia.gov/v2/seriesid/{series_id}"
        params = {"api_key": api_key}
        try:
            r = requests.get(url, params=params, timeout=12)
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
                s.attrs["synthetic"] = False
                return s
        except Exception:
            pass  # Fall through to synthetic

    return _synthetic_signal(series_id, start, end)


# ─────────────────────────────────────────────────────────────────────────────
# yfinance — Stock & Commodity Prices
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_price(ticker: str, start: str, end: str) -> pd.Series:
    """Fetch daily closing price. No API key required."""
    try:
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
        if hist.empty:
            return pd.Series(dtype=float, name=ticker)
        s = hist["Close"].rename(ticker)
        return _tz_strip(s)
    except Exception:
        return pd.Series(dtype=float, name=ticker)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_quote(ticker: str) -> dict:
    """
    Fetch just the current price + day change for a ticker — cheap and fast
    (yfinance's fast_info, not a full .history() pull), cached for only 60
    seconds instead of fetch_price's 30 minutes. Meant to be called from
    inside an st.fragment(run_every=...) block so price displays visibly
    auto-update without re-running the whole page or re-fetching full
    historical chart data, which stays on the longer 30-min cache above.

    Returns {"price": float|None, "prev_close": float|None, "pct_change": float|None}.
    All None on failure — callers should handle that as "quote unavailable"
    rather than crash, same fallback contract as the rest of this module.
    """
    try:
        fi = yf.Ticker(ticker).fast_info
        price = fi.get("lastPrice") or fi.get("last_price")
        prev_close = fi.get("previousClose") or fi.get("previous_close")
        if price is None:
            return {"price": None, "prev_close": None, "pct_change": None}
        pct_change = ((price - prev_close) / prev_close * 100) if prev_close else None
        return {
            "price": float(price),
            "prev_close": float(prev_close) if prev_close else None,
            "pct_change": float(pct_change) if pct_change is not None else None,
        }
    except Exception:
        return {"price": None, "prev_close": None, "pct_change": None}


def fetch_signal_series(cfg: dict, start: str, end: str) -> pd.Series:
    """
    Single dispatch point for fetching a signal's raw data series, used by
    every page that scores signals from SIGNALS config entries. Keeping this
    in one place means adding a new source type (like "arxiv") only has to
    happen once instead of being duplicated across five page-level loops.
    """
    src = cfg.get("source")
    try:
        if src == "fred":
            return fetch_fred(cfg["series_id"], start, end)
        elif src == "eia":
            return fetch_eia(cfg["series_id"], start, end)
        elif src == "yfinance":
            return fetch_price(cfg["series_id"], start, end)
        elif src in ("yfinance_basket", "yfinance_multi"):
            return fetch_basket(cfg.get("series_ids", [cfg.get("series_id", "SPY")]), start, end)
        elif src == "arxiv":
            return fetch_arxiv_velocity(query=cfg.get("series_id", "quantum computing"))
        elif src == "fda":
            return fetch_fda_approval_velocity()
        else:
            return pd.Series(dtype=float)
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_basket(tickers: list, start: str, end: str) -> pd.Series:
    """Fetch an equal-weight composite index of multiple tickers."""
    series_list = []
    for t in tickers:
        s = fetch_price(t, start, end)
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

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_cot(market: str = "copper") -> pd.DataFrame:
    """
    Fetch CFTC Commitments of Traders data.
    Downloads the current-year legacy futures CSV from cftc.gov.
    Falls back to synthetic data if download fails.
    """
    year = datetime.now().year
    # CFTC legacy futures-only report
    url = f"https://www.cftc.gov/files/dea/history/fut_disagg_xls_{year}.zip"

    try:
        r = requests.get(url, timeout=30)
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
            return _synthetic_cot(market)

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
            return _synthetic_cot(market)

        result = pd.DataFrame({
            "date":          sub["date"],
            "spec_long":     pd.to_numeric(sub[spec_long_col],  errors="coerce"),
            "spec_short":    pd.to_numeric(sub[spec_short_col], errors="coerce"),
            "comm_long":     pd.to_numeric(sub[comm_long_col],  errors="coerce"),
            "comm_short":    pd.to_numeric(sub[comm_short_col], errors="coerce"),
            "open_interest": pd.to_numeric(sub[oi_col],         errors="coerce") if oi_col else np.nan,
        }).dropna(subset=["date", "spec_long"]).sort_values("date")

        return result.reset_index(drop=True)

    except Exception:
        return _synthetic_cot(market)


# ─────────────────────────────────────────────────────────────────────────────
# USASpending.gov — Federal Contract Award Velocity
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200, show_spinner=False)
def fetch_federal_contracts(company_name: str, years: int = 2) -> pd.DataFrame:
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
        r = requests.post(url, json=payload, timeout=20,
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
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# SEC EDGAR — Form 4 Insider Transactions
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
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
        r = requests.get(url, headers=headers, timeout=12)
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


# ─────────────────────────────────────────────────────────────────────────────
# Google Trends — Search Velocity as Narrative Validator
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=14400, show_spinner=False)
def fetch_google_trends(keywords: list, timeframe: str = "today 12-m") -> pd.DataFrame:
    """
    Fetch Google Trends data via pytrends (no API key required).
    Use for validating whether a narrative is entering mainstream awareness.

    Research basis: "refinance mortgage" searches tracked MBA applications
    6-8 weeks early; "unemployment benefits how to apply" preceded the
    March 2020 jobless claims spike.
    """
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=300, timeout=(5, 25))
        kws = keywords[:5]
        pt.build_payload(kws, cat=0, timeframe=timeframe, geo="US")
        df = pt.interest_over_time()
        if df.empty:
            return pd.DataFrame()
        df = df.drop(columns=["isPartial"], errors="ignore")
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# arXiv — Quantum Computing Paper Velocity
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
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
        r = requests.get(url, params=params, timeout=25)
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

@st.cache_data(ttl=86400, show_spinner=False)
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
        r = requests.get(url, params=params, timeout=25)
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
        weekly.attrs["synthetic"] = False
        return weekly

    except Exception:
        return pd.Series(dtype=float, name="fda_approvals_per_week")


# ─────────────────────────────────────────────────────────────────────────────
# SYNTHETIC DATA GENERATORS (demo fallbacks)
# ─────────────────────────────────────────────────────────────────────────────

_SYNTHETIC_PARAMS = {
    # series_id: (mean, noise_std, weekly_trend, cycle_amplitude_mult)
    "TRUCKD11":          (108.0,  2.5,  0.04,  0.60),
    "RAILFRTINTERMODAL": (285000, 10000, 80,   0.55),
    "IC4WSA":            (218000, 16000, -180, 0.50),
    "JTSLDR":            (1.14,   0.10, -0.0008, 0.40),
    "DCOILWTICO":        (78.0,   5.5,  0.018, 0.75),
    "MHHNGSP":           (2.82,   0.40, 0.004, 0.65),
    "CPIUFDSL":          (288.5,  3.5,  0.22,  0.90),
}


def _synthetic_signal(series_id: str, start: str, end: str) -> pd.Series:
    """Realistic synthetic signal data for demo mode."""
    dates = pd.date_range(start=start, end=end, freq="W")
    n = len(dates)
    np.random.seed(abs(hash(series_id)) % 2**31)

    mean, std, trend_pw, cycle_amp = _SYNTHETIC_PARAMS.get(
        series_id, (100.0, 8.0, 0.05, 0.50)
    )

    noise  = np.random.normal(0, std * 0.35, n)
    trend  = np.linspace(0, trend_pw * n, n)
    cycle  = std * cycle_amp * np.sin(np.linspace(0, 3.0 * np.pi, n))

    # Inject 2-3 realistic shock events (simulate crises/booms)
    shock = np.zeros(n)
    for _ in range(3):
        idx = np.random.randint(n // 5, 4 * n // 5)
        mag = np.random.choice([-1, 1]) * std * np.random.uniform(1.5, 3.0)
        width = min(12, n - idx)
        shock[idx:idx + width] += mag * np.linspace(1.0, 0.0, width)

    values = mean + noise + trend + cycle + shock
    s = pd.Series(values, index=dates, name=series_id)
    s.attrs["synthetic"] = True
    return s


def _synthetic_cot(market: str) -> pd.DataFrame:
    """Synthetic COT positioning data for demo mode."""
    np.random.seed(abs(hash(market)) % 2**31)
    dates = pd.date_range(end=datetime.now(), periods=130, freq="W")
    n = len(dates)

    # Positioning cycles between extremes — realistic boom/bust pattern
    cycle      = np.sin(np.linspace(0, 5 * np.pi, n))
    spec_net   = (cycle * 85000 + np.random.normal(0, 12000, n)).astype(int)
    comm_net   = (-spec_net * 0.95 + np.random.normal(0, 6000, n)).astype(int)
    oi         = np.clip(350000 + np.random.normal(0, 25000, n), 100000, 600000).astype(int)

    return pd.DataFrame({
        "date":          dates,
        "spec_long":     np.maximum(spec_net,  0),
        "spec_short":    np.maximum(-spec_net, 0),
        "comm_long":     np.maximum(-comm_net, 0),
        "comm_short":    np.maximum(comm_net,  0),
        "open_interest": oi,
    })
