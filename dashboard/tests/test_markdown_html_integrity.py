"""Guard against raw HTML leaking onto the page as visible source.

Streamlit renders `st.markdown(..., unsafe_allow_html=True)` through a markdown
parser, and markdown terminates a raw-HTML block at the first BLANK line. Every
indented line after that terminator is then parsed as an indented code block, so
the remainder of the component is printed to the user as literal HTML source.

This shipped once, on the Ticker Deep Dive confluence banner: an optional
fragment was written as a conditional interpolation occupying its own source
line inside the HTML template::

    <div ...>Conviction: ...</div>
    {f'<div ...>{_earn_caveat}</div>' if _earn_caveat else ''}
    <div style="font-size:0.70rem;...">      <-- rendered as a CODE BLOCK

Whenever the condition was false the interpolation produced an empty string and
the line collapsed to whitespace — the exact blank line that ends the HTML
block. The bug is invisible in the truthy case, which is why it survived
review: it only appears for tickers with no upcoming earnings or no derivable
thesis horizon.

The fix is to pre-render optional fragments into a variable and append them to
an adjacent line, so an empty fragment never owns a line. These tests encode
that rule structurally rather than trusting future edits to remember it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parent.parent

# A source line that is nothing but a single `{...}` interpolation whose
# expression can evaluate to an empty string.
_LONE_OPTIONAL_INTERP = re.compile(
    r"""^\s*\{[^{}]*\bif\b.*\belse\b\s*(?:''|"")\s*\}\s*$"""
)

# A source line that is entirely whitespace inside a template.
_BLANK = re.compile(r"^\s*$")


def _python_files() -> list[Path]:
    files: list[Path] = []
    for sub in ("pages", "utils", "components"):
        d = DASHBOARD / sub
        if d.is_dir():
            files.extend(sorted(d.rglob("*.py")))
    return files


def _html_template_strings(path: Path):
    """Yield (lineno, source_text) for every multi-line string that looks like
    an HTML template — i.e. contains an HTML tag and spans >1 line."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:  # pragma: no cover - a broken file fails elsewhere
        pytest.fail(f"{path.name} does not parse: {exc}")

    for node in ast.walk(tree):
        parts = []
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            parts = [node.value]
        elif isinstance(node, ast.JoinedStr):
            parts = [
                v.value
                for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            ]
        if not parts:
            continue
        text = "".join(parts)
        if "\n" not in text or "<div" not in text and "<span" not in text:
            continue
        yield node.lineno, text


def test_no_lone_optional_interpolation_inside_html_templates():
    """An optional fragment must never occupy its own line in an HTML template.

    When the condition is false the line becomes blank and ends the raw-HTML
    block, dumping the rest of the markup to the page as source.
    """
    offenders: list[str] = []

    for path in _python_files():
        src_lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, _ in _html_template_strings(path):
            # Scan the physical source of the template, not the parsed value:
            # the parsed value has interpolations stripped out.
            for offset in range(lineno - 1, min(lineno + 400, len(src_lines))):
                line = src_lines[offset]
                if _LONE_OPTIONAL_INTERP.match(line):
                    offenders.append(
                        f"{path.relative_to(DASHBOARD)}:{offset + 1}: {line.strip()}"
                    )

    assert not offenders, (
        "Optional HTML fragment occupies its own line inside a markdown HTML "
        "template. When the condition is false this leaves a blank line, which "
        "terminates the raw-HTML block and renders the rest as a code block.\n"
        "Pre-render the fragment into a variable and append it to an adjacent "
        "line instead.\n  " + "\n  ".join(sorted(set(offenders)))
    )


def test_deep_dive_banner_keeps_optional_fragments_inline():
    """Pin the specific banner that regressed.

    The earnings caveat and thesis-window note must be appended to the end of
    the conviction line, never placed on lines of their own.
    """
    src = (DASHBOARD / "pages" / "3_Ticker_Deep_Dive.py").read_text(encoding="utf-8")

    conviction_lines = [
        ln for ln in src.splitlines() if "Conviction:" in ln and "<div" in ln
    ]
    assert conviction_lines, "confluence banner conviction line not found"

    line = conviction_lines[0]
    for frag in ("{_earn_caveat_html}", "{_horizon_note_html}"):
        assert frag in line, (
            f"{frag} must be interpolated on the conviction line so an empty "
            "value cannot create a blank line inside the HTML block"
        )

    # And they must be pre-rendered as complete, single-line strings.
    for name in ("_earn_caveat_html", "_horizon_note_html"):
        assert f"{name} = (" in src, f"{name} should be pre-rendered before the template"


@pytest.mark.parametrize(
    "template,expect_offender",
    [
        ("<div>a</div>\n{x if x else ''}\n<div>b</div>\n", True),
        ("<div>a</div>{x if x else ''}\n<div>b</div>\n", False),
    ],
)
def test_detector_catches_the_shape_it_claims_to(template, expect_offender):
    """The regex must actually fire on the bug and stay quiet on the fix."""
    hit = any(_LONE_OPTIONAL_INTERP.match(ln) for ln in template.splitlines())
    assert hit is expect_offender


def test_blank_line_terminates_html_block_assumption():
    """Document the markdown behaviour this guard depends on.

    If a future Streamlit/markdown version stops treating a blank line as an
    HTML-block terminator, this guard becomes unnecessary rather than wrong —
    but the assumption should be explicit, not folklore.
    """
    md = pytest.importorskip("markdown")
    broken = md.markdown("<div>a</div>\n\n    <div>b</div>")
    assert "<code>" in broken or "&lt;div&gt;" in broken, (
        "expected the indented line after a blank line to be treated as a code "
        "block; if this fails, re-evaluate the guard above"
    )
