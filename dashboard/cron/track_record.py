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
# Bounded in time. The first live run sat silent for hours after starting:
# yfinance's threaded download waits for every ticker's thread with no time
# limit, and nothing here had a deadline. Now each batch download runs under
# BATCH_TIMEOUT_S (a batch that overruns is fetched again one ticker at a time,
# each call with its own 8s timeout), the whole study stops at --deadline-min,
# every batch logs its progress, and a stuck process dumps every thread's stack
# so the next stall names the line it is stuck on.
#
# Run manually from dashboard/:
#   python -m cron.track_record --force --limit 40

from __future__ import annotations

import argparse
import faulthandler
import gc
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

RERUN_DAYS = 28
HISTORY_YEARS = 10
BATCH = 40
BATCH_TIMEOUT_S = 180
DEADLINE_MIN = 60


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


def _rss_mb() -> float:
    try:
        from cron.score_universe import _rss_mb as rss
        return round(rss(), 1)
    except Exception:
        return 0.0


def _within(timeout: float, fn, *args):
    """fn(*args), or raise TimeoutError if it has not returned in `timeout`s.

    The call runs on a daemon thread, so a download that never returns is
    abandoned rather than holding the process (a ThreadPoolExecutor's workers
    are joined at exit, which would hang it there instead).
    """
    box: dict = {}

    def target():
        try:
            box["value"] = fn(*args)
        except BaseException as exc:  # handed back to the caller below
            box["error"] = exc

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError(f"no answer after {timeout:.0f}s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def study_in_batches(tickers: List[str], prices_batch, series, end, batch: int = BATCH, *,
                     one=None, batch_timeout: float = BATCH_TIMEOUT_S,
                     deadline: Optional[float] = None, clock=time.monotonic) -> dict:
    """The study over many tickers, fetching prices a batch at a time so ten
    years of daily prices for 500 stocks are never all in memory at once.

    `one(ticker, start, end)` fetches a single ticker; it is the fallback for a
    batch download that overruns `batch_timeout`. `deadline` (a `clock()`
    value) stops the study between batches; the result then says so and
    counts only the companies it reached.
    """
    from utils import exposure as ex
    from utils import track_record as tr

    start = (end - timedelta(days=365 * HISTORY_YEARS)).isoformat()
    _log("fetching_series", series=len(ex.FACTORS))
    levels = {f.series_id: series(f.series_id, start, end.isoformat()) for f in ex.FACTORS}
    pairs: List[dict] = []
    market_daily = None
    stopped = None
    n_batches = -(-len(tickers) // batch)
    for n, i in enumerate(range(0, len(tickers), batch), 1):
        if deadline is not None and clock() > deadline:
            stopped = "deadline"
            break
        chunk = tickers[i:i + batch]
        wanted = tuple(chunk + [ex.MARKET_TICKER])
        t0 = clock()
        try:
            daily = dict(_within(batch_timeout, prices_batch, wanted, start, end.isoformat()) or {})
            how = "batch"
        except TimeoutError:
            if one is None:
                raise
            how = "one_by_one"
            daily = {t: one(t, start, end.isoformat())
                     for t in wanted if t != ex.MARKET_TICKER or market_daily is None}
        # The cached batch fetcher would otherwise keep every batch's ten
        # years of prices in memory for the rest of the run.
        getattr(prices_batch, "clear", lambda: None)()
        if market_daily is None:
            market_daily = daily.get(ex.MARKET_TICKER)
        daily[ex.MARKET_TICKER] = market_daily
        before = len(pairs)
        pairs.extend(tr.study_pairs(daily, levels, end))
        _log("batch", n=f"{n}/{n_batches}", fetch=how, seconds=round(clock() - t0, 1),
             priced=sum(1 for t in chunk if daily.get(t) is not None and len(daily[t])),
             pairs=len(pairs) - before, rss_mb=_rss_mb())
        del daily
        gc.collect()
    out = tr.summarize(pairs)
    out.update(available=bool(pairs), end=str(end), universe=len(tickers),
               then_weeks=tr.THEN_WEEKS, next_weeks=tr.NEXT_WEEKS, stopped=stopped)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="run even if a recent result exists")
    ap.add_argument("--limit", type=int, default=0, help="only the first N tickers (testing)")
    ap.add_argument("--deadline-min", type=int, default=DEADLINE_MIN)
    args = ap.parse_args([] if argv is None else argv)

    if not os.environ.get("DATABASE_URL"):
        _log("refused", reason="DATABASE_URL is not set")
        return 2

    from cron.measure_library import load_constituents
    from utils import exposure as ex
    from utils import track_record as tr
    from utils.db import init_db
    from utils.fetchers import _get_fred_key, fetch_fred, fetch_price, fetch_prices_batch

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
    t0 = time.monotonic()
    _log("start", tickers=len(tickers), deadline_min=args.deadline_min, rss_mb=_rss_mb())
    # If anything still stalls, print every thread's stack every ten minutes,
    # so the log shows where instead of going quiet.
    faulthandler.dump_traceback_later(600, repeat=True)
    try:
        result = study_in_batches(tickers, fetch_prices_batch, fred, now.date(), one=fetch_price,
                                  deadline=t0 + args.deadline_min * 60)
    finally:
        faulthandler.cancel_dump_traceback_later()
    _log("finished", pairs=result["n_pairs"], stocks=result["n_stocks"],
         origins=len(result["origins"]), stopped=result["stopped"] or "no",
         seconds=round(time.monotonic() - t0))
    if not result["available"]:
        return 1   # nothing measured: an outage, not a quiet month
    return 0 if tr.save(result) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
