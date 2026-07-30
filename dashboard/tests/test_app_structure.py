"""
Structural sanity checks: every .py file in pages/ is accounted for, and
the syntax of every file in the project parses cleanly. These are the
cheapest possible tests — they should fail in milliseconds and catch the
dumbest class of mistake (typo, stray bracket, orphaned page file) before
anything else even runs.
"""

import ast
from pathlib import Path

from tests.conftest import DASHBOARD_ROOT, ROUTED_PAGES


def _all_project_py_files():
    files = []
    for sub in ("", "pages", "utils"):
        for p in (DASHBOARD_ROOT / sub).glob("*.py"):
            files.append(p)
    return files


def test_every_python_file_parses():
    """Catches syntax errors before Streamlit ever gets a chance to."""
    bad = []
    for f in _all_project_py_files():
        try:
            ast.parse(f.read_text())
        except SyntaxError as e:
            bad.append(f"{f.relative_to(DASHBOARD_ROOT)}: {e}")
    assert not bad, "Syntax errors found:\n" + "\n".join(bad)


def test_every_pages_file_is_accounted_for():
    """
    Every file under pages/ must be a routed page (in ROUTED_PAGES). If
    someone adds a new page file and forgets to register it in app.py's
    st.navigation(), or forgets to update ROUTED_PAGES, this catches the
    drift instead of it silently never being tested. (Retired-stub pages
    used to be a separate, allowed category here -- removed along with
    the actual stub files once a real filesystem could delete them.)
    """
    known = {Path(p).name for p in ROUTED_PAGES}
    actual = {p.name for p in (DASHBOARD_ROOT / "pages").glob("*.py")}
    unaccounted = actual - known
    assert not unaccounted, (
        f"pages/ contains files not listed in ROUTED_PAGES in tests/conftest.py: {unaccounted}"
    )


def test_app_py_navigation_matches_routed_pages():
    """
    Parses app.py's st.navigation() call and checks every st.Page(...) path
    it registers is exactly the set in ROUTED_PAGES — catches the case where
    app.py changes but conftest.py's mirror of it doesn't (or vice versa).
    """
    tree = ast.parse((DASHBOARD_ROOT / "app.py").read_text())
    registered = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "Page":
            if node.args and isinstance(node.args[0], ast.Constant):
                registered.add(node.args[0].value)
    assert registered == set(ROUTED_PAGES), (
        f"app.py registers {registered} but tests/conftest.py's ROUTED_PAGES "
        f"has {set(ROUTED_PAGES)} — keep these in sync."
    )


def test_schema_initialization_is_process_cached_with_page_fallback():
    app = (DASHBOARD_ROOT / "app.py").read_text(encoding="utf-8")
    brief = (DASHBOARD_ROOT / "pages" / "2_Today_Digest.py").read_text(
        encoding="utf-8"
    )

    assert "@st.cache_resource(show_spinner=False)" in app
    assert "def _initialize_app_database()" in app
    assert 'st.session_state["_ua_app_db_ready"] = True' in app
    assert 'if not st.session_state.get("_ua_app_db_ready"):' in brief
    assert brief.index('if not st.session_state.get("_ua_app_db_ready"):') < brief.index(
        "    init_db()"
    )
