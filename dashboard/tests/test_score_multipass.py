"""Multi-pass scoring: reset the import baseline by starting a new process.

Production PERF logs on 2026-08-02 showed score-core reaching 404.8MB and
stopping after 34 of 249 targets. Stalest-first ordering already made runs
resume across nights, so the gap was never resumption — it was throughput
within one night, capped by an import baseline no in-process cleanup can
reclaim.

These pin the supervisor's stopping rules, because the failure modes are
"burns 6 process starts achieving nothing" and "quits while work remains".
"""

from __future__ import annotations

import json
import types

import pytest

from cron import score_universe as su


def _args(**over):
    base = dict(tier="core", rotate_days=7, budget=250, deadline_min=40,
                max_rss_mb=390, dry_run=False, passes=4,
                status_file="", fail_on_shortfall=False)
    base.update(over)
    return types.SimpleNamespace(**base)


class _Recorder:
    """Stands in for subprocess.run, scripting one status dict per pass."""
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        payload = self.scripted.pop(0) if self.scripted else {"scored": 0, "remaining": 0}
        path = cmd[cmd.index("--status-file") + 1]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return types.SimpleNamespace(returncode=0)


def _run(monkeypatch, scripted, **over):
    rec = _Recorder(scripted)
    monkeypatch.setattr(su.subprocess if hasattr(su, "subprocess") else __import__("subprocess"),
                        "run", rec, raising=False)
    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", rec)
    su._supervise(_args(**over))
    return rec


def test_runs_each_pass_in_a_separate_process(monkeypatch):
    """The whole point: a fresh process per pass, not a loop in one process."""
    rec = _run(monkeypatch, [{"scored": 34, "remaining": 215}] * 4, passes=4)
    assert len(rec.calls) == 4
    for cmd in rec.calls:
        assert "cron.score_universe" in cmd
        assert "--status-file" in cmd
        # a child must never recurse into supervisor mode
        assert "--passes" not in cmd


def test_finishing_a_budget_slice_does_not_stop_the_run(monkeypatch):
    """`remaining == 0` means "this pass finished ITS 250", not "universe done".

    This was a real production regression. Once --budget was tuned down to the
    ~215 targets one pass can physically finish, every healthy pass ended with
    remaining=0, the supervisor read that as completion, and score-rest stopped
    after ONE pass of ten — using 184s of a 2400s deadline. Coverage comes from
    launching another pass against a freshly re-selected stalest slice.
    """
    rec = _run(monkeypatch, [{"scored": 218, "remaining": 0, "already_fresh": 0, "targets": 250},
                             {"scored": 214, "remaining": 0, "already_fresh": 0, "targets": 250},
                             {"scored": 209, "remaining": 0, "already_fresh": 0, "targets": 250}],
               passes=3)
    assert len(rec.calls) == 3, (
        "a completed budget slice must not end the run while time and passes remain")


def test_stops_when_the_stalest_slice_is_already_fresh(monkeypatch):
    """The honest completion signal: nothing staler left to reach.

    Targets are re-selected stalest-first each pass, so if even the STALEST
    slice already carries today's date, every remaining pass would only rescore
    today's work.
    """
    rec = _run(monkeypatch, [{"scored": 218, "remaining": 0, "already_fresh": 0, "targets": 250},
                             {"scored": 0, "remaining": 0, "already_fresh": 250, "targets": 250},
                             {"scored": 99, "remaining": 0, "already_fresh": 0, "targets": 250}],
               passes=4)
    assert len(rec.calls) == 2


def test_a_partly_fresh_slice_keeps_going(monkeypatch):
    """Only a FULLY fresh slice means done — 249 of 250 still leaves work."""
    rec = _run(monkeypatch, [{"scored": 10, "remaining": 0, "already_fresh": 249, "targets": 250},
                             {"scored": 10, "remaining": 0, "already_fresh": 250, "targets": 250},
                             {"scored": 10, "remaining": 0, "already_fresh": 0, "targets": 250}],
               passes=4)
    assert len(rec.calls) == 2


def test_missing_freshness_information_never_stops_the_run(monkeypatch):
    """An old child, or a failed staleness lookup, reports no already_fresh.

    Absent information must not read as "everything is fresh" — that would
    silently reinstate the one-pass-and-quit bug. _count_fresh returns 0 when
    the lookup fails, and the supervisor treats targets=0 as unknown.
    """
    rec = _run(monkeypatch, [{"scored": 50, "remaining": 0},
                             {"scored": 50, "remaining": 0},
                             {"scored": 50, "remaining": 0}], passes=3)
    assert len(rec.calls) == 3


class TestCountFresh:
    def test_counts_only_targets_carrying_todays_date(self):
        seen = {"A": "2026-08-06", "B": "2026-08-01", "C": ""}
        assert su._count_fresh(["A", "B", "C"], seen, "2026-08-06") == 1

    def test_unknown_staleness_counts_as_not_fresh(self):
        # None = "could not find out". Returning len(targets) here would stop
        # the supervisor on ignorance.
        assert su._count_fresh(["A", "B"], None, "2026-08-06") == 0
        assert su._count_fresh(["A", "B"], {}, "2026-08-06") == 0

    def test_a_future_dated_snapshot_still_counts_as_fresh(self):
        assert su._count_fresh(["A"], {"A": "2026-08-07"}, "2026-08-06") == 1


def test_stops_when_a_pass_makes_no_progress(monkeypatch):
    """Guard tripped before a single ticker — another identical pass is waste."""
    rec = _run(monkeypatch, [{"scored": 34, "remaining": 200},
                             {"scored": 0, "remaining": 200},
                             {"scored": 34, "remaining": 166}], passes=4)
    assert len(rec.calls) == 2


def test_passes_share_one_wall_clock_deadline(monkeypatch):
    """Each child gets the REMAINING time, never a fresh full deadline.

    Without this, --passes 6 --deadline-min 40 could run for four hours and
    collide with the next night's cron.

    The clock must actually ADVANCE for this to mean anything: an earlier
    version asserted only "non-increasing", which 40/40/40 satisfies — exactly
    the bug. Caught by mutation-testing this file.
    """
    clock = {"t": 1000.0}
    monkeypatch.setattr(su.time, "monotonic", lambda: clock["t"])

    rec = _Recorder([{"scored": 5, "remaining": 5}] * 3)
    def advancing(cmd, **kw):
        out = rec(cmd, **kw)
        clock["t"] += 600            # each pass burns 10 minutes
        return out
    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", advancing)

    su._supervise(_args(passes=3, deadline_min=40))
    budgets = [int(c[c.index("--deadline-min") + 1]) for c in rec.calls]

    assert budgets[0] <= 40
    assert all(b > a for a, b in zip(budgets[1:], budgets)), (
        f"deadline reset per pass instead of shrinking: {budgets}")
    assert budgets[-1] <= 20, f"third pass should have ~20min left, got {budgets}"


def test_a_crashed_pass_does_not_abort_silently(monkeypatch):
    """A failing child stops the loop rather than spinning; nothing raises."""
    def boom(cmd, **kw):
        raise OSError("spawn failed")
    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", boom)
    su._supervise(_args(passes=3))          # must not raise


def test_single_pass_is_the_previous_behaviour():
    """--passes 1 must not enter supervisor mode at all."""
    import inspect
    src = inspect.getsource(su.main)
    assert "if args.passes > 1:" in src
    assert "_supervise(args)" in src
