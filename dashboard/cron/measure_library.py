#!/usr/bin/env python3
# cron/measure_library.py
# Unstructured Alpha — measure the S&P 500 into the stock library, weekly
#
# WHY
# ---
# The stock library (utils/stock_library.py) only filled when someone opened a
# stock's page, so the public /exposure pages -- and the /ticker redirects that
# depend on them -- existed for a handful of names. This measures every S&P 500
# company once a week with the same engine and the same method as the app, and
# refreshes anything already in the library, so the pages exist before anyone
# asks for them and history builds up one row per data week.
#
# HOW
# ---
# The five economic series are fetched once per run, not once per stock. Prices
# are fetched in batches, each with the market series, and every stock is then
# measured as a one-holding, 100% portfolio -- exactly what the stock page does.
#
# RULES
# -----
#   * A stock that can't be measured is skipped and counted, never filled in.
#   * Stalest first: never-measured stocks, then the oldest. A run that stops on
#     its deadline or memory guard picks up where it left off next week.
#   * Anything measured in the last --fresh-days is left alone, so a re-run the
#     same week does nothing rather than repeating the work.
#   * Exits non-zero when it measured nothing at all, so Render marks a provider
#     outage as a failed run instead of a quiet success.
#   * Runs as PASSES, each a fresh process (see _supervise). One process stops
#     on its memory guard after ~75 stocks in ~3 minutes; the deadline is 40.
#     Live on 2026-10-06 that meant 50 new stocks a week, and a stock measured
#     once waited six weeks for its refresh behind every never-measured one.
#
# The list of companies is cron/sp500.csv, a checked-in snapshot of the index
# (source: github.com/datasets/s-and-p-500-companies), in Yahoo ticker form
# (BRK-B, not BRK.B). Index changes are a few a quarter; refresh it by hand.
#
# Scheduled as the first job of the "weekly-universe" group (cron/run_group.py,
# render.yaml's grow-universe service), with the defaults below.
# Run manually from dashboard/:
#   python -m cron.measure_library --budget 20

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple

_here = Path(__file__).resolve().parent.parent   # dashboard/
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from utils.memory import release_memory  # noqa: E402

CONSTITUENTS = Path(__file__).resolve().parent / "sp500.csv"
# Its own ceiling, not the scorer's 390MB. Live on 2026-10-04 the library
# stopped on that guard after three batches (75 of 426 stocks) at 422MB --
# still 90MB under Render's 512MB limit -- so at that pace the index took six
# weeks. The run now stops on its own trend instead (see run()), below this
# hard ceiling.
DEFAULT_MAX_RSS_MB = int(os.environ.get("MEASURE_MAX_RSS_MB", "460"))
GROWTH_MARGIN = 1.5     # stop when the next batch, grown like the worst one so far, would cross

Target = Tuple[str, str]   # (ticker, name)


def _log(event: str, **fields) -> None:
    try:
        from utils.observability import log_event
        log_event(event, **fields)
    except Exception:
        pass
    print(f"[measure_library] {event} " + " ".join(f"{k}={v}" for k, v in fields.items()),
          flush=True)


def load_constituents(path: Path = CONSTITUENTS) -> List[Target]:
    """(ticker, name) for each company in the checked-in index list."""
    with open(path, newline="", encoding="utf-8") as fh:
        return [(r["ticker"].strip().upper(), r["name"].strip())
                for r in csv.DictReader(fh) if r.get("ticker", "").strip()]


# The largest index members, roughly by market value. Used ONLY to order
# never-measured stocks: a run that fills the library a slice at a time used to
# go alphabetically, so after the first live run A..EBAY were measured and
# MSFT, JPM, XOM and the rest of the names an adviser looks up first were not.
# Nothing here is shown or measured differently; an approximate order is fine,
# and every name must be in cron/sp500.csv (tested).
PRIORITY = (
    "NVDA MSFT AAPL AMZN GOOGL GOOG META AVGO TSLA BRK-B JPM LLY V WMT ORCL MA XOM "
    "NFLX COST JNJ HD PG ABBV BAC PLTR KO UNH CVX PM GE CSCO AMD WFC IBM CRM MS ABT "
    "LIN MCD GS AXP INTU DIS T MRK PEP VZ NOW TMO CAT RTX ISRG BKNG UBER QCOM ADBE "
    "PGR SCHW BLK AMGN TXN SPGI NEE C BA"
).split()


def plan_targets(constituents: Iterable[Target], library: Iterable[dict], now: datetime,
                 fresh_days: int, priority: Iterable[str] = PRIORITY) -> List[Target]:
    """What to measure this run, stalest first.

    The index plus everything already in the library (a stock someone viewed
    deserves its weekly row too). Never-measured stocks come first -- the
    largest companies (PRIORITY) ahead of the rest -- then the oldest
    measurement; anything measured within fresh_days is left out.
    """
    last: Dict[str, str] = {}
    names: Dict[str, str] = {}
    for row in library:
        last[row["ticker"]] = str(row.get("measured_at") or "")
        names[row["ticker"]] = row.get("name") or ""
    wanted: Dict[str, str] = {}
    for ticker, name in constituents:
        wanted.setdefault(ticker, name)
    for ticker, name in names.items():
        wanted.setdefault(ticker, name)

    cutoff = (now - timedelta(days=fresh_days)).isoformat()
    due = [(t, n) for t, n in wanted.items() if not last.get(t) or last[t] < cutoff]
    rank = {t: i for i, t in enumerate(priority)}
    # An empty timestamp sorts before every real one: never-measured goes first,
    # and within a timestamp the largest companies go before the alphabet.
    return sorted(due, key=lambda tn: (last.get(tn[0], ""), rank.get(tn[0], len(rank)), tn[0]))


