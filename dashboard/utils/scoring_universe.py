"""
utils/scoring_universe.py — which symbols we are willing to SCORE.

Search spans ~12.6k US-listed symbols (utils/symbols.py). Scoring must not.

WHY THIS EXISTS
---------------
The Confluence Score is a macro-correlation model. Running it over the whole
listed universe would produce confident-looking numbers for instruments where the
model is meaningless:

  • leveraged / inverse ETPs  — "Direxion Daily SOFI Bull 2X", "Corgi RKLB 2x"
      Their returns are a mechanical multiple of an underlying, reset daily.
      A macro correlation on them describes the multiplier, not the economy.
  • plain ETFs / ETNs / funds — baskets, not companies. (The handful of
      macro-relevant sector ETFs we DO want are already in the curated 280.)
  • warrants, units, rights, preferreds — derivative or hybrid claims whose price
      is driven by the terms of the instrument, not the macro backdrop.
  • SPACs / blank-check shells pre-deal — trade at trust value, near-zero macro beta.

For a product positioned on precision, a fake number is worse than an honest
"not scored yet". Everything excluded here stays fully SEARCHABLE and can still be
analysed on demand — it just doesn't get a precomputed score it hasn't earned.

This module is deliberately pure + offline (name/flag heuristics only). The second
gate — sufficient price history and liquidity — needs price data and belongs in the
scoring worker, not here.
"""
from __future__ import annotations

import re

# ── Exclusion reasons (stable identifiers, safe to store/aggregate) ───────────
OK = "scoreable"
EXCL_ETF = "etf_or_fund"
EXCL_LEVERAGED = "leveraged_or_inverse"
EXCL_DERIVATIVE = "warrant_unit_right"
EXCL_PREFERRED = "preferred_or_debt"
EXCL_SPAC = "spac_shell"
EXCL_SYMBOL_FORM = "non_common_symbol"

# Leveraged / inverse product tells. Checked on the RAW security name.
_LEVERAGED_RE = re.compile(
    r"(\b\d(\.\d)?X\b|\b[23]X\b|ULTRA(SHORT|PRO)?|INVERSE|\bBULL\b|\bBEAR\b|"
    r"DAILY\s+TARGET|LEVERAGED|\bSHORT\b|\-1X|\bENHANCED\s+YIELD\b)",
    re.IGNORECASE,
)
# Funds / pooled vehicles that the ETF flag sometimes misses.
_FUND_RE = re.compile(
    r"\b(ETF|ETN|FUND|TRUST|INDEX|PORTFOLIO|SHARES\s+OF\s+BENEFICIAL|"
    r"CLOSED\s+END|COMMODITY\s+POOL)\b",
    re.IGNORECASE,
)
_DERIVATIVE_RE = re.compile(r"\b(WARRANT|WARRANTS|UNIT|UNITS|RIGHT|RIGHTS)\b", re.IGNORECASE)
_PREFERRED_RE = re.compile(
    r"\b(PREFERRED|PFD|DEPOSITARY\s+SHARE|NOTE[S]?\s+DUE|DEBENTURE|"
    r"%\s+SERIES|SUBORDINATED)\b",
    re.IGNORECASE,
)
# "Acquisition" anywhere in the name is a strong blank-check tell — the suffix
# varies wildly (Corp / Inc. / Co / Holdings / Ltd), so matching only "Acquisition
# Corp" let shells like "Artius II Acquisition Inc." through. Operating companies
# almost never carry it, and erring toward exclusion is the correct bias here:
# a shell trading at trust value has near-zero macro beta, so any score is noise.
_SPAC_RE = re.compile(r"\b(ACQUISITION|BLANK\s+CHECK)\b", re.IGNORECASE)

# Symbol shapes that denote non-common share classes on the tape.
# 5-letter NASDAQ symbols ending W/R/U = warrant/right/unit.
_SYM_SUFFIX_RE = re.compile(r"^[A-Z]{4}[WRU]$")
# Dotted/dashed suffixes: BRK.A is fine (common), but .W/.U/.R/.P are not.
_SYM_DOT_SUFFIX_RE = re.compile(r"[.\-](W|WS|U|R|RT|P|PR[A-Z]?)$", re.IGNORECASE)


def classify(symbol: str, name: str, is_etf: bool = False) -> str:
    """
    Return OK if this symbol is a plain common stock we're willing to score,
    else a stable exclusion reason. Pure function — no I/O, never raises.
    """
    sym = (symbol or "").strip().upper()
    nm = (name or "").strip()
    if not sym:
        return EXCL_SYMBOL_FORM

    # Leveraged/inverse first: these are often ALSO flagged as ETFs, but the
    # distinction matters for reporting (and they're the most dangerous to score).
    if _LEVERAGED_RE.search(nm):
        return EXCL_LEVERAGED
    if is_etf or _FUND_RE.search(nm):
        return EXCL_ETF
    if _DERIVATIVE_RE.search(nm):
        return EXCL_DERIVATIVE
    if _PREFERRED_RE.search(nm):
        return EXCL_PREFERRED
    if _SPAC_RE.search(nm):
        return EXCL_SPAC
    if _SYM_DOT_SUFFIX_RE.search(sym) or _SYM_SUFFIX_RE.match(sym):
        return EXCL_SYMBOL_FORM
    return OK


def build_scoring_universe(records: dict[str, dict] | None = None) -> dict:
    """
    Partition the listed universe into what we'll score vs what we won't.

    Returns:
        {
          "scoreable": {SYMBOL: short_name},
          "excluded":  {SYMBOL: reason},
          "stats":     {reason: count, "total": int, "scoreable": int},
        }

    Curated tracked tickers are ALWAYS scoreable — they're hand-picked (and
    include the macro-relevant sector ETFs the generic rules would drop).
    Never raises; degrades to the tracked set.
    """
    try:
        if records is None:
            from utils.symbols import fetch_symbol_records
            records = fetch_symbol_records()
    except Exception:
        records = {}

    try:
        from utils.config import TICKERS
        tracked = set(TICKERS.keys())
    except Exception:
        tracked = set()

    scoreable: dict[str, str] = {}
    excluded: dict[str, str] = {}
    stats: dict[str, int] = {}

    for sym, rec in (records or {}).items():
        try:
            short = rec.get("short_name") or rec.get("name") or sym
            if sym in tracked:                       # curated always wins
                scoreable[sym] = short
                stats[OK] = stats.get(OK, 0) + 1
                continue
            reason = classify(sym, rec.get("name", ""), bool(rec.get("etf")))
            if reason == OK:
                scoreable[sym] = short
            else:
                excluded[sym] = reason
            stats[reason] = stats.get(reason, 0) + 1
        except Exception:
            continue

    # Ensure every tracked ticker is present even if absent from the directory.
    for t in tracked:
        scoreable.setdefault(t, t)

    stats["total"] = len(records or {})
    stats["scoreable"] = len(scoreable)
    return {"scoreable": scoreable, "excluded": excluded, "stats": stats}


def get_scoring_universe() -> dict:
    """Streamlit-cached wrapper (24h). Safe on every rerun."""
    try:
        import streamlit as st

        @st.cache_data(ttl=86400, show_spinner=False, max_entries=1)
        def _cached() -> dict:
            return build_scoring_universe()

        return _cached()
    except Exception:
        return build_scoring_universe()
