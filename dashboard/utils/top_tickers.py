"""
utils/top_tickers.py
====================
Fast "what the machine is flagging right now" screener.

The pure ``rank_top_tickers`` path accepts an already-loaded real signal
snapshot and performs no provider calls. ``get_top_tickers`` preserves the
shared live-cache behavior used by background jobs and deeper product pages.
Both paths run pure-Python compute_confluence() across the ticker universe.

Deliberately omits the price-momentum blend from the Stock Screener
(which requires a 1-year yfinance download for all tickers) because:
  1. Home page needs to load fast.
  2. Macro signal alignment is the *differentiated* view — price momentum
     is available everywhere else.

The result answers: "Which tickers does the macro data favor right now,
ignoring what their charts look like?"
"""

from __future__ import annotations

import streamlit as st

from utils.config import SIGNALS, TICKERS
from utils.analysis import compute_confluence


def rank_top_tickers(all_scores: dict) -> dict:
    """Rank the ticker universe from caller-supplied real signal scores.

    This function is deliberately provider-free. It lets latency-sensitive
    surfaces such as Home reuse their canonical persisted snapshot rather than
    starting a 47-source refresh before the first useful content can paint.
    Missing signals remain missing and are excluded; no neutral placeholder
    rows are invented.
    """
    rows: list[dict] = []
    for ticker, meta in TICKERS.items():
        sig_ids = meta.get("signals", list(SIGNALS.keys()))
        weights = {
            sid: SIGNALS[sid].get("pcs", 5) / 10.0
            for sid in sig_ids
            if sid in SIGNALS
        }
        ticker_scores = {
            sid: all_scores[sid]
            for sid in sig_ids
            if sid in all_scores
            and isinstance(all_scores[sid], dict)
            and not all_scores[sid].get("error")
            and all_scores[sid].get("status") != "insufficient_data"
        }
        if not ticker_scores:
            continue

        conf = compute_confluence(ticker_scores, weights=weights)
        rows.append({
            "ticker":  ticker,
            "name":    meta.get("name", ticker),
            "sector":  meta.get("sector", "Other"),
            "score":   round(conf["overall_score"], 1),
            "case":    conf["case"],
            "conv":    conf["conviction"],
            "bull":    conf["bull_count"],
            "bear":    conf["bear_count"],
            "signals": len(ticker_scores),
        })

    rows.sort(key=lambda r: -r["score"])

    bullish = [r for r in rows if r["case"] == "BULL"][:6]
    bearish = [r for r in sorted(rows, key=lambda r: r["score"]) if r["case"] == "BEAR"][:4]

    by_sector: dict[str, list[dict]] = {}
    for row in rows[:30]:
        by_sector.setdefault(row["sector"], []).append(row)

    return {
        "bullish": bullish,
        "bearish": bearish,
        "by_sector": by_sector,
        "all": rows,
    }


@st.cache_data(ttl=7200, show_spinner=False, max_entries=2)
def get_top_tickers(signal_scores_hash: int = 0) -> dict:
    """
    Compute macro confluence scores for every ticker in the universe using
    the pre-loaded signal cache. Returns top bullish and top bearish lists.

    `signal_scores_hash` is a version key so callers can bust the cache when
    the signal data refreshes (pass len(signal_scores) as a simple proxy).

    Returns:
        {
            "bullish": [{"ticker", "name", "sector", "score", "bull", "bear", "signals"}, ...],
            "bearish": [...],
            "by_sector": {"sector_name": [ticker_rows...]},
        }
    """
    # Import here (not module-level) to avoid circular imports when the home
    # page imports this before the Streamlit runtime is fully initialised.
    from utils.signals_cache import get_all_signal_scores

    all_scores = get_all_signal_scores()
    return rank_top_tickers(all_scores)
