# utils/conviction.py
# Unstructured Alpha — Conviction Context Engine
#
# get_conviction_context() answers three questions about any ticker score:
#
#   1. Signal alignment — of the signals MOST RELEVANT to this ticker's sector,
#      how many are pointing the same direction as the score?
#      E.g. "7 / 9 relevant signals bullish"
#
#   2. Historical precedent — in past instances where this ticker's score was
#      in the same range (±10 pts), what happened to the price over the next 30 days?
#      E.g. "avg +8.2% over 30d (5 of 6 instances positive)"
#
#   3. Conviction sentence — one plain-English line combining both.
#
# Performance notes:
#   - Historical price fetching is cached for 6h (score ranges don't change intraday).
#   - We fetch a single price series from yfinance covering the earliest → latest
#     relevant date window rather than one call per instance.
#   - The function is intentionally lightweight on the alignment side: it only
#     needs the pre-fetched signal_states dict (from get_all_signal_scores()) and
#     the TICKERS/SECTOR_SIGNAL_MAP config — no extra DB reads.

from __future__ import annotations

import datetime
from typing import Optional

import streamlit as st

from utils import db
from sqlalchemy import select, and_
from utils.config import TICKERS
from utils.ticker_score import SECTOR_SIGNAL_MAP, _DEFAULT_SIGNAL_IDS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _relevant_signal_ids(ticker: str) -> list[str]:
    """Return the signal IDs most relevant to this ticker's sector."""
    meta   = TICKERS.get(ticker.upper(), {})
    sector = meta.get("sector", "")
    # Prefer per-ticker signal list if it exists (it's already sector-tailored)
    if meta.get("signals"):
        return meta["signals"]
    # Fall back to sector map, then defaults
    return SECTOR_SIGNAL_MAP.get(sector, _DEFAULT_SIGNAL_IDS)


def _direction_for_score(score: float) -> str:
    """Map a score to the expected signal direction."""
    if score >= 55:
        return "bullish"
    if score <= 45:
        return "bearish"
    return "neutral"


def _confidence_level(aligned: int, total: int) -> str:
    if total == 0:
        return "Low"
    pct = aligned / total
    if pct >= 0.70:
        return "High"
    if pct >= 0.50:
        return "Medium"
    return "Low"


# ── Historical forward-return lookup ─────────────────────────────────────────

@st.cache_data(ttl=21600, show_spinner=False, max_entries=64)
def _get_historical_forward_returns(
    ticker: str,
    score_mid: float,
    days_forward: int = 30,
) -> dict:
    """
    Find past snapshots where ticker's score was within ±10 of score_mid,
    at least 35 days ago (so the forward window has closed). Fetch a single
    yfinance price series covering all relevant dates, then compute forward
    returns for each instance.

    Returns:
        {
            "n":          int,    # number of usable historical instances
            "avg_return": float,  # average 30d forward return, pct
            "win_rate":   float,  # fraction of instances where return > 0
            "instances":  list[dict],  # [{date, score, return}]
        }
    """
    empty = {"n": 0, "avg_return": 0.0, "win_rate": 0.0, "instances": []}

    low  = score_mid - 10
    high = score_mid + 10
    today       = datetime.date.today()
    cutoff_date = (today - datetime.timedelta(days=35)).strftime("%Y-%m-%d")

    # Pull all matching historical snapshots
    try:
        from utils.db import score_snapshots
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(score_snapshots.c.snapshot_date, score_snapshots.c.score)
                .where(and_(
                    score_snapshots.c.ticker == ticker.upper(),
                    score_snapshots.c.snapshot_date <= cutoff_date,
                    score_snapshots.c.score  >= low,
                    score_snapshots.c.score  <= high,
                ))
                .order_by(score_snapshots.c.snapshot_date.asc())
                .limit(20)
            ).mappings().all()
    except Exception:
        return empty

    if not rows:
        return empty

    # Determine the price-fetch window
    dates = [r["snapshot_date"] for r in rows]
    start_dt  = datetime.datetime.strptime(dates[0],  "%Y-%m-%d").date()
    end_dt    = datetime.datetime.strptime(dates[-1], "%Y-%m-%d").date() + datetime.timedelta(days=days_forward + 5)
    if end_dt > today:
        end_dt = today

    # Single yfinance call covering the whole window
    try:
        import yfinance as yf
        px_df = yf.download(
            ticker.upper(),
            start=str(start_dt),
            end=str(end_dt + datetime.timedelta(days=1)),
            progress=False,
            auto_adjust=True,
        )
        if px_df.empty:
            return empty
        # Build date → close price dict
        px_map = {}
        for idx, row in px_df.iterrows():
            d = idx.date() if hasattr(idx, "date") else idx
            try:
                close = float(row["Close"])
            except Exception:
                continue
            px_map[str(d)] = close
    except Exception:
        return empty

    # For each snapshot, find entry price and forward price
    def _nearest_price(date_str: str, px_map: dict, offset_days: int = 0) -> Optional[float]:
        """Return price on or after date + offset, up to 5 trading-day buffer."""
        base = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        for delta in range(offset_days, offset_days + 6):
            d = str(base + datetime.timedelta(days=delta))
            if d in px_map:
                return px_map[d]
        return None

    instances = []
    for r in rows:
        entry_px   = _nearest_price(r["snapshot_date"], px_map, offset_days=0)
        forward_px = _nearest_price(r["snapshot_date"], px_map, offset_days=days_forward)
        if entry_px and forward_px and entry_px > 0:
            fwd_return = (forward_px - entry_px) / entry_px * 100
            instances.append({
                "date":   r["snapshot_date"],
                "score":  r["score"],
                "return": round(fwd_return, 1),
            })

    if not instances:
        return empty

    returns   = [i["return"] for i in instances]
    avg_ret   = sum(returns) / len(returns)
    wins      = sum(1 for r in returns if r > 0)
    return {
        "n":          len(instances),
        "avg_return": round(avg_ret, 1),
        "win_rate":   round(wins / len(instances), 2),
        "instances":  instances,
    }


