# utils/nowcast.py
# Unstructured Alpha — macro nowcast harness
#
# WHY THIS EXISTS
# ---------------
# The Confluence Score tries to predict equity returns from macro signals. That
# claim cannot be validated at this product's sample sizes: PR #211 found zero
# of 47 signals x 3 tickers surviving their own confidence interval, and the
# power analysis behind PR #214 showed why — 19 monthly signals resolve to ~23
# usable observations (minimum detectable |r| = 0.413) and 4 quarterly ones to
# ~7 (|r| = 0.754). The strongest correlation ever observed here was 0.19. The
# search could not have found anything.
#
# Nowcasting is the same data pointed at a question that CAN be answered. The
# target stops being a noisy weekly return and becomes a specific number
# published on a known date, so:
#
#   * the cadence mismatch disappears — a monthly signal predicting a monthly
#     release is a matched problem, where predicting weekly returns was not;
#   * there is a real baseline to beat (last month's value), so "did this help"
#     has an answer rather than a p-value nobody can interpret;
#   * a result arrives every month instead of every twelve weeks.
#
# WHAT THIS MODULE DELIBERATELY DOES NOT DO
# -----------------------------------------
# It does not claim an edge. It computes an out-of-sample error and compares it
# against the naive forecast. If the model does not beat "last month's value",
# `beats_naive` is False and that is the finding — reported, not tuned away.
#
# THE INFORMATION CUTOFF, STATED PRECISELY
# ----------------------------------------
# `feature_lag_months=1` (the default) predicts month M using high-frequency
# data through the END of month M-1. That is strictly a one-month-ahead
# FORECAST, and it is unambiguously free of look-ahead.
#
# A true nowcast (lag 0) would use partial within-month data up to the release
# date, which is more informative but requires per-release intra-month cutoffs
# that are not implemented here. Rather than approximate them and quietly leak
# days of future information, this module refuses lag 0. When the intra-month
# calendar is built, that is the moment to allow it — see nowcast_target_spec().

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# The target: Industrial Production, Manufacturing.
#
# It was the Philadelphia Fed index until 2026-09-03. Two measured reasons for
# moving, both recorded in docs/NOWCAST_RESULTS.md:
#
#   1. TIMING. The Philadelphia Fed index publishes inside its own month, so a
#      true nowcast of it (lag 0) is not leak-free. Industrial Production for
#      month M does not print until mid-M+1, which makes every input from month
#      M legitimately available — the whole task the pivot proposed.
#   2. IT IS BETTER USED AS A PREDICTOR. Regional Fed surveys ask firms the
#      same question the IP index later answers, roughly four weeks earlier.
#      Philadelphia and Empire State are now predictors, which they cannot be
#      while one of them is also the target.
#
# NOT ISM either way: the ISM Manufacturing PMI is licensed and is not
# redistributed on FRED, which is why utils/config.py's signal keyed "ism_pmi"
# actually carries the Philadelphia Fed series. The nowcast names what it uses.
NOWCAST_TARGET_SERIES = "IPMANSICS"
NOWCAST_TARGET_NAME = "Industrial Production: Manufacturing"

# Months between the end of the period a target describes and its publication.
#
# This is what makes lag 0 legitimate. Industrial Production for month M prints
# in the middle of M+1, so at the end of month M every high-frequency input for
# M is known and the official number is not — a genuine nowcast window. The
# Philadelphia Fed index has a release lag of ZERO by this definition (it
# publishes inside the month it describes), which is exactly why it is a
# predictor here and not the target.
NOWCAST_TARGET_RELEASE_LAG_MONTHS = 1

