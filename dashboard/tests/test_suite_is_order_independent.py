"""A test must not depend on what ran before it.

Two mechanisms let earlier tests change the world for later ones, and both had
already caused real failures:

1. sys.modules stubs (fixed in #171)
   Three files replaced utils.config / utils.taxonomy at import time and never
   restored them, so anything collected afterwards in the same xdist worker read
   a fabricated registry.

2. The database schema (fixed here)
   conftest points the app at a fresh temp sqlite file -- and nothing created
   the tables in it. They appeared only if some earlier test happened to drive
   app.py through AppTest, which calls init_db() as a side effect.

   Measured before the fix: tests/test_ticker_deep_dive_sections.py passed in
   the full suite and failed on its own with "no such table: score_snapshots".
   The page reads score history; on its own, nothing had built the table.

Both share a shape: the suite is green, every individual claim looks verified,
and some of them were only ever true because of their neighbours.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_CONFTEST = (Path(__file__).resolve().parent / "conftest.py").read_text(encoding="utf-8")


def test_the_schema_is_built_before_any_test_runs():
    assert "_schema_exists" in _CONFTEST, (
        "the session-scoped schema fixture is gone; tables again exist only if "
        "some earlier test happens to call init_db()"
    )
    # AST, not substring. The fixture's own docstring explains what init_db()
    # does and why -- a text search matches the explanation and passes even when
    # the call itself is deleted. Verified: that mutation slipped through the
    # first version of this test.
    fn = next(
        n for n in ast.walk(ast.parse(_CONFTEST))
        if isinstance(n, ast.FunctionDef) and n.name == "_schema_exists"
    )
    calls = {
        c.func.id for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    }
    assert "init_db" in calls, (
        "the fixture no longer CALLS init_db(); the schema is not created and "
        "tables exist only if some other test happens to build them"
    )


def test_the_schema_fixture_is_session_scoped_and_automatic():
    """Per-test scope would rebuild needlessly; opt-in would not be applied."""
    i = _CONFTEST.index("def _schema_exists")
    decorator = _CONFTEST[:i].rsplit("@pytest.fixture", 1)[-1]
    assert "scope=\"session\"" in decorator, "the schema fixture is not session-scoped"
    assert "autouse=True" in decorator, (
        "the schema fixture is not autouse, so a test file that does not ask "
        "for it is back to depending on its neighbours"
    )


def test_the_database_still_points_at_a_throwaway_file():
    """The fixture must never build the schema in someone's real database."""
    assert "tempfile.mkstemp" in _CONFTEST, (
        "the test database is no longer a temp file -- init_db() now runs "
        "against whatever UNSTRUCTURED_ALPHA_DATABASE_URL resolves to"
    )
    env = re.search(
        r'os\.environ\["UNSTRUCTURED_ALPHA_DATABASE_URL"\]\s*=\s*(.+)', _CONFTEST
    )
    assert env and "_TEST_DB_PATH" in env.group(1), (
        "the test DB URL no longer points at the temp file"
    )
    assert _CONFTEST.index("UNSTRUCTURED_ALPHA_DATABASE_URL") < _CONFTEST.index(
        "def _schema_exists"
    ), "the env var must be set before the fixture that builds the schema"
