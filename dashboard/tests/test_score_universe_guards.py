"""Guards on the batch scoring cron.

Render killed the first score-core run nine minutes in: "Ran out of memory
(used over 512MB)". The run had a wall-clock deadline but no memory guard, so
it was killed rather than stopping, and an OOM kill loses the whole run — which
then repeats identically the following night. That is why score_snapshots held
43 rows weeks after the cron was scheduled.

These tests cover the guard itself and the failure modes that would make it
worse than useless: tripping on a healthy run, or never tripping at all.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parent.parent

# Subprocess-based runs touch the network and take ~1min; deselect with
#   pytest -m 'not slow'
slow = pytest.mark.slow


def _run(env_extra: dict[str, str], *args: str) -> str:
    env = {**os.environ, **env_extra}
    proc = subprocess.run(
        [sys.executable, "-m", "cron.score_universe", "--dry-run", *args],
        cwd=DASHBOARD, env=env, capture_output=True, text=True, timeout=300,
    )
    return proc.stdout + proc.stderr


# ── The guard ─────────────────────────────────────────────────────────────────

@slow
def test_memory_guard_stops_cleanly_instead_of_being_killed():
    """A limit below the import baseline must halt the run gracefully."""
    out = _run({"SCORE_MAX_RSS_MB": "50"}, "--tier", "core", "--budget", "50")
    assert "memory_guard_reached" in out
    # Crucially it still reaches run_complete: a clean stop, not a kill.
    assert "run_complete" in out


@slow
def test_healthy_run_is_not_stopped_by_the_guard():
    """The guard must not fire at the default limit on a small run.

    This is the regression that matters most: a guard reading PEAK rss would
    trip on every check after the first spike and silently stop all real work.
    """
    out = _run({}, "--tier", "core", "--budget", "3")
    assert "memory_guard_reached" not in out
    assert "run_complete" in out


# ── The reading ───────────────────────────────────────────────────────────────

def test_rss_reader_returns_a_plausible_current_value():
    sys.path.insert(0, str(DASHBOARD))
    from cron.score_universe import _rss_mb

    mb = _rss_mb()
    assert mb > 0, "could not read RSS at all"
    assert mb < 100_000, "implausible RSS — units are probably wrong"


@pytest.mark.skipif(
    not Path("/proc/self/statm").exists(),
    reason=(
        "Current-RSS reads come from /proc/self/statm, which only exists on "
        "Linux. The cron runs on Linux; the getrusage fallback used on macOS is "
        "peak-based and deliberately conservative, so this behaviour cannot be "
        "asserted here."
    ),
)
def test_rss_reader_reports_current_not_peak():
    """ru_maxrss never falls, so a peak-based guard halts healthy runs.

    Allocating and freeing a large block should not leave the reading
    permanently elevated by that block's full size.
    """
    sys.path.insert(0, str(DASHBOARD))
    from cron.score_universe import _rss_mb

    before = _rss_mb()
    blob = bytearray(180 * 1024 * 1024)  # 180MB
    during = _rss_mb()
    del blob
    import gc
    gc.collect()
    after = _rss_mb()

    assert during > before, "reader did not observe the allocation at all"
    # A peak-based reader would keep `after` at roughly `during`.
    assert after < during - 50, (
        f"reading stayed at {after:.0f}MB after freeing 180MB (peak was "
        f"{during:.0f}MB) — this looks like a peak metric, which would trip the "
        "guard permanently after any single spike"
    )


def test_rss_reader_never_raises(monkeypatch):
    """An unreadable RSS must yield 0.0, which cannot trip the guard."""
    sys.path.insert(0, str(DASHBOARD))
    import cron.score_universe as su

    def boom(*a, **k):
        raise OSError("no /proc here")

    monkeypatch.setattr("builtins.open", boom)
    monkeypatch.setattr(su, "sys", sys)
    # resource may still work; either way it must not raise.
    assert su._rss_mb() >= 0.0


# ── Configuration ─────────────────────────────────────────────────────────────

def test_default_limit_leaves_headroom_under_the_starter_ceiling():
    sys.path.insert(0, str(DASHBOARD))
    from cron.score_universe import DEFAULT_MAX_RSS_MB

    assert DEFAULT_MAX_RSS_MB < 512, "guard must fire before Render's OOM kill"
    assert DEFAULT_MAX_RSS_MB > 270, (
        "measured baseline is ~270MB with signals loaded; a limit at or below "
        "that would stop every run before it scored anything"
    )


def test_limit_is_overridable_by_env():
    """So the limit can be raised with the plan without a code change."""
    sys.path.insert(0, str(DASHBOARD))
    src = (DASHBOARD / "cron" / "score_universe.py").read_text()
    assert "SCORE_MAX_RSS_MB" in src


def test_guard_is_checked_before_the_deadline():
    """Otherwise a memory stop gets misreported as a timeout."""
    src = (DASHBOARD / "cron" / "score_universe.py").read_text()
    assert src.index("memory_guard_reached") < src.index("deadline_reached")


def test_memory_is_checked_inside_each_chunk():
    """A guard only between batches cannot prevent a mid-batch Render OOM."""
    src = (DASHBOARD / "cron" / "score_universe.py").read_text()
    assert "MEMORY_CHECK_EVERY" in src
    assert "chunk_pos % MEMORY_CHECK_EVERY" in src
    assert "fetch_prices_batch.clear()" in src


# ── Convergence ───────────────────────────────────────────────────────────────
# The guard alone does not fix coverage. Targets used to be alphabetical, so a
# run that stopped early always stopped at the same place and the tail of the
# universe was unreachable no matter how many nights the cron ran. These cover
# the ordering that turns repeated partial runs into full coverage.

def _stalest(monkeypatch, last_seen: dict[str, str], targets: list[str],
             kind: str = "full") -> list[str]:
    sys.path.insert(0, str(DASHBOARD))
    import cron.score_universe as su

    class _Result:
        def __init__(self, rows): self._rows = rows
        def fetchall(self): return self._rows

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **k): return _Result(list(last_seen.items()))

    class _Engine:
        def connect(self): return _Conn()

    monkeypatch.setitem(sys.modules, "utils.db",
                        type("m", (), {"engine": _Engine()})())
    return su._stalest_first(targets, kind)


def test_never_scored_tickers_come_first(monkeypatch):
    out = _stalest(monkeypatch,
                   {"AAPL": "2026-07-18", "CCJ": "2026-07-19"},
                   ["AAPL", "CCJ", "NEWCO"])
    assert out[0] == "NEWCO"


def test_stalest_scored_ticker_precedes_freshest(monkeypatch):
    out = _stalest(monkeypatch,
                   {"AAPL": "2026-07-01", "CCJ": "2026-07-19", "MSFT": "2026-07-10"},
                   ["CCJ", "MSFT", "AAPL"])
    assert out == ["AAPL", "MSFT", "CCJ"]


def test_ordering_is_not_alphabetical(monkeypatch):
    """The regression: alphabetical order made the tail unreachable."""
    out = _stalest(monkeypatch,
                   {"AAA": "2026-07-19", "ZZZ": "2026-07-01"},
                   ["AAA", "ZZZ"])
    assert out == ["ZZZ", "AAA"], "freshly-scored AAA must not be re-scored first"


def test_budget_truncation_after_ordering_covers_the_stalest(monkeypatch):
    """A budget of 2 must pick the two most-neglected names, not the first two."""
    last = {"AAA": "2026-07-19", "BBB": "2026-07-18", "YYY": "2026-07-01"}
    out = _stalest(monkeypatch, last, ["AAA", "BBB", "YYY", "ZZZ_NEW"])[:2]
    assert set(out) == {"ZZZ_NEW", "YYY"}


def test_lookup_failure_degrades_to_input_order(monkeypatch):
    """A broken lookup must not stop the run."""
    sys.path.insert(0, str(DASHBOARD))
    import cron.score_universe as su

    class _Engine:
        def connect(self): raise RuntimeError("db unreachable")

    monkeypatch.setitem(sys.modules, "utils.db",
                        type("m", (), {"engine": _Engine()})())
    assert su._stalest_first(["B", "A"], "full") == ["B", "A"]


def test_score_kind_helper_matches_the_tiers():
    sys.path.insert(0, str(DASHBOARD))
    from cron.score_universe import score_kind_for_tier

    assert score_kind_for_tier("core") == "full"
    assert score_kind_for_tier("rest") == "macro_momentum"


def test_write_kind_and_staleness_kind_come_from_one_helper():
    """If they drifted, a tier would treat the wrong scores as coverage."""
    src = (DASHBOARD / "cron" / "score_universe.py").read_text()
    assert src.count("score_kind_for_tier(args.tier)") >= 2
