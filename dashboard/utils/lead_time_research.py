# utils/lead_time_research.py
# Unstructured Alpha — Lead-Time Research for Alt-Data Signals
#
# WHY THIS MODULE EXISTS, SEPARATELY FROM utils/analysis.py's EXISTING
# LAG-SCAN: the Ticker Deep Dive page already has a "Deep Correlation Scan
# — Lead Time Optimizer" (compute_correlation()) that tests lags 0-16 weeks
# against the macro/FRED-style signals and reports whichever lag produces
# the strongest correlation. That tool has never been applied to the
# alt-data differentiator signals (insider activity, short interest) at
# all -- this module extends the SAME underlying methodology to those,
# while fixing two real statistical problems that the existing tool does
# not address:
#
#   1. MULTIPLE COMPARISONS: scanning 17 lags and reporting whichever one
#      looks best is a textbook way to manufacture a false positive --
#      with 17 independent tests at p<0.05, you'd expect roughly one to
#      look "significant" purely by chance even if there's no real
#      relationship at all. This module requires the best lag to survive a
#      Bonferroni-corrected threshold (alpha / number of lags tested)
#      before treating it as a real finding.
#
#   2. OVERFITTING: a lag that looks great on the data it was discovered in
#      tells you nothing about whether it generalizes. This module always
#      splits the history chronologically -- finds the best lag using only
#      the earlier ~70% of history, then tests that SAME lag (not a
#      re-optimized one) against the held-out, more recent ~30% it has
#      never seen. A relationship that doesn't hold up out-of-sample is
#      reported as such, not quietly dropped.
#
# A third problem -- a relationship that only shows up for one specific
# ticker is much more likely a coincidence of that ticker's own history
# than a real, generalizable lead-time effect -- is addressed by
# pooled_lag_scan_across_sector(), which runs the same validated scan
# across a ticker's sector peers (via utils.config.TICKERS) and pools the
# results the same way compute_backtested_pcs() already pools macro-signal
# backtests across multiple tickers.
#
# compute_signal_reliability_score() combines all of the above into a
# single 0-100 number -- but, deliberately, NOT as another opaque score:
# it always returns its component breakdown alongside the number, so a
# user (or this app's own UI) can see exactly why a given lead-time finding
# scored the way it did. The entire point of this feature is to be more
# transparent than a black-box composite score, not to build a fancier one.

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

from utils.analysis import align_series
from utils.config import TICKERS


# ─────────────────────────────────────────────────────────────────────────────
# EVENT DATA → WEEKLY SERIES ADAPTERS
# ─────────────────────────────────────────────────────────────────────────────
#
# Insider transactions and FINRA short-interest reports arrive on irregular,
# sparse dates (one transaction date, one bi-monthly settlement date) --
# not the regular weekly cadence align_series()/compute_correlation() were
# built around for FRED-style signals. These adapters collapse each into a
# clean, date-indexed Series; align_series()'s own .resample("W") call
# handles the actual weekly binning, so these deliberately do NOT
# pre-aggregate to week themselves -- duplicate same-week dates are left
# for align_series to bin, exactly as it already does for any other
# irregularly-sampled input.

def build_insider_intensity_series(tx_df: pd.DataFrame) -> pd.Series:
    """
    Net insider-buying intensity per transaction date: (count of P
    transactions) − (count of S transactions) on that date. Deliberately
    COUNT-based, not dollar-value-based -- consistent with
    score_insider_activity()'s own documented reasoning (Lakonishok & Lee
    2001; Seyhun): clustering of independent buyers is the more
    predictive pattern, and dollar value can't be fairly compared across
    market caps without data this product doesn't reliably have.
    """
    if tx_df.empty or "date" not in tx_df.columns or "code" not in tx_df.columns:
        return pd.Series(dtype=float)

    df = tx_df.dropna(subset=["date"]).copy()
    df["sign"] = df["code"].map({"P": 1, "S": -1}).fillna(0)
    daily = df.groupby("date")["sign"].sum()
    return daily.sort_index()


def build_short_interest_change_series(si_df: pd.DataFrame) -> pd.Series:
    """
    FINRA's own period-over-period change_pct, indexed by settlement date.
    Already a rate-of-change measure (not a level), so no further
    transformation is needed before handing it to align_series().
    """
    if si_df.empty or "date" not in si_df.columns or "change_pct" not in si_df.columns:
        return pd.Series(dtype=float)

    s = si_df.dropna(subset=["date", "change_pct"]).set_index("date")["change_pct"]
    return s.sort_index()


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATED LAG-SCAN (multiple-comparisons correction + out-of-sample test)
# ─────────────────────────────────────────────────────────────────────────────

