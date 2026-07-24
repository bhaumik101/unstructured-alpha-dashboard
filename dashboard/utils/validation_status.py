# utils/validation_status.py
# Unstructured Alpha — Consolidated Model Validation Status
#
# WHY THIS MODULE EXISTS: every score this product computes (macro signals,
# insider activity, short interest, 13F, the Confluence/Supercycle
# composites) has gone through a DIFFERENT amount and kind of real
# validation -- some backtested with real significance numbers, some
# explicitly NOT validated and documented as such, some validated only
# per-ticker on demand rather than as a single global number. This module
# is the single, honest source of truth for "how validated is X, exactly,"
# pulling from the actual scoring/backtest functions rather than
# restating anything from memory -- every claim below traces back to a
# real function call or a docstring that was re-read at the time this was
# written, not approximated.
#
# backtest_all_macro_signals() was moved here from pages/8_About.py
# (previously a page-local function) so the new Model Validation
# Dashboard (pages/11_Model_Validation.py) and the About page's signal
# library both call the exact same implementation -- duplicating this
# logic across two pages would risk them silently drifting out of sync
# with each other, which is exactly the kind of inconsistency a
# "validation" feature cannot afford to have.

from datetime import datetime, timedelta
from typing import Dict

import pandas as pd
import streamlit as st

from utils.config import SIGNALS
from utils.fetchers import fetch_signal_series, fetch_price
from utils.analysis import compute_backtested_pcs
from utils.lead_time_research import (
    lag_scan_with_validation, pooled_lag_scan_across_sector, compute_signal_reliability_score,
)


@st.cache_data(ttl=86400, show_spinner=False)
def backtest_all_macro_signals(_v: int = 2) -> Dict[str, dict]:
    """
    Backtest every macro/FRED-style signal's PCS against up to 5 of its
    relevant tickers (not just the first one) so a signal that only
    correlates with one ticker doesn't get an inflated, falsely-broad PCS.
    Cached for 24h since this is a real-data validation pass over ~38
    signals x up to 5 tickers each, not a cheap live score.

    Returns {signal_id: compute_backtested_pcs() result}. Each result has
    "backtested": False (with pcs=None) when there wasn't enough
    overlapping data to test at all -- callers must treat that as "not
    validated," never silently substitute a default.
    """
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    out = {}
    for sig_id, cfg in SIGNALS.items():
        try:
            # Point-in-time: backtest on first-print data (see get_all_signal
            # _validation below) so revised-in-hindsight FRED values can't inflate
            # a signal's historical PCS.
            sig_series = fetch_signal_series(cfg, start, end, point_in_time=True)
            test_tickers = (cfg.get("relevant_tickers") or [])[:5]
            price_series_list = [fetch_price(t, start, end) for t in test_tickers]
            out[sig_id] = compute_backtested_pcs(
                sig_series, price_series_list,
                lag_weeks=cfg.get("lag_weeks", 0), tickers=test_tickers,
            )
        except Exception:
            out[sig_id] = {"pcs": None, "backtested": False, "n_tested": 0,
                            "significance_rate": 0.0, "avg_abs_r": 0.0, "details": []}
    return out


@st.cache_data(ttl=86400, show_spinner=False)
def validate_all_macro_signals(_v: int = 1) -> Dict[str, dict]:
    """
    The universal lag-validation rollout (2026-06-22): every macro/FRED-
    style signal now gets the SAME rigorous treatment that was previously
    only built for insider activity and short interest --
    lag_scan_with_validation()'s out-of-sample split + Bonferroni
    correction, pooled_lag_scan_across_sector()'s cross-ticker
    confirmation, and compute_signal_reliability_score()'s transparent
    0-100 score with full component breakdown. This is a NEW, more
    rigorous validation pass alongside (not a replacement for)
    backtest_all_macro_signals() above -- that simpler same-sample
    significance test still backs the "Static PCS" backtest column on the
    About page, and nothing about live confluence-score weighting
    (utils/ticker_score.py) changes here. This function exists
    specifically for the Model Validation Dashboard's headline claim:
    every signal, validated the same rigorous way, no exceptions.

    Design: for each signal, the FIRST relevant ticker is the "primary"
    validation (mirrors how a ticker's own Deep Dive page treats insider/
    short-interest -- current ticker = primary), and up to 4 more relevant
    tickers form the pooled cross-ticker confirmation set -- mirroring
    sector-peer pooling exactly, just using the signal's own hand-curated
    relevant_tickers instead of utils.config.TICKERS sector groupings
    (more appropriate here: a signal's relevant_tickers were chosen
    specifically because the signal is thought to apply to them).

    Returns {signal_id: {"validation": ..., "pooled": ..., "reliability": ...}}.
    Every signal gets an entry, even with zero testable tickers or a fetch
    failure -- never silently omitted, so a caller's "N of M validated"
    count is never quietly wrong.
    """
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    out: Dict[str, dict] = {}
    for sig_id, cfg in SIGNALS.items():
        test_tickers = (cfg.get("relevant_tickers") or [])[:5]
        if not test_tickers:
            out[sig_id] = {
                "validation": {"error": "No relevant tickers configured for this signal", "n": 0},
                "pooled": None,
                "reliability": {"score": 0, "label": "Insufficient data to assess", "components": {}},
            }
            continue

        try:
            # POINT-IN-TIME: validation must only ever see data as it was known
            # at the time. For FRED signals this returns first-print (initial
            # release) values instead of today's revised numbers, removing
            # look-ahead/revision bias from the backtest inputs. Live scoring
            # elsewhere keeps latest-revised (the current reading IS the latest).
            sig_series = fetch_signal_series(cfg, start, end, point_in_time=True)
        except Exception:
            sig_series = pd.Series(dtype=float)

        primary_ticker, pool_tickers = test_tickers[0], test_tickers[1:]

        try:
            primary_price = fetch_price(primary_ticker, start, end)
        except Exception:
            primary_price = pd.Series(dtype=float)

        if sig_series.empty or primary_price.empty:
            validation = {"error": "Insufficient overlapping data for the primary ticker", "n": 0}
        else:
            validation = lag_scan_with_validation(sig_series, primary_price, scan_max_lag=16)

        pooled = None
        if pool_tickers and not validation.get("error"):
            signal_per_ticker = {t: sig_series for t in pool_tickers}
            price_per_ticker = {}
            for t in pool_tickers:
                try:
                    price_per_ticker[t] = fetch_price(t, start, end)
                except Exception:
                    price_per_ticker[t] = pd.Series(dtype=float)
            pooled = pooled_lag_scan_across_sector(signal_per_ticker, price_per_ticker, scan_max_lag=16)

        reliability = compute_signal_reliability_score(validation, pooled)
        out[sig_id] = {"validation": validation, "pooled": pooled, "reliability": reliability}

    return out