# PRE-SPECIFIED PREDICTORS, each with a mechanism, chosen before seeing a score.
#
# This is the discipline the Confluence Score never had: it weighted all 47
# signals by a hand-assigned 1-10 number (31 of them sat at 7 or 8) with no
# stated reason why any particular signal should move any particular ticker.
# Throwing all 24 high-frequency series at ~120 monthly observations would
# repeat that mistake in a new coat — with that many free parameters something
# always fits.
#
# Specified here rather than by SIGNALS key alone, because two of them cannot
# come from utils/config.py:
#
#   * credit_spread uses BAA10Y, not the config's hy_spread (BAMLH0A0HYM2).
#     FRED's own note on that series reads "Starting in April 2026, this series
#     will only include 3 years of observations" — ICE BofA changed the licence,
#     so it now returns 37 months however wide a window you ask for, and one
#     short series silently caps the whole design matrix through the inner join.
#     BAA10Y is Moody's Baa yield over the 10-year Treasury: the same mechanism
#     (credit conditions facing corporate borrowers), daily back to 1986, no cap.
#
#   * first_print is per-predictor. Market-derived series — yields, spreads,
#     futures, ETF prices — are never revised, so requesting a vintage buys
#     nothing. Statistical series are revised and must be read first-print or
#     the backtest scores itself against numbers nobody could have known.
#     rail_traffic pays 41 months of history for that and it is worth it.
#
# Adding a predictor because it improved the backtest is exactly the failure
# this list exists to prevent. If the set changes, the mechanism goes in `why`.


@dataclass(frozen=True)
class Predictor:
    key: str
    why: str
    signal: Optional[str] = None      # utils/config.py SIGNALS key
    fred: Optional[str] = None        # explicit FRED series id
    first_print: bool = False         # True only for genuinely revised series
    # RELEASE TIMING. A predictor is usable at lag 0 only if its month-M value
    # is published BEFORE the target's month-M value. Weekly and daily series
    # always qualify. Monthly ones must be checked against the calendar:
    # Industrial Production for month M prints mid-M+1, so anything landing
    # after that is look-ahead however innocent it looks.
    safe_at_lag0: bool = True


NOWCAST_PREDICTORS: tuple[Predictor, ...] = (
    # ── same construct, measured earlier ────────────────────────────────────
    # The strongest mechanism available and the practitioner standard: regional
    # Fed manufacturing surveys ask firms the same question the IP index later
    # answers, and publish around the 15th-20th of month M while national IP
    # for month M does not print until mid-M+1. This is not a discovered
    # correlation, it is the same measurement arriving sooner. It is also not
    # proprietary insight — everyone who nowcasts IP uses these.
    Predictor("empire_state", "NY Fed manufacturing survey — same construct, ~4 weeks earlier",
              fred="GACDISA066MSFRBNY", first_print=True, safe_at_lag0=True),
    Predictor("philly_fed", "Philadelphia Fed manufacturing survey — same construct, ~4 weeks earlier",
              fred="GACDFSA066MSFRBPHI", first_print=True, safe_at_lag0=True),

    # ── financial conditions lead real activity ─────────────────────────────
    # Adrian, Boyarchenko & Giannone (2019) on financial conditions and the
    # downside of the growth distribution; Gilchrist & Zakrajsek (2012) on
    # credit spreads predicting activity. NFCI is a weekly composite, so it is
    # available continuously rather than only at month end.
    Predictor("financial_conditions", "Chicago Fed NFCI — credit, leverage and risk conditions",
              fred="NFCI", first_print=False, safe_at_lag0=True),
    Predictor("credit_spread", "credit conditions facing industrial borrowers",
              fred="BAA10Y", first_print=False, safe_at_lag0=True),

    # ── labour adjusts before output is measured ────────────────────────────
    # Claims are the fastest hard labour series in existence. Hours are the
    # margin firms flex before headcount, and AWHMAN ships with the Employment
    # Situation on the first Friday of M+1 — ahead of IP's mid-month release.
    Predictor("initial_claims", "weekly initial claims — fastest hard labour series",
              fred="ICSA", first_print=True, safe_at_lag0=True),
    Predictor("continued_claims", "weekly continued claims — persistence of layoffs",
              fred="CCSA", first_print=True, safe_at_lag0=True),
    Predictor("mfg_hours", "manufacturing weekly hours — firms flex hours before headcount",
              fred="AWHMAN", first_print=True, safe_at_lag0=True),

    # ── physical movement of goods ──────────────────────────────────────────
    # NOT SAFE AT LAG 0, measured 2026-09-03: FRED's first-print series was last
    # observed at 2026-06 while the open nowcast month was 2026-08 — a
    # publication lag of roughly two months. Historically the value for month M
    # exists in the data, so a lag-0 backtest happily uses it; in real time it
    # does not exist until M+2. That is look-ahead, and it silently inflated the
    # first factor-model result until the cron ran and could not find the month.
    Predictor("rail_traffic", "intermodal freight volume — physical goods movement",
              signal="rail_traffic", first_print=True, safe_at_lag0=False),

    # ── market-derived, forward-looking but noisy ───────────────────────────
    Predictor("yield_curve", "financial conditions and expected activity",
              signal="yield_curve", first_print=False, safe_at_lag0=True),
    Predictor("copper", "the classic industrial-demand metal",
              signal="copper", first_print=False, safe_at_lag0=True),
    Predictor("crude_oil", "energy input cost and demand proxy",
              signal="crude_oil", first_print=False, safe_at_lag0=True),
    Predictor("semiconductor_etf", "manufacturing cycle for the sector that leads it",
              signal="semiconductor_etf", first_print=False, safe_at_lag0=True),
)