def lag_scan_with_validation(
    signal: pd.Series,
    price: pd.Series,
    scan_max_lag: int = 16,
    oos_fraction: float = 0.3,
    alpha: float = 0.05,
    min_fold_n: int = 8,
) -> dict:
    """
    Find the best lead-time lag for `signal` vs `price`, using ONLY the
    earlier (1 - oos_fraction) share of overlapping history, then test that
    exact lag against the held-out, more recent oos_fraction share it never
    saw during lag selection. The in-sample "best lag" is also required to
    survive a Bonferroni correction (alpha / number of lags actually
    tested) before being treated as a real finding -- without this, the
    best of 17 noisy comparisons looks "significant" far more often than
    alpha would suggest.

    The split point is anchored to a single calendar date (derived from the
    lag=0 alignment), not a fixed row count per lag -- so every lag's
    in-sample/out-of-sample split refers to the same actual point in time,
    which is what "out-of-sample" is supposed to mean.

    Returns a dict with "error" set (and nothing else meaningful) if there
    isn't enough overlapping data to do this honestly. On success, returns:
        n                    : total overlapping weekly observations
        split_date           : the date separating in-sample from out-of-sample
        in_sample_scan        : {lag: {"r", "p", "n"}} for every lag testable in-sample
        best_lag              : the lag with the largest |r| IN-SAMPLE ONLY
        in_sample_r/p          : that lag's in-sample correlation and p-value
        n_comparisons          : how many lags were actually tested (for the correction)
        corrected_alpha        : alpha / n_comparisons
        survives_correction    : bool -- in_sample_p < corrected_alpha
        out_of_sample          : {"r","p","n","significant","same_sign_as_in_sample"} or None
        holds_out_of_sample    : bool -- the real bar for "this looks like a genuine finding"
    """
    base = align_series(signal, price, 0)
    if len(base) < 16:
        return {"error": f"Insufficient overlapping data ({len(base)} weeks)", "n": len(base)}

    split_pos = int(len(base) * (1 - oos_fraction))
    split_pos = max(min_fold_n, min(split_pos, len(base) - min_fold_n))
    if split_pos < min_fold_n or (len(base) - split_pos) < min_fold_n:
        return {
            "error": f"Not enough history to hold out a validation period "
                     f"(need >={2 * min_fold_n} weeks, have {len(base)})",
            "n": len(base),
        }
    split_date = base.index[split_pos]

    in_sample_scan: Dict[int, dict] = {}
    for lag in range(0, scan_max_lag + 1):
        al = align_series(signal, price, lag)
        al_is = al[al.index < split_date]
        if len(al_is) < min_fold_n:
            continue
        sr = al_is["signal"].pct_change().dropna()
        pr = al_is["price"].pct_change().dropna()
        cb = pd.DataFrame({"s": sr, "p": pr}).dropna()
        if len(cb) < min_fold_n:
            continue
        r, p = stats.pearsonr(cb["s"], cb["p"])
        in_sample_scan[lag] = {"r": round(float(r), 4), "p": round(float(p), 6), "n": len(cb)}

    if not in_sample_scan:
        return {"error": "Insufficient in-sample data across all candidate lags", "n": len(base)}

    n_comparisons = len(in_sample_scan)
    corrected_alpha = alpha / n_comparisons

    best_lag = max(in_sample_scan, key=lambda k: abs(in_sample_scan[k]["r"]))
    best = in_sample_scan[best_lag]
    survives_correction = bool(best["p"] < corrected_alpha)

    al_best = align_series(signal, price, best_lag)
    al_oos = al_best[al_best.index >= split_date]
    out_of_sample = None
    if len(al_oos) >= min_fold_n:
        sr = al_oos["signal"].pct_change().dropna()
        pr = al_oos["price"].pct_change().dropna()
        cb = pd.DataFrame({"s": sr, "p": pr}).dropna()
        if len(cb) >= max(6, min_fold_n - 2):
            r_oos, p_oos = stats.pearsonr(cb["s"], cb["p"])
            out_of_sample = {
                "r": round(float(r_oos), 4),
                "p": round(float(p_oos), 6),
                "n": len(cb),
                "significant": bool(p_oos < alpha),
                "same_sign_as_in_sample": bool(
                    r_oos != 0 and best["r"] != 0 and np.sign(r_oos) == np.sign(best["r"])
                ),
            }

    holds_out_of_sample = bool(
        out_of_sample is not None
        and out_of_sample["significant"]
        and out_of_sample["same_sign_as_in_sample"]
    )

    return {
        "error": None,
        "n": len(base),
        "split_date": split_date,
        "in_sample_scan": in_sample_scan,
        "best_lag": best_lag,
        "in_sample_r": best["r"],
        "in_sample_p": best["p"],
        "n_comparisons": n_comparisons,
        "corrected_alpha": round(corrected_alpha, 5),
        "survives_correction": survives_correction,
        "out_of_sample": out_of_sample,
        "holds_out_of_sample": holds_out_of_sample,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-TICKER POOLING
# ─────────────────────────────────────────────────────────────────────────────

def get_sector_peers(ticker: str, max_peers: int = 6) -> List[str]:
    """
    Sector peers for `ticker` via utils.config.TICKERS, excluding ETFs
    (an ETF's "sector" is the literal string "ETF", which groups dozens of
    unrelated index funds together -- not a meaningful peer set for this
    purpose) and excluding the ticker itself.
    """
    info = TICKERS.get(ticker)
    if not info:
        return []
    sector = info.get("sector")
    if not sector or sector == "ETF":
        return []
    peers = [t for t, v in TICKERS.items() if v.get("sector") == sector and t != ticker]
    return peers[:max_peers]


def pooled_lag_scan_across_sector(
    signal_per_ticker: Dict[str, pd.Series],
    price_per_ticker: Dict[str, pd.Series],
    scan_max_lag: int = 16,
) -> dict:
    """
    Run lag_scan_with_validation() for every ticker that has both a signal
    series and a price series available, and pool the results the same way
    compute_backtested_pcs() already pools macro-signal backtests: a
    significance_rate (fraction of tested tickers where the lag holds up
    out-of-sample) and avg_abs_r. A relationship that only shows up for one
    name is much more likely a coincidence of that name's specific history
    than a real, generalizable lead-time effect -- this is the check for
    that, not a replacement for the single-ticker result.
    """
    results = []
    for tkr, sig in signal_per_ticker.items():
        price = price_per_ticker.get(tkr)
        if sig is None or sig.empty or price is None or price.empty:
            continue
        v = lag_scan_with_validation(sig, price, scan_max_lag=scan_max_lag)
        if not v.get("error"):
            v = dict(v)
            v["ticker"] = tkr
            results.append(v)

    if not results:
        return {"n_tickers": 0, "significance_rate": 0.0, "avg_abs_r": 0.0, "details": []}

    sig_rate = sum(1 for r in results if r["holds_out_of_sample"]) / len(results)
    avg_abs_r = sum(abs(r["in_sample_r"]) for r in results) / len(results)
    return {
        "n_tickers": len(results),
        "significance_rate": round(sig_rate, 2),
        "avg_abs_r": round(avg_abs_r, 3),
        "details": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL RELIABILITY SCORE — a transparent meta-score, not another black box
# ─────────────────────────────────────────────────────────────────────────────

def compute_signal_reliability_score(validation: dict, pooled: Optional[dict] = None) -> dict:
    """
    Combine corrected significance, out-of-sample hold-up, sample size, and
    (if available) cross-ticker pooled confirmation into a single 0-100
    "how much should you trust this lead-time finding" score.

    Deliberately returns the component breakdown alongside the score, every
    time -- the whole point of this feature is to be more transparent than
    a competitor's black-box composite (e.g. TipRanks' Smart Score, which
    discloses none of its weighting or validation), so the meta-score
    itself must not become an opaque number either.
    """
    if validation.get("error"):
        return {"score": 0, "label": "Insufficient data to assess", "components": {}}

    components: Dict[str, float] = {}

    # Survives the multiple-comparisons correction -- without this, "best
    # lag" is likely just the best of N noisy guesses, not a real finding.
    components["corrected_significance"] = 35.0 if validation["survives_correction"] else 0.0

    # Holds up on data it was never fit to -- the strongest single defense
    # against overfitting a lag that only worked by chance, historically.
    components["out_of_sample_validation"] = 35.0 if validation["holds_out_of_sample"] else 0.0

    # Sample size adequacy: a significant r on 10 weekly observations
    # deserves much less trust than the same r on 150. Full credit at
    # roughly 2 years of weekly data (104 weeks).
    n = validation.get("n", 0)
    components["sample_size"] = round(min(15.0, 15.0 * n / 104.0), 1)

    # Cross-ticker pooled confirmation, if a sector peer scan was run.
    if pooled and pooled.get("n_tickers", 0) > 1:
        components["pooled_confirmation"] = round(15.0 * pooled.get("significance_rate", 0.0), 1)
    else:
        components["pooled_confirmation"] = 0.0

    score = int(round(sum(components.values())))
    score = max(0, min(100, score))

    if score >= 70:
        label = "Reasonably well-supported"
    elif score >= 40:
        label = "Suggestive, not yet well-supported"
    else:
        label = "Weak — likely noise"

    return {"score": score, "label": label, "components": components}
