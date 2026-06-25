"""
utils/convergence.py
====================
Signal Convergence Event detection.

A "convergence event" fires when 3+ macro signals ALL move in the same
direction for the same ticker within a short window. This is fundamentally
different from any individual signal going bullish/bearish — convergence
means *multiple independent data sources are telling the same story*, which
is where the highest-conviction setups historically come from.

How it works:
  1. Pull recent signal flips from signal_snapshots (via get_signal_flips).
  2. Map each signal → the tickers it's relevant to (from TICKERS config,
     where each ticker lists its relevant signal IDs).
  3. For each ticker, count how many of its relevant signals flipped to
     BULLISH (or BEARISH) in the last `days_back` days.
  4. If the count ≥ min_signals, it's a convergence event.

Zero additional API calls — uses the same cached signal data and the
existing signal_snapshots DB table.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import streamlit as st

from utils.config import SIGNALS, TICKERS


@st.cache_data(ttl=3600, show_spinner=False, max_entries=2)
def get_convergence_events(
    days_back: int = 7,
    min_signals: int = 3,
) -> list[dict]:
    """
    Find tickers where ≥ min_signals of their relevant signals all moved
    to bullish (or bearish) within the last `days_back` days.

    Returns a list of convergence event dicts, sorted by signal count desc:
        [{
            "ticker":      str,
            "name":        str,
            "direction":   "bullish" | "bearish",
            "count":       int,          # number of aligned signals
            "signals":     list[str],    # signal names that aligned
            "sector":      str,
        }, ...]

    Uses signal_snapshots for flip detection + TICKERS config for mapping.
    """
    try:
        from utils.score_history import get_signal_flips
        from utils.signals_cache import get_all_signal_scores

        # All signals that flipped in the window
        flips = get_signal_flips(days_back=days_back)
        current_scores = get_all_signal_scores()

        # Build: signal_id → current status
        # We want signals that are CURRENTLY bullish/bearish AND flipped recently
        recently_flipped_bull: set[str] = set()
        recently_flipped_bear: set[str] = set()
        for f in flips:
            if f["to_status"] == "bullish":
                recently_flipped_bull.add(f["signal_id"])
            elif f["to_status"] == "bearish":
                recently_flipped_bear.add(f["signal_id"])

        # Also include signals that have been bullish/bearish for a while
        # (convergence isn't just about flips — it's about current alignment)
        current_bull: set[str] = set()
        current_bear: set[str] = set()
        for sid, sv in current_scores.items():
            if sv.get("error"):
                continue
            if sv.get("status") == "bullish":
                current_bull.add(sid)
            elif sv.get("status") == "bearish":
                current_bear.add(sid)

        events: list[dict] = []

        for ticker, meta in TICKERS.items():
            relevant = set(meta.get("signals", list(SIGNALS.keys())))
            ticker_bull = relevant & current_bull
            ticker_bear = relevant & current_bear

            # For convergence: at least one of the aligned signals must have
            # flipped recently (otherwise it's just a persistent state, not an event)
            bull_fresh = ticker_bull & recently_flipped_bull
            bear_fresh = ticker_bear & recently_flipped_bear

            if len(ticker_bull) >= min_signals and bull_fresh:
                events.append({
                    "ticker":    ticker,
                    "name":      meta.get("name", ticker),
                    "direction": "bullish",
                    "count":     len(ticker_bull),
                    "fresh":     len(bull_fresh),
                    "signals":   [
                        current_scores[sid].get("name", sid)
                        for sid in sorted(ticker_bull,
                                          key=lambda s: -current_scores.get(s, {}).get("score", 50))
                        if sid in current_scores
                    ][:6],
                    "sector": meta.get("sector", "Other"),
                    "score":  round(
                        sum(current_scores.get(s, {}).get("score", 50) for s in ticker_bull) /
                        max(1, len(ticker_bull)), 1
                    ),
                })

            if len(ticker_bear) >= min_signals and bear_fresh:
                events.append({
                    "ticker":    ticker,
                    "name":      meta.get("name", ticker),
                    "direction": "bearish",
                    "count":     len(ticker_bear),
                    "fresh":     len(bear_fresh),
                    "signals":   [
                        current_scores[sid].get("name", sid)
                        for sid in sorted(ticker_bear,
                                          key=lambda s: current_scores.get(s, {}).get("score", 100))
                        if sid in current_scores
                    ][:6],
                    "sector": meta.get("sector", "Other"),
                    "score":  round(
                        sum(current_scores.get(s, {}).get("score", 50) for s in ticker_bear) /
                        max(1, len(ticker_bear)), 1
                    ),
                })

        events.sort(key=lambda e: (-e["count"], -e["fresh"]))
        return events

    except Exception:
        return []


def render_convergence_events(
    events: list[dict],
    max_bull: int = 4,
    max_bear: int = 2,
    compact: bool = False,
) -> None:
    """
    Render convergence events as styled cards using Streamlit.
    Call this from home page or Today's Brief after get_convergence_events().

    compact=True → single-line chips (for Today's Brief sidebar)
    compact=False → full cards (for home page section)
    """
    import streamlit as st

    bull_events = [e for e in events if e["direction"] == "bullish"][:max_bull]
    bear_events = [e for e in events if e["direction"] == "bearish"][:max_bear]

    if not bull_events and not bear_events:
        st.caption("No convergence events detected in the last 7 days.")
        return

    def _card(ev: dict) -> str:
        col   = "#1B5E20" if ev["direction"] == "bullish" else "#7B1010"
        bg    = "#EDF7ED" if ev["direction"] == "bullish" else "#FDF0F0"
        arrow = "▲" if ev["direction"] == "bullish" else "▼"
        sigs  = " · ".join(ev["signals"][:4])
        fresh_note = f" · {ev['fresh']} fresh flip{'s' if ev['fresh'] != 1 else ''}" if ev.get("fresh") else ""
        return (
            f'<div style="background:{bg};border-radius:7px;padding:10px 14px;'
            f'margin-bottom:8px;border-left:4px solid {col};font-family:Georgia,serif;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="font-size:0.92rem;font-weight:700;color:#1A1612;">{ev["ticker"]}</span>'
            f'<span style="font-size:0.72rem;font-weight:700;color:{col};">'
            f'{arrow} {ev["count"]} signals{fresh_note}</span>'
            f'</div>'
            f'<div style="font-size:0.74rem;color:#5A5450;margin-top:3px;">{ev["name"][:35]}</div>'
            f'<div style="font-size:0.68rem;color:#8B7355;margin-top:4px;line-height:1.4;">{sigs}</div>'
            f'</div>'
        )

    if bull_events:
        st.markdown(
            '<div style="font-size:0.70rem;font-weight:700;color:#1B5E20;'
            'letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px;">'
            '⚡ BULLISH CONVERGENCE</div>',
            unsafe_allow_html=True,
        )
        st.markdown("".join(_card(e) for e in bull_events), unsafe_allow_html=True)

    if bear_events:
        st.markdown(
            '<div style="font-size:0.70rem;font-weight:700;color:#7B1010;'
            'letter-spacing:0.08em;text-transform:uppercase;margin:8px 0 6px;">'
            '⚡ BEARISH CONVERGENCE</div>',
            unsafe_allow_html=True,
        )
        st.markdown("".join(_card(e) for e in bear_events), unsafe_allow_html=True)