def memo_series(fetch: Callable[[str, str, str], object]) -> Callable[[str, str, str], object]:
    """One fetch per economic series per run, however many stocks are measured.

    A failure is remembered too: the engine excludes a force whose series is
    missing, and asking again 500 times would only slow the run down.
    """
    seen: Dict[Tuple[str, str, str], object] = {}

    def fetcher(series_id: str, start: str, end: str):
        key = (series_id, start, end)
        if key not in seen:
            try:
                seen[key] = fetch(series_id, start, end)
            except Exception:
                seen[key] = None
        return seen[key]
    return fetcher


def measure_batch(batch: List[Target], prices_batch: Callable[[tuple, str, str], Mapping],
                  series: Callable[[str, str, str], object], end) -> Iterable[Tuple[str, str, dict]]:
    """(ticker, name, report) for each stock in the batch, one price fetch for all of them."""
    from utils import exposure as ex

    held: Dict[str, object] = {}
    asked: set = set()

    def prices(tickers, start, stop):
        # The engine asks for [ticker, SPY, the price-sourced forces]; the
        # whole batch is fetched on the first ask. What was asked and came
        # back empty is remembered as asked: otherwise one fund Yahoo can't
        # return would refetch the whole batch for every stock in it.
        missing = [t for t in tickers if t not in asked]
        if missing:
            want = tuple(sorted({t for t, _ in batch} | set(tickers)))
            held.update(prices_batch(want, start, stop) or {})
            asked.update(want)
        return {t: held.get(t) for t in tickers}

    for ticker, name in batch:
        # history_weeks=0: the library stores readings, never the rolling line,
        # and ten years of prices per stock cost the run a quarter of its stocks.
        report = ex.build_exposure_report([{"ticker": ticker, "weight_pct": 100}], prices,
                                          series, end=end, max_holdings=1, history_weeks=0)
        yield ticker, name, report


def _rss_mb() -> float:
    from cron.score_universe import _rss_mb as rss
    return rss()


def run(targets: List[Target], *, prices_batch, series, record, end, batch_size: int,
        deadline: float, max_rss_mb: int, clock=time.monotonic, rss=_rss_mb) -> dict:
    stats = {"targets": len(targets), "measured": 0, "failed": 0, "stop": "done"}
    worst_growth = 0.0
    for n, i in enumerate(range(0, len(targets), batch_size), 1):
        if clock() > deadline:
            stats["stop"] = "deadline"
            break
        used = rss()
        if used and (used >= max_rss_mb or used + GROWTH_MARGIN * worst_growth >= max_rss_mb):
            stats["stop"] = "memory"
            break
        for ticker, name, report in measure_batch(targets[i:i + batch_size], prices_batch,
                                                  series, end):
            if report.get("status") == "ok" and record(report, name):
                stats["measured"] += 1
            else:
                stats["failed"] += 1
                stats.setdefault("failed_tickers", []).append(ticker)
                _log("not_measured", ticker=ticker,
                     reason=str(report.get("message") or "not recorded")[:80])
        # The batch fetcher is st.cache_data ("MemoryCacheStorageManager" in
        # the log): without this every batch's prices stay for the whole run.
        getattr(prices_batch, "clear", lambda: None)()
        release_memory()
        after = rss()
        if used and after:
            worst_growth = max(worst_growth, after - used)
        _log("batch", n=n, measured=stats["measured"], rss_mb=round(after or 0, 1))
    stats["remaining"] = stats["targets"] - stats["measured"] - stats["failed"]
    return stats


DEFAULT_PASSES = int(os.environ.get("MEASURE_PASSES", "12"))


