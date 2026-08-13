"""The false "Page not found" must be removed only when the route is real.

Observed live on /signal-dashboard while signed in, and on /track-record: a
large overlay reading "The page that you have requested does not seem to
exist. Running the app's main page." — with the correct page rendering
underneath it.

It is a cold-start race, not a routing bug. st.navigation() is already the
first Streamlit call in app.py, but on a freshly started process the frontend
resolves the URL before the page list exists. Warm loads never show it, which
is why it survived: it greets the FIRST visitor after every deploy and every
idle spin-down, on a link that works.

The danger in "just hide the message" is hiding a real 404 too. The guard is
that the current path must have a registered route, proven by a proxy
page_link with that exact slug — the same list render_header emits. These
tests pin that the guard cannot be dropped or loosened.
"""

from __future__ import annotations

import re
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "inject_boot_splash.py"
_SRC = _SCRIPT.read_text(encoding="utf-8")


def _fn() -> str:
    i = _SRC.index("function uaDropFalse404()")
    depth, j = 0, _SRC.index("{", i)
    for k in range(j, len(_SRC)):
        if _SRC[k] == "{":
            depth += 1
        elif _SRC[k] == "}":
            depth -= 1
            if depth == 0:
                return _SRC[j : k + 1]
    raise AssertionError("could not find the end of uaDropFalse404")


def test_the_suppressor_exists_and_runs():
    body = _fn()
    assert body, "uaDropFalse404 is missing"
    assert "uaDropFalse404()" in _SRC.replace("function uaDropFalse404()", ""), (
        "uaDropFalse404 is defined but never called"
    )


def test_it_only_fires_on_a_registered_route():
    """The whole safety argument. A real 404 must keep its message."""
    body = _fn()
    assert "registered" in body, "no registered-route guard"
    assert re.search(r"if\(!registered\)\s*return", body), (
        "the guard must bail out early when the slug has no registered route, "
        "or a genuine 404 gets silently swallowed"
    )
    assert "st-key-ua_spa_proxy_rail" in body, (
        "the route list must come from the proxy rail — the same list "
        "render_header emits — not a hardcoded array that will drift"
    )


def test_the_registered_check_precedes_any_removal():
    body = _fn()
    guard = body.index("if(!registered)")
    removals = [m.start() for m in re.finditer(r"\.remove\(\)", body)]
    assert removals, "nothing is ever removed"
    assert all(guard < r for r in removals), (
        "every removal must happen after the registered-route guard"
    )


def test_home_is_never_touched():
    """An empty slug is the default page and always valid."""
    body = _fn()
    assert re.search(r"if\(!slug\)\s*return", body), (
        "home ('' slug) should return early rather than scan the DOM"
    )


def test_it_targets_the_wrapper_structurally_not_by_emotion_hash():
    body = _fn()
    assert "st-emotion-cache" not in body, (
        "emotion hashes change between Streamlit releases; walk up to a "
        "data-testid instead"
    )
    assert re.search(r"stToast|stAlert|stDialog", body), (
        "should find the alert/toast wrapper by data-testid"
    )
