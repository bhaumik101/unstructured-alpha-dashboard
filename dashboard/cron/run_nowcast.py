#!/usr/bin/env python3
"""Monthly: score last month's nowcast, then publish this month's.

Render cron, 8th of each month. That date is not arbitrary — it is the only
window where every input exists and the answer does not:

    first Friday   Employment Situation publishes AWHMAN for the month
    the 8th        THIS JOB RUNS
    ~the 15th      Industrial Production publishes the month being nowcast

Running on the 1st looked right and is wrong: AWHMAN for the month has not
published yet, and the job correctly refuses rather than dropping a required
predictor. Running after the 15th would not be a nowcast at all.

    resolve  fill `actual` for any logged month that has since published
    publish  compute and record the nowcast for the month that just ended

ORDER MATTERS, the same way it does in cron/resolve_predictions.py: scoring
runs FIRST so a month is never published and scored in the same pass, which
would make the timestamps meaningless.

WHY THIS CRON IS THE POINT
docs/NOWCAST_RESULTS.md records ten configurations searched against 2011-2026.
That history is spent — the best result there is the best of ten tries. This
job builds the only record that is not: an estimate written down before the
number exists, scored against what printed. Twelve months of it is worth more
than anything further extractable from the backtest.

Nothing here may be tuned while the record accumulates. Changing the target,
the predictors, the lag or the model restarts the clock.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import pandas as pd  # noqa: E402

from utils.config import SIGNALS  # noqa: E402
from utils.db import init_db  # noqa: E402
from utils.fetchers import fetch_signal_series  # noqa: E402
from utils.nowcast import (  # noqa: E402
    MIN_FEATURE_COVERAGE,
    NOWCAST_TARGET_RELEASE_LAG_MONTHS,
    NOWCAST_PREDICTORS,
    predictors_for_lag,
    NOWCAST_TARGET_NAME,
    NOWCAST_TARGET_SERIES,
    N_FACTORS,
    RIDGE_ALPHA,
    build_design,
    extract_factors,
    monthly_aggregate,
    ridge_coefficients,
)
from utils.nowcast_log import (  # noqa: E402
    get_forward_record,
    log_nowcast,
    next_target_month,
    resolve_nowcasts,
)

# The locked specification. Duplicated here as a comment rather than a config
# knob on purpose: a cron flag that changes the model is a tuning surface, and
# this record is only worth keeping if the specification cannot drift.
#
#   target      IPMANSICS (Industrial Production: Manufacturing)
#   predictors  the twelve in NOWCAST_PREDICTORS
#   lag         0 — leak-free, IP for month M prints mid-M+1
#   model       factor, 3 components, RIDGE_ALPHA = 10.0
#   baseline    last published level
ESTIMATOR = "factor"
HISTORY_YEARS = 15


def _window() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return ((now - timedelta(days=365 * HISTORY_YEARS)).strftime("%Y-%m-%d"),
            now.strftime("%Y-%m-%d"))


def _fetch_target(start: str, end: str) -> pd.Series:
    return fetch_signal_series(
        {"source": "fred", "series_id": NOWCAST_TARGET_SERIES,
         "name": NOWCAST_TARGET_NAME},
        start, end, point_in_time=True,
    )


def _fetch_predictors(start: str, end: str) -> dict:
    out = {}
    for pred in predictors_for_lag(0):
        cfg = SIGNALS.get(pred.signal) if pred.signal else {
            "source": "fred", "series_id": pred.fred, "name": pred.key,
        }
        if not cfg:
            continue
        try:
            series = fetch_signal_series(cfg, start, end, point_in_time=pred.first_print)
        except Exception as exc:
            print(f"[nowcast] {pred.key} fetch failed: {type(exc).__name__}", flush=True)
            continue
        if series is not None and not series.empty:
            out[pred.key] = series
    return out


def main() -> int:
    print(f"[nowcast] starting at {datetime.now(timezone.utc).isoformat()}", flush=True)

    if not os.environ.get("FRED_API_KEY"):
        print("[nowcast] FRED_API_KEY is not set — cannot run. Not falling back "
              "to anything.", flush=True)
        return 2

    init_db()
    start, end = _window()

    target = _fetch_target(start, end)
    if target is None or target.empty:
        print(f"[nowcast] target {NOWCAST_TARGET_SERIES} returned nothing", flush=True)
        return 1
    target_monthly = monthly_aggregate(target, how="last")
    if target_monthly.empty:
        print("[nowcast] target has no monthly observations", flush=True)
        return 1

    # ── 1. score anything that has published since the last run ─────────────
    def _actual_for(_series: str, month: str):
        stamp = pd.Timestamp(f"{month}-01")
        return float(target_monthly.loc[stamp]) if stamp in target_monthly.index else None

    resolve_nowcasts(_actual_for)

    # ── 2. publish this month's estimate ────────────────────────────────────
    last_published = str(target_monthly.index[-1])[:7]
    target_month = next_target_month(last_published)
    print(f"[nowcast] target published through {last_published}; "
          f"nowcasting {target_month}", flush=True)

    features = _fetch_predictors(start, end)
    print(f"[nowcast] fetched {len(features)}/{len(predictors_for_lag(0))} lag-0-safe "
          f"predictors", flush=True)

    X, y, dropped = build_design(
        target_monthly, features, feature_lag_months=0,
        min_coverage=MIN_FEATURE_COVERAGE,
        # Asserts the target publishes after the month it describes, which is
        # what makes lag 0 leak-free here. See the constant's justification.
        target_release_lag_months=NOWCAST_TARGET_RELEASE_LAG_MONTHS,
    )
    if dropped:
        print(f"[nowcast] dropped for short history: {'; '.join(dropped)}", flush=True)
    if X.empty or len(y) < 40:
        print(f"[nowcast] not enough aligned history to fit ({len(y)} months)", flush=True)
        return 1

    # The row for target_month needs this month's feature values, which the
    # design only carries once the target row exists. Build it directly.
    feature_row = {}
    stamp = pd.Timestamp(f"{target_month}-01")
    for name in X.columns:
        monthly = monthly_aggregate(features[name], how="mean").diff()
        if stamp not in monthly.index or pd.isna(monthly.loc[stamp]):
            print(f"[nowcast] {name} has no value for {target_month} — cannot "
                  f"nowcast without it", flush=True)
            return 1
        feature_row[name] = float(monthly.loc[stamp])

    # Fit on everything observed, exactly as walk_forward does at its last step.
    import numpy as np

    X_all = X.to_numpy(dtype=float)
    y_all = y.to_numpy(dtype=float)
    y_change = np.diff(y_all)
    X_for_change = X_all[1:]

    mu = X_for_change.mean(axis=0)
    sigma = X_for_change.std(axis=0, ddof=0)
    sigma[sigma == 0] = 1.0
    Xs = (X_for_change - mu) / sigma
    y_centre = y_change.mean()

    loadings = extract_factors(Xs, n_factors=N_FACTORS)
    beta = ridge_coefficients(Xs @ loadings, y_change - y_centre, alpha=RIDGE_ALPHA)

    x_test = (np.array([feature_row[c] for c in X.columns]) - mu) / sigma
    predicted_change = float((x_test @ loadings) @ beta + y_centre)
    # Same a-priori clamp the backtest uses: never forecast a change larger than
    # anything ever observed.
    predicted_change = min(max(predicted_change, float(y_change.min())),
                           float(y_change.max()))

    naive = float(y_all[-1])
    predicted = naive + predicted_change

    written = log_nowcast(
        target_series=NOWCAST_TARGET_SERIES,
        target_month=target_month,
        predicted=predicted,
        naive=naive,
        estimator=ESTIMATOR,
        n_features=X.shape[1],
        features_used=list(X.columns),
    )
    print(f"[nowcast] {target_month}: predicted={predicted:.3f} naive={naive:.3f} "
          f"({'recorded' if written else 'already on record'})", flush=True)

    record = get_forward_record(NOWCAST_TARGET_SERIES)
    print(f"[nowcast] forward record: {record['n_logged']} logged, "
          f"{record['n_scored']} scored"
          + (f", skill {record['skill']}" if record["skill"] is not None
             else f" — {record['note']}"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
