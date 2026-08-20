"""init_db() must survive being called from two places at once.

metadata.create_all(checkfirst=True) is not atomic. It inspects the schema and
then issues CREATE TABLE, so two callers can both pass the inspection before
either creates anything; the loser raises

    sqlite3.OperationalError: table users already exists

That is not hypothetical. seo/main.py warms the engine in a daemon thread at
import specifically to pay the init_db() cost off the request path -- so any
other init_db() in the same process races it. Measured: tests/test_brief_page.py
imports seo.main at module scope and failed roughly 1 run in 5, all 8 tests
erroring at fixture setup, with exactly that error.

The same collision is available to the live SEO service whenever a request
initialises while the warm thread is still running.

A correction goes with this. #179 said init_db() "is CREATE TABLE IF NOT EXISTS,
so tests that also call it are unaffected". The first half is roughly right and
the conclusion was wrong: checkfirst makes it idempotent in sequence, not under
concurrency.
"""

from __future__ import annotations

import ast
import threading
from pathlib import Path

_DB_SRC = (Path(__file__).resolve().parent.parent / "utils" / "db.py").read_text(
    encoding="utf-8"
)


def test_init_db_holds_a_lock_for_the_whole_body():
    """Both create_all AND the migrations must be inside the critical section."""
    fn = next(
        n for n in ast.walk(ast.parse(_DB_SRC))
        if isinstance(n, ast.FunctionDef) and n.name == "init_db"
    )
    withs = [n for n in fn.body if isinstance(n, ast.With)]
    assert withs, "init_db no longer serialises; concurrent callers can collide"

    guarded = {
        c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", "")
        for w in withs for c in ast.walk(w) if isinstance(c, ast.Call)
    }
    assert "create_all" in guarded, "create_all is outside the lock"
    migrations = [
        n.value.func.id
        for n in fn.body
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id.startswith("_migrate")
    ]
    assert not migrations, (
        "these migrations run outside the lock and can interleave with another "
        f"caller's create_all: {migrations}"
    )


def test_concurrent_init_db_calls_do_not_raise():
    """The actual behaviour, not just its shape."""
    from utils.db import init_db

    errors: list[BaseException] = []

    def _go():
        try:
            init_db()
        except BaseException as exc:      # noqa: BLE001 - recording, not handling
            errors.append(exc)

    threads = [threading.Thread(target=_go) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, (
        "concurrent init_db() raised: "
        + "; ".join(f"{type(e).__name__}: {str(e)[:80]}" for e in errors)
    )
