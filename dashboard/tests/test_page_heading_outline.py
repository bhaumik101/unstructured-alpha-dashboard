"""A page's heading levels must start at h2 and not skip.

Every page emits an h1 from render_page_header (or the Home hero). Markdown
headings inside the page continue that outline, so the shallowest one must be
h2. Measured on the deployed Ticker Deep Dive before this was fixed:

    H1, H3, H4, H5, H3, H5, H5, H5, H5, H3, H3, H5, H4, H3

H2 never appeared. The reader jumps h1 -> h3, then h3 -> h5. On a 15-screen
page that is the difference between a skimmable outline and a wall.

WHY THE RULE IS "CONTIGUOUS SET" AND NOT "NO SKIP IN ORDER"
-----------------------------------------------------------
Headings live in different `if` branches, so source order is not render order
and not every heading appears in the same run. Asserting "no skip between
consecutive headings in file order" would fail on perfectly correct pages where
an h4 in one branch is followed in the file by an h2 in another.

What IS safe to assert regardless of branching: the SET of levels a page uses
must be contiguous starting at h2. A page using {h2, h3, h4} is fine in any
order. A page using {h3, h4, h5} has no h2 under its h1 no matter which branch
runs, and a page using {h2, h4} has an orphan level.

WHAT THIS DELIBERATELY CANNOT CATCH
-----------------------------------
Mutation-tested: demoting ONE section from h2 back to h3, while other h2s
remain, leaves the set {h2, h3, h4} contiguous and passes. The rule sees the
levels a page uses, not whether each individual heading sits at the right depth
for its content.

That is the price of being branch-safe, and it is the right trade here — a
false failure on every correct page would get the test deleted. Catching
per-heading depth needs the rendered DOM in document order, which belongs with
the axe harness in scripts/a11y_audit.mjs, not in a source-parsing unit test.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PAGES = _ROOT / "pages"

# Pages emit headings two ways, and the outline is the union of both. Counting
# only markdown would have missed the <h2 class="section-header"> elements on
# Signal Dashboard entirely — they are real headings in the shipped DOM.
# Must be the argument to a Streamlit text call. Matching any quoted "# ..."
# string counted chart axis titles as headings -- `title=dict(text="# Tickers")`
# on Stock Screener and `y_title="# of signals"` on Home both registered as h1,
# which would have demanded "fixing" a chart label.
_HEADING = re.compile(
    r'st\.(?:markdown|write|subheader)\(\s*f?["\'](#{1,6})\s'
)
_HTML_HEADING = re.compile(r"<h([1-6])[\s>]")                     # <h2 class="...">


def _html_levels(src: str) -> set[int]:
    """HTML heading levels, ignoring h1 — that belongs to render_page_header."""
    return {int(m.group(1)) for m in _HTML_HEADING.finditer(src)} - {1}

# Pages whose outline is not yet corrected. Deep Dive was fixed first because it
# is the deepest page in the product at ~15 screens. Shrink this list; never
# grow it.
_NOT_YET_FIXED = {
    # 37_Legal.py emits 31 <h3> in raw HTML with inline sizing. Promoting them
    # pushes 16px -> 20.8px under the global h2 rule, which is a visible change
    # on a legal document and wants its own review rather than riding along with
    # 17 mechanical markdown shifts.
    "37_Legal.py",
}
# Removed from the backlog by the honesty test below, which found them already
# valid rather than taking my word for it:
#   3_Ticker_Deep_Dive.py  fixed (heading promotion)
#   1_Signal_Dashboard.py  fixed (section-header div -> h2)
#   45_Options_Flow.py     already {h2, h3, h4}
#   9_AI_Assistant.py      already {h2}


def _levels(path: Path) -> set[int]:
    src = path.read_text(encoding="utf-8")
    return {len(m.group(1)) for m in _HEADING.finditer(src)} | _html_levels(src)


def _describe(levels: set[int]) -> str:
    return "{" + ", ".join(f"h{l}" for l in sorted(levels)) + "}"


def test_deep_dive_outline_is_contiguous_from_h2():
    """The page this phase fixed."""
    lv = _levels(_PAGES / "3_Ticker_Deep_Dive.py")
    assert lv, "no markdown headings found — re-point this test"
    assert min(lv) == 2, (
        f"Ticker Deep Dive starts at h{min(lv)}, so there is no h2 under the "
        f"page h1. Levels: {_describe(lv)}"
    )
    expected = set(range(2, max(lv) + 1))
    assert lv == expected, (
        f"Ticker Deep Dive skips a level: has {_describe(lv)}, "
        f"expected {_describe(expected)}"
    )


def test_no_page_regresses_into_the_unfixed_list():
    """Pages already corrected must stay corrected.

    A page is 'corrected' by not being in _NOT_YET_FIXED. If one of those grows
    a skipped level, this fails rather than quietly rejoining the backlog.
    """
    bad = []
    for path in sorted(_PAGES.glob("*.py")):
        if path.name in _NOT_YET_FIXED:
            continue
        lv = _levels(path)
        if not lv:
            continue
        if min(lv) != 2 or lv != set(range(2, max(lv) + 1)):
            bad.append(f"{path.name}: {_describe(lv)}")
    assert not bad, "these pages had a valid outline and no longer do:\n" + "\n".join(bad)


def test_the_backlog_list_is_honest():
    """Nothing may sit in the backlog that is already fine.

    Keeps the list from becoming a permanent excuse: if a page's outline is
    already contiguous from h2, it must be removed from _NOT_YET_FIXED so the
    remaining count reflects real work.
    """
    stale = []
    for name in sorted(_NOT_YET_FIXED):
        path = _PAGES / name
        if not path.is_file():
            stale.append(f"{name}: file no longer exists")
            continue
        lv = _levels(path)
        if not lv:
            continue  # no markdown headings — nothing to fix, but harmless
        if min(lv) == 2 and lv == set(range(2, max(lv) + 1)):
            stale.append(f"{name}: outline is already valid {_describe(lv)}")
    assert not stale, (
        "remove these from _NOT_YET_FIXED — they no longer need fixing:\n"
        + "\n".join(stale)
    )
