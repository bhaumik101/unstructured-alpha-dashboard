"""The Track Record must hold the calls the model made, not the ones that fit on a page.

Convergence events are the input to prediction_log, which is what the Track
Record page scores the model on. Until now the only thing that wrote them was
render_convergence_events() -- and it logs what it DRAWS:

    bull_events[:max_bull]   capped at 3 (Today's Brief) or 4 (Home)
    bear_events[:max_bear]   capped at 1-2

So at most five to seven calls per day could ever be recorded, and only on days
when somebody opened one of those two pages. The admin dashboard shows days with
zero unique visitors -- 2026-08-09 and 2026-08-15 among them -- on which the
model made calls that were never written down.

Two distinct biases, both invisible from inside the number:

  display   the record kept the highest-ranked events, which are not a random
            sample of the model's calls
  traffic   whether a day is represented at all depended on whether anyone
            was looking

A scheduled job now logs every detected event. log_prediction() is idempotent on
(ticker, event_date, event_type), so both writers can run without duplicating.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CONV = (_ROOT / "utils" / "convergence.py").read_text(encoding="utf-8")
_DIGEST = (_ROOT / "cron" / "send_digest.py").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> ast.FunctionDef:
    return next(
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.FunctionDef) and n.name == name
    )


def test_a_headless_logger_exists():
    fn = _fn(_CONV, "log_convergence_predictions")
    calls = {
        c.func.id for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    }
    assert "_log_convergence_prediction_once" in calls, (
        "log_convergence_predictions no longer logs anything"
    )


def test_the_headless_logger_does_not_slice_the_event_list():
    """Any cap here reintroduces the display bias in a new place."""
    fn = _fn(_CONV, "log_convergence_predictions")
    # Specifically: the loop must iterate `events` itself. A blanket "no
    # slices" check is wrong -- the error branch slices a string for the log
    # line, and the first version of this test failed on that rather than on a
    # cap being reintroduced.
    loops = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
    assert loops, "the logger no longer iterates the events"
    iterated_bare = any(
        isinstance(loop.iter, ast.Name) and loop.iter.id == "events" for loop in loops
    )
    assert iterated_bare, (
        "the headless logger iterates something other than `events` directly -- "
        "if that is a slice, it records a subset again, which is the bias this "
        "function exists to remove"
    )


def test_a_scheduled_job_calls_it():
    """Rendering must not be the only writer."""
    tree = ast.parse(_DIGEST)
    called = {
        c.func.id for c in ast.walk(tree)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    }
    assert "log_convergence_predictions" in called, (
        "no cron logs convergence predictions, so the Track Record is back to "
        "recording only what a page happened to draw for a visitor"
    )


def test_the_render_path_still_logs_too():
    """Belt and braces: a failed cron run should not lose that day entirely."""
    fn = _fn(_CONV, "render_convergence_events")
    calls = {
        c.func.id for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    }
    assert "_log_convergence_prediction_once" in calls, (
        "the render path stopped logging; the cron is now the only writer and "
        "one failed run means a day with no record"
    )


def test_logging_is_idempotent_so_two_writers_are_safe():
    src = (_ROOT / "utils" / "prediction_log.py").read_text(encoding="utf-8")
    fn = _fn(src, "log_prediction")
    body = ast.get_source_segment(src, fn) or ""
    assert "upsert_stmt" in body, (
        "log_prediction no longer upserts, so the cron and the page would "
        "insert duplicate rows for the same call"
    )
