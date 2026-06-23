"""
utils/signals_cache.py — single shared signal-scoring cache.

PROBLEM SOLVED:
  Before this module, five separate pages each had their own @st.cache_data
  function that iterated over all ~40 SIGNALS and called fetch_signal_series +
  score_signal independently:
      home_page.py        _home_load_all()            ttl=7200
      1_Signal_Dashboard  load_all_signals()          ttl=3600
      2_Today_Digest      compute_all_signal_scores() ttl=7200
      12_Sector_Map       _compute_sector_scores()    ttl=7200
      6_Stock_Screener    load_all_signal_scores()    ttl=3600

  Even though fetch_signal_series has its own cache (so HTTP calls are not
  repeated within the TTL window), each page's scoring function had a DIFFERENT
  cache key, so:
    - User A opens Home           → home cache warms, scores computed once
    - User B opens Signal Dash    → SEPARATE cache key, scores computed again
    - User C opens Stock Screener → SEPARATE cache key, scores computed AGAIN

  With a single shared function, all five pages draw from the SAME cache entry.
  One set of score computations per 2-hour window, regardless of which page
  the first visitor lands on.

USAGE (all five pages now do this):
    from utils.signals_cache import get_all_signal_scores
    all_sv = get_all_signal_scores()

RETURN SHAPE per signal_id key:
    {
      "score":         float,    # 0–100
      "status":        str,      # "bullish" | "bearish" | "neutral" | "insufficient_data"
      "z_score":       float,
      "percentile":    float,
      "current":       float,
      "mean_52w":      float,
      "std_52w":       float,
      "deviation_pct": float,
      "trend_4w_pct":  float,
      "config":        dict,     # raw SIGNALS[sig_id] entry
      "data":          pd.Series,# full raw fetch (for sparklines in Signal Dashboard)
      "name":          str,
      "category":      str,
      "tier":          int,
      "pcs":           int,
      "is_synthetic":  bool,
      "error":         bool,     # True if fetch/score raised an exception
    }

The "data" key is included so Signal Dashboard can render sparklines without a
second fetch call. Other pages simply ignore it. The incremental pickle cost (~2MB
for 40 Series) is negligible vs. the saved API round-trips.
"""

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from utils.config import SIGNALS


@st.cache_data(ttl=7200, show_spinner=False, max_entries=1)
def get_all_signal_scores(_v: int = 1) -> dict:
    """
    Fetch and score every signal in the SIGNALS library.

    _v is a version sentinel — callers can pass st.session_state.get("cache_v", 1)
    to force-bust the cache (e.g. after a Refresh button click) without
    changing the function signature.

    Cached 2 hours. Signals are weekly/monthly FRED/EIA series; their values
    do not change faster than that intraday.
    """
    # Deferred imports — avoids circular import at module level since this
    # module is imported by pages at the top of their files before Streamlit
    # has fully initialized the app context.
    from utils.fetchers import fetch_signal_series, is_synthetic
    from utils.analysis import score_signal

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    results: dict = {}
    for sig_id, cfg in SIGNALS.items():
        try:
            s      = fetch_signal_series(cfg, start, end)
            scored = score_signal(s, inverse=cfg.get("inverse", False))
            results[sig_id] = {
                **scored,
                "config":       cfg,
                "data":         s,
                "name":         cfg["name"],
                "category":     cfg.get("category", "macro"),
                "tier":         cfg.get("tier", 1),
                "pcs":          cfg.get("pcs", 5),
                "is_synthetic": is_synthetic(s),
                "error":        False,
            }
        except Exception:
            results[sig_id] = {
                "score":         50.0,
                "status":        "insufficient_data",
                "z_score":       0.0,
                "percentile":    50.0,
                "current":       float("nan"),
                "mean_52w":      float("nan"),
                "std_52w":       float("nan"),
                "deviation_pct": 0.0,
                "trend_4w_pct":  0.0,
                "config":        cfg,
                "data":          pd.Series(dtype=float),
                "name":          cfg["name"],
                "category":      cfg.get("category", "macro"),
                "tier":          cfg.get("tier", 1),
                "pcs":           cfg.get("pcs", 5),
                "is_synthetic":  False,
                "error":         True,
            }
    return results
