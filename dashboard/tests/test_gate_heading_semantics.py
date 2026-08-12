"""A gated page still needs an h1.

Found by the live surface sweep: Portfolio Suite had zero h1 elements and its
heading hierarchy started at h2. `require_pro()` calls `st.stop()` before
`render_page_header()` ever runs, so the h1 that #133/#134 gave every page
never gets emitted on a gated one. The gate's own heading IS the page title in
that state.

Both gate branches are affected -- signed-out ("Sign in to access X") and
signed-in-free ("Unlock X") -- across the 12 pages behind require_pro.

The styling is the same specificity fight as .ua-page-title, and the numbers
here are measured on the deployed gate rather than read off the rule: a global
`h2 { font-size: 1.3rem !important }` had been beating `.pro-gate h2`'s own
1.45rem, so the heading always rendered at 20.8px. As an h1 it would instead
take `h1 { font-size: 1.75rem !important }` (28px) plus the default 18.76px
margins.
"""

from __future__ import annotations

import re
from pathlib import Path

_BILLING = Path(__file__).resolve().parent.parent / "utils" / "billing.py"
_SRC = _BILLING.read_text(encoding="utf-8")


def _gate_css() -> str:
    i = _SRC.index("_PRO_GATE_CSS")
    block = _SRC[i : _SRC.index('"""', _SRC.index('"""', i) + 3)]
    return re.sub(r"/\*.*?\*/", "", block, flags=re.S)


def test_both_gate_branches_emit_an_h1():
    """Signed-out and signed-in-free both render a gate; both are page titles."""
    headings = re.findall(r"<(h[1-6])>[^<]*(?:Sign in to access|Unlock)", _SRC)
    assert headings, "the gate headings moved -- re-point this test"
    assert len(headings) == 2, (
        f"expected both gate branches, found {len(headings)}: {headings}"
    )
    assert set(headings) == {"h1"}, (
        f"a gated page has no other page title, so the gate heading must be an "
        f"h1; found {headings}"
    )


def test_the_gate_h1_is_styled_so_it_renders_as_it_did():
    """Semantics change, appearance does not.

    Without !important the h1 takes the global `h1 { font-size: 1.75rem
    !important }` and the browser's default margins -- 28px and 18.76px instead
    of 20.8px and 0/8px.
    """
    css = _gate_css()
    rule = re.search(r"\.pro-gate h1\s*\{([^}]*)\}", css)
    assert rule, ".pro-gate h1 has no rule; the heading will be restyled"
    body = rule.group(1)
    for prop in ("font-size", "margin"):
        m = re.search(rf"(?<![-\w]){prop}\s*:[^;]*;", body)
        assert m, f".pro-gate h1 must set {prop}"
        assert "!important" in m.group(0), (
            f".pro-gate h1 `{m.group(0).strip()}` loses to the global h1 rule"
        )


def test_no_stale_h2_rule_is_left_behind():
    """The old rule would silently do nothing once the tag changed."""
    css = _gate_css()
    assert ".pro-gate h2" not in css, (
        "the .pro-gate h2 rule no longer matches anything -- remove it rather "
        "than leaving a declaration that reads as active"
    )
