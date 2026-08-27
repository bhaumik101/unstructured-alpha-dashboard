# utils/analysis.py
# Unstructured Alpha — Analysis Engine
#
# Correlation engine  : lag-adjusted Pearson r, rolling correlation, lag optimizer
# Signal scoring       : z-score vs. 52-week baseline → bull/bear/neutral status
# COT scoring          : commercial vs. speculator positioning extremes
# Confluence scoring   : weighted multi-signal bull/bear case generator
# Power Supercycle     : thematic convergence scoring

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# SERIES ALIGNMENT
# ─────────────────────────────────────────────────────────────────────────────

def _strip_tz(s: pd.Series) -> pd.Series:
    if hasattr(s.index, "tz") and s.index.tz is not None:
        s = s.copy()
        s.index = s.index.tz_localize(None)
    return s


def align_series(
    signal: pd.Series,
    price: pd.Series,
    lag_weeks: int = 0,
    freq: str = "W",
) -> pd.DataFrame:
    """
    Resample both series to weekly, shift signal forward by lag_weeks,
    then align on common dates.

    lag_weeks = 4 means the signal is shifted 4 weeks into the future
    (i.e., the signal from 4 weeks ago is compared to today's price),
    which tests whether the signal leads the price.
    """
    sig_w = _strip_tz(signal).resample(freq).mean().dropna()
    prc_w = _strip_tz(price).resample(freq).last().dropna()

    if lag_weeks > 0:
        sig_w = sig_w.shift(lag_weeks)

    aligned = pd.DataFrame({"signal": sig_w, "price": prc_w}).dropna()
    return aligned


