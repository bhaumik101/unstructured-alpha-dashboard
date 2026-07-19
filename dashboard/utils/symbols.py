"""
utils/symbols.py — the full US-listed symbol universe for search/autocomplete.

WHY: our scored universe is ~280 tickers, but users want to search and watch
*any* listed stock. This provides a large, cached symbol index (~13k US-listed
equities + ETFs) so search boxes can autocomplete on every keystroke, while the
280 scored tickers remain what the signal engine actually models.

SOURCE: NASDAQ Trader's public symbol directory (no API key, no auth):
  nasdaqlisted.txt  — NASDAQ-listed        (pipe-delimited)
  otherlisted.txt   — NYSE / AMEX / ARCA   (pipe-delimited, different columns)

DESIGN:
- Fetched through utils.resilience (circuit breaker + bounded retries + timeout).
- Cached in-process for 24h; a refetch costs ~1-2s once per day per process.
- ALWAYS degrades: on any failure it falls back to the tracked TICKERS so search
  keeps working rather than breaking the page.
- Test issues are filtered out; symbols are capped (MAX_SEARCH_SYMBOLS) so the
  option payload sent to the browser stays bounded.
"""
from __future__ import annotations

import os

_NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
_OTHER_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"

# Bound the payload handed to the browser. ~13k is the real universe; this is a
# safety valve, tunable without a code change.
MAX_SEARCH_SYMBOLS = max(500, int(os.getenv("MAX_SEARCH_SYMBOLS", "15000")))

_NAME_MAXLEN = 38  # keep labels compact — this list ships to the client


def _clean_name(raw: str) -> str:
    """Trim the very verbose security names in the directory files."""
    n = (raw or "").strip()
    for cut in (" - Class ", " - Ordinary Shares", " - Common Stock",
                " Common Stock", " Class A", " Ordinary Shares",
                " American Depositary Shares", " - American Depositary"):
        i = n.find(cut)
        if i > 0:
            n = n[:i]
            break
    n = n.strip(" .,-")
    return n[:_NAME_MAXLEN]


def _parse(text: str, sym_idx: int, name_idx: int, test_idx: int | None) -> dict[str, str]:
    """Parse one pipe-delimited directory file into {SYMBOL: name}."""
    out: dict[str, str] = {}
    for line in (text or "").splitlines()[1:]:      # skip header
        if not line or line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) <= max(sym_idx, name_idx):
            continue
        sym = (parts[sym_idx] or "").strip().upper()
        if not sym or not sym.replace(".", "").replace("-", "").isalnum():
            continue
        if test_idx is not None and len(parts) > test_idx and parts[test_idx].strip() == "Y":
            continue                                 # test issue — not tradeable
        out[sym] = _clean_name(parts[name_idx])
    return out


def _parse_records(text: str, sym_idx: int, name_idx: int,
                   test_idx: int | None, etf_idx: int | None,
                   exchange: str) -> dict[str, dict]:
    """
    Richer parse keeping the ETF flag — the directory tells us outright whether a
    symbol is an exchange-traded product, which is far more reliable than trying
    to infer it from the security name.
    """
    out: dict[str, dict] = {}
    for line in (text or "").splitlines()[1:]:
        if not line or line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) <= max(sym_idx, name_idx):
            continue
        sym = (parts[sym_idx] or "").strip().upper()
        if not sym or not sym.replace(".", "").replace("-", "").isalnum():
            continue
        if test_idx is not None and len(parts) > test_idx and parts[test_idx].strip() == "Y":
            continue
        is_etf = False
        if etf_idx is not None and len(parts) > etf_idx:
            is_etf = parts[etf_idx].strip().upper() == "Y"
        out[sym] = {
            "symbol": sym,
            "name": (parts[name_idx] or "").strip(),   # RAW name — classifiers need it
            "short_name": _clean_name(parts[name_idx]),
            "etf": is_etf,
            "exchange": exchange,
        }
    return out


def fetch_symbol_records() -> dict[str, dict]:
    """{SYMBOL: {symbol,name,short_name,etf,exchange}} for all US-listed symbols."""
    from utils.resilience import resilient_get
    merged: dict[str, dict] = {}
    # nasdaqlisted: Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot|ETF|NextShares
    try:
        r = resilient_get(_NASDAQ_URL, provider="nasdaq_symdir", timeout=20)
        if r.status_code == 200:
            merged.update(_parse_records(r.text, 0, 1, test_idx=3, etf_idx=6, exchange="NASDAQ"))
    except Exception:
        pass
    # otherlisted: ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot|Test Issue|NASDAQ Symbol
    try:
        r = resilient_get(_OTHER_URL, provider="nasdaq_symdir", timeout=20)
        if r.status_code == 200:
            merged.update(_parse_records(r.text, 0, 1, test_idx=6, etf_idx=4, exchange="NYSE/AMEX"))
    except Exception:
        pass
    return merged


def fetch_symbol_directory() -> dict[str, str]:
    """{SYMBOL: name} for all US-listed symbols. Empty dict on failure."""
    try:
        return {s: r["short_name"] for s, r in fetch_symbol_records().items()}
    except Exception:
        return {}


def _tracked_fallback() -> dict[str, str]:
    try:
        from utils.config import TICKERS
        return {t: (m.get("name") or t)[:_NAME_MAXLEN] for t, m in TICKERS.items()}
    except Exception:
        return {}


def build_symbol_index() -> dict[str, str]:
    """
    {SYMBOL: "SYM — Company Name"} for search widgets.

    Merges the full directory with our tracked tickers (tracked names win, since
    they're curated), sorted by symbol. Falls back to tracked-only on failure so
    search never breaks.
    """
    tracked = _tracked_fallback()
    try:
        universe = fetch_symbol_directory()
    except Exception:
        universe = {}
    if not universe:
        universe = dict(tracked)

    universe.update(tracked)  # curated names take precedence
    if len(universe) > MAX_SEARCH_SYMBOLS:
        # Keep every tracked ticker, then fill up to the cap alphabetically.
        keep = dict(tracked)
        for s in sorted(universe):
            if len(keep) >= MAX_SEARCH_SYMBOLS:
                break
            keep.setdefault(s, universe[s])
        universe = keep

    return {s: (f"{s} — {n}" if n else s) for s, n in sorted(universe.items())}


def get_symbol_index() -> dict[str, str]:
    """Streamlit-cached wrapper (24h). Safe to call on every rerun."""
    try:
        import streamlit as st

        @st.cache_data(ttl=86400, show_spinner=False, max_entries=1)
        def _cached() -> dict:
            return build_symbol_index()

        return _cached()
    except Exception:
        return build_symbol_index()


def is_tracked(symbol: str) -> bool:
    """True if the symbol is in our scored universe (vs merely listed)."""
    try:
        from utils.config import TICKERS
        return (symbol or "").upper().strip() in TICKERS
    except Exception:
        return False