def predictors_for_lag(feature_lag_months: int) -> tuple[Predictor, ...]:
    """The predictors usable at a given lag.

    At lag 0 a predictor is only usable if its month-M value publishes before
    the target's does. Anything slower is look-ahead — it exists in history, so
    a backtest will use it happily, and it will not exist in real time.

    This is enforced structurally rather than by remembering, because the
    failure is invisible: the backtest simply scores better.
    """
    if feature_lag_months == 0:
        return tuple(p for p in NOWCAST_PREDICTORS if p.safe_at_lag0)
    return NOWCAST_PREDICTORS


# DELIBERATELY EXCLUDED, and why — each of these looks helpful and is not.
#
#   NEWORDER, AMTMNO, ISRATIO
#       Census orders and inventories. Advance Durable Goods for month M
#       releases ~26 days after month end, i.e. AFTER Industrial Production for
#       month M. Using them at lag 0 is look-ahead, however mechanically sound
#       "orders lead production" sounds.
#
#   IPG2211S (IP: Utilities), IPMANSICS when the target is INDPRO
#       Components of the target index. Regressing a total on part of itself.
#
#   WEI (NY Fed Weekly Economic Index)
#       Itself a nowcast. Including it would mean re-serving the New York Fed's
#       model and calling the output ours.
#
#   hy_spread / BAMLH0A0HYM2
#       ICE BofA capped it to a rolling 3 years in April 2026. Replaced by
#       BAA10Y, which carries the same mechanism without the cap.

# Backwards-compatible view for callers that only want the ids.
NOWCAST_FEATURE_SIGNALS: tuple[str, ...] = tuple(p.key for p in NOWCAST_PREDICTORS)

# A predictor must overlap this fraction of the target's months to be used.
#
# THE BUG THIS EXISTS TO PREVENT. build_design inner-joins every feature, so the
# SHORTEST one sets the sample for all of them. Run against real data on
# 2026-09-03, a 136-month target collapsed to 32 aligned months because
# hy_spread returned 37 (licence cap) and lumber_futures 50 (the CME relaunched
# lumber as LBR in 2022). Seven predictors with a decade of history were thrown
# away by two that did not have one, and the harness could only report that it
# had too little data — not that two features had eaten the rest.
#
# Short predictors are now dropped and NAMED, so the trade is visible instead of
# silent. 0.8 keeps anything covering four fifths of the target.
MIN_FEATURE_COVERAGE = 0.8

# Ridge penalty. FIXED, not tuned. With ~120 monthly observations and 20-odd
# candidate features, selecting alpha against the evaluation window is the
# fastest way to manufacture a result that does not survive contact with new
# data. A stated prior that was never fitted is more defensible than a tuned
# number whose tuning nobody can audit. Selecting it by inner cross-validation
# INSIDE each training window is the correct upgrade; it is not done here.
RIDGE_ALPHA = 10.0

# Months of history required before the first out-of-sample prediction. Three
# years is enough to estimate a handful of coefficients without pretending a
# 12-observation fit means anything.
MIN_TRAIN_MONTHS = 36


