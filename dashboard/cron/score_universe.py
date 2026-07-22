#!/usr/bin/env python3
# cron/score_universe.py
# Unstructured Alpha — Batch Confluence-Score Worker
#
# Precomputes Confluence Scores for the qualifying universe (~5.3k common stocks,
# see utils/scoring_universe.py) and writes them to score_snapshots, so Deep Dive,
# the screener and the recommender READ a score instead of computing one cold.
#
# WHY THIS IS TRACTABLE
#   The 47 macro signals are ticker-INDEPENDENT. They're fetched once and reused
#   for every ticker in the run (via the module-level cache in utils/fetchers),
#   so the marginal cost per ticker is a batched price fetch plus correlation
#   math — not 47 more network calls.
#
# DESIGN RULES
#   • Runs OFF the interactive path — this is a cron/worker, never the web process.
#   • Bounded: chunked batch fetches, a hard ticker budget, and a wall-clock
#     deadline, so a run can't grow without limit or overlap the next one.
#   • Memory-safe: prices are released and the heap trimmed between chunks.
#   • Idempotent: record_score_snapshot upserts on (ticker, snapshot_date), and a
#     FAILED compute never writes — so a bad run cannot overwrite good data.
#   • Isolated per ticker: one bad symbol never aborts the run.
#
# TIERS (cadence lives in render.yaml, not here)
#   core : the curated tickers + everything users actually watch  → run daily
#   rest : the remaining qualifying universe, rotated in daily slices so the whole
#          universe is refreshed over --rotate-days without scoring 5k every day
#
# Run manually (from dashboard/):
#   python -m cron.score_universe --tier core --dry-run
#   python -m cron.score_universe --tier rest --rotate-days 7

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_here = Path(__file__).resolve().parent.parent   # dashboard/
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

CHUNK_SIZE = 30           # small enough to stay below Render Starter's 512MB cap
MEMORY_CHECK_EVERY = 5    # stop within a chunk instead of waiting for its end
DEFAULT_BUDGET = 1200     # max tickers scored in one run
DEFAULT_DEADLINE_MIN = 50  # wall-clock guard

# Memory guard. Render killed the first core run nine minutes in with
# "Ran out of memory (used over 512MB)". Crons inherit the Starter plan (512MB)
# unless render.yaml gives them one, and the web service's `plan: standard` does
# not apply to them.
#
# Measured on this codebase (scripts/measure_cron_memory.py):
#   imports alone ......... 208MB  (pandas 77, scipy 56, yfinance 26, streamlit 31)
#   + all 47 signals ...... 268MB
#   + a 120-symbol chunk .. 232MB  (the price frame itself is only 0.5MB)
#
# So the fixed cost is ~270MB and the price frames are negligible; what remains
# is consumed gradually while scoring hundreds of tickers through the full path.
# The run already had a wall-clock deadline but no memory guard, so it was killed
# rather than stopping — and an OOM kill loses the entire run, which then repeats
# identically the next night. Stopping cleanly banks whatever was scored and lets
# the next run continue, so the universe fills in over several days instead of
# never.
DEFAULT_MAX_RSS_MB = int(os.environ.get("SCORE_MAX_RSS_MB", "430"))


