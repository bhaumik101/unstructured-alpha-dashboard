"""Section labels must be headings, and must not be restyled into headings.

Signal Dashboard runs ~11 screens and its major sections — MULTI-SIGNAL HEAT
MAP, TOP SIGNALS TO WATCH, SIGNAL INDEPENDENCE — already had visible titles.
They were `<div class="section-header">`, so the document outline could not see
them: the whole page reported a single h1. Same defect as the page title in
#133, one level down.

The conversion is semantics-only and MUST stay pixel-identical, which is the
part that needs guarding. `.section-header` renders 0.63rem uppercase
micro-labels, while the global heading rules set colour, family, weight,
letter-spacing and a size on h2 — all !important. Without matching !important
here, promoting the tag silently turns a 10px label into a 20.8px heading. That
exact failure shipped once already, in #133, and was fixed in #134.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CSS = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")
# pages/retired/ is not shipped, so it is deliberately excluded.
_LIVE_PAGES = [p for p in _ROOT.glob("pages/*.py")]


def _emissions() -> list[tuple[str, str]]:
    """(filename, tag) for every element carrying class="section-header"."""
    out = []
    for path in _LIVE_PAGES:
        for m in re.finditer(r'<(\w+)\s+class="section-header"', path.read_text(encoding="utf-8")):
            out.append((path.name, m.group(1).lower()))
    return out


def test_section_headers_are_emitted_as_headings():
    emitted = _emissions()
    assert emitted, "no section-header elements found — re-point this test"
    divs = [f"{f}: <{t}>" for f, t in emitted if t != "h2"]
    assert not divs, (
        "these section labels are not headings, so they are invisible to the "
        "document outline and to screen-reader heading navigation:\n"
        + "\n".join(divs)
    )


def test_the_section_header_rule_survives_the_global_heading_rules():
    """Semantics change, appearance does not.

    Each of these is set !important by the global h1-h3 / h2 rules. A plain
    declaration here loses, and the label becomes a heading visually too.
    """
    block = re.sub(r"/\*.*?\*/", "", _CSS, flags=re.S)
    i = block.index(".section-header {")
    rule = block[i : block.index("}", i) + 1]

    for prop in ("font-size", "font-weight", "color", "font-family",
                 "letter-spacing", "margin"):
        m = re.search(rf"(?<![-\w]){prop}\s*:[^;]*;", rule)
        assert m, f".section-header must set {prop} to hold its appearance"
        assert "!important" in m.group(0), (
            f".section-header `{m.group(0).strip()}` loses to the global heading "
            f"rules; the label will render as a full-size heading"
        )


def test_the_permalink_widget_is_hidden_on_section_headers():
    """Streamlit attaches a hover anchor to anything it parses as a heading.

    These are labels, not anchor targets, and the icon shifts them on hover.
    """
    assert re.search(
        r'\.section-header \[data-testid="stHeaderActionElements"\]\s*\{[^}]*display:\s*none',
        _CSS,
    ), "the heading permalink widget is not hidden on .section-header"