@dataclass
class NowcastScore:
    """Out-of-sample scorecard for one target. Every field is measured."""
    target: str = NOWCAST_TARGET_NAME
    series_id: str = NOWCAST_TARGET_SERIES
    n_features: int = 0
    n_train_initial: int = 0
    n_scored: int = 0
    feature_lag_months: int = 1
    estimator: str = "ridge"
    rmse_model: Optional[float] = None
    rmse_naive: Optional[float] = None
    mae_model: Optional[float] = None
    mae_naive: Optional[float] = None
    skill: Optional[float] = None          # 1 - rmse_model/rmse_naive; >0 beats naive
    beats_naive: Optional[bool] = None
    # Diebold-Mariano on the squared-error differential. Skill alone is
    # dominated by a handful of crisis months and will report a confident
    # positive off three observations; this says whether the difference is
    # distinguishable from noise at all.
    dm_stat: Optional[float] = None
    dm_p_value: Optional[float] = None
    significant: Optional[bool] = None
    months_model_closer: Optional[float] = None
    available: bool = False
    reason: str = ""
    features_used: List[str] = field(default_factory=list)
    features_dropped: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _unavailable(reason: str, **kw) -> NowcastScore:
    """Explicitly unavailable, never a fabricated zero.

    A score of 0.0 and "there was not enough data to compute a score" are
    completely different claims; this module never lets the second render as
    the first.
    """
    return NowcastScore(available=False, reason=reason, **kw)


def monthly_aggregate(series: pd.Series, how: str = "mean") -> pd.Series:
    """Collapse a daily/weekly series to one observation per calendar month.

    Indexed by MONTH START so it lines up with a monthly release for that
    month. Empty in, empty out — never interpolated: a month with no
    observations must stay missing rather than inherit a neighbour's value,
    because an invented input is indistinguishable from a real one downstream.
    """
    if series is None or len(series) == 0:
        return pd.Series(dtype=float)
    s = series.dropna()
    if s.empty:
        return pd.Series(dtype=float)
    if not isinstance(s.index, pd.DatetimeIndex):
        try:
            s.index = pd.to_datetime(s.index)
        except Exception:
            return pd.Series(dtype=float)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    try:
        s.index = s.index.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    agg = s.resample("MS").mean() if how == "mean" else s.resample("MS").last()
    return agg.dropna()


def build_design(
    target: pd.Series,
    features: Dict[str, pd.Series],
    feature_lag_months: int = 1,
    min_coverage: float = MIN_FEATURE_COVERAGE,
    target_release_lag_months: int = 0,
) -> tuple[pd.DataFrame, pd.Series, List[str]]:
    """Assemble the aligned (X, y) for a one-month-ahead forecast of `target`.

    y is the target's monthly LEVEL. X is each feature's monthly change, shifted
    forward by `feature_lag_months` so the row for month M carries only
    information from month M-lag and earlier.

    Feature CHANGES rather than levels, deliberately: most of these series are
    near-random-walks in level, so a level regression mostly rediscovers a
    common trend and reports a flattering in-sample fit that does not survive
    differencing. The target stays in levels because the scorecard compares
    against the naive level forecast, which is what a reader cares about.

    Returns (X, y, dropped) — `dropped` names every predictor excluded for
    insufficient overlap, so a shrunken model is never silent.

    Raises ValueError on feature_lag_months < 1 — see the module docstring on
    why lag 0 is refused rather than approximated.
    """
    if feature_lag_months < 0:
        raise ValueError("feature_lag_months cannot be negative")
    if feature_lag_months == 0 and target_release_lag_months < 1:
        raise ValueError(
            "feature_lag_months=0 is a true nowcast and is only leak-free when the "
            "target publishes AFTER the month it describes. Pass "
            "target_release_lag_months>=1 to assert that (Industrial Production "
            "for month M prints mid-M+1, so it qualifies; the Philadelphia Fed "
            "index publishes inside its own month and does not). Allowing lag 0 "
            "without that assertion leaks days of future data silently."
        )

    y = monthly_aggregate(target, how="last")
    if y.empty:
        return pd.DataFrame(), pd.Series(dtype=float), []

    # Coverage is measured against the target's own span, then short predictors
    # are dropped BEFORE the join. Doing it after would be too late: the inner
    # join has already truncated everything to the shortest series by then.
    needed = max(1, int(round(len(y) * min_coverage)))
    cols: Dict[str, pd.Series] = {}
    dropped: List[str] = []
    for name, raw in (features or {}).items():
        monthly = monthly_aggregate(raw, how="mean")
        overlap = int(monthly.index.isin(y.index).sum()) if not monthly.empty else 0
        if overlap < needed:
            dropped.append(f"{name} ({overlap}/{len(y)} months, needs {needed})")
            continue
        # Change, then shift into the future so month M sees month M-lag.
        cols[name] = monthly.diff().shift(feature_lag_months)

    if not cols:
        return pd.DataFrame(), pd.Series(dtype=float), dropped

    X = pd.DataFrame(cols).sort_index()
    frame = X.join(y.rename("__y__"), how="inner").dropna()
    if frame.empty:
        return pd.DataFrame(), pd.Series(dtype=float), dropped

    y_aligned = frame.pop("__y__")
    return frame, y_aligned, dropped


