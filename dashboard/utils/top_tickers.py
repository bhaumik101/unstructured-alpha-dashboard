"""
utils/top_tickers.py
====================
Fast "what the machine is flagging right now" screener.

Uses the SAME cached signal scores that home page, Today's Brief, and Signal
Dashboard already load — zero additional API calls. Runs pure-Python
compute_confluence() across all 193 tickers in <0.1 seconds.

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

    rows: list[dict] = []
    for ticker, meta in TICKERS.items():
        sig_ids = meta.get("signals", list(SIGNALS.keys()))
        # Weight by PCS (same as screener fast-path)
        weights = {
            sid: SIGNALS[sid].get("pcs", 5) / 10.0
            for sid in sig_ids
            if sid in SIGNALS
        }
        ticker_scores = {
            sid: all_scores.get(sid, {"score": 50, "status": "neutral"})
            for sid in sig_ids
            if sid in all_scores
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

    # Group top 20 by sector
    by_sector: dict[str, list[dict]] = {}
    for r in rows[:30]:
        by_sector.setdefault(r["sector"], []).append(r)

    return {
        "bullish":   bullish,
        "bearish":   bearish,
        "by_sector": by_sector,
        "all":       rows,
    }
