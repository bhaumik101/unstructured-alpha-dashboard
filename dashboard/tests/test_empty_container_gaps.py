"""Guard for the rule that collapses element containers which cannot paint.

The page's vertical block is display:flex with row-gap:16px, so every child
costs 16px whether or not it renders. A st.markdown emitting only a <style> or
<script> tag is a 0px-tall flex child that still takes a full gap. Measured on
the deployed app 2026-08-11: 8 of them on Signal Dashboard (112px), 2 on Home
(32px). PR #131 fixed the same arithmetic for the 33 proxy links; this is the
rest of it.

The rule is a `display: none` on a `:has()` selector, which makes its scope the
entire safety argument. A broader draft -- one that also took `st.html`
wrappers out of flow, to reclaim the top nav's and the scroll-to-top button's
gaps -- was probed in the browser first and pulled 2,682px of REAL content off
Home, because Home renders content through st.html. These tests exist so that
draft cannot come back by accident.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_HEADER_SRC = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")

_MARKER = "Element containers that cannot paint"


def _rule_block() -> str:
    """The selector list plus its declaration block."""
    idx = _HEADER_SRC.find(_MARKER)
    assert idx != -1, f"the {_MARKER!r} rule is gone from the stylesheet"
    end = _HEADER_SRC.find("}", idx)
    assert end != -1, "the rule has no closing brace"
    return _HEADER_SRC[idx:end]


def _selectors() -> list[str]:
    block = _rule_block()
    # Everything after the last comment close, up to the opening brace.
    body = block[block.rfind("*/") + 2 : block.rfind("{")]
    return [s.strip() for s in body.split(",") if s.strip()]


def test_the_rule_only_hides_containers_that_cannot_render_anything():
    """Every selector must carry an emptiness proof, not just a shape.

    Without the :not(), `:has([data-testid="stMarkdownContainer"])` matches
    EVERY markdown on the page -- which is most of the app.
    """
    for sel in _selectors():
        if "stEmpty" in sel:
            continue  # st.empty() is a placeholder; it renders nothing by definition
        assert ":not(" in sel, (
            f"this selector hides any markdown container, painted or not: {sel}"
        )
        assert re.search(r":not\(.*\*:not\(style\):not\(script\).*\)", sel), (
            "the guard must be 'contains no child other than style/script' -- "
            f"anything looser hides real content: {sel}"
        )


def test_the_rule_does_not_reach_st_html():
    """st.html carries real content on Home; a draft that included it cost
    2,682px of that page. Measured, not theorised."""
    block = _rule_block()
    selectors_only = block[block.rfind("*/") + 2 :]
    assert "stHtml" not in selectors_only, (
        "st.html wrappers must stay in flow -- Home renders real content "
        "through st.html, and taking those out of flow collapses the page"
    )


def test_the_rule_stays_scoped_to_the_main_page_body():
    """Unscoped, this would also strip containers inside the sidebar and any
    dialog, whose layouts are not this flex column."""
    for sel in _selectors():
        assert sel.startswith('[data-testid="stMain"]'), (
            f"selector must be scoped to the main body: {sel}"
        )