def ridge_coefficients(X: np.ndarray, y: np.ndarray, alpha: float = RIDGE_ALPHA) -> np.ndarray:
    """Closed-form ridge on already-standardised X and centred y.

    Implemented directly rather than pulled from scikit-learn: this repo ships
    numpy/scipy only, and a five-line solve nobody has to trust a dependency for
    is easier to audit than an import. The intercept is NOT penalised — it is
    handled by centring y outside this function.
    """
    n_features = X.shape[1]
    gram = X.T @ X + alpha * np.eye(n_features)
    try:
        return np.linalg.solve(gram, X.T @ y)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(gram) @ (X.T @ y)


# Number of common factors extracted from the predictor block.
#
# FIXED A PRIORI at three, not selected against the evaluation window. Stock &
# Watson's work on large macro panels repeatedly finds a small number of factors
# — typically two to four — carrying most of the comovement, and the twelve
# predictors here span four blocks (surveys, labour, financial conditions,
# physical activity) that plausibly load on fewer common drivers than that.
#
# Choosing k by a variance rule computed INSIDE each training window is the
# natural refinement and would still be leak-free. Choosing it by which value
# scored best would not be, and is why this is a constant.
N_FACTORS = 3


def extract_factors(X_std: np.ndarray, n_factors: int = N_FACTORS) -> np.ndarray:
    """Loadings for the leading `n_factors` principal components of X_std.

    X_std must already be standardised on the TRAINING window alone. Returns a
    (features x factors) matrix; project with `X_std @ loadings`.

    WHY FACTORS RATHER THAN MORE REGULARISATION. Twelve macro predictors are
    not twelve independent pieces of information — regional surveys, claims and
    financial conditions all move with the same cycle. Ridge handles that
    collinearity by shrinking every coefficient; a factor model handles it by
    admitting there are only a few underlying drivers, which both denoises the
    inputs and cuts the effective parameter count from twelve to three. On ~100
    training months that difference is the whole ballgame.

    Sign indeterminacy of the SVD is irrelevant here: the regression is refitted
    on the factors inside every window, so a flipped component flips its
    coefficient too.
    """
    n_factors = max(1, min(int(n_factors), X_std.shape[1]))
    try:
        _u, _s, vt = np.linalg.svd(X_std, full_matrices=False)
    except np.linalg.LinAlgError:
        return np.eye(X_std.shape[1])[:, :n_factors]
    return vt[:n_factors].T