def get_static_validation_summary() -> list:
    """
    Validation status for every score category that ISN'T a per-signal
    macro backtest (those come from backtest_all_macro_signals() instead,
    computed live/cached, not hand-written here). These five entries are
    deliberately NOT computed live -- they're either a one-time documented
    finding (Confluence/Supercycle's walk-forward backtest, already
    disclosed in utils/analysis.py's docstrings) or a structural fact about
    what methodology applies and why (insider/short-interest's per-ticker,
    on-demand validated scan; 13F's deliberate exclusion).

    Every number quoted here was copied verbatim from the actual source
    docstring it describes (utils/analysis.py's compute_confluence() and
    compute_supercycle_score(), utils/lead_time_research.py's module
    docstring) at the time this was written -- not approximated or
    recalled from memory. If those backtests are ever re-run with
    different results, this summary needs updating to match, not the
    other way around.
    """
    return [
        {
            "category": "Confluence Score (per-ticker macro composite)",
            "status": "Backtested — NOT validated",
            "detail": (
                "Walk-forward backtest found no statistically significant relationship between the "
                "score and forward returns, pooled across 6 tickers. High conviction means the "
                "signals agree with each other right now — it does not yet mean they're right."
            ),
            "source": "utils/analysis.py — compute_confluence() docstring",
        },
        {
            "category": "Power Supercycle Score",
            "status": "Backtested — NOT validated",
            "detail": (
                "Walk-forward backtest (6 tickers spanning the thesis — CEG, VST, NEE, ETN, VRT, PWR — "
                "~19 monthly checkpoints, pooled) found no statistically significant relationship with "
                "1/2/3-month forward returns in either direction (all |r| < 0.07, p > 0.5 pooled). Two "
                "of the six tickers showed a significant NEGATIVE relationship in isolation before "
                "pooling, driven by the two most narrative-extended names, where a high reading "
                "coincided with a cyclical top rather than leading one."
            ),
            "source": "utils/analysis.py — compute_supercycle_score() docstring",
        },
        {
            "category": "Insider Activity (Form 4 open-market buys/sells)",
            "status": "Validated methodology available — per-ticker, on demand",
            "detail": (
                "Has a real out-of-sample-tested, multiple-comparisons-corrected lead-time scan "
                "(Bonferroni correction across lags tested; best lag fit on the earlier ~70% of "
                "history, then re-tested on the held-out, more recent ~30% it never saw). This is NOT "
                "a single global number — run it for a specific ticker on that ticker's Deep Dive page "
                "(\"Run validated lead-time scan\"), since whether this signal leads price, and by how "
                "long, can genuinely differ by ticker and sector."
            ),
            "source": "utils/lead_time_research.py — lag_scan_with_validation()",
        },
        {
            "category": "Short Interest (FINRA consolidated)",
            "status": "Validated methodology available — per-ticker, on demand",
            "detail": (
                "Same validated lead-time methodology as Insider Activity above, run on demand per "
                "ticker. Sample size is the real constraint here: FINRA's API caps results at 50 rows "
                "and reports bi-monthly, so even 2 years of history is roughly 48 data points before "
                "weekly resampling — the Signal Reliability Score's sample-size component reflects "
                "this directly rather than hiding it."
            ),
            "source": "utils/lead_time_research.py — lag_scan_with_validation()",
        },
        {
            "category": "13F Institutional Positioning",
            "status": "Deliberately NOT lag-scanned",
            "detail": (
                "13F filings are quarterly — a few years of history is only 8-12 data points, not "
                "enough to honestly fit and validate a lead-time lag. Rather than fit a curve to "
                "8 points and call it a finding, this signal is excluded from the validated lead-time "
                "scan entirely. The audit trail (source filing links) is still available on each "
                "ticker's Deep Dive page."
            ),
            "source": "utils/lead_time_research.py — module docstring",
        },
    ]