# ── Fast alignment-only helper (no yfinance, safe for bulk use) ───────────────

def get_signal_alignment(ticker: str, score: float, signal_states: dict) -> tuple[int, int]:
    """
    Return (aligned, total) — signals pointing same direction as score.
    Cheap: no DB reads, no network calls. Safe to call for every rec card.
    """
    direction = _direction_for_score(score)
    rel_ids   = _relevant_signal_ids(ticker)
    aligned = 0
    total   = 0
    for sig_id in rel_ids:
        state = signal_states.get(sig_id, {})
        if not state or state.get("error"):
            continue
        total += 1
        if state.get("status") == direction:
            aligned += 1
    return aligned, total


# ── Public API ────────────────────────────────────────────────────────────────

def get_conviction_context(
    ticker: str,
    score: float,
    signal_states: dict,
    days_forward: int = 30,
) -> dict:
    """
    Return conviction context for a ticker + current score.

    Args:
        ticker:        Uppercase ticker symbol, e.g. "NVDA"
        score:         Confluence score (0–100)
        signal_states: Dict from get_all_signal_scores():
                       { signal_id: { "status": "bullish"|"bearish"|"neutral", ... } }
        days_forward:  Forward return window in days (default 30)

    Returns:
        {
            "aligned":         int,   # signals pointing same direction as score
            "total_relevant":  int,   # total relevant signals with data
            "direction":       str,   # "bullish" | "bearish" | "neutral"
            "confidence":      str,   # "High" | "Medium" | "Low"
            "hist_n":          int,   # historical instances found
            "hist_avg_return": float, # avg forward return %
            "hist_win_rate":   float, # win rate (0–1)
            "sentence":        str,   # plain-English conviction line
        }
    """
    ticker    = ticker.upper().strip()
    direction = _direction_for_score(score)
    rel_ids   = _relevant_signal_ids(ticker)

    # Count alignment
    aligned = 0
    total   = 0
    for sig_id in rel_ids:
        state = signal_states.get(sig_id, {})
        if not state or state.get("error"):
            continue
        total += 1
        if state.get("status") == direction:
            aligned += 1

    confidence = _confidence_level(aligned, total)

    # Historical forward returns (cached)
    hist = _get_historical_forward_returns(ticker, round(score, -1), days_forward)

    # Build sentence
    direction_word = direction.capitalize()

    if total > 0:
        alignment_clause = f"{aligned}/{total} relevant signals {direction}"
    else:
        alignment_clause = "signal alignment unavailable"

    if hist["n"] >= 3:
        sign     = "+" if hist["avg_return"] >= 0 else ""
        win_pct  = round(hist["win_rate"] * 100)
        hist_clause = (
            f"historically preceded {sign}{hist['avg_return']}% over {days_forward}d "
            f"({hist['n']} instances, {win_pct}% positive)"
        )
    elif hist["n"] >= 1:
        sign = "+" if hist["avg_return"] >= 0 else ""
        hist_clause = (
            f"small sample: {sign}{hist['avg_return']}% avg over {days_forward}d "
            f"({hist['n']} instance{'s' if hist['n'] > 1 else ''})"
        )
    else:
        hist_clause = "no prior score history in this range yet"

    sentence = f"{alignment_clause.capitalize()} — {hist_clause}."

    return {
        "aligned":         aligned,
        "total_relevant":  total,
        "direction":       direction,
        "confidence":      confidence,
        "hist_n":          hist["n"],
        "hist_avg_return": hist["avg_return"],
        "hist_win_rate":   hist["win_rate"],
        "sentence":        sentence,
    }