def walk_forward(
    X: pd.DataFrame,
    y: pd.Series,
    min_train: int = MIN_TRAIN_MONTHS,
    alpha: float = RIDGE_ALPHA,
    estimator: str = "ridge",
    n_factors: int = N_FACTORS,
) -> pd.DataFrame:
    """Expanding-window out-of-sample predictions, one month at a time.

    For each month t >= min_train the model is refitted on rows 0..t-1 ONLY and
    then asked for t. Nothing about row t — not its target, not its scale —
    touches the fit.

    THE LEAK THIS AVOIDS. Standardising X over the whole sample before
    splitting is the classic error: the test row's mean and standard deviation
    then encode the future, and out-of-sample error improves for a reason that
    has nothing to do with predictive power. Here mu/sigma are computed inside
    the loop, from the training slice alone.

    The model predicts the CHANGE from the previous level; the returned
    prediction is that change added back to the last observed level, so it is
    directly comparable with the naive forecast in the same column units.
    """
    rows: List[dict] = []
    if X.empty or len(y) != len(X) or len(y) <= min_train:
        return pd.DataFrame(columns=["actual", "predicted", "naive"])

    X_all = X.to_numpy(dtype=float)
    y_all = y.to_numpy(dtype=float)

    for t in range(min_train, len(y_all)):
        X_train, y_train = X_all[:t], y_all[:t]
        prev_level = y_all[t - 1]

        # Target the CHANGE, so the model is never rewarded for rediscovering
        # persistence — which is exactly what the naive baseline already is.
        y_train_change = np.diff(y_train)
        X_train_for_change = X_train[1:]
        if len(y_train_change) < 8:
            continue

        mu = X_train_for_change.mean(axis=0)
        sigma = X_train_for_change.std(axis=0, ddof=0)
        sigma[sigma == 0] = 1.0

        Xs = (X_train_for_change - mu) / sigma
        y_centre = y_train_change.mean()
        x_test = (X_all[t] - mu) / sigma

        if estimator == "factor":
            # Loadings come from the TRAINING window only, like mu and sigma.
            # Fitting them on the full panel would leak the test month's
            # covariance into the projection — the same standardisation leak in
            # a less obvious costume.
            loadings = extract_factors(Xs, n_factors=n_factors)
            factors_train = Xs @ loadings
            beta = ridge_coefficients(factors_train, y_train_change - y_centre, alpha=alpha)
            predicted_change = float((x_test @ loadings) @ beta + y_centre)
        else:
            beta = ridge_coefficients(Xs, y_train_change - y_centre, alpha=alpha)
            predicted_change = float(x_test @ beta + y_centre)

        # SANITY CLAMP, specified a priori and not because it improved a score.
        #
        # A linear model handed inputs far outside their training range
        # extrapolates without limit. Measured on real data 2026-09-03: for
        # April 2020 this predicted a change of +182 on a diffusion index whose
        # month-over-month change had never exceeded +71 in the sample, giving a
        # level of +169.6 against an actual of -56.6. That is not a forecast, it
        # is the model leaving the region where it has any evidence at all.
        #
        # A change larger than anything ever observed in training is therefore
        # clipped back to the observed envelope. This constrains only the
        # pathological tail; ordinary months are untouched. It is reported both
        # ways in the PR so the effect is visible rather than absorbed.
        lo, hi = float(y_train_change.min()), float(y_train_change.max())
        predicted_change = min(max(predicted_change, lo), hi)

        rows.append({
            "date": y.index[t],
            "actual": float(y_all[t]),
            "predicted": prev_level + predicted_change,
            "naive": prev_level,
        })

    if not rows:
        return pd.DataFrame(columns=["actual", "predicted", "naive"])
    out = pd.DataFrame(rows).set_index("date")
    return out


