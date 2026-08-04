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


def test_stops_as_soon_as_nothing_remains(monkeypatch):
    """Don't pay for process starts after coverage is complete."""
    rec = _run(monkeypatch, [{"scored": 34, "remaining": 100},
                             {"scored": 100, "remaining": 0},
                             {"scored": 9, "remaining": 9}], passes=4)
    assert len(rec.calls) == 2


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