# ─────────────────────────────────────────────────────────────────────────────
# CORRELATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def compute_correlation(
    signal: pd.Series,
    price: pd.Series,
    lag_weeks: int = 0,
    scan_max_lag: int = 16,
) -> dict:
    """
    Full correlation analysis between a signal and a price series.

    Returns:
        pearson_r       : correlation coefficient at the specified lag
        r_squared       : R² at the specified lag
        p_value         : two-tailed p-value
        significant     : True if p < 0.05
        n               : number of overlapping weekly observations
        aligned         : DataFrame of raw signal + price (weekly)
        aligned_returns : DataFrame of week-over-week returns (used for correlation)
        rolling_corr    : 26-week rolling correlation Series
        lag_scan        : Dict[lag → r] for lags 0..scan_max_lag
        best_lag        : lag (in weeks) that maximises |r|
        best_r          : r at best_lag
    """
    aligned = align_series(signal, price, lag_weeks)

    if len(aligned) < 12:
        return {
            "error": f"Insufficient overlapping data ({len(aligned)} weeks)",
            "n": len(aligned),
            "lag_scan": {},
            "aligned": aligned,
        }

    sig_ret = aligned["signal"].pct_change().dropna()
    prc_ret = aligned["price"].pct_change().dropna()
    combined = pd.DataFrame({"s": sig_ret, "p": prc_ret}).dropna()

    if len(combined) < 8:
        return {"error": "Insufficient return data", "n": len(combined), "lag_scan": {}}

    r, p_val = stats.pearsonr(combined["s"], combined["p"])

    # Rolling 26-week correlation
    rolling_corr = combined["s"].rolling(26).corr(combined["p"])

    # Lag scan — find optimal prediction window
    lag_scan: Dict[int, float] = {}
    for test_lag in range(0, scan_max_lag + 1):
        al = align_series(signal, price, test_lag)
        if len(al) < 12:
            continue
        sr = al["signal"].pct_change().dropna()
        pr = al["price"].pct_change().dropna()
        cb = pd.DataFrame({"s": sr, "p": pr}).dropna()
        if len(cb) >= 8:
            rc, _ = stats.pearsonr(cb["s"], cb["p"])
            lag_scan[test_lag] = round(rc, 4)

    best_lag = max(lag_scan, key=lambda k: abs(lag_scan[k])) if lag_scan else lag_weeks
    best_r   = lag_scan.get(best_lag, r)

    return {
        "pearson_r":      round(float(r), 4),
        "r_squared":      round(float(r ** 2), 4),
        "p_value":        round(float(p_val), 6),
        "significant":    bool(p_val < 0.05),
        "n":              len(combined),
        "aligned":        aligned,
        "aligned_returns": combined,
        "rolling_corr":   rolling_corr,
        "lag_scan":       lag_scan,
        "best_lag":       best_lag,
        "best_r":         round(float(best_r), 4),
        "current_lag":    lag_weeks,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FAST SINGLE-LAG CORRELATION (per-ticker weighting)
# ─────────────────────────────────────────────────────────────────────────────

def compute_quick_correlation(
    signal: pd.Series,
    price: pd.Series,
    lag_weeks: int = 0,
) -> float:
    """
    Fast Pearson r at a single specified lag — no lag scanning.
    Used for real-time per-ticker correlation weighting on the Ticker Deep Dive.

    Returns a value in [-1, 1]. Returns 0.0 on failure / insufficient data.
    Positive r = signal moves in same direction as price.
    Negative r with inverse=True means the signal is still predictive (bearish signal).
    """
    try:
        aligned = align_series(signal, price, lag_weeks)
        if len(aligned) < 12:
            return 0.0
        sr = aligned["signal"].pct_change().dropna()
        pr = aligned["price"].pct_change().dropna()
        cb = pd.DataFrame({"s": sr, "p": pr}).dropna()
        if len(cb) < 8:
            return 0.0
        r, p = stats.pearsonr(cb["s"], cb["p"])
        # Only count statistically meaningful correlations (p < 0.20)
        # otherwise treat as noise and return a weak weight
        if p >= 0.20:
            return float(round(r * 0.5, 4))  # dampen insignificant correlations
        return float(round(r, 4))
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# EVIDENCE CORRECTIONS
#
# Two statistical problems in how correlation was turned into a weight, both
# fixed here rather than at the call site so every consumer inherits them.
#
# 1. MULTIPLE COMPARISONS. Each ticker is tested against ~47 signals at an
#    uncorrected alpha of 0.05. On pure noise that returns roughly two
#    "significant" signals per ticker by construction. Bonferroni across 47 is
#    valid but brutally conservative; Benjamini-Hochberg controls the expected
#    proportion of false discoveries instead, which is the right error rate when
#    the question is "which of these signals are worth weighting" rather than
#    "is this one signal real".
#
# 2. SAMPLE SIZE WAS INVISIBLE. |r| entered the weight raw, so r = 0.30 measured
#    over 8 observations counted exactly as much as r = 0.30 over 100. At n = 8
#    a correlation must exceed about 0.71 to be distinguishable from zero; at
#    n = 100, about 0.20. Weighting by the LOWER CONFIDENCE BOUND on |r| folds
#    effect size, sample size and significance into one number: a correlation
#    that cannot be told apart from noise shrinks to zero on its own, with no
#    threshold to tune.
# ─────────────────────────────────────────────────────────────────────────────

# Two-sided normal critical value for a 95% interval.
_Z_CRIT_95 = 1.959963984540054

# A signal whose correlation with this ticker is unmeasurable still carries its
# own reading, so it keeps a floor share rather than dropping out entirely.
# Named so it is a decision rather than a literal buried in an expression.
WEIGHT_FLOOR = 0.15


def benjamini_hochberg(p_values, alpha: float = 0.05):
    """Benjamini-Hochberg FDR correction over one family of tests.

    Returns (rejected, q_values), both parallel to the input.

    `rejected[i]` is True when hypothesis i is rejected controlling the false
    discovery rate at `alpha`. `q_values[i]` is the smallest FDR at which that
    hypothesis would be rejected -- the BH-adjusted p-value, enforced monotone
    non-decreasing in rank as the procedure requires.

    An empty family returns empty lists. NaN or None p-values are treated as
    1.0 (never rejected) rather than dropped, so the returned lists stay
    aligned with the caller's signal order.
    """
    import math as _math

    ps = []
    for value in (p_values or []):
        try:
            v = float(value)
        except (TypeError, ValueError):
            v = 1.0
        if _math.isnan(v):
            v = 1.0
        ps.append(min(max(v, 0.0), 1.0))

    m = len(ps)
    if m == 0:
        return [], []

    order = sorted(range(m), key=lambda i: ps[i])

    # Adjusted p-values, computed from the largest rank downward so the
    # running minimum enforces monotonicity in one pass.
    q_sorted = [1.0] * m
    running_min = 1.0
    for rank in range(m, 0, -1):
        idx = order[rank - 1]
        candidate = min(1.0, ps[idx] * m / rank)
        running_min = min(running_min, candidate)
        q_sorted[rank - 1] = running_min

    q_values = [1.0] * m
    for rank, idx in enumerate(order):
        q_values[idx] = q_sorted[rank]

    rejected = [q_values[i] <= alpha for i in range(m)]
    return rejected, q_values


def correlation_lower_bound(r: float, n: int, z_crit: float = _Z_CRIT_95) -> float:
    """Lower confidence bound on |r|, via the Fisher z transform.

    z = arctanh(|r|) is approximately normal with standard error
    1/sqrt(n - 3), so the bound is tanh(max(0, z - z_crit / sqrt(n - 3))).

    Returns 0.0 whenever the interval reaches zero -- i.e. whenever the
    correlation is not distinguishable from no correlation at this sample size.
    That is the property that makes it usable as a weight directly: it needs no
    significance threshold, because an unconvincing correlation shrinks itself.

    n <= 3 has no defined standard error and returns 0.0.
    """
    import math as _math

    try:
        r = abs(float(r))
        n = int(n)
    except (TypeError, ValueError):
        return 0.0
    if n <= 3 or _math.isnan(r):
        return 0.0

    # arctanh diverges at 1; a sample correlation of exactly +/-1 is a
    # degenerate fit, not infinite evidence.
    r = min(r, 0.999999)
    z = _math.atanh(r)
    se = 1.0 / _math.sqrt(n - 3)
    lower = z - z_crit * se
    if lower <= 0:
        return 0.0
    return float(round(_math.tanh(lower), 4))


# The largest |r| that is still a believable TRUE macro-signal-to-equity-return
# correlation. Published cross-sectional return predictors live far below this;
# PR #211's scan of 47 signals x 3 tickers peaked at r=0.19. A sample so small
# that it could only ever flag something above this ceiling is not a weak test,
# it is a test that cannot produce a believable positive -- whatever it does
# flag is noise, by construction.
MIN_DETECTABLE_R_CEILING = 0.35


def min_detectable_r(n: int, alpha: float = 0.05) -> float:
    """Smallest |r| this sample size could distinguish from zero at `alpha`.

    This is the critical value of the Pearson test, so it says what the sample
    is CAPABLE of detecting, independent of what it happened to observe:

        n=  7  ->  0.754      n= 32  ->  0.349
        n= 23  ->  0.413      n=103  ->  0.194
        n= 519 ->  0.086

    Returns 1.0 for n <= 3, where the test is undefined.
    """
    try:
        n = int(n)
    except (TypeError, ValueError):
        return 1.0
    if n <= 3:
        return 1.0

    import math as _math

    t = float(stats.t.ppf(1 - alpha / 2, n - 2))
    return float(round(t / _math.sqrt(t * t + n - 2), 4))


def compute_quick_correlation_stats(
    signal: pd.Series,
    price: pd.Series,
    lag_weeks: int = 0,
) -> dict:
    """
    Fast Pearson r + p-value at a single specified lag — no lag scanning.

    Unlike compute_quick_correlation (which dampens but never exposes the
    p-value), this returns the actual significance test result so callers
    can filter signals by genuine statistical significance (p < 0.05) for
    a specific ticker, rather than relying on PCS alone.

    Returns {"r", "p_value", "significant", "n", "r_lower", "min_detectable_r",
    "underpowered"}. n = number of overlapping return observations used.
    A p_value of 1.0 / significant=False is returned whenever there isn't
    enough overlapping data to run the test at all.

    THE POWER GATE (2026-08-26). r_lower is forced to 0.0 whenever the sample
    could not have detected a believable correlation in the first place, i.e.
    when min_detectable_r(n) > MIN_DETECTABLE_R_CEILING. Without this, small
    samples were the ones MOST able to produce an outsized weight, which
    inverts what weighting on a confidence bound was supposed to achieve:

        sample                needs |r| >=   P(pure noise clears the 0.15 floor)
        quarterly (n~7)          0.815                  2.63%
        monthly   (n~23)         0.530                  1.04%
        weekly    (n~103)        0.335                  0.05%

    A monthly signal is ~20x likelier than a weekly one to be handed an
    above-floor weight by chance alone -- and utils/ticker_score.py's raw
    >= 20 observation gate lets monthly signals through, so this was live.
    The gate only ever REMOVES weight; it can never add any.
    """
    def _empty(n: int) -> dict:
        return {"r": 0.0, "p_value": 1.0, "significant": False, "n": n,
                "r_lower": 0.0, "min_detectable_r": min_detectable_r(n),
                "underpowered": True}

    try:
        aligned = align_series(signal, price, lag_weeks)
        if len(aligned) < 12:
            return _empty(len(aligned))
        sr = aligned["signal"].pct_change().dropna()
        pr = aligned["price"].pct_change().dropna()
        cb = pd.DataFrame({"s": sr, "p": pr}).dropna()
        if len(cb) < 8:
            return _empty(len(cb))
        r, p = stats.pearsonr(cb["s"], cb["p"])
        n = len(cb)

        floor_r = min_detectable_r(n)
        underpowered = floor_r > MIN_DETECTABLE_R_CEILING

        # Lower 95% bound on |r|. This is what should be weighted on: it is
        # zero whenever the correlation cannot be told apart from noise at
        # this sample size, so it encodes effect size and evidence together.
        # Zeroed outright when the sample could not have found a believable
        # correlation at all -- see THE POWER GATE above.
        bound = 0.0 if underpowered else correlation_lower_bound(r, n)

        return {
            "r":                float(round(r, 4)),
            "p_value":          float(round(p, 6)),
            "significant":      bool(p < 0.05),
            "n":                n,
            "r_lower":          bound,
            "min_detectable_r": floor_r,
            "underpowered":     bool(underpowered),
        }
    except Exception:
        return _empty(0)


def bartlett_effective_n(x, y, max_lag: Optional[int] = None) -> int:
    """Effective sample size for a correlation between two autocorrelated series.

        n_eff = n / (1 + 2 * sum_k rho_x(k) * rho_y(k))

    Bartlett's variance formula. The product rho_x(k)*rho_y(k) is what matters:
    if EITHER series is white noise the sum vanishes and n_eff == n, which is
    the correct answer -- overlapping windows on one side alone do not inflate
    the variance of a correlation. Persistence on both sides shrinks it.

    Clipped to [1, n]: a negative sum (anti-persistence) would otherwise claim
    more independent observations than rows actually exist.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = int(min(len(x), len(y)))
    if n < 8:
        return max(n, 0)

    if max_lag is None:
        max_lag = max(1, min(n // 4, 26))

    def _acf(v, k):
        v = v - v.mean()
        denom = float(np.dot(v, v))
        if denom <= 0:
            return 0.0
        return float(np.dot(v[:-k], v[k:]) / denom)

    total = 0.0
    for k in range(1, int(max_lag) + 1):
        if k >= n:
            break
        total += _acf(x, k) * _acf(y, k)

    inflation = 1.0 + 2.0 * total
    if inflation <= 0:
        return n
    return int(max(1, min(n, round(n / inflation))))


def compute_forward_return_correlation(
    signal: pd.Series,
    price: pd.Series,
    benchmark: Optional[pd.Series] = None,
    horizon_weeks: int = 4,
    lag_weeks: int = 0,
) -> dict:
    """Correlate a signal against FORWARD CUMULATIVE, market-adjusted returns.

    Two changes from compute_quick_correlation_stats, both aimed at raising the
    effect size rather than chasing sample size:

    1. THE TARGET IS A HORIZON, NOT A WEEK. That function correlates a signal
       change against a SINGLE week's return. One week of a single stock is
       mostly noise. Over H weeks a persistent drift accumulates ~H while its
       noise accumulates ~sqrt(H), so the detectable signal-to-noise improves
       ~sqrt(H) -- about 2x at H=4, 3.5x at H=12. 4/8/12 weeks are also the
       horizons this product already resolves its own predictions at.

    2. THE MARKET IS REGRESSED OUT. Weekly single-stock returns are dominated
       by the market factor. Testing a macro signal against a raw stock return
       largely tests it against SPY. When `benchmark` is given, the stock's
       forward return is regressed on the benchmark's forward return over the
       same window and the RESIDUAL is what gets correlated -- so the question
       becomes "does this signal explain what the market does not."

    THE OVERLAP TRAP. Forward windows at consecutive weeks share H-1 weeks of
    returns, so rows are not independent and a p-value on the raw row count can
    be badly anti-conservative. The fix is NOT n // H: overlap inflates the
    variance of a correlation only when BOTH series are autocorrelated, so
    n // H is wildly over-conservative against a white-noise signal (measured:
    0% false positives AND 0% power at H=4, i.e. a dead test) and is not
    adaptive to how autocorrelated a given signal actually is.

    n_effective uses Bartlett's formula instead,

        n_eff = n / (1 + 2 * sum_k rho_x(k) * rho_y(k))

    which is the standard effective sample size for a correlation between two
    autocorrelated series. It reduces to n when either side is white noise --
    so a signal whose changes carry no memory keeps its full power -- and it
    shrinks exactly as far as the two series' shared persistence demands. Every
    inference (p_value, r_lower, min_detectable_r, the power gate) runs on
    n_effective; the point estimate of r still uses every row.

    Returns the compute_quick_correlation_stats contract plus "n_effective",
    "horizon_weeks" and "beta_adjusted". `n` is the raw overlapping row count,
    reported so the difference is visible rather than hidden.
    """
    def _empty(n: int = 0, n_eff: int = 0) -> dict:
        return {"r": 0.0, "p_value": 1.0, "significant": False, "n": n,
                "n_effective": n_eff, "r_lower": 0.0,
                "min_detectable_r": min_detectable_r(n_eff),
                "underpowered": True, "horizon_weeks": int(horizon_weeks),
                "beta_adjusted": benchmark is not None}

    try:
        H = int(horizon_weeks)
        if H < 1:
            return _empty()

        prc_w = _strip_tz(price).resample("W").last().dropna()
        sig_w = _strip_tz(signal).resample("W").mean().dropna()
        if prc_w.empty or sig_w.empty:
            return _empty()

        # Forward cumulative return over the next H weeks, dated at its START.
        fwd = (prc_w.shift(-H) / prc_w - 1.0).dropna()

        if benchmark is not None and not benchmark.empty:
            bench_w = _strip_tz(benchmark).resample("W").last().dropna()
            bench_fwd = (bench_w.shift(-H) / bench_w - 1.0).dropna()
            paired = pd.DataFrame({"y": fwd, "x": bench_fwd}).dropna()
            if len(paired) < 8:
                return _empty(len(paired))
            var_x = float(paired["x"].var())
            if var_x > 0:
                beta = float(paired["y"].cov(paired["x"])) / var_x
                intercept = float(paired["y"].mean()) - beta * float(paired["x"].mean())
                fwd = paired["y"] - (intercept + beta * paired["x"])
            else:
                fwd = paired["y"]

        sig_chg = sig_w.pct_change()
        if lag_weeks > 0:
            sig_chg = sig_chg.shift(lag_weeks)

        cb = pd.DataFrame({"s": sig_chg, "p": fwd}).dropna()
        cb = cb.replace([np.inf, -np.inf], np.nan).dropna()
        n = len(cb)
        n_eff = bartlett_effective_n(cb["s"].to_numpy(), cb["p"].to_numpy())
        if n < 8 or n_eff < 4:
            return _empty(n, n_eff)
        if float(cb["s"].std()) == 0.0 or float(cb["p"].std()) == 0.0:
            return _empty(n, n_eff)

        r = float(np.corrcoef(cb["s"], cb["p"])[0, 1])
        if not np.isfinite(r):
            return _empty(n, n_eff)

        # p-value on the NON-overlapping count, not the row count.
        if abs(r) >= 1.0:
            p = 0.0
        else:
            t_stat = r * math.sqrt(max(n_eff - 2, 1) / max(1.0 - r * r, 1e-12))
            p = float(2.0 * (1.0 - stats.t.cdf(abs(t_stat), max(n_eff - 2, 1))))

        floor_r = min_detectable_r(n_eff)
        underpowered = floor_r > MIN_DETECTABLE_R_CEILING
        bound = 0.0 if underpowered else correlation_lower_bound(r, n_eff)

        return {
            "r":                float(round(r, 4)),
            "p_value":          float(round(p, 6)),
            "significant":      bool(p < 0.05),
            "n":                n,
            "n_effective":      n_eff,
            "r_lower":          bound,
            "min_detectable_r": floor_r,
            "underpowered":     bool(underpowered),
            "horizon_weeks":    H,
            "beta_adjusted":    benchmark is not None,
        }
    except Exception:
        return _empty()


def compute_backtested_pcs(
    signal_series: pd.Series,
    price_series_list: List[pd.Series],
    lag_weeks: int = 0,
    tickers: Optional[List[str]] = None,
) -> dict:
    """
    Compute a REAL Predictive Confidence Score from actual backtested
    correlation + significance, instead of a hand-assigned 1-10 number.

    Tests the signal against ALL of its claimed relevant tickers' price
    histories (passed in by the caller — callers should pass a representative
    sample, e.g. up to 5, not just the first one: a signal that correlates
    well with one ticker and poorly with the rest should NOT score as if it
    were broadly validated).

    WHY THIS IS NOT WEIGHTED ON |r| AND RAW SIGNIFICANCE ANY MORE
    -------------------------------------------------------------
    Until 2026-08-26 the formula was

        PCS = clip(1 + significance_rate*5 + avg_abs_r*4, 1, 10)

    where significance_rate counted tickers with an UNCORRECTED p < 0.05 and
    avg_abs_r averaged raw |r|. Both inputs are the exact quantities PR #211
    removed from live weighting, for the same reason they are wrong here:
    raw |r| does not distinguish r=0.30 over 8 observations from r=0.30 over
    100, and testing a signal against 5 tickers at an uncorrected alpha=0.05
    is a 5-test family with no correction applied.

    Measured, not asserted -- scripts/measure_pcs_calibration.py, 3000 trials
    per row, 101 weekly observations, 5 tickers per signal:

        true rho    OLD mean PCS / P(PCS>=3)    NEW mean PCS / P(PCS>=3)
          0.00          1.32 /   5.7%               1.06 /   0.4%
          0.10          2.26 /  38.2%               1.37 /   7.7%
          0.19          4.35 /  92.4%               2.85 /  56.2%
          0.50          8.00 / 100.0%               7.23 / 100.0%

    rho=0.19 is the STRONGEST correlation PR #211 found anywhere across 47
    signals x 3 tickers, so the middle rows are the regime this product
    actually operates in -- and there the old formula handed out a mean PCS
    of 4.35 for a relationship that does not survive its own confidence
    interval. Because weight is proportional to PCS, the old formula's null
    p95 of 3 against a p5 of 1 is a 3.0x weight spread manufactured purely
    from noise, WIDER than the 1.8x spread the static config produces on
    purpose (its PCS values span 5..9). Wiring the old formula into live
    weighting would therefore have made the score noisier, not more measured.

    The new formula is calibrated, not merely less sensitive: it reads lower
    at every rho, but the drop is steep where evidence is weak (P(PCS>=3)
    38.2% -> 7.7% at rho=0.10) and absent where it is strong (100% -> 100% at
    rho=0.50). It is NOT immune -- 56% of rho=0.19 signals still reach PCS>=3
    -- it just no longer becomes confident on noise alone.

    The formula now uses the evidence-bearing forms of both inputs:
      - evidence_rate : fraction of tested tickers surviving Benjamini-Hochberg
                        correction across the ticker family (one family: this
                        signal against each of its relevant tickers)
      - avg_r_lower   : average LOWER 95% confidence bound on |r| (Fisher z),
                        which is 0 whenever the correlation cannot be told
                        apart from zero at that ticker's sample size
      PCS = clip(1 + evidence_rate*5 + avg_r_lower*4, 1, 10), rounded.

    `significance_rate` and `avg_abs_r` are still returned, unchanged, as the
    honest raw per-test read -- they are simply no longer what PCS is built
    from.

    `tickers`, if provided, must be parallel to price_series_list — each
    result in "details" is tagged with its ticker symbol so callers can show
    exactly which tickers passed/failed, not just an aggregate number.

    Returns {"pcs": int|None, "backtested": bool, "n_tested": int,
             "significance_rate": float, "avg_abs_r": float,
             "evidence_rate": float, "avg_r_lower": float, "details": [...]}.
    pcs is None and backtested=False when there isn't enough overlapping data
    to run the test at all — callers should fall back to a static default in
    that case, and label it clearly as unvalidated rather than presenting it
    as equivalent to a backtested score.
    """
    results = []
    for i, price_series in enumerate(price_series_list):
        if signal_series is None or signal_series.empty or price_series is None or price_series.empty:
            continue
        stat = compute_quick_correlation_stats(signal_series, price_series, lag_weeks=lag_weeks)
        stat["ticker"] = tickers[i] if tickers and i < len(tickers) else None
        if stat["n"] >= 8:
            results.append(stat)

    if not results:
        return {
            "pcs": None, "backtested": False, "n_tested": 0,
            "significance_rate": 0.0, "avg_abs_r": 0.0,
            "evidence_rate": 0.0, "avg_r_lower": 0.0, "details": [],
        }

    # This signal against each of its relevant tickers is ONE family of tests.
    # Correct across it once, exactly as utils/ticker_score.py corrects across
    # the 47-signal family it tests against a single ticker.
    rejected, q_values = benjamini_hochberg([r["p_value"] for r in results], alpha=0.05)
    for position, stat in enumerate(results):
        stat["q_value"] = round(q_values[position], 6) if q_values else 1.0
        stat["significant_fdr"] = bool(rejected[position]) if rejected else False

    sig_rate    = sum(1 for r in results if r["significant"]) / len(results)
    avg_abs_r   = sum(abs(r["r"]) for r in results) / len(results)
    ev_rate     = sum(1 for r in results if r["significant_fdr"]) / len(results)
    avg_r_lower = sum(r.get("r_lower", 0.0) for r in results) / len(results)

    pcs_raw = 1 + ev_rate * 5 + avg_r_lower * 4
    pcs     = int(round(max(1.0, min(10.0, pcs_raw))))

    return {
        "pcs": pcs, "backtested": True, "n_tested": len(results),
        "significance_rate": round(sig_rate, 2), "avg_abs_r": round(avg_abs_r, 3),
        "evidence_rate": round(ev_rate, 2), "avg_r_lower": round(avg_r_lower, 4),
        "details": results,
    }
# ─────────────────────────────────────────────────────────────────────────────
# BASIC TECHNICAL INDICATORS (Ticker Deep Dive, 2026-06-22 per explicit
# user request for "volume, RSI and other basic indicators")
# ─────────────────────────────────────────────────────────────────────────────

def compute_rsi(price: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder's Relative Strength Index -- the standard, textbook RSI
    formula (Wilder's own exponential smoothing with alpha=1/period, NOT
    a plain rolling-mean approximation, which some simplified
    implementations substitute and which produces visibly different
    values). Returns a Series of the same index as `price`, with NaN for
    the first `period` points where there isn't enough history yet.

    RSI = 100 - (100 / (1 + RS)), RS = avg_gain / avg_loss over `period`
    bars, where avg_gain/avg_loss use Wilder's smoothing (equivalent to
    an EMA with alpha = 1/period, adjust=False -- confirmed against
    pandas' own ewm() semantics, not assumed).

    Bounded in [0, 100] by construction: 100 when there have been zero
    losses in the lookback (textbook convention for "RS = infinity"), 0
    when there have been zero gains -- both verified directly with
    synthetic monotonic series in tests/test_technical_indicators_unit.py,
    not just trusted from the formula on paper.
    """
    if price.empty or len(price) < 2:
        return pd.Series(dtype=float, index=price.index)

    delta = price.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    # avg_loss == 0 (no losses at all in the lookback) makes rs = inf,
    # which already correctly evaluates to rsi = 100 via the formula
    # above -- EXCEPT when avg_gain is also 0 (a perfectly flat price),
    # where 0/0 = NaN rather than a meaningful "neutral" reading. Treat
    # that specific case as RSI = 50 (textbook convention: no movement
    # at all means no momentum in either direction).
    flat = (avg_gain == 0) & (avg_loss == 0)
    rsi = rsi.where(~flat, 50.0)

    return rsi


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL SCORING
# ─────────────────────────────────────────────────────────────────────────────