def score_predictions(frame: pd.DataFrame) -> dict:
    """RMSE/MAE for model and naive, plus the skill score.

    skill = 1 - rmse_model / rmse_naive. Positive means the model beat "last
    month's value"; zero or negative means it did not, which is a legitimate
    and publishable outcome.
    """
    if frame is None or frame.empty:
        return {"rmse_model": None, "rmse_naive": None, "mae_model": None,
                "mae_naive": None, "skill": None, "beats_naive": None, "n_scored": 0,
                "dm_stat": None, "dm_p_value": None, "significant": None,
                "months_model_closer": None}

    err_m = (frame["predicted"] - frame["actual"]).to_numpy(dtype=float)
    err_n = (frame["naive"] - frame["actual"]).to_numpy(dtype=float)
    rmse_m = float(np.sqrt(np.mean(err_m ** 2)))
    rmse_n = float(np.sqrt(np.mean(err_n ** 2)))
    skill = None if rmse_n == 0 else float(1.0 - rmse_m / rmse_n)

    # DIEBOLD-MARIANO, and why the scorecard refuses to report skill without it.
    #
    # Measured 2026-09-03 on IP: Manufacturing at lag 0: skill read +0.280,
    # which looks like a 28% error reduction over a random walk across 100
    # months. It was not. DM p = 0.20, it did not survive correction for the
    # six configurations searched, the model was closer to the truth in only
    # 45% of months, and excluding 2020 the skill inverted to -0.105. The whole
    # figure came from three crisis months where the naive forecast was
    # catastrophically wrong and the model was merely very wrong — RMSE squares
    # errors, so a handful of outliers own the result.
    #
    # months_model_closer is reported alongside for the same reason: it is the
    # median-flavoured companion to an RMSE that only reports the mean.
    with np.errstate(invalid="ignore", divide="ignore"):
        loss_diff = err_m ** 2 - err_n ** 2
        denom = float(np.std(loss_diff, ddof=1)) / np.sqrt(len(loss_diff)) if len(loss_diff) > 1 else 0.0
        dm = float(np.mean(loss_diff) / denom) if denom > 0 else None
    if dm is None or not np.isfinite(dm):
        dm, dm_p = None, None
    else:
        from scipy import stats as _st
        dm_p = float(2.0 * (1.0 - _st.norm.cdf(abs(dm))))

    closer = float(np.mean(np.abs(err_m) < np.abs(err_n)))

    return {
        "dm_stat": None if dm is None else round(dm, 4),
        "dm_p_value": None if dm_p is None else round(dm_p, 6),
        "significant": None if dm_p is None else bool(dm_p < 0.05 and rmse_m < rmse_n),
        "months_model_closer": round(closer, 4),
        "rmse_model": round(rmse_m, 4),
        "rmse_naive": round(rmse_n, 4),
        "mae_model": round(float(np.mean(np.abs(err_m))), 4),
        "mae_naive": round(float(np.mean(np.abs(err_n))), 4),
        "skill": None if skill is None else round(skill, 4),
        "beats_naive": None if skill is None else bool(skill > 0),
        "n_scored": int(len(frame)),
    }


def run_nowcast_backtest(
    target: pd.Series,
    features: Dict[str, pd.Series],
    feature_lag_months: int = 1,
    min_train: int = MIN_TRAIN_MONTHS,
    alpha: float = RIDGE_ALPHA,
    min_coverage: float = MIN_FEATURE_COVERAGE,
    target_release_lag_months: int = 0,
    estimator: str = "ridge",  # scripts default to "factor"; see N_FACTORS
    n_factors: int = N_FACTORS,
) -> NowcastScore:
    """End-to-end: align, walk forward, score. Never raises on thin data."""
    try:
        X, y, dropped = build_design(
            target, features, feature_lag_months=feature_lag_months,
            min_coverage=min_coverage,
            target_release_lag_months=target_release_lag_months,
        )
    except ValueError as exc:
        return _unavailable(str(exc), feature_lag_months=feature_lag_months)

    if X.empty:
        return _unavailable(
            "no predictor covered enough of the target's span",
            feature_lag_months=feature_lag_months, features_dropped=dropped,
        )
    if len(y) <= min_train:
        return _unavailable(
            f"only {len(y)} aligned months; {min_train + 1} needed before the first "
            f"out-of-sample month",
            n_features=X.shape[1], feature_lag_months=feature_lag_months,
            features_used=list(X.columns), features_dropped=dropped,
        )

    frame = walk_forward(X, y, min_train=min_train, alpha=alpha,
                         estimator=estimator, n_factors=n_factors)
    scored = score_predictions(frame)
    if not scored["n_scored"]:
        return _unavailable(
            "walk-forward produced no scored months",
            n_features=X.shape[1], feature_lag_months=feature_lag_months,
            features_used=list(X.columns), features_dropped=dropped,
        )

    return NowcastScore(
        n_features=X.shape[1],
        n_train_initial=min_train,
        feature_lag_months=feature_lag_months,
        available=True,
        reason="",
        features_used=list(X.columns),
        features_dropped=dropped,
        estimator=estimator,
        **scored,
    )
