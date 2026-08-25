#!/usr/bin/env python3
# cron/resolve_predictions.py
# Unstructured Alpha — Prediction Auto-Resolution Cron
#
# Runs as a Render Cron Job at 02:00 UTC on Mondays and Thursdays
# (render.yaml: "0 2 * * 1,4"). This header said "daily" while the blueprint
# said twice a week, which matters: the resolver's grace period is sized to the
# real cadence, not the documented one.
#
# Finds pending predictions whose forward windows (4w/8w/12w) have expired,
# fetches realized prices via yfinance, and marks them correct/incorrect. A
# prediction only leaves the pending pool once ALL THREE windows have closed,
# so nothing can resolve before it is twelve weeks old -- see
# utils.prediction_log.RESOLUTION_HORIZON_WEEKS.
#
# Run manually (from the dashboard/ directory):
#   python -m cron.resolve_predictions
# or:
#   python cron/resolve_predictions.py

import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the dashboard/ directory is on sys.path so `utils.*` imports work
_here = Path(__file__).resolve().parent.parent   # dashboard/
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from utils.db import init_db
from utils.prediction_log import resolve_pending


def main() -> None:
    print(f"[resolve] starting at {datetime.now(timezone.utc).isoformat()}", flush=True)

    init_db()

    # Resolve up to 200 predictions per run — generous cap for a nightly cron.
    # In steady state this processes only a handful of rows (one convergence
    # event per ticker per day at most), so the yfinance batch fetch stays fast.
    resolved = resolve_pending(max_resolve=200)

    print(f"[resolve] done — resolved={resolved}", flush=True)


if __name__ == "__main__":
    main()