def _rss_mb() -> float:
    """CURRENT resident set size in MB, or 0.0 when it cannot be determined.

    Deliberately current rather than peak. getrusage's ru_maxrss is a high-water
    mark that never falls, so once a single chunk spiked the guard would trip on
    every later check even after release_memory() handed the heap back — halting
    healthy runs. Render kills on current usage, so that is what to compare
    against. /proc/self/statm is the current figure on Linux, which is where the
    cron actually runs; getrusage is the fallback elsewhere and is only a
    conservative approximation.

    Returning 0.0 on failure means an unavailable reading can never trip the
    guard and stop a run that was doing fine.
    """
    try:
        with open("/proc/self/statm", "rb") as fh:
            pages = int(fh.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") / 1024 / 1024
    except Exception:
        pass
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / 1024 / 1024 if sys.platform == "darwin" else peak / 1024
    except Exception:
        return 0.0


def score_kind_for_tier(tier: str) -> str:
    """Which score_kind a tier writes. Single definition, used for both the
    write and the staleness lookup so the two can never disagree."""
    return "full" if tier == "core" else "macro_momentum"


def _stalest_first(targets: list[str], score_kind: str) -> list[str]:
    """Order by least-recently-scored, never-scored first.

    A run that stops early — on budget, deadline or the memory guard — must not
    keep re-scoring the same alphabetical prefix, or the tail of the universe is
    unreachable in principle. Sorting by the age of each ticker's most recent
    snapshot of THIS kind turns a series of partial runs into full coverage.

    Matching on score_kind matters: a ticker with a fresh macro_momentum score
    still needs a full one, and treating those as interchangeable would starve
    the core tier.

    Any failure returns the input order unchanged — a lookup problem should
    degrade to the old behaviour, not stop the run.
    """
    try:
        from sqlalchemy import text
        from utils.db import engine

        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT ticker, MAX(snapshot_date) AS last_seen
                FROM score_snapshots
                WHERE score_kind = :kind OR (:kind = 'full' AND score_kind IS NULL)
                GROUP BY ticker
            """), {"kind": score_kind}).fetchall()
        last_seen = {r[0]: (r[1] or "") for r in rows}
    except Exception as exc:
        _log("staleness_lookup_failed", error=str(exc)[:120])
        return targets

    # "" sorts before any real date, so never-scored tickers come first.
    return sorted(targets, key=lambda t: (last_seen.get(t, ""), t))


def _log(event: str, **fields):
    """Structured line when observability is available, plain print otherwise."""
    try:
        from utils.observability import log_event
        log_event(event, **fields)
    except Exception:
        pass
    print(f"[score_universe] {event} " +
          " ".join(f"{k}={v}" for k, v in fields.items()), flush=True)


def _memory_limit_reached(limit_mb: int, scored: int, remaining: int) -> bool:
    """Return True when the worker should bank its progress and stop.

    Checking only between 120-symbol chunks was too coarse: the July 22 REST
    run crossed 512MB and was killed halfway through its first chunk before the
    existing guard could run a second time.  The caller now checks this helper
    between small groups of tickers as well as before every batch fetch.
    """
    rss = _rss_mb()
    if rss and rss >= limit_mb:
        _log("memory_guard_reached", rss_mb=round(rss, 1), limit_mb=limit_mb,
             scored=scored, remaining=max(0, remaining))
        return True
    return False


def _core_tickers() -> list[str]:
    """Curated tickers + every ticker any user actually watches."""
    out: set[str] = set()
    try:
        from utils.config import TICKERS
        out.update(TICKERS.keys())
    except Exception:
        pass
    try:  # anything on a real watchlist is worth keeping fresh daily
        from sqlalchemy import select
        from utils.db import engine, watchlist
        with engine.begin() as conn:
            for r in conn.execute(select(watchlist.c.ticker).distinct()).fetchall():
                if r[0]:
                    out.add(str(r[0]).upper().strip())
    except Exception:
        pass
    return sorted(out)


def _rest_slice(scoreable: dict, core: set[str], rotate_days: int) -> list[str]:
    """
    Today's slice of the non-core universe. Deterministic rotation by day-of-year
    so consecutive runs cover different symbols and the whole universe is
    refreshed every `rotate_days` — no cursor/state to keep in sync.
    """
    rest = sorted(s for s in scoreable if s not in core)
    if not rest or rotate_days <= 1:
        return rest
    day = datetime.now(timezone.utc).timetuple().tm_yday % rotate_days
    return [s for i, s in enumerate(rest) if i % rotate_days == day]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["core", "rest", "all"], default="core")
    ap.add_argument("--rotate-days", type=int, default=7)
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    ap.add_argument("--deadline-min", type=int, default=DEFAULT_DEADLINE_MIN)
    ap.add_argument("--max-rss-mb", type=int, default=DEFAULT_MAX_RSS_MB,
                    help="stop cleanly before the host OOM-kills the process")
    ap.add_argument("--dry-run", action="store_true",
                    help="select + gate tickers but write nothing")
    args = ap.parse_args()

    t0 = time.monotonic()
    deadline = t0 + args.deadline_min * 60

    from utils.db import init_db
    from utils.scoring_universe import (
        build_scoring_universe, qualifies_on_price, OK,
    )
    from utils.ticker_score import compute_full_ticker_score, price_window
    from utils.fetchers import fetch_prices_batch
    from utils.score_history import record_score_snapshot
    try:
        from utils.memory import release_memory
    except Exception:
        release_memory = lambda: None            # noqa: E731

    init_db()

    universe = build_scoring_universe()
    scoreable = universe["scoreable"]
    core = set(_core_tickers())

    if args.tier == "core":
        # Everything in core is scored regardless of the offline classifier: these
        # are curated tickers and symbols real users chose to watch. The price
        # gate below still applies, so nothing gets a score without real data.
        targets = sorted(core)
    elif args.tier == "rest":
        targets = _rest_slice(scoreable, core, args.rotate_days)
    else:
        targets = sorted(set(scoreable) | core)

    # Stalest first. This is what makes a budget-limited or memory-limited run
    # actually converge: targets used to be alphabetical, so every run scored the
    # same leading slice and stopped, and anything past the cut-off would never be
    # reached no matter how many nights the cron ran. Ordering by least-recently
    # scored means each run resumes where the last one gave up, and coverage
    # fills in over successive days.
    targets = _stalest_first(targets, score_kind_for_tier(args.tier))
    targets = targets[: args.budget]

    # WHICH score this run produces — these are DIFFERENT metrics, not two
    # precisions of the same one (measured on AAPL: 45.6 full vs 56.3 macro-only),
    # so they're stored under distinct score_kind values and never conflated.
    #   core → the full Confluence Score, matching Ticker Deep Dive exactly.
    #          Costly (4 network calls/ticker) but this tier is small.
    #   rest → macro + momentum only: the same blend the Screener already labels
    #          "Macro + Momentum Rank". ~425x faster, which is the only reason
    #          scoring thousands of tickers is possible at all.
    want_optional = args.tier == "core"
    # Same helper the staleness ordering uses, so the kind a run WRITES can
    # never drift from the kind it treats as already-covered.
    score_kind = score_kind_for_tier(args.tier)

    _log("run_start", tier=args.tier, universe=len(scoreable), core=len(core),
         targets=len(targets), score_kind=score_kind, dry_run=args.dry_run)

    start_px, end_px = price_window()
    stats = {"scored": 0, "written": 0, "gated": 0, "failed": 0, "chunks": 0}
    gate_reasons: dict[str, int] = {}

    stop_for_memory = False
    for i in range(0, len(targets), CHUNK_SIZE):
        # Checked per chunk, in the same place as the deadline, because both are
        # "stop cleanly and keep what we have" conditions. Ordered before the
        # deadline check so a memory stop is reported as such rather than being
        # masked by a coincident timeout.
        if _memory_limit_reached(args.max_rss_mb, stats["scored"],
                                 len(targets) - i):
            break

        if time.monotonic() > deadline:
            _log("deadline_reached", scored=stats["scored"])
            break
        chunk = tuple(targets[i:i + CHUNK_SIZE])
        stats["chunks"] += 1
        try:
            prices = fetch_prices_batch(chunk, start_px, end_px)
        except Exception as exc:
            _log("chunk_fetch_failed", chunk=i // CHUNK_SIZE, error=str(exc)[:120])
            continue

        for chunk_pos, tkr in enumerate(chunk):
            # The old guard ran only once per 120 tickers.  A leaking cache or
            # allocator arena could therefore add >80MB before we looked again,
            # leaving Render to kill the process at 512MB.  Check inside the
            # chunk and trim periodically so completed snapshots survive.
            if chunk_pos and chunk_pos % MEMORY_CHECK_EVERY == 0:
                release_memory()
                remaining = len(targets) - (i + chunk_pos)
                if _memory_limit_reached(args.max_rss_mb, stats["scored"], remaining):
                    stop_for_memory = True
                    break
            try:
                series = prices.get(tkr)
                reason = qualifies_on_price(series)
                if reason != OK:
                    stats["gated"] += 1
                    gate_reasons[reason] = gate_reasons.get(reason, 0) + 1
                    continue
                full = compute_full_ticker_score(tkr, price_series=series,
                                                 include_optional=want_optional)
                conf = (full or {}).get("confluence") or {}
                score = conf.get("overall_score")
                if score is None:
                    stats["failed"] += 1
                    continue
                stats["scored"] += 1
                if not args.dry_run:
                    # Only a SUCCESSFUL compute ever writes — a failure must not
                    # overwrite a good prior snapshot.
                    record_score_snapshot(tkr, float(score),
                                          conf.get("case", ""), conf.get("conviction", ""),
                                          kind=score_kind)
                    stats["written"] += 1
            except Exception:
                stats["failed"] += 1
                continue

        del prices
        # This process is a one-shot worker.  Keeping each batch in Streamlit's
        # process-local cache only retains DataFrames that will never be reused.
        # Clearing it here has no effect on the separately running web service.
        try:
            fetch_prices_batch.clear()
        except Exception:
            pass
        release_memory()      # keep peak RSS flat across chunks
        if stop_for_memory:
            break

    _log("run_complete", tier=args.tier, duration_s=round(time.monotonic() - t0, 1),
         **stats, **{f"gate_{k}": v for k, v in gate_reasons.items()})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:                      # never fail the cron loudly
        print(f"[score_universe] fatal: {exc}", file=sys.stderr, flush=True)
    sys.exit(0)
