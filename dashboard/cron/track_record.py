#!/usr/bin/env python3
# cron/track_record.py
# Unstructured Alpha — run the out-of-sample track record study, monthly
#
# Measures the core exposures of every S&P 500 company (cron/sp500.csv) on
# three years of weekly data at origins every six months, measures them again
# on the following year, and publishes how well the first reading held up
# (utils/track_record.py). The result is added to research_results; the
# /evidence page reads the newest run.
#
# Runs as the last job of the weekly "weekly-universe" group, but only does
# the work once every RERUN_DAYS: the answer moves slowly and the study pulls
# ten years of prices. A run that finds nothing to publish exits non-zero so
# Render marks a provider outage as a failure.
#
# Run manually from dashboard/:
#   python -m cron.track_record --force --limit 40

from __future__ import annotations

import argparse
import gc
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

RERUN_DAYS = 28
HISTORY_YEARS = 10
BATCH = 40


def _log(event: str, **fields) -> None:
    print(f"[track_record] {event} " + " ".join(f"{k}={v}" for k, v in fields.items()), flush=True)


def is_fresh(latest: Optional[dict], now: datetime, days: int = RERUN_DAYS) -> bool:
    if not latest or not latest.get("computed_at"):
        return False
    try:
        at = datetime.fromisoformat(str(latest["computed_at"]))
    except ValueError:
        return False
    return now - at < timedelta(days=days)


def study_in_batches(tickers: List[str], prices_batch, series, end, batch: int = BATCH) -> dict:
    """The study over many tickers, fetching prices a batch at a time so ten
    years of daily prices for 500 stocks are never all in memory at once."""
    from utils import exposure as ex
    from utils import track_record as tr

    start = (end - timedelta(days=365 * HISTORY_YEARS)).isoformat()
    levels = {f.series_id: series(f.series_id, start, end.isoformat()) for f in ex.FACTORS}
    pairs: List[dict] = []
    market_daily = None
    for i in range(0, len(tickers), batch):
        chunk = tickers[i:i + batch]
        daily = dict(prices_batch(tuple(chunk + [ex.MARKET_TICKER]), start, end.isoformat()) or {})
        if market_daily is None:
            market_daily = daily.get(ex.MARKET_TICKER)
        daily[ex.MARKET_TICKER] = market_daily
        pairs.extend(tr.study_pairs(daily, levels, end))
        del daily
        gc.collect()
    out = tr.summarize(pairs)
    out.update(available=bool(pairs), end=str(end), universe=len(tickers),
               then_weeks=tr.THEN_WEEKS, next_weeks=tr.NEXT_WEEKS)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="run even if a recent result exists")
    ap.add_argument("--limit", type=int, default=0, help="only the first N tickers (testing)")
    args = ap.parse_args([] if argv is None else argv)

    if not os.environ.get("DATABASE_URL"):
        _log("refused", reason="DATABASE_URL is not set")
        return 2

    from cron.measure_library import load_constituents
    from utils import exposure as ex
    from utils import track_record as tr
    from utils.db import init_db
    from utils.fetchers import _get_fred_key, fetch_fred, fetch_prices_batch

    init_db()
    now = datetime.now(timezone.utc)
    if not args.force and is_fresh(tr.latest(), now):
        _log("skipped", reason=f"a result from the last {RERUN_DAYS} days exists")
        return 0

    key = _get_fred_key()

    def fred(sid, start, end):
        s = fetch_fred(sid, start, end, api_key=key) if key else None
        return s if s is not None and len(s) else ex.fetch_fred_public(sid, start, end)

    tickers = [t for t, _ in load_constituents()]
    if args.limit:
        tickers = tickers[:args.limit]
    result = study_in_batches(tickers, fetch_prices_batch, fred, now.date())
    _log("finished", pairs=result["n_pairs"], stocks=result["n_stocks"],
         origins=len(result["origins"]))
    if not result["available"]:
        return 1   # nothing measured: an outage, not a quiet month
    return 0 if tr.save(result) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
