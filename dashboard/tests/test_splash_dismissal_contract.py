"""The splash must stop covering the first data fetch — without ever lifting
over an empty page.

`isStreamlitBusy()` is true for the whole first script run, and that run
includes the provider calls. So the full-screen cover stayed up through data
fetching, not just through Streamlit's boot. A labelled "Building your command
center…" spinner inside the real page is better progress information than a
logo, and the app has ~98 st.spinner sites to provide it.

`ready()` now has a layout budget: past LAYOUT_READY_MS it lifts as soon as the
page structure exists. Two properties matter and neither is visible to any
rendering test, so they are asserted against the real source of the function —
not a Python mirror of it. A mirror would keep passing after the implementation
changed underneath it, which is exactly how a previous test on this project
gave false confidence.
"""

from __future__ import annotations

import re
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "inject_boot_splash.py"
_SRC = _SCRIPT.read_text(encoding="utf-8")


def _ready_body() -> str:
    """The real `function ready(){...}` body from the injected JS."""
    i = _SRC.index("function ready(){")
    depth, j = 0, _SRC.index("{", i)
    for k in range(j, len(_SRC)):
        if _SRC[k] == "{":
            depth += 1
        elif _SRC[k] == "}":
            depth -= 1
            if depth == 0:
                return _SRC[j : k + 1]
    raise AssertionError("could not find the end of ready()")


def _const(name: str) -> int:
    m = re.search(rf"var {name}\s*=\s*(\d+)", _SRC)
    assert m, f"{name} is missing"
    return int(m.group(1))


def test_the_layout_budget_sits_between_the_floor_and_the_hard_timeout():
    floor, budget, cap = (
        _const("MIN_VISIBLE_MS"),
        _const("LAYOUT_READY_MS"),
        _const("HARD_TIMEOUT_MS"),
    )
    assert floor < budget < cap, (
        f"LAYOUT_READY_MS ({budget}) must be above the minimum visible time "
        f"({floor}) and well below the hard timeout ({cap})"
    )


def test_the_splash_never_lifts_over_an_empty_page():
    """The one thing the budget must not cost us.

    hasRenderedContent() has to gate every exit path, including the budget one.
    If the budget check came first, a slow page would drop the cover onto a
    blank canvas at LAYOUT_READY_MS.
    """
    body = _ready_body()
    content = body.index("hasRenderedContent()")
    budget = body.index("LAYOUT_READY_MS")
    assert content < budget, (
        "hasRenderedContent() must be checked BEFORE the layout budget can "
        "return true, or the splash lifts over an empty page"
    )
    assert re.search(r"if\(!hasRenderedContent\(\)\)\s*return false", body), (
        "hasRenderedContent() must be a hard gate, not one term of an OR"
    )


def test_the_minimum_visible_floor_is_still_checked_first():
    body = _ready_body()
    assert body.index("MIN_VISIBLE_MS") < body.index("hasRenderedContent()"), (
        "the floor must be evaluated before anything else, so a fast render "
        "cannot produce a flash of splash"
    )


def test_fast_loads_still_wait_to_be_genuinely_ready():
    """The budget is a ceiling on waiting, not a replacement for readiness.

    Under LAYOUT_READY_MS the original condition must still apply, otherwise
    this stops being "lift once layout renders" and becomes "lift at 900ms".
    """
    body = _ready_body()
    assert "isStreamlitBusy()" in body, (
        "the not-busy check was removed entirely; fast loads would lift the "
        "splash mid-render instead of when ready"
    )
    assert "SETTLE_MS" in body, "the DOM-settle check was removed entirely"


def test_the_hard_timeout_still_exists():
    """The splash must never be able to cover an error forever."""
    uses = [
        ln.strip()
        for ln in _SRC.splitlines()
        if "HARD_TIMEOUT_MS" in ln and not re.match(r"\s*var HARD_TIMEOUT_MS", ln)
    ]
    assert uses, "HARD_TIMEOUT_MS is declared but never used"
    assert any("setTimeout" in ln and "hide()" in ln for ln in uses), (
        f"the hard-timeout escape hatch must still call hide(); found: {uses}"
    )
