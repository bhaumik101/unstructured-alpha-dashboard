"""
SEC EDGAR XBRL company facts — real reported fundamentals, free and redistributable.

WHY THIS EXISTS
    We advertise "SEC EDGAR" on the Signal Dashboard and on the paid Upgrade
    page, but until now EDGAR backed exactly one Pro widget (Form 4 insider
    filings) and ZERO of the 47 signals. Worse, `hyperscaler_capex` was named
    "Hyperscaler CapEx", described as "trailing capital expenditure", cited to
    sec.gov — and actually computed an equal-weight SHARE PRICE index of
    MSFT/AMZN/GOOGL/META via fetch_basket(). This module makes that signal
    measure what its name says.

WHY EDGAR RATHER THAN A PAID FEED
    Priced vendors at the tier we could afford (Massive $29, Tiingo $30,
    EODHD $20) license data for personal/internal use only; displaying it to
    subscribers starts around $399–2,499/mo. EDGAR is public domain, has no
    per-seat license, needs no key, and is the ORIGINAL source those vendors
    scrape for US fundamentals.

TWO PARSING RULES, both ground-truthed against live payloads (2026-08-02) and
NOT assumed — getting either wrong silently corrupts the series:

  1. DISCRETE QUARTERS ONLY. A fact carries a "frame" key like "CY2025Q1" only
     when it covers a clean calendar quarter. Rows without one are cumulative
     year-to-date spans; MSFT reports both, e.g.
         start 2025-07-01 end 2026-03-31 val 80_146_000_000   (9 months, no frame)
         start 2026-01-01 end 2026-03-31 val 30_876_000_000   (frame CY2026Q1)
     Summing everything double-counts by roughly 3x.

  2. RESTATEMENTS ARE VINTAGES. The same period recurs under several accession
     numbers with different "filed" dates. That makes EDGAR natively
     point-in-time: the earliest filed value is what the market actually knew
     that day. This mirrors fetch_fred_first_print() — same honesty rule,
     different provider.
"""

from __future__ import annotations

import re
from typing import Iterable

import pandas as pd
import streamlit as st

from utils.resilience import resilient_get  # shared session + circuit breakers

# SEC requires a descriptive UA with contact info on every automated request.
# https://www.sec.gov/os/webmaster-faq#developers
_SEC_UA = {"User-Agent": "UnstructuredAlpha/1.0 research@unstructuredalpha.com"}

# Only "CY####Q#" is a discrete quarter. Bare "CY####" is a full year and must
# not be mixed into a quarterly series.
_QUARTER_FRAME = re.compile(r"^CY\d{4}Q[1-4]$")


@st.cache_data(ttl=604800, show_spinner=False, max_entries=1)  # 7d — CIK assignments are ~immutable
def _ticker_to_cik() -> dict:
    """Map upper-case ticker → zero-padded 10-digit CIK.

    Fetched rather than hard-coded on purpose: a wrong constant here would
    silently pull another company's financials, which is far worse than a
    missing series. Returns {} on any failure so callers degrade to empty.
    """
    try:
        r = resilient_get("https://www.sec.gov/files/company_tickers.json",
                          provider="sec_edgar", headers=_SEC_UA, timeout=20)
        r.raise_for_status()
        return {
            str(row["ticker"]).upper(): f"{int(row['cik_str']):010d}"
            for row in (r.json() or {}).values()
            if row.get("ticker") and row.get("cik_str") is not None
        }
    except Exception:
        return {}


@st.cache_data(ttl=86400, show_spinner=False, max_entries=64)
def fetch_sec_concept(cik: str, tag: str, taxonomy: str = "us-gaap",
                      unit: str = "USD", first_print: bool = False) -> pd.Series:
    """Quarterly series for one XBRL concept, indexed by period-end date.

    first_print=True returns the value as ORIGINALLY filed (earliest `filed`
    per period); False returns the latest restatement. Live scoring wants the
    restated number; backtests must use first_print or they see figures that
    did not exist yet.
    """
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json"
    try:
        r = resilient_get(url, provider="sec_edgar", headers=_SEC_UA, timeout=20)
        r.raise_for_status()
        facts = (r.json() or {}).get("units", {}).get(unit, [])
    except Exception:
        return pd.Series(dtype=float)

    rows = [f for f in facts if _QUARTER_FRAME.match(str(f.get("frame", "")))]
    if not rows:
        return pd.Series(dtype=float)

    df = pd.DataFrame(rows)
    df["end"] = pd.to_datetime(df["end"], errors="coerce")
    df["filed"] = pd.to_datetime(df.get("filed"), errors="coerce")
    df = df.dropna(subset=["end", "val"])
    # One row per period: earliest filing for first-print, latest otherwise.
    df = df.sort_values("filed", ascending=first_print).drop_duplicates("end", keep="first")

    out = df.set_index("end")["val"].astype(float).sort_index()
    out.name = tag
    return out


def fetch_sec_concept_sum(tickers: Iterable[str], tag: str, taxonomy: str = "us-gaap",
                          unit: str = "USD", first_print: bool = False) -> pd.Series:
    """Summed quarterly series across companies — a real aggregate, in dollars.

    Only quarters where EVERY requested company has filed are kept. A partial
    sum would show up as a spurious collapse the moment one filer lags, which
    on a capex signal reads as demand falling off a cliff.
    """
    cikmap = _ticker_to_cik()
    series = []
    for t in tickers:
        cik = cikmap.get(str(t).upper())
        if not cik:
            continue
        s = fetch_sec_concept(cik, tag, taxonomy, unit, first_print)
        if not s.empty:
            series.append(s.rename(str(t).upper()))

    if not series:
        return pd.Series(dtype=float)

    df = pd.concat(series, axis=1).dropna(how="any")
    if df.empty:
        return pd.Series(dtype=float)
    out = df.sum(axis=1)
    out.name = "sec_sum"
    return out
