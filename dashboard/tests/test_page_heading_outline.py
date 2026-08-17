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

# Markdown heading inside a Python string literal: "## Title" / f"### {x}"
_HEADING = re.compile(r'["\'](#{1,6})\s+[^"\'\n]{2,80}["\']')

# Pages whose outline is not yet corrected. Deep Dive was fixed first because it
# is the deepest page in the product at ~15 screens. Shrink this list; never
# grow it.
_NOT_YET_FIXED = {
    "1_Signal_Dashboard.py", "2_Today_Digest.py",
    "4_Power_Supercycle.py", "5_Market_Overview.py", "6_Stock_Screener.py",
    "10_Watchlist.py", "27_Factor_Exposure.py",
    "29_Upgrade.py", "30_Track_Record_Live.py", "32_Profile.py",
    "35_Signal_Strategy.py", "38_Admin.py", "40_Stock_Recommender.py",
    "41_Alternative_Data.py", "42_Sector_View.py", "43_Events_Forecasts.py",
    "44_Portfolio_Suite.py", "46_Thesis_Journal.py",
    "48_Data_Trust.py", "49_Decision_Queue.py", "50_Investor_Checkup.py",
    "51_Signal_Research.py", "home_page.py",
}
# Removed from the backlog by the honesty test below, which found them already
# valid rather than taking my word for it:
#   3_Ticker_Deep_Dive.py  fixed in this change
#   45_Options_Flow.py     already {h2, h3, h4}
#   9_AI_Assistant.py      already {h2}


def _levels(path: Path) -> set[int]:
    return {len(m.group(1)) for m in _HEADING.finditer(path.read_text(encoding="utf-8"))}


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
