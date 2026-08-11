"""Chrome markup must never be able to render as an indented code block.

The masthead shipped as a multi-line indented f-string. That worked only while
its left slot was always non-empty. The moment the slot could be empty, the
template produced a blank line followed by an 8-space-indented "</div>" -- and
Streamlit's markdown parser reads blank-line-then-4-space-indent as an INDENTED
CODE BLOCK. The result was the raw masthead source printed on screen, on every
page, in production.

utils/header._render_topnav already documents this exact hazard for the nav
markup ("Streamlit's markdown parser treats blank-line-then-4-space-indented
HTML as an indented CODE BLOCK -- which was dumping the raw <div
class='ua-tnav-group'>... source as literal text") and avoids it with st.html().
The same trap was sitting one function away, and an interpolated slot that could
go empty was all it took to spring it.

The rule these pin: chrome HTML is emitted either through st.html(), or as a
single line with no leading whitespace. Never as an indented multi-line
markdown template with interpolated slots.
"""

from __future__ import annotations

import re
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent
HEADER = DASHBOARD / "utils" / "header.py"


def _render_header_body() -> str:
    src = HEADER.read_text(encoding="utf-8")
    return src.split("def render_header(", 1)[1].split("\ndef ", 1)[0]


def test_masthead_is_not_an_indented_multiline_markdown_template() -> None:
    body = _render_header_body()
    # A triple-quoted st.markdown whose first markup line is indented is the
    # precise shape that fails.
    offenders = re.findall(
        r'st\.markdown\(\s*f?"""\s*\n(\s+)<', body
    )
    assert not offenders, (
        "render_header emits HTML via an indented multi-line markdown template. "
        "If any interpolated slot renders empty, Streamlit treats the block as "
        "an indented code block and prints the raw markup to the user. Emit it "
        "on one unindented line, or use st.html()."
    )


def test_masthead_omits_its_left_slot_rather_than_leaving_it_blank() -> None:
    """Drop the empty container — but note this was NOT what broke rendering.

    The first version of this test claimed the empty <div> caused the code
    block. It did not: the cause was the blank LINE the indented template put
    inside it. Omitting the container is still right (an empty flex child is
    dead weight), but the guard that actually prevents the bug is the
    single-unindented-line test above, and mis-attributing it here would send
    the next reader after the wrong thing.
    """
    body = _render_header_body()
    assert '_left_block = f\'<div class="ua-header-left">{_left_html}</div>\' if _left_html else ""' in body, (
        "the left slot must be dropped entirely when empty, not rendered as an "
        "empty container"
    )


def test_right_block_right_aligns_without_a_left_sibling() -> None:
    """.ua-header is flex/space-between, which only pushes this block right
    while something sits to its left. With the masthead's left slot empty it
    became the sole child and drifted to the middle of the page."""
    css = HEADER.read_text(encoding="utf-8")
    block = css.split(".ua-header-right {", 1)[1].split("}", 1)[0]
    assert "margin-left: auto" in block, (
        "the header's right block must right-align on its own, not by relying "
        "on a sibling that may not exist"
    )


def test_masthead_markup_has_no_leading_whitespace_before_a_tag() -> None:
    """Belt and braces: no string literal in the masthead starts with spaces
    followed by '<'."""
    body = _render_header_body()
    bad = re.findall(r'f?[\'"]\s{4,}<div', body)
    assert not bad, f"indented HTML string literals in the masthead: {bad}"
