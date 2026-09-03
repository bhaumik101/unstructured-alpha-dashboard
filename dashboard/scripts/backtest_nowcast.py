#!/usr/bin/env python3
"""Backtest the macro nowcast against the naive forecast. Real data, no keys, no run.

    python scripts/backtest_nowcast.py
    python scripts/backtest_nowcast.py --json
    python scripts/backtest_nowcast.py --years 15

Requires FRED_API_KEY (and EIA_API_KEY for nothing here, but the fetch layer
shares a dispatcher). Run it on Render, or anywhere the keys are set — it
cannot run locally in this repo's default environment and says so rather than
producing a number from nothing.

WHAT IT ANSWERS
---------------
One question: does combining the pre-specified high-frequency signals predict
next month's Philadelphia Fed Manufacturing Index better than simply saying
"the same as last month"?

A positive skill score means yes. Zero or negative means no — which is a real
answer, arrived at in weeks on a well-posed question, and is publishable
exactly as it stands. The point of the pivot is that this question HAS an
answer; the equity-return question does not, at this sample size.

THE TARGET IS FETCHED FIRST-PRINT
--------------------------------
fetch_signal_series(..., point_in_time=True) returns each observation's INITIAL
release rather than today's revised value. A backtest fed revised data is
scoring itself against numbers nobody could have known at the time, and will
overstate. That is the single most common way a macro backtest cheats without
anyone intending it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import pandas as pd  # noqa: E402

from utils.config import SIGNALS  # noqa: E402
from utils.fetchers import fetch_signal_series  # noqa: E402
from utils.nowcast import (  # noqa: E402
    NOWCAST_PREDICTORS,
    NOWCAST_TARGET_NAME,
    NOWCAST_TARGET_SERIES,
    run_nowcast_backtest,
)


def _target_config() -> dict:
    """The Philadelphia Fed index, addressed by series id rather than by the
    config key — utils/config.py files it under "ism_pmi", which it is not."""
    return {
        "source": "fred",
        "series_id": NOWCAST_TARGET_SERIES,
        "name": NOWCAST_TARGET_NAME,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", type=int, default=15,
                    help="history window to request (default 15)")
    ap.add_argument("--lag", type=int, default=1,
                    help="feature lag in months; 1 = one-month-ahead forecast (default)")
    ap.add_argument("--json", action="store_true", help="emit JSON only")
    args = ap.parse_args()

    if not os.environ.get("FRED_API_KEY"):
        message = ("FRED_API_KEY is not set. This backtest reads real first-print "
                   "history and will not run without it — it does not fall back to "
                   "synthetic data.")
        if args.json:
            print(json.dumps({"available": False, "reason": message}, indent=2))
        else:
            print(f"[nowcast] {message}")
        return 2

    end = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=365 * args.years)).strftime("%Y-%m-%d")

    if not args.json:
        print(f"[nowcast] target : {NOWCAST_TARGET_NAME} ({NOWCAST_TARGET_SERIES})")
        print(f"[nowcast] window : {start} -> {end}   (first-print)")
        print(f"[nowcast] lag    : {args.lag} month(s)")

    # POINT-IN-TIME. Revised values would let the backtest score itself against
    # numbers that did not exist at the time.
    target = fetch_signal_series(_target_config(), start, end, point_in_time=True)
    if target is None or target.empty:
        reason = f"target {NOWCAST_TARGET_SERIES} returned no observations"
        print(json.dumps({"available": False, "reason": reason}, indent=2)
              if args.json else f"[nowcast] {reason}")
        return 1

    features: dict[str, pd.Series] = {}
    missing: list[str] = []
    for pred in NOWCAST_PREDICTORS:
        # Explicit FRED series where config cannot supply one; see the
        # Predictor block in utils/nowcast.py for why credit_spread is not
        # the config's hy_spread.
        cfg = SIGNALS.get(pred.signal) if pred.signal else {
            "source": "fred", "series_id": pred.fred, "name": pred.key,
        }
        if not cfg:
            missing.append(f"{pred.key} (not in SIGNALS)")
            continue
        try:
            # first_print PER PREDICTOR: market-derived series are never
            # revised, so a vintage request buys nothing and can cost history.
            series = fetch_signal_series(cfg, start, end, point_in_time=pred.first_print)
        except Exception as exc:
            missing.append(f"{pred.key} ({type(exc).__name__})")
            continue
        if series is None or series.empty:
            missing.append(f"{pred.key} (empty)")
            continue
        features[pred.key] = series

    if not args.json:
        print(f"[nowcast] fetched: {len(features)} of {len(NOWCAST_PREDICTORS)} predictors"
              + (f"   missing: {', '.join(missing)}" if missing else ""))

    result = run_nowcast_backtest(target, features, feature_lag_months=args.lag)
    payload = result.as_dict()
    payload["missing_features"] = missing
    payload["target_observations"] = int(len(target.dropna()))

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0 if result.available else 1

    if not result.available:
        print(f"[nowcast] UNAVAILABLE — {result.reason}")
        return 1

    verdict = "BEATS naive" if result.beats_naive else "does NOT beat naive"
    print()
    print(f"  months scored out-of-sample : {result.n_scored}")
    print(f"  predictors used             : {result.n_features}  ({', '.join(result.features_used)})")
    if result.features_dropped:
        print(f"  dropped, too little history : {'; '.join(result.features_dropped)}")
    print(f"  RMSE  model / naive         : {result.rmse_model} / {result.rmse_naive}")
    print(f"  MAE   model / naive         : {result.mae_model} / {result.mae_naive}")
    print(f"  skill (1 - model/naive)     : {result.skill}")
    print()
    print(f"  VERDICT: {verdict}")
    if not result.beats_naive:
        print("  A loss here is a real result. Report it; do not tune against this window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
