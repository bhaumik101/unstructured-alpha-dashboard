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
# All functions fall back to synthetic demo data (or an empty result, where
# fabricating a synthetic value wouldn't be honest) if real data is
# unavailable.

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
def fetch_fred(series_id: str, start: str, end: str, api_key: str = "") -> pd.Series:
    """
    Fetch a FRED data series.
    Falls back to synthetic data if no API key is configured. The returned
    series carries s.attrs["synthetic"] so callers/pages can detect and
    visibly flag demo data instead of silently presenting it as real.

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
def fetch_eia(series_id: str, start: str, end: str, api_key: str = "") -> pd.Series:
    """
    Fetch an EIA data series via the API v2 backward-compatibility endpoint
    (api.eia.gov/v2/seriesid/{id}), which accepts legacy v1-style series IDs
    such as WCESTUS1 (weekly crude stocks ex-SPR) and NW2_EPG0_SWO_R48_BCF
    (weekly Lower-48 working gas in underground storage) — both confirmed
    live on EIA's own dnav pages as of 2026.

    Falls back to synthetic data if no key is configured or the fetch fails,
    same contract as fetch_fred(): s.attrs["synthetic"] marks which is which.

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
            return fetch_fred(cfg["series_id"], start, end, api_key=_get_fred_key())
        elif src == "eia":
            return fetch_eia(cfg["series_id"], start, end, api_key=_get_eia_key())
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


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_insider_transactions_detail(ticker: str, days: int = 180, max_filings: int = 20) -> pd.DataFrame:
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
    (shares * price, signed: + for P, - for S).
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
        r = requests.get(search_url, headers=headers, timeout=12)
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
    except Exception:
        return pd.DataFrame()

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

        try:
            xr = requests.get(xml_url, headers=headers, timeout=12)
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
            })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# FINRA — Consolidated Equity Short Interest
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=43200, show_spinner=False)
def fetch_short_interest(ticker: str, years: float = 1.5) -> pd.DataFrame:
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
        r = requests.post(url, json=payload, headers=headers, timeout=15)
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
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# SEC EDGAR — Form 13F institutional holdings (curated funds only)
# ─────────────────────────────────────────────────────────────────────────────

_THIRTEENF_NS = {"t": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}
_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_13f_holdings(cik: str, fund_name: str, max_filings: int = 2) -> pd.DataFrame:
    """
    Fetch a fund's most recent Form 13F-HR holdings, real and live, for the
    curated funds in utils/config.CURATED_FUNDS.

    Endpoint chain verified live, 2026-06-21, against Berkshire Hathaway
    (CIK 1067983), Pershing Square (CIK 1336528), and Scion Asset Management
    (CIK 1649339) before any of this was written:
      1. EDGAR atom feed (browse-edgar, type=13F-HR) -> accession numbers.
         13F-HR/A amendments are explicitly excluded -- a re-filed amendment
         is not a new quarter's worth of positioning, and including it would
         double-count or misdate a period.
      2. Each filing's /index.json -> the information table's actual XML
         filename. This is NOT a fixed convention (Berkshire's filing agent
         used "53405.xml"; Pershing Square's and Scion's used "infotable.xml")
         -- same lesson as Form 4's filename variability, solved the same way:
         read the real directory listing, don't assume a name.
      3. primary_doc.xml -> the real periodOfReport (e.g. "03-31-2026"),
         since the filing date and the quarter the holdings are AS OF are
         different things and conflating them would misdate every position.
      4. The information table XML itself -- infoTable entries with fields
         nameOfIssuer, cusip, value, shrsOrPrnAmt/sshPrnamt, and an OPTIONAL
         putCall field. putCall is the field that makes this non-trivial:
         a "Put" position is a BEARISH bet (or hedge), not bullish share
         ownership, even though it appears in the same information table
         alongside plain long stock positions -- confirmed live in Scion's
         actual filing (their NVIDIA position is a Put, their Halliburton
         position is a Call, neither is a plain share holding). Treating
         every line as "the fund owns this stock" would have been wrong.

    Returns one row per (filing period x holding), with columns: fund,
    period (the real periodOfReport, not the filing date), filed_date,
    cusip, issuer, shares, value, direction ("long" for a plain share
    position or a Call option, "short" for a Put option).
    """
    headers = {"User-Agent": "Unstructured Alpha research dashboard (contact: research@unstructuredalpha.example)"}
    rows = []
    try:
        atom_url = (
            f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
            f"&type=13F-HR&dateb=&owner=include&count=20&output=atom"
        )
        r = requests.get(atom_url, headers=headers, timeout=15)
        r.raise_for_status()
        feed = ET.fromstring(r.content)

        filings = []
        for entry in feed.findall("a:entry", _ATOM_NS):
            cat = entry.find("a:category", _ATOM_NS)
            form_type = cat.get("term") if cat is not None else ""
            if form_type != "13F-HR":  # excludes 13F-HR/A amendments on purpose
                continue
            content = entry.find("a:content", _ATOM_NS)
            if content is None:
                continue
            acc = content.find("a:accession-number", _ATOM_NS)
            if acc is None or not acc.text:
                continue
            filings.append(acc.text.strip())
            if len(filings) >= max_filings:
                break

        for accession in filings:
            accession_nodash = accession.replace("-", "")
            base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}"

            idx_r = requests.get(f"{base}/index.json", headers=headers, timeout=15)
            idx_r.raise_for_status()
            items = idx_r.json().get("directory", {}).get("item", [])
            info_table_name = next(
                (it["name"] for it in items
                 if it["name"].lower().endswith(".xml") and it["name"].lower() != "primary_doc.xml"),
                None,
            )
            if not info_table_name:
                continue

            period = None
            try:
                pd_r = requests.get(f"{base}/primary_doc.xml", headers=headers, timeout=15)
                pd_r.raise_for_status()
                pd_root = ET.fromstring(pd_r.content)
                for el in pd_root.iter():
                    if el.tag.endswith("periodOfReport") and el.text:
                        period = pd.to_datetime(el.text.strip(), format="%m-%d-%Y", errors="coerce")
                        break
            except Exception:
                pass

            tbl_r = requests.get(f"{base}/{info_table_name}", headers=headers, timeout=20)
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
                })
    except Exception:
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


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