def score_signal(signal: pd.Series, inverse: bool = False) -> dict:
    """
    Score the current signal reading vs. its 52-week history.

    Returns a 0–100 score (50 = neutral, ≥65 = bullish, ≤35 = bearish).
    inverse=True means a rising signal is bearish (e.g., jobless claims).

    Z-score basis:
        score = clip(50 + z * 15, 0, 100)
    A 2σ move from the 52-week mean → score of ~80 (strong signal).
    """
    clean = signal.dropna()
    if len(clean) < 12:
        return {
            "score":         50.0,
            "status":        "insufficient_data",
            "z_score":       0.0,
            "percentile":    50.0,
            "current":       float("nan"),
            "mean_52w":      float("nan"),
            "std_52w":       float("nan"),
            "deviation_pct": 0.0,
            "trend_4w_pct":  0.0,
        }

    current  = float(clean.iloc[-1])
    hist_52w = clean.tail(52)
    mean     = float(hist_52w.mean())
    std      = float(hist_52w.std())
    z        = (current - mean) / std if std > 0 else 0.0
    pct      = float(stats.percentileofscore(clean.values, current))

    if inverse:
        z   = -z
        pct = 100.0 - pct

    score = float(np.clip(50.0 + z * 15.0, 0.0, 100.0))

    # 4-week momentum
    if len(clean) >= 8:
        recent = float(clean.tail(4).mean())
        prior  = float(clean.iloc[-8:-4].mean())
        trend_pct = (recent - prior) / abs(prior) * 100.0 if prior != 0 else 0.0
        if inverse:
            trend_pct = -trend_pct
    else:
        trend_pct = 0.0

    if score >= 65:
        status = "bullish"
    elif score <= 35:
        status = "bearish"
    else:
        status = "neutral"

    return {
        "score":         round(score, 1),
        "status":        status,
        "z_score":       round(z, 2),
        "percentile":    round(pct, 1),
        "current":       round(current, 4),
        "mean_52w":      round(mean, 4),
        "std_52w":       round(std, 4),
        "deviation_pct": round((current - mean) / mean * 100 if mean != 0 else 0.0, 2),
        "trend_4w_pct":  round(trend_pct, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL CONFIDENCE
# ─────────────────────────────────────────────────────────────────────────────

def compute_signal_confidence(
    score_result: dict,
    pcs: Optional[int] = None,
) -> dict:
    """
    Derive a human-readable confidence level from a score_signal() result.

    Confidence measures *how strongly* the signal is speaking — independent of
    direction. A High-confidence bearish signal is a clearer read than a
    Low-confidence bullish one.

    Factors considered:
      - |z_score|      : how far the current reading is from its 52w mean.
                         ≥ 1.5σ = meaningful deviation; ≥ 2.5σ = extreme.
      - trend alignment: does the 4-week momentum agree with the status?
                         Disagreement (e.g. bullish status but falling momentum)
                         reduces confidence.
      - pcs (1–10)     : backtested Predictive Confidence Score from lag scan.
                         Higher PCS means the signal has historically led price.

    Returns:
        {
          "level":  "High" | "Medium" | "Low",
          "icon":   str,               # ◆ ◇ ○
          "color":  str,               # hex for the badge
          "note":   str,               # one plain-English sentence
        }
    """
    if score_result.get("status") == "insufficient_data":
        return {
            "level": "Low",
            "icon":  "○",
            "color": "#6B7FBF",
            "note":  "Not enough data history to score with confidence.",
        }

    z         = abs(score_result.get("z_score", 0.0))
    status    = score_result.get("status", "neutral")
    trend     = score_result.get("trend_4w_pct", 0.0)
    pcs_score = pcs if pcs is not None else 5   # default to mid if unknown

    # Trend alignment: does recent momentum agree with the signal direction?
    trend_agrees = (
        (status == "bullish" and trend > 0)
        or (status == "bearish" and trend < 0)
        or (status == "neutral")
    )

    # Score the three inputs: z, alignment, pcs
    z_strong    = z >= 2.0
    z_moderate  = z >= 1.0
    pcs_strong  = pcs_score >= 7
    pcs_moderate = pcs_score >= 4

    if z_strong and trend_agrees and pcs_strong:
        level = "High"
        icon  = "◆"
        color = "#00D566"
        note  = (
            f"Strong read — {z:.1f}σ from 52w mean, "
            f"momentum aligns, historically predictive (PCS {pcs_score}/10)."
        )
    elif z_strong and trend_agrees:
        level = "High"
        icon  = "◆"
        color = "#00D566"
        note  = (
            f"Strong deviation ({z:.1f}σ) with confirming momentum — "
            f"PCS {pcs_score}/10."
        )
    elif z_moderate and (pcs_moderate or trend_agrees):
        level = "Medium"
        icon  = "◇"
        color = "#F59E0B"
        note  = (
            f"Moderate read — {z:.1f}σ from 52w mean"
            + (", momentum aligns" if trend_agrees else ", but momentum is mixed")
            + f". PCS {pcs_score}/10."
        )
    elif z_moderate:
        level = "Medium"
        icon  = "◇"
        color = "#F59E0B"
        note  = (
            f"{z:.1f}σ deviation but momentum is counter-trend — "
            f"read with caution. PCS {pcs_score}/10."
        )
    else:
        level = "Low"
        icon  = "○"
        color = "#6B7FBF"
        note  = (
            f"Within normal range ({z:.1f}σ) — "
            f"no clear directional edge right now. PCS {pcs_score}/10."
        )

    return {"level": level, "icon": icon, "color": color, "note": note}


# ─────────────────────────────────────────────────────────────────────────────
# COT POSITIONING SCORE
# ─────────────────────────────────────────────────────────────────────────────

def score_cot(cot_df: pd.DataFrame) -> dict:
    """
    Score CFTC COT positioning.

    Interpretation (from Project Bible §CFTC COT):
        - Commercials = "smart money" — they hedge real exposure
        - Extreme commercial net LONG + extreme speculator net SHORT → contrarian BULL
        - Extreme speculator net LONG + commercial net SHORT → contrarian BEAR

    Returns a 0–100 score driven by commercial positioning percentile.
    """
    if cot_df.empty or len(cot_df) < 12:
        return {
            "score": 50.0, "status": "neutral",
            "spec_net": 0, "comm_net": 0,
            "spec_net_pct": 50.0, "comm_net_pct": 50.0,
            "spec_extreme": False, "comm_extreme": False,
            "contrarian_signal": None,
        }

    df = cot_df.copy()
    df["spec_net"] = df["spec_long"] - df["spec_short"]
    df["comm_net"] = df["comm_long"] - df["comm_short"]

    curr_spec = float(df["spec_net"].iloc[-1])
    curr_comm = float(df["comm_net"].iloc[-1])

    spec_pct = float(stats.percentileofscore(df["spec_net"].values, curr_spec))
    comm_pct = float(stats.percentileofscore(df["comm_net"].values, curr_comm))

    comm_mean = float(df["comm_net"].mean())
    comm_std  = float(df["comm_net"].std())
    comm_z    = (curr_comm - comm_mean) / comm_std if comm_std > 0 else 0.0

    score = float(np.clip(50.0 + comm_z * 15.0, 0.0, 100.0))

    spec_extreme = spec_pct >= 85 or spec_pct <= 15
    comm_extreme = comm_pct >= 85 or comm_pct <= 15

    # Contrarian signal: extremes in both, opposite directions
    contrarian = None
    if spec_pct >= 85 and comm_pct <= 20:
        contrarian = "BEARISH SETUP — Specs at extreme long, commercials hedging short"
    elif spec_pct <= 15 and comm_pct >= 80:
        contrarian = "BULLISH SETUP — Specs at extreme short, commercials net long"

    return {
        "score":              round(score, 1),
        "status":             "bullish" if score >= 65 else ("bearish" if score <= 35 else "neutral"),
        "spec_net":           int(curr_spec),
        "comm_net":           int(curr_comm),
        "spec_net_pct":       round(spec_pct, 1),
        "comm_net_pct":       round(comm_pct, 1),
        "spec_extreme":       spec_extreme,
        "comm_extreme":       comm_extreme,
        "contrarian_signal":  contrarian,
        "net_positions_df":   df[["date", "spec_net", "comm_net"]].tail(104),
    }


# ─────────────────────────────────────────────────────────────────────────────
# INSIDER TRADING ACTIVITY (real Form 4 transaction detail, not just filings)
# ─────────────────────────────────────────────────────────────────────────────

def score_insider_activity(tx_df: pd.DataFrame) -> dict:
    """
    Score genuine open-market insider buying/selling from real Form 4
    transaction detail (utils/fetchers.fetch_insider_transactions_detail —
    parsed XML, transactionCode P/S only, not grants/vesting/options).

    Methodology, deliberately NOT dollar-amount-based: a $1M purchase is
    massive for a small-cap and trivial for a mega-cap, and this product
    has no reliable market-cap context to normalize that fairly. Instead
    this scores on insider COUNT and clustering, which is also what the
    academic literature (Lakonishok & Lee 2001; Seyhun) actually finds most
    predictive: multiple INDEPENDENT insiders buying in the same window is
    a much stronger signal than one large purchase by one person, since it
    is harder to coordinate/fake and more often reflects genuine shared
    conviction (e.g. several executives buying around the same earnings
    cycle) rather than one person's idiosyncratic liquidity need.

    Returns {"score": float, "status": str, "distinct_buyers": int,
             "distinct_sellers": int, "buy_count": int, "sell_count": int,
             "net_value": float, "cluster_bonus_applied": bool}.
    """
    if tx_df.empty or "code" not in tx_df.columns:
        return {
            "score": 50.0, "status": "no_data", "distinct_buyers": 0,
            "distinct_sellers": 0, "buy_count": 0, "sell_count": 0,
            "net_value": 0.0, "cluster_bonus_applied": False, "evidence": [],
        }

    buys  = tx_df[tx_df["code"] == "P"]
    sells = tx_df[tx_df["code"] == "S"]
    distinct_buyers  = buys["insider"].nunique()
    distinct_sellers = sells["insider"].nunique()
    total_distinct = distinct_buyers + distinct_sellers

    # Audit-trail evidence: one entry per transaction, each linking back to
    # the exact Form 4 it came from. Capped at the 20 most recent so this
    # doesn't balloon the returned dict for a heavily-traded name; the UI
    # is meant to show "here's what's actually backing this score," not
    # every transaction ever filed.
    evidence = []
    if "date" in tx_df.columns:
        for _, row in tx_df.sort_values("date", ascending=False).head(20).iterrows():
            evidence.append({
                "date": row["date"],
                "description": f"{row.get('insider', 'Unknown')} ({row.get('role', 'Unknown')}) "
                                f"{'bought' if row.get('code') == 'P' else 'sold'} "
                                f"{abs(row.get('shares', 0)):,.0f} shares",
                "value": row.get("value", 0.0),
                "source_url": row.get("source_url"),
            })

    if total_distinct == 0:
        return {
            "score": 50.0, "status": "no_data", "distinct_buyers": 0,
            "distinct_sellers": 0, "buy_count": len(buys), "sell_count": len(sells),
            "net_value": float(tx_df["value"].sum()), "cluster_bonus_applied": False,
            "evidence": evidence,
        }

    buy_ratio = distinct_buyers / total_distinct
    score = 50.0 + (buy_ratio - 0.5) * 80.0

    # Cluster bonus: 3+ distinct insiders independently buying, with no
    # sellers at all, is the single strongest pattern in this dataset --
    # push it further bullish than the ratio alone would.
    cluster_bonus_applied = False
    if distinct_buyers >= 3 and distinct_sellers == 0:
        score = min(score + 15.0, 95.0)
        cluster_bonus_applied = True
    elif distinct_sellers >= 3 and distinct_buyers == 0:
        score = max(score - 15.0, 5.0)
        cluster_bonus_applied = True

    score = float(np.clip(score, 5.0, 95.0))

    return {
        "score": round(score, 1),
        "status": "bullish" if score >= 65 else ("bearish" if score <= 35 else "neutral"),
        "distinct_buyers": int(distinct_buyers),
        "distinct_sellers": int(distinct_sellers),
        "buy_count": len(buys),
        "sell_count": len(sells),
        "net_value": float(tx_df["value"].sum()),
        "cluster_bonus_applied": cluster_bonus_applied,
        "evidence": evidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FEDERAL CONTRACT VELOCITY
# ─────────────────────────────────────────────────────────────────────────────

def score_contract_velocity(contracts_df: pd.DataFrame) -> dict:
    """
    Score federal contract award velocity for a company.
    Compares trailing 6-month award volume to prior 6-month baseline.
    """
    if contracts_df.empty or "date" not in contracts_df.columns:
        return {
            "score": 50.0, "status": "no_data", "recent_total": 0, "prior_total": 0,
            "pct_change": 0.0, "award_count": 0,
        }

    df = contracts_df.dropna(subset=["date", "amount"]).copy()
    now   = pd.Timestamp.now()
    cut6  = now - pd.Timedelta(days=182)
    cut12 = now - pd.Timedelta(days=365)

    recent = df[df["date"] >= cut6]["amount"].sum()
    prior  = df[(df["date"] >= cut12) & (df["date"] < cut6)]["amount"].sum()

    if prior <= 0:
        pct_chg = 100.0 if recent > 0 else 0.0
    else:
        pct_chg = (recent - prior) / prior * 100.0

    # Map % change to 0-100 score: +100% change → ~80 score; −50% → ~30
    z = pct_chg / 50.0  # ±50% ≈ ±1 z-score
    score = float(np.clip(50.0 + z * 15.0, 0.0, 100.0))

    return {
        "score":        round(score, 1),
        "status":       "bullish" if score >= 65 else ("bearish" if score <= 35 else "neutral"),
        "recent_total": recent,
        "prior_total":  prior,
        "pct_change":   round(pct_chg, 1),
        "award_count":  len(df),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SHORT INTEREST (real FINRA exchange-listed data)
# ─────────────────────────────────────────────────────────────────────────────

def score_short_interest(si_df: pd.DataFrame) -> dict:
    """
    Score short interest trend from utils/fetchers.fetch_short_interest()
    (real FINRA consolidated short interest, bi-monthly settlement dates).

    INVERSE signal: rising short interest = more bearish positioning being
    built = lower score. This intentionally does NOT model short-squeeze
    dynamics (very high short interest + a price catalyst can produce a
    sharp bullish squeeze) -- that requires combining this with price
    action in a way this product doesn't yet do reliably, so the squeeze
    case is called out as a caveat in the UI rather than silently modeled.

    Averages the most recent 2 reporting periods' change_pct (FINRA's own
    period-over-period calculation) rather than just the latest one, since
    a single bi-monthly reading can be noisy.

    Returns {"score", "status", "latest_change_pct", "short_shares",
             "days_to_cover", "periods"}.
    """
    if si_df.empty or "change_pct" not in si_df.columns:
        return {
            "score": 50.0, "status": "no_data", "latest_change_pct": 0.0,
            "short_shares": 0, "days_to_cover": 0.0, "periods": 0, "evidence": [],
        }

    si_df = si_df.dropna(subset=["change_pct"])
    if si_df.empty:
        return {
            "score": 50.0, "status": "no_data", "latest_change_pct": 0.0,
            "short_shares": 0, "days_to_cover": 0.0, "periods": 0, "evidence": [],
        }

    recent = si_df.tail(2)
    avg_change = float(recent["change_pct"].mean())
    latest = si_df.iloc[-1]

    # Audit-trail evidence: one entry per FINRA settlement-date report. NO
    # source_url here, deliberately, rather than a fake one -- FINRA's API
    # doesn't expose a stable per-record deep link the way SEC EDGAR does,
    # so the "source" is named plainly (settlement date + dataset), not
    # presented as a clickable permalink that doesn't really point anywhere
    # specific.
    evidence = [
        {
            "date": row["date"],
            "description": f"FINRA consolidated short interest, settlement date "
                            f"{row['date'].strftime('%Y-%m-%d') if pd.notna(row['date']) else 'unknown'}: "
                            f"{row.get('change_pct', 0):+.1f}% vs. prior period",
            "value": row.get("change_pct", 0.0),
            "source_url": None,
            "source_label": "FINRA consolidated short interest (no stable per-record deep link available)",
        }
        for _, row in si_df.tail(10).iterrows()
    ]

    # ±15 percentage points of period-over-period change is treated as a
    # roughly 1-"sigma" move for this signal -- a calibration choice, not
    # derived from a backtest (this signal has not been backtested the way
    # the Confluence/Supercycle scores have -- see About -> Methodology).
    z = -avg_change / 15.0
    score = float(np.clip(50.0 + z * 15.0, 5.0, 95.0))

    return {
        "score": round(score, 1),
        "status": "bullish" if score >= 65 else ("bearish" if score <= 35 else "neutral"),
        "latest_change_pct": round(float(latest.get("change_pct", 0.0)), 2),
        "short_shares": int(latest.get("short_shares", 0)),
        "days_to_cover": round(float(latest.get("days_to_cover", 0.0)), 2),
        "periods": len(si_df),
        "evidence": evidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 13F INSTITUTIONAL POSITIONING (curated, hand-verified fund whitelist)
# ─────────────────────────────────────────────────────────────────────────────

def score_13f_positioning(fund_rows: List[dict]) -> dict:
    """
    Score curated-fund 13F positioning for one ticker.

    fund_rows: one dict per curated fund that holds (or held last quarter)
    this ticker, each shaped {"fund", "style", "latest_shares",
    "latest_period", "prior_shares", "prior_period"}. "latest_shares" is
    SIGNED -- negative means the fund's position is net short via Put
    options (see fetch_13f_holdings' docstring), not a plain share count.
    "prior_shares" is None if that fund's prior-quarter filing wasn't
    available or didn't include this ticker (a real "they didn't hold it
    last quarter," not missing data -- the caller is responsible for that
    distinction since it requires the fund's FULL holdings, not just the
    rows matching this one ticker).

    This signal is structurally the slowest-moving and most stale of this
    product's signals: 13F filings are quarterly with a 45-day filing lag,
    and the curated funds here don't all file on the same schedule (one of
    the three, as of this writing, has a most-recent filing nearly three
    quarters old). That staleness is surfaced via "latest_period" in the
    UI, not hidden.

    Returns {"score", "status", "funds_long", "funds_short",
             "new_positions", "exited_or_trimmed", "n_funds"}.
    """
    if not fund_rows:
        return {
            "score": 50.0, "status": "no_data", "funds_long": 0, "funds_short": 0,
            "new_positions": 0, "exited_or_trimmed": 0, "n_funds": 0, "evidence": [],
        }

    score = 50.0
    funds_long = 0
    funds_short = 0
    new_positions = 0
    exited_or_trimmed = 0
    evidence = []

    for row in fund_rows:
        latest = row.get("latest_shares") or 0.0
        prior = row.get("prior_shares")
        direction_sign = 1 if latest > 0 else (-1 if latest < 0 else 0)
        if direction_sign > 0:
            funds_long += 1
        elif direction_sign < 0:
            funds_short += 1
        if direction_sign == 0:
            continue

        if prior is None or prior == 0:
            trend_mult = 1.2  # newly initiated this quarter
            new_positions += 1
            trend_desc = "new position this quarter"
        elif abs(latest) > abs(prior) * 1.05:
            trend_mult = 1.3  # adding to the position
            trend_desc = "adding to position"
        elif abs(latest) < abs(prior) * 0.95:
            trend_mult = 0.7  # trimming
            exited_or_trimmed += 1
            trend_desc = "trimming position"
        else:
            trend_mult = 1.0  # roughly unchanged
            trend_desc = "roughly unchanged"

        score += direction_sign * 15.0 * trend_mult

        evidence.append({
            "date": row.get("latest_period"),
            "description": f"{row.get('fund', 'Unknown fund')} "
                            f"{'long' if direction_sign > 0 else 'short (via Put)'} "
                            f"{abs(latest):,.0f} shares — {trend_desc}",
            "value": latest,
            "source_url": row.get("latest_source_url"),
        })

    score = float(np.clip(score, 5.0, 95.0))
    return {
        "score": round(score, 1),
        "status": "bullish" if score >= 65 else ("bearish" if score <= 35 else "neutral"),
        "funds_long": funds_long,
        "funds_short": funds_short,
        "new_positions": new_positions,
        "exited_or_trimmed": exited_or_trimmed,
        "n_funds": len(fund_rows),
        "evidence": evidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-SIGNAL CONFLUENCE SCORING
# ─────────────────────────────────────────────────────────────────────────────

def compute_confluence(
    signal_scores: Dict[str, dict],
    weights: Optional[Dict[str, float]] = None,
) -> dict:
    """
    Compute a weighted multi-signal confluence score for a ticker.

    Each signal_score dict must contain at least:
        {"score": float, "status": "bullish"|"bearish"|"neutral"}

    Returns overall_score (0–100), conviction level, and signal breakdowns.
    This is the PRIMARY differentiator — no other retail platform does this.

    Note on "conviction": it measures AGREEMENT among the input signals
    (what fraction point the same direction), not validated predictive
    accuracy. A walk-forward backtest of this function (see
    compute_supercycle_score's docstring for the specific numbers) found no
    significant relationship between the resulting score and forward returns
    pooled across 6 tickers. High conviction means the signals agree with
    each other right now — it does not yet mean they're right.
    """
    if not signal_scores:
        return {
            "overall_score": 50.0,
            "conviction": "No Data",
            "case": "NEUTRAL",
            "bull_count": 0,
            "bear_count": 0,
            "neutral_count": 0,
            "bull_signals": [],
            "bear_signals": [],
            "neutral_signals": [],
        }

    bull, bear, neutral = [], [], []
    w_sum   = 0.0
    w_total = 0.0

    for sig_id, sd in signal_scores.items():
        w  = (weights or {}).get(sig_id, 1.0)
        sc = float(sd.get("score", 50))
        w_sum   += sc * w
        w_total += w

        st_val = sd.get("status", "neutral")
        if st_val == "bullish":
            bull.append(sig_id)
        elif st_val == "bearish":
            bear.append(sig_id)
        else:
            neutral.append(sig_id)

    overall = w_sum / w_total if w_total > 0 else 50.0
    n = len(signal_scores)

    agreement = max(len(bull), len(bear)) / n if n > 0 else 0.0
    if agreement >= 0.80:
        conviction = "Very High"
    elif agreement >= 0.60:
        conviction = "High"
    elif agreement >= 0.40:
        conviction = "Moderate"
    else:
        conviction = "Low / Mixed"

    # ── Effective independent signals (de-correlated conviction) ──────────────
    # Raw agreement counts each agreeing signal as one piece of evidence, but
    # signals sharing a macro factor (VIX + put/call = risk appetite; HY + IG =
    # credit) are the same bet counted twice. Recompute conviction on the
    # EFFECTIVE number of independent signals so "9 agree" can't masquerade as
    # nine independent votes when it's really ~3. Additive: the Confluence Score
    # value and the raw `conviction` above are unchanged; this only adds an
    # honest, de-correlated read alongside them. See utils/signal_independence.
    _CONV_ORDER = ["Low / Mixed", "Moderate", "High", "Very High"]
    try:
        from utils.signal_independence import effective_signal_count, independence
        _winner = bull if len(bull) >= len(bear) else bear
        _eff_win = effective_signal_count(_winner)
        # Correlation weakens EVIDENCE STRENGTH, not the agreement fraction: if
        # all 7 agree, 100% agree either way, but 7 signals across 2 factors are
        # ~2 independent votes. So conviction is CAPPED by the absolute effective
        # count — high conviction needs both broad agreement AND enough truly
        # independent evidence.
        if _eff_win >= 5.0:
            _evidence_cap = "Very High"
        elif _eff_win >= 3.5:
            _evidence_cap = "High"
        elif _eff_win >= 2.0:
            _evidence_cap = "Moderate"
        else:
            _evidence_cap = "Low / Mixed"
        _conviction_eff = _CONV_ORDER[min(_CONV_ORDER.index(conviction),
                                          _CONV_ORDER.index(_evidence_cap))]
        _independence = independence(_winner)
        _eff_ratio = _independence["ratio"]
    except Exception:
        # Independence is a qualifier, never load-bearing — degrade to raw.
        _eff_win, _eff_ratio = float(max(len(bull), len(bear))), 1.0
        _conviction_eff = conviction
        _independence = {"raw": max(len(bull), len(bear)),
                         "effective": float(max(len(bull), len(bear))),
                         "ratio": 1.0, "n_factors": 0, "factors": {}}

    if overall >= 62:
        case = "BULL"
    elif overall <= 38:
        case = "BEAR"
    else:
        case = "NEUTRAL"

    return {
        "overall_score":   round(overall, 1),
        "conviction":      conviction,
        "case":            case,
        "bull_count":      len(bull),
        "bear_count":      len(bear),
        "neutral_count":   len(neutral),
        "bull_signals":    bull,
        "bear_signals":    bear,
        "neutral_signals": neutral,
        # De-correlated read (see block above). effective_signals is the
        # independent-signal count on the winning side; conviction_effective is
        # conviction recomputed on effective agreement; independence carries the
        # per-factor breakdown for display ("9 aligned across ~3 factors").
        "effective_signals":     round(_eff_win, 2),
        "independence_ratio":    round(_eff_ratio, 3),
        "conviction_effective":  _conviction_eff,
        "independence":          _independence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POWER SUPERCYCLE CONVERGENCE SCORE
# ─────────────────────────────────────────────────────────────────────────────

# Signal weights reflect PCS scores and thematic centrality to the thesis
_SUPERCYCLE_WEIGHTS: Dict[str, float] = {
    "uranium_proxy":     2.2,   # Nuclear fuel demand = core thesis driver
    "copper":            2.0,   # Grid buildout = physical constraint
    "natural_gas":       1.6,   # Data center co-located generation
    "hyperscaler_capex": 1.8,   # AI demand = the trigger
    "ata_trucking":      0.9,   # Macro backdrop
    "jobless_claims":    0.7,   # Macro risk-off indicator (inverse)
    "crude_oil":         0.8,   # Energy complex health
    "food_cpi":          0.5,   # Inflation / real rate context
}


def compute_supercycle_score(signal_scores: Dict[str, dict]) -> dict:
    """
    Compute the Power Supercycle alignment score.

    The thesis: AI training → massive compute → power demand → grid buildout
    → copper + nuclear/gas → uranium + SWU tight → cycle repeats.

    IMPORTANT — what this score is and isn't: it is a real-time read of how
    many of the 8 underlying signals are currently elevated vs. their own
    trailing history, weighted toward the legs judged most central to the
    thesis. It is NOT a validated predictor of forward returns. A walk-forward
    backtest (real production code, 6 tickers spanning the thesis — CEG, VST,
    NEE, ETN, VRT, PWR — ~19 monthly checkpoints, pooled) found no
    statistically significant relationship between this score and 1/2/3-month
    forward returns in either direction (all |r| < 0.07, p > 0.5 pooled).
    Two of the six tickers showed a significant NEGATIVE relationship in
    isolation before pooling — driven by the two most narrative-extended
    names, where a high reading coincided with a cyclical top rather than
    leading one. Treat this score as a description of current signal
    alignment, not a forecast, until a larger/longer backtest says otherwise.

    Score ≥70: signals strongly aligned bullish (not "confirmed" — aligned).
    Score 50–70: building alignment, not yet strong.
    Score <50: signals diverging from / against the thesis.
    """
    result = compute_confluence(signal_scores, weights=_SUPERCYCLE_WEIGHTS)

    # Status label describes CURRENT SIGNAL ALIGNMENT only — deliberately not
    # phrased as "confirmed" or "conviction", since that would claim a
    # predictive validity this score has not earned (see backtest note above).
    score = result["overall_score"]
    if score >= 72:
        thesis_status = "STRONGLY ALIGNED — Most legs of the Power Supercycle are reading bullish right now"
    elif score >= 60:
        thesis_status = "ALIGNING — Some signals bullish, not yet a strong majority"
    elif score >= 45:
        thesis_status = "MIXED — Signals are split between bullish and bearish readings"
    else:
        thesis_status = "DIVERGING — Most signals are currently reading against the thesis"

    result["thesis_status"] = thesis_status
    return result


# ─────────────────────────────────────────────────────────────────────────────
# BULL/BEAR NARRATIVE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

_SIGNAL_BULL_TEMPLATES = {
    "ata_trucking":      "ATA Trucking Tonnage is running {dev_pct:+.1f}% above its 52-week average, signaling broad freight demand expansion — historically a {lag}-week leading indicator for industrial and transportation stocks.",
    "rail_traffic":      "Rail intermodal traffic is elevated {dev_pct:+.1f}% vs. baseline, suggesting import pipeline strength and manufacturing activity {lag} weeks out.",
    "jobless_claims":    "Initial jobless claims are running {dev_pct:+.1f}% below 52-week average — labor market resilience that historically supports consumer spending for {lag}+ weeks.",
    "layoffs_rate":      "The BLS layoffs rate is {dev_pct:+.1f}% below baseline, indicating corporate confidence in near-term demand.",
    "crude_oil":         "WTI crude trending above 52-week mean by {dev_pct:+.1f}% — rising energy demand reflects healthy industrial activity.",
    "natural_gas":       "Henry Hub gas prices elevated {dev_pct:+.1f}% — indicates power demand exceeding supply, favorable for gas producers and pipeline operators.",
    "uranium_proxy":     "Uranium market (URA proxy) running {dev_pct:+.1f}% above 52-week average — signals accelerating utility demand for nuclear fuel ahead of new reactor commitments.",
    "copper":            "COMEX copper trading {dev_pct:+.1f}% above 52-week average — physical tightness in the grid buildout critical material. LME inventory dynamics confirm.",
    "hyperscaler_capex": "Hyperscaler CapEx composite is running elevated — AI infrastructure investment at record pace, driving multi-year power and infrastructure demand.",
    "food_cpi":          "Food CPI is below trend — reduced agricultural supply pressure supports grocery and food-service margins.",
    "quantum_proxy":     "Quantum computing equity basket is trending higher — institutional sentiment on milestone timing is improving.",
}

_SIGNAL_BEAR_TEMPLATES = {
    "ata_trucking":      "ATA Trucking Tonnage has deteriorated {dev_pct:+.1f}% below its 52-week average — freight contraction typically precedes manufacturing and retail slowdowns by {lag} weeks.",
    "rail_traffic":      "Rail intermodal traffic is tracking {dev_pct:+.1f}% below baseline — import pipeline weakness suggesting inventory drawdowns ahead.",
    "jobless_claims":    "Initial jobless claims have risen {dev_pct:+.1f}% above 52-week average — labor market deterioration that historically pressures consumer discretionary spending.",
    "layoffs_rate":      "BLS layoffs rate is elevated {dev_pct:+.1f}% above baseline — corporate caution on near-term demand.",
    "crude_oil":         "WTI crude below 52-week mean by {dev_pct:+.1f}% — demand destruction signal for energy complex.",
    "natural_gas":       "Henry Hub below baseline — power demand softness or oversupply, pressuring gas producer margins.",
    "uranium_proxy":     "Uranium market (URA proxy) below 52-week average by {dev_pct:+.1f}% — slowing utility contracting pace, reduced nuclear fuel demand.",
    "copper":            "COMEX copper below 52-week average by {dev_pct:+.1f}% — grid buildout pace slowing or oversupply from mine expansions.",
    "hyperscaler_capex": "Hyperscaler CapEx composite showing deceleration — data center investment cycle may be plateauing.",
    "food_cpi":          "Food CPI rising {dev_pct:+.1f}% above trend — agricultural supply disruption feeding through to grocery and food-service margins.",
    "quantum_proxy":     "Quantum computing equity basket is weakening — institutional skepticism on near-term milestone timing.",
}


def build_narrative(
    ticker: str,
    signal_scores: Dict[str, dict],
    signal_configs: dict,
) -> dict:
    """
    Build a structured bull and bear case narrative based on signal readings.
    Returns text bullets for each side plus an overall conviction assessment.
    """
    bull_points, bear_points = [], []

    for sig_id, sd in signal_scores.items():
        cfg    = signal_configs.get(sig_id, {})
        lag    = cfg.get("lag_weeks", 4)
        dev    = sd.get("deviation_pct", 0.0)
        status = sd.get("status", "neutral")

        if status == "bullish":
            tmpl = _SIGNAL_BULL_TEMPLATES.get(sig_id)
            if tmpl:
                bull_points.append(tmpl.format(dev_pct=abs(dev), lag=lag))
        elif status == "bearish":
            tmpl = _SIGNAL_BEAR_TEMPLATES.get(sig_id)
            if tmpl:
                bear_points.append(tmpl.format(dev_pct=abs(dev), lag=lag))

    confluence = compute_confluence(signal_scores)

    return {
        "bull_points":  bull_points,
        "bear_points":  bear_points,
        "confluence":   confluence,
        "ticker":       ticker,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FORWARD PREDICTION MODEL
# ─────────────────────────────────────────────────────────────────────────────

def predict_ticker_forward(
    confluence_score: float,
    price_series: pd.Series,
    signal_scores: Dict[str, dict],
    horizons_days: list[int] | None = None,
) -> dict:
    """
    Signal-based forward probability model for a ticker.

    Inputs:
      confluence_score : weighted confluence 0-100 (already momentum-blended)
      price_series     : daily close prices
      signal_scores    : {sig_id: scored} dict
      horizons_days    : list of forecast horizons (default [30, 60, 90])

    Returns:
      horizons         : list[{days, label, bull_pct, bear_pct, neutral_pct,
                                price_low, price_mid, price_high}]
      annual_vol_pct   : annualized historical volatility %
      momentum_1m      : 1-month return %
      momentum_3m      : 3-month return %
      regime           : "BULL" | "BEAR" | "NEUTRAL"
      regime_strength  : 0-100
      key_signals      : list of (name, status) for top 3 driving signals
      plain_english    : one-paragraph summary for non-professionals
    """
    if horizons_days is None:
        horizons_days = [30, 60, 90]

    ps = price_series.dropna()
    last_price = float(ps.iloc[-1]) if len(ps) > 0 else 100.0

    # ── Momentum ──────────────────────────────────────────────────────────────
    def _ret(n: int) -> float:
        if len(ps) >= n:
            return float((ps.iloc[-1] / ps.iloc[-n]) - 1)
        return 0.0

    mom_1m = _ret(22)
    mom_3m = _ret(66)
    mom_6m = _ret(132)
    mom_1y = _ret(252)

    # ── Historical Volatility ─────────────────────────────────────────────────
    if len(ps) >= 30:
        daily_rets = ps.pct_change().dropna()
        ann_vol = float(daily_rets.std() * np.sqrt(252))
    else:
        ann_vol = 0.25  # default 25% vol

    # ── Base Bull Probability from Confluence ─────────────────────────────────
    # Map 0-100 confluence → 5-95% bull probability (logistic-like mapping)
    # Score=50 → ~50% bull, Score=75 → ~75% bull, Score=25 → ~25% bull
    base_bull = np.clip(confluence_score, 5.0, 95.0)

    # ── Momentum Adjustment ───────────────────────────────────────────────────
    # Positive 1M momentum adds up to +8 ppt; negative subtracts up to -8 ppt
    mom_adj = np.clip(mom_1m * 0.4 + mom_3m * 0.2, -0.08, 0.08) * 100

    # ── Signal Trend Consistency Adjustment ──────────────────────────────────
    # If >60% of signals are one-directional, add conviction bonus
    n_bull = sum(1 for v in signal_scores.values() if v.get("status") == "bullish")
    n_bear = sum(1 for v in signal_scores.values() if v.get("status") == "bearish")
    n_sig  = max(1, len(signal_scores))
    consistency_adj = 0.0
    if n_bull / n_sig > 0.60:
        consistency_adj = +5.0
    elif n_bear / n_sig > 0.60:
        consistency_adj = -5.0

    final_bull = float(np.clip(base_bull + mom_adj + consistency_adj, 5.0, 95.0))
    final_bear = float(np.clip(100 - final_bull - 10, 3.0, 90.0))
    final_neutral = max(2.0, 100.0 - final_bull - final_bear)

    # Normalise so they sum to 100
    total = final_bull + final_bear + final_neutral
    final_bull    = round(final_bull    / total * 100, 1)
    final_bear    = round(final_bear    / total * 100, 1)
    final_neutral = round(100.0 - final_bull - final_bear, 1)

    # ── Per-Horizon Outputs ───────────────────────────────────────────────────
    horizons = []
    for days in horizons_days:
        t = days / 252.0
        vol_range = ann_vol * np.sqrt(t)

        # Expected drift: bull_prob pushes price toward bull centre
        drift = (final_bull - final_bear) / 100.0 * ann_vol * t

        price_mid  = round(last_price * (1 + drift), 2)
        price_high = round(last_price * (1 + drift + vol_range), 2)
        price_low  = round(last_price * (1 + drift - vol_range), 2)

        horizons.append({
            "days":        days,
            "label":       f"{days}D",
            "bull_pct":    final_bull,
            "bear_pct":    final_bear,
            "neutral_pct": final_neutral,
            "price_low":   price_low,
            "price_mid":   price_mid,
            "price_high":  price_high,
        })

    # ── Regime ───────────────────────────────────────────────────────────────
    regime = "BULL" if final_bull > 60 else ("BEAR" if final_bear > 60 else "NEUTRAL")
    regime_strength = round(max(final_bull, final_bear), 1)

    # ── Key Signals ──────────────────────────────────────────────────────────
    # Sort by absolute score deviation from 50 — highest deviation = most informative
    key_sigs = sorted(
        [(sid, v) for sid, v in signal_scores.items()],
        key=lambda x: abs(x[1].get("score", 50) - 50),
        reverse=True,
    )[:3]

    # ── Plain-English Summary ─────────────────────────────────────────────────
    trend_word  = "rising" if mom_1m > 0.02 else ("falling" if mom_1m < -0.02 else "flat")
    regime_word = "bullish" if regime == "BULL" else ("bearish" if regime == "BEAR" else "mixed")
    conviction_word = (
        "strong" if regime_strength > 70 else
        "moderate" if regime_strength > 55 else
        "weak"
    )

    plain_english = (
        f"Based on {n_sig} independent alternative data signals, the current macro environment "
        f"is {regime_word} for this ticker with {conviction_word} conviction "
        f"({regime_strength:.0f}% probability). "
        f"The stock has been {trend_word} over the past month "
        f"({mom_1m:+.1%}). "
        f"Over the next 30 days, the model estimates a {final_bull:.0f}% chance of upside "
        f"and {final_bear:.0f}% chance of downside, "
        f"with a price range of ${price_low:.2f}–${price_high:.2f} (±{ann_vol*np.sqrt(30/252):.1%} "
        f"based on {ann_vol:.0%} annualised vol). "
        f"This is NOT a buy/sell recommendation — it's a probability estimate from macro signals."
    ).replace("$", "\\$")  # escape for markdown

    return {
        "horizons":         horizons,
        "annual_vol_pct":   round(ann_vol * 100, 1),
        "momentum_1m":      round(mom_1m * 100, 2),
        "momentum_3m":      round(mom_3m * 100, 2),
        "momentum_6m":      round(mom_6m * 100, 2),
        "momentum_1y":      round(mom_1y * 100, 2),
        "regime":           regime,
        "regime_strength":  regime_strength,
        "last_price":       last_price,
        "key_signals":      [(sid, v.get("status", "neutral")) for sid, v in key_sigs],
        "plain_english":    plain_english,
        "final_bull":       final_bull,
        "final_bear":       final_bear,
        "final_neutral":    final_neutral,
    }
