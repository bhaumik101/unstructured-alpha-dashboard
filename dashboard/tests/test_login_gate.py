"""Guards for the blocking sign-in gate (utils.auth_ui.require_login).

Two bugs found live on 2026-08-11, both invisible to the suite because nothing
here asserted anything about the gate:

  - /thesis-journal told the visitor "Sign in to use your watchlist". The line
    was a literal in require_login() from when Watchlist was the only caller.
  - /welcome rendered a COMPLETELY BLANK page. require_login() runs at module
    line 30, before the page emits anything, and the not-ready branch was a
    bare st.stop(). CookieManager is a Streamlit component and reports
    readiness only after it renders, so stopping with nothing flushed leaves
    the page blank with no path forward.

Both are source-level assertions: the gate calls st.stop(), so exercising it
for real needs a Streamlit runtime this suite does not have.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_AUTH_UI = _ROOT / "utils" / "auth_ui.py"
_AUTH_UI_SRC = _AUTH_UI.read_text(encoding="utf-8")

# Every page that blocks on a login. pages/retired/ is not registered in app.py.
_CALLERS = [
    _ROOT / "pages" / "10_Watchlist.py",
    _ROOT / "pages" / "46_Thesis_Journal.py",
    _ROOT / "pages" / "47_Account_Setup.py",
]


def _require_login_node() -> ast.FunctionDef:
    for node in ast.walk(ast.parse(_AUTH_UI_SRC)):
        if isinstance(node, ast.FunctionDef) and node.name == "require_login":
            return node
    raise AssertionError("require_login is gone from utils/auth_ui.py")


def test_every_blocking_page_is_still_covered_here():
    """Drift guard: a new require_login() caller must be added to _CALLERS.

    Without this, someone adds a fourth gated page, it inherits whatever the
    default prompt is, and the copy test below still passes.
    """
    found = {
        p.relative_to(_ROOT).as_posix()
        for p in _ROOT.glob("pages/*.py")
        if re.search(r"^\s*\w+\s*=\s*require_login\(", p.read_text(encoding="utf-8"), re.M)
    }
    known = {p.relative_to(_ROOT).as_posix() for p in _CALLERS}
    assert found == known, (
        f"require_login() callers changed -- update _CALLERS in this test. "
        f"new: {sorted(found - known)}, gone: {sorted(known - found)}"
    )


def test_gate_copy_is_not_hardcoded_to_one_page():
    """The prompt must come from the caller, not a literal in the gate."""
    node = _require_login_node()
    # The docstring names the old string while explaining the bug, so assert
    # against the executable statements only.
    stmts = node.body[1:] if ast.get_docstring(node) else node.body
    code = "\n".join(ast.get_source_segment(_AUTH_UI_SRC, s) or "" for s in stmts)
    assert "your watchlist" not in code, (
        "require_login() hard-codes watchlist copy again -- every gated page "
        "would show it, as /thesis-journal and /welcome did"
    )
    args = [a.arg for a in node.args.args]
    assert "prompt" in args, "require_login must take the gate line as a parameter"


def test_each_gated_page_passes_its_own_prompt():
    """A page relying on the default gets generic copy, which is the bug."""
    for page in _CALLERS:
        src = page.read_text(encoding="utf-8")
        # Anchored on the assignment: the word also appears in imports and in
        # a prose comment, and matching those made this test pass on nothing.
        call = re.search(r"^\s*\w+\s*=\s*require_login\((.*?)\)\s*$", src, re.M | re.S)
        assert call, f"{page.name}: require_login call not found"
        arg = call.group(1).strip()
        assert arg, f"{page.name}: passes no prompt, so it inherits generic copy"
        assert "watchlist" not in arg.lower() or page.name.startswith("10_"), (
            f"{page.name}: is not the watchlist but says 'watchlist'"
        )


def test_the_not_ready_branch_renders_before_it_stops():
    """A bare st.stop() here is the /welcome blank page.

    The branch must emit markup first -- both so the visitor sees something
    and so CookieManager has a render in which to become ready.
    """
    node = _require_login_node()
    branch = next(
        (
            n
            for n in ast.walk(node)
            if isinstance(n, ast.If)
            and "ready" in (ast.get_source_segment(_AUTH_UI_SRC, n.test) or "")
        ),
        None,
    )
    assert branch is not None, "the cookies-not-ready branch is gone"
    body = "\n".join(
        ast.get_source_segment(_AUTH_UI_SRC, stmt) or "" for stmt in branch.body
    )
    assert "st.stop()" in body, "expected this branch to still halt the script"
    renders = [ln for ln in body.splitlines() if re.search(r"\b(_render_gate_brand|st\.(markdown|caption|write|html|info))\b", ln)]
    assert renders, (
        "the cookies-not-ready branch stops without rendering anything -- that "
        "is a blank page, which is what /welcome shipped as"
    )
