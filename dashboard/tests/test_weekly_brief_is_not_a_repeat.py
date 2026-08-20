"""The weekly brief must be this week's, and must not depend on a visitor.

Two failures that compound, both silent.

1. NOTHING SCHEDULED GENERATED THE NOTE
   utils.narrative_engine.generate_weekly_note() was called from exactly one
   place: app.py, on a page load, gated by should_auto_generate() -- true on
   Sundays when no note exists yet. No cron called it.

   So the content of the weekly newsletter depended on a human opening the app
   on a Sunday before the 16:00 UTC send. On a product with ~190 landing
   visitors total, a Sunday morning with no traffic is an ordinary occurrence,
   not an edge case.

2. THE SENDER HAD NO RECENCY FILTER
   _get_latest_brief() takes the newest macro_narratives row, full stop. With
   no note generated, that is LAST week's -- so every subscriber receives a
   brief they have already read, under the subject "Weekly Macro Brief", and
   nothing in the email says it is a repeat.

The cron now generates the note itself and refuses to send one older than two
days, exiting non-zero so Render surfaces a missing brief rather than logging a
quiet success. cron/check_data_freshness.py also watches macro_narratives now.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SENDER = (_ROOT / "cron" / "send_brief_subscribers.py").read_text(encoding="utf-8")
_FRESHNESS = (_ROOT / "cron" / "check_data_freshness.py").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> ast.FunctionDef:
    return next(
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.FunctionDef) and n.name == name
    )


def test_the_cron_generates_the_note_itself():
    """Otherwise the newsletter's content depends on Sunday traffic."""
    calls = {
        c.func.id for c in ast.walk(_fn(_SENDER, "_ensure_fresh_note"))
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    }
    assert "generate_weekly_note" in calls, (
        "the cron no longer generates the note, so it is back to relying on a "
        "visitor loading app.py before the send"
    )
    main = _fn(_SENDER, "main")
    called = [
        c.func.id for c in ast.walk(main)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    ]
    assert "_ensure_fresh_note" in called, "main() never asks for a fresh note"
    assert called.index("_ensure_fresh_note") < called.index("_get_latest_brief"), (
        "the note is generated after it is read, so the first send still uses "
        "whatever was already there"
    )


def test_a_stale_brief_is_refused_rather_than_re_sent():
    main = _fn(_SENDER, "main")
    src = ast.get_source_segment(_SENDER, main) or ""
    assert "_brief_age_days" in src, "main() no longer checks the brief's age"
    assert re.search(r"sys\.exit\(\s*1\s*\)", src), (
        "a stale brief should exit non-zero so Render shows a failed run; a "
        "silent return looks identical to a successful send"
    )


def test_the_age_limit_cannot_span_a_week():
    """Any limit >= 7 lets last week's brief through, which is the whole bug."""
    m = re.search(r"_MAX_BRIEF_AGE_DAYS\s*=\s*(\d+)", _SENDER)
    assert m, "_MAX_BRIEF_AGE_DAYS is gone"
    assert int(m.group(1)) < 7, (
        f"limit is {m.group(1)} days — at 7 or more, a brief generated last "
        "Sunday still qualifies and subscribers get the repeat this guards against"
    )


def test_freshness_monitor_watches_the_narratives_table():
    assert '"macro_narratives"' in _FRESHNESS, (
        "macro_narratives is unmonitored, so a generator that stops producing "
        "notes is invisible until someone notices a duplicate newsletter"
    )


def test_the_generator_is_still_reachable_from_the_app_too():
    """The cron is the guarantee; the page load is the fast path. Keep both."""
    app = (_ROOT / "app.py").read_text(encoding="utf-8")
    assert "should_auto_generate" in app, (
        "app.py no longer generates on Sunday page loads; the cron is now the "
        "only path and a failed run means no brief at all"
    )
