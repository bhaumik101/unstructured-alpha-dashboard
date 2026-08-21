"""The Deep Dive rail is a reading order, and it has to survive a theme change.

The rail walks from what the score IS, through what moves it, to what the model
says, to the evidence underneath -- ending with Catalysts & News, Earnings Track
Record and Earnings Sentiment adjacent, so those read as one line of research
rather than being separated by unrelated sections.

WHY A THEME CHANGE IS THE INTERESTING CASE
------------------------------------------
The theme control is an <a href>, not a JS attribute swap, so switching themes
NAVIGATES. That is a fresh Streamlit session and session_state is gone with it.
The selection survives only because two things line up:

  _sync_section_query()  writes ?section=<slug> when the selection is not the
                         default, and deletes it when it is
  _theme_switch_href()   rebuilds the query string keeping every parameter
                         except `theme`

Break either and the reader is silently returned to Overview every time they
switch themes. Both are asserted below.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PAGE = (_ROOT / "pages" / "3_Ticker_Deep_Dive.py").read_text(encoding="utf-8")
_HEADER = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")

EXPECTED_ORDER = [
    "Overview",
    "Thesis Workspace",
    "Price & Technicals",
    "Signal Detail",
    "Model & Cases",
    "Deep Correlation Scan",
    "Insider & Short Interest",
    "13F & Federal Contracts",
    "Catalysts & News",
    "Earnings Track Record",
    "Earnings Sentiment",
]


def _rail_sections() -> list[str]:
    block = _PAGE[_PAGE.index("sections=("): _PAGE.index('section_key="dive_section"')]
    return re.findall(r'"([^"]+)",', block)


def _branch_sections() -> list[str]:
    return re.findall(r'^(?:if|elif) section == "([^"]+)"', _PAGE, re.M)


def test_the_rail_is_in_the_intended_reading_order():
    assert _rail_sections() == EXPECTED_ORDER


def test_catalysts_and_earnings_are_one_uninterrupted_sequence():
    """Split by anything else and they stop reading as one investigation."""
    rail = _rail_sections()
    seq = ["Catalysts & News", "Earnings Track Record", "Earnings Sentiment"]
    idx = [rail.index(s) for s in seq]
    assert idx == sorted(idx) and idx[-1] - idx[0] == len(seq) - 1, (
        f"catalysts and earnings are interrupted: positions {idx} in {rail}"
    )


def test_every_rail_section_renders_and_nothing_renders_unlisted():
    """A rail entry with no branch is a dead click; a branch with no entry is
    analysis the reader cannot reach."""
    rail, branches = _rail_sections(), _branch_sections()
    assert sorted(rail) == sorted(branches), (
        f"rail-only: {sorted(set(rail) - set(branches))}  "
        f"branch-only: {sorted(set(branches) - set(rail))}"
    )


def test_overview_is_first_because_that_is_what_default_means():
    """render_sidebar_base takes options[0] as the default landing view."""
    assert _rail_sections()[0] == "Overview"
    assert re.search(
        r"_default = default_section if default_section in _options else _options\[0\]",
        _HEADER,
    ), "the rail no longer defaults to the first option; re-check what lands first"


def test_only_the_selected_section_executes():
    """if/elif, not st.tabs(): tabs execute every body on every run."""
    branch_lines = re.findall(r"^(if|elif) section == ", _PAGE, re.M)
    assert branch_lines.count("if") == 1, "more than one independent if-chain"
    assert len(branch_lines) == len(EXPECTED_ORDER)
    # AST, not substring: the module docstring explains why the rail was chosen
    # OVER st.tabs(), so a text search matches the rationale and fails on
    # correct code. Sixth time in this codebase that a guard has matched its own
    # explanation; the reliable question is "is there a CALL", not "is the name
    # written anywhere".
    calls = [
        n for n in ast.walk(ast.parse(_PAGE))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "tabs"
    ]
    assert not calls, (
        "st.tabs() is called at line(s) "
        + ", ".join(str(c.lineno) for c in calls)
        + " — tabs execute every body on every rerun, which is the cost this "
        "rail exists to avoid"
    )


def test_the_selection_is_written_to_the_url():
    """Without this, a theme change drops the reader back to Overview."""
    assert re.search(r'st\.query_params\["section"\] = requested_slug', _HEADER), (
        "the rail no longer publishes its selection to the query string"
    )


def test_the_theme_link_preserves_the_section():
    """It rebuilds the query string; anything it drops is lost on theme switch."""
    fn = _HEADER[_HEADER.index("def _theme_switch_href"):]
    fn = fn[: fn.index("\ndef ")]
    assert 'if str(key) == "theme":' in fn and "continue" in fn, (
        "the theme link no longer filters only `theme` out of the query string"
    )
    assert "pairs.extend(" in fn, (
        "the theme link stopped carrying existing query parameters, so ?section= "
        "is dropped and the reader lands back on Overview"
    )
