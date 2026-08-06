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


def _headroom(ready_mb: float, limit_mb: int):
    """Working room left above fixed startup cost — or "unknown" if RSS is unreadable.

    _rss_mb() returns 0.0 when it cannot read the process, so a naive
    `limit - ready` would report the FULL budget as available for a process we
    know nothing about. That is the same shape of lie as the exit-0 that hid
    truncated runs for weeks: a missing measurement rendered as a healthy one.
    Unknown has to look unknown, because this number is what decides whether to
    buy a bigger instance.
    """
    if not ready_mb or ready_mb <= 0:
        return "unknown"
    return round(limit_mb - ready_mb, 1)


def score_kind_for_tier(tier: str) -> str:
    """Which score_kind a tier writes. Single definition, used for both the
    write and the staleness lookup so the two can never disagree."""
    return "full" if tier == "core" else "macro_momentum"


def _stalest_first(targets: list[str], score_kind: str,
                   last_seen: dict | None = None) -> list[str]:
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
    last_seen = _last_seen_map(score_kind) if last_seen is None else last_seen
    if last_seen is None:
        return targets

    # "" sorts before any real date, so never-scored tickers come first.
    return sorted(targets, key=lambda t: (last_seen.get(t, ""), t))


def _last_seen_map(score_kind: str) -> dict | None:
    """ticker -> most recent snapshot_date for this kind, or None if unavailable.

    None means "we could not find out", which callers must treat differently
    from "nothing is fresh" — guessing the latter would stop a run that still
    had work to do.
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
        return {r[0]: (r[1] or "") for r in rows}
    except Exception as exc:
        _log("staleness_lookup_failed", error=str(exc)[:120])
        return None


def _count_fresh(targets: list[str], last_seen: dict | None, today: str) -> int:
    """How many of THIS pass's targets already carry today's snapshot.

    This is what tells the supervisor the universe is covered. A pass whose
    entire stalest-first slice is already fresh means there is nothing older
    left to reach, so further passes would only rescore today's work.

    Unknown staleness returns 0 — never stop early on missing information.
    """
    if not last_seen:
        return 0
    return sum(1 for t in targets if last_seen.get(t, "") >= today)


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
    ap.add_argument("--passes", type=int, default=1,
                    help="run the scorer this many times in FRESH subprocesses. "
                         "The memory guard is what limits a run, and the biggest "
                         "consumer is the import baseline, which a new process "
                         "resets for free. Default 1 = previous behaviour.")
    ap.add_argument("--status-file", default="",
                    help="internal: child writes its result here for the supervisor")
    ap.add_argument("--fail-on-shortfall", action="store_true",
                    help="exit non-zero when the run stops before covering its "
                         "targets (off by default: the rest tier is DESIGNED to "
                         "cover its universe over --rotate-days, so a partial "
                         "run there is normal and would page every night)")
    args = ap.parse_args()

    if args.passes > 1:
        _supervise(args)
        return

    t0 = time.monotonic()
    deadline = t0 + args.deadline_min * 60

    # Memory budget accounting. The guard says WHEN a run stopped but never WHERE
    # the budget went, and that distinction decides the fix: if the import baseline
    # already sits near --max-rss-mb there is almost no working room, so more
    # --passes buys little and the instance has to grow; if the baseline is low,
    # passes are free and sufficient. scripts/measure_cron_memory.py recorded 208MB
    # of imports, but that predates a lot of code — measure in the process that
    # actually runs rather than trusting a stale note.
    rss_interpreter = round(_rss_mb(), 1)
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
    rss_imports = round(_rss_mb(), 1)

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
    _last_seen = _last_seen_map(score_kind_for_tier(args.tier))
    targets = _stalest_first(targets, score_kind_for_tier(args.tier), _last_seen)
    targets = targets[: args.budget]
    # Computed on the SLICE this pass will actually attempt, before scoring.
    # If every one of them is already fresh, the universe has no staler work
    # left and the supervisor should stop rather than rescore today's rows.
    _today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    already_fresh = _count_fresh(targets, _last_seen, _today)

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

    rss_ready = round(_rss_mb(), 1)
    _log("run_start", tier=args.tier, universe=len(scoreable), core=len(core),
         targets=len(targets), score_kind=score_kind, dry_run=args.dry_run,
         rss_interpreter_mb=rss_interpreter, rss_imports_mb=rss_imports,
         rss_ready_mb=rss_ready, rss_limit_mb=args.max_rss_mb,
         # What is actually available for scoring work. This is the number that
         # decides passes-vs-instance; everything above it is fixed cost that a
         # fresh subprocess re-pays on every pass.
         rss_headroom_mb=_headroom(rss_ready, args.max_rss_mb),
         already_fresh=already_fresh)

    start_px, end_px = price_window()
    stats = {"scored": 0, "written": 0, "gated": 0, "failed": 0, "chunks": 0}
    gate_reasons: dict[str, int] = {}

    stop_for_memory = False
    rss_peak = rss_ready
    # What a truncated run has to be able to say for itself. Without these the
    # only trace of an early stop is a memory_guard_reached line further up the
    # log, so run_complete reads identically whether the run covered 34 targets
    # or all 249 — which is how a 14%-coverage night looked like a success.
    stop_reason = ""
    remaining_at_stop = 0
    for i in range(0, len(targets), CHUNK_SIZE):
        # Checked per chunk, in the same place as the deadline, because both are
        # "stop cleanly and keep what we have" conditions. Ordered before the
        # deadline check so a memory stop is reported as such rather than being
        # masked by a coincident timeout.
        if _memory_limit_reached(args.max_rss_mb, stats["scored"],
                                 len(targets) - i):
            stop_reason, remaining_at_stop = "memory", len(targets) - i
            break

        if time.monotonic() > deadline:
            _log("deadline_reached", scored=stats["scored"])
            stop_reason, remaining_at_stop = "deadline", len(targets) - i
            break
        chunk = tuple(targets[i:i + CHUNK_SIZE])
        stats["chunks"] += 1
        rss_peak = max(rss_peak, round(_rss_mb(), 1))
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
                rss_peak = max(rss_peak, round(_rss_mb(), 1))
                remaining = len(targets) - (i + chunk_pos)
                if _memory_limit_reached(args.max_rss_mb, stats["scored"], remaining):
                    stop_for_memory = True
                    stop_reason, remaining_at_stop = "memory", remaining
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

    covered = len(targets) - remaining_at_stop
    coverage_pct = round(100.0 * covered / len(targets), 1) if targets else 100.0
    _log("run_complete", tier=args.tier, duration_s=round(time.monotonic() - t0, 1),
         **stats,
         stopped_early=bool(stop_reason), stop_reason=stop_reason or "none",
         remaining=remaining_at_stop, coverage_pct=coverage_pct,
         rss_ready_mb=rss_ready, rss_peak_mb=rss_peak,
         # Growth attributable to scoring work, as opposed to fixed startup cost.
         rss_work_mb=round(rss_peak - rss_ready, 1),
         **{f"gate_{k}": v for k, v in gate_reasons.items()})

    if args.status_file:
        # The supervisor needs to know whether progress was made and whether
        # anything is left; parsing our own log line would be brittle.
        try:
            import json
            with open(args.status_file, "w", encoding="utf-8") as fh:
                json.dump({"scored": stats["scored"], "written": stats["written"],
                           "remaining": remaining_at_stop,
                           "stop_reason": stop_reason or "none",
                           "already_fresh": already_fresh,
                           "targets": len(targets)}, fh)
        except Exception as exc:
            _log("status_write_failed", error=str(exc)[:120])

    if stop_reason:
        # A separate, greppable event so "did last night actually finish?" is one
        # query rather than an eyeball over the whole log. The core tier is the
        # one to watch: it is meant to be refreshed DAILY, so unlike rest it has
        # no rotation window to make a partial run acceptable.
        _log("coverage_shortfall", tier=args.tier, stop_reason=stop_reason,
             covered=covered, targets=len(targets),
             remaining=remaining_at_stop, coverage_pct=coverage_pct)
        if args.fail_on_shortfall:
            sys.exit(1)


def _supervise(args) -> None:
    """Run the scorer repeatedly in fresh processes until coverage or deadline.

    WHY SUBPROCESSES. Stalest-first ordering already made runs resume across
    NIGHTS — that is not the gap. The gap is throughput WITHIN one night:
    production logs show score-core reaching 404.8MB and stopping after 34 of
    249 targets, because the import baseline (streamlit, pandas, scipy,
    yfinance) consumes most of the 390MB budget before any ticker is scored.
    Nothing inside the process can give that baseline back — gc and cache
    clearing only reclaim what the run itself allocated.

    Exiting does give it back. Each pass starts at baseline, scores until the
    guard, and dies; the OS reclaims everything. Stalest-first then makes the
    next pass begin exactly where the last one stopped, so N passes cover
    roughly N times as many tickers for the price of N process starts.

    Stops early on: a stalest-first slice that is ALREADY entirely fresh (the
    universe has no staler work left), no progress (the guard tripped before a
    single ticker, so another pass would repeat it), or the shared deadline.

    Deliberately NOT on "this pass finished its list". That slice is only
    --budget long, and once budget was tuned to per-pass capacity every healthy
    pass finished it, which stopped the supervisor after one pass.
    """
    import json
    import subprocess
    import tempfile

    started = time.monotonic()
    deadline = started + args.deadline_min * 60
    base = [sys.executable, "-m", "cron.score_universe",
            "--tier", args.tier,
            "--rotate-days", str(args.rotate_days),
            "--budget", str(args.budget),
            "--max-rss-mb", str(args.max_rss_mb)]
    if args.dry_run:
        base.append("--dry-run")

    totals = {"scored": 0, "written": 0, "passes": 0}
    for n in range(1, args.passes + 1):
        left_min = (deadline - time.monotonic()) / 60
        if left_min <= 1:
            _log("supervisor_deadline", completed_passes=n - 1)
            break

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fh:
            status_path = fh.name
        cmd = base + ["--deadline-min", str(max(1, int(left_min))),
                      "--status-file", status_path]
        try:
            subprocess.run(cmd, check=False, timeout=max(60, left_min * 60))
            with open(status_path, "r", encoding="utf-8") as fh:
                st = json.load(fh)
        except Exception as exc:
            _log("pass_failed", pass_n=n, error=str(exc)[:120])
            break
        finally:
            try:
                os.unlink(status_path)
            except Exception:
                pass

        totals["scored"] += int(st.get("scored", 0))
        totals["written"] += int(st.get("written", 0))
        totals["passes"] = n
        _log("pass_complete", pass_n=n, scored=st.get("scored"),
             remaining=st.get("remaining"), stop_reason=st.get("stop_reason"))

        # NOT `remaining <= 0`. `remaining` counts what is left of THIS pass's
        # budgeted slice, so once --budget was tuned down to per-pass capacity
        # every healthy pass ended at 0 and the supervisor stopped after pass 1
        # — burning one pass of ten and 184s of a 2400s deadline. Coverage comes
        # from launching another pass against a freshly re-selected stalest
        # slice; the run is only genuinely done when that slice is all fresh.
        fresh, attempted = int(st.get("already_fresh", 0)), int(st.get("targets", 0))
        if attempted > 0 and fresh >= attempted:
            _log("supervisor_complete", reason="universe_fresh",
                 already_fresh=fresh, targets=attempted)
            break
        if int(st.get("scored", 0)) == 0:
            # The guard tripped before a single ticker was scored. A further
            # pass would start from the same baseline and do the same thing.
            _log("supervisor_stopped", reason="no_progress_in_pass")
            break

    _log("supervisor_summary", tier=args.tier, **totals,
         duration_s=round(time.monotonic() - started, 1))


def _cli() -> int:
    """Run main() and translate the outcome into an exit code.

    Split out from the __main__ block so the exit-code contract is testable
    without spawning a subprocess: the behaviour being protected here is
    precisely the one that hid failures for weeks.
    """
    try:
        main()
    except SystemExit as exc:                     # --fail-on-shortfall, not a crash
        return int(exc.code or 0)
    except Exception as exc:
        # This used to swallow the exception and exit 0, so a run that died on
        # its first ticker still showed "finished successfully" in Render and
        # never triggered the failure notification the service is configured to
        # send. A crash is exactly the case that should page.
        print(f"[score_universe] fatal: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