def _parse(argv: Optional[List[str]]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=600, help="most stocks to measure per pass")
    ap.add_argument("--batch-size", type=int, default=25)
    ap.add_argument("--fresh-days", type=int, default=6)
    ap.add_argument("--deadline-min", type=int, default=40, help="for the whole run, every pass")
    ap.add_argument("--max-rss-mb", type=int, default=DEFAULT_MAX_RSS_MB)
    ap.add_argument("--passes", type=int, default=DEFAULT_PASSES,
                    help="fresh processes to run, each until its memory guard; 1 = in-process")
    # Internal: what the supervisor passes to each pass.
    ap.add_argument("--status-file", default="", help=argparse.SUPPRESS)
    ap.add_argument("--skip", default="", help=argparse.SUPPRESS)
    # run_group calls main() with no arguments while sys.argv holds the group's
    # own; parsing that would reject the group name, so no argv means defaults.
    return ap.parse_args([] if argv is None else argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse(argv)
    if not os.environ.get("DATABASE_URL"):
        # Without it init_db() quietly uses a local SQLite file, and every
        # measurement would be written somewhere nothing reads.
        _log("refused", reason="DATABASE_URL is not set")
        return 2
    if args.passes > 1 and not args.status_file:
        return _supervise(args)
    return _one_pass(args)


def _one_pass(args: argparse.Namespace) -> int:
    t0 = time.monotonic()
    from utils import exposure as ex
    from utils import stock_library as lib
    from utils.db import init_db
    from utils.fetchers import _get_fred_key, fetch_fred, fetch_prices_batch

    init_db()
    now = datetime.now(timezone.utc)
    skip = {t for t in args.skip.split(",") if t}
    targets = [t for t in plan_targets(load_constituents(), lib.latest(limit=5000), now,
                                       args.fresh_days) if t[0] not in skip][:args.budget]
    _log("start", targets=len(targets), skipped=len(skip), rss_mb=round(_rss_mb(), 1))
    if not targets:
        _log("finished", reason="everything is fresh")
        _write_status(args.status_file, {"targets": 0, "measured": 0, "failed": 0, "stop": "fresh"})
        return 0

    def fred(series_id, start, end):
        key = _get_fred_key()
        s = fetch_fred(series_id, start, end, api_key=key) if key else None
        return s if s is not None and len(s) else ex.fetch_fred_public(series_id, start, end)

    series = memo_series(ex.prefetching(fred, ex.REPORT_SERIES_IDS))
    stats = run(targets, prices_batch=fetch_prices_batch, series=series,
                record=lib.record, end=now.date(), batch_size=args.batch_size,
                deadline=t0 + args.deadline_min * 60, max_rss_mb=args.max_rss_mb)
    _log("finished", seconds=round(time.monotonic() - t0), rss_mb=round(_rss_mb(), 1),
         **{k: v for k, v in stats.items() if k != "failed_tickers"})
    _write_status(args.status_file, stats)
    # Nothing measured at all is an outage (prices or FRED down), not a quiet week.
    return 1 if stats["measured"] == 0 else 0


def _write_status(path: str, stats: dict) -> None:
    if not path:
        return
    import json
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(stats, fh)


def _run_pass_subprocess(argv: List[str], timeout_s: float) -> Optional[dict]:
    """One pass in a fresh interpreter; its status file, or None if it died."""
    import json
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fh:
        path = fh.name
    try:
        subprocess.run([sys.executable, "-m", "cron.measure_library", *argv,
                        "--status-file", path], check=False, timeout=timeout_s,
                       cwd=str(_here))
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        _log("pass_failed", error=str(exc)[:120])
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _supervise(args: argparse.Namespace, run_pass=_run_pass_subprocess,
               clock=time.monotonic) -> int:
    """Run passes in fresh processes until the index is fresh or time is up.

    Each pass starts at the import baseline, measures until its memory guard,
    and exits; the OS takes the memory back. Stalest-first then makes the next
    pass begin where the last stopped -- a measured stock is fresh, so it is
    never picked twice in a run. (cron/score_universe.py's supervisor solves
    the same problem the same way.)

    Stops on: a pass with nothing to do (everything fresh), a pass that
    measured nothing (an outage, or a guard that trips before the first batch:
    another pass would only repeat it), a pass that died, or the deadline.
    A stock that failed is skipped by later passes this run, so a handful of
    unmeasurable tickers at the head of the queue cannot eat every pass.
    """
    deadline = clock() + args.deadline_min * 60
    skip: List[str] = [t for t in args.skip.split(",") if t]
    total = {"passes": 0, "measured": 0, "failed": 0}
    reason = "passes"
    for n in range(1, args.passes + 1):
        left_min = (deadline - clock()) / 60
        if left_min <= 1:
            reason = "deadline"
            break
        argv = ["--passes", "1", "--budget", str(args.budget), "--batch-size", str(args.batch_size),
                "--fresh-days", str(args.fresh_days), "--max-rss-mb", str(args.max_rss_mb),
                "--deadline-min", str(max(1, int(left_min)))]
        if skip:
            argv += ["--skip", ",".join(skip)]
        st = run_pass(argv, max(60.0, left_min * 60))
        if st is None:
            reason = "pass_died"
            break
        total["passes"] = n
        total["measured"] += int(st.get("measured", 0))
        total["failed"] += int(st.get("failed", 0))
        skip += [t for t in st.get("failed_tickers", []) if t not in skip]
        _log("pass_complete", pass_n=n, measured=st.get("measured"), failed=st.get("failed"),
             stop=st.get("stop"))
        if int(st.get("targets", 0)) == 0:
            reason = "everything_fresh"
            break
        if int(st.get("measured", 0)) == 0:
            reason = "no_progress"
            break
    _log("supervisor_summary", stop=reason, **total)
    # Same contract as a single pass: measuring nothing while work existed is an outage.
    return 1 if total["measured"] == 0 and reason != "everything_fresh" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
