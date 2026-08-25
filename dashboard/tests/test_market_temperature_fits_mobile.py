"""The four market-temperature counts must fit a 375px viewport.

Measured in the browser at 375x812 before this fix: the stat row is a
`display:flex; flex-wrap:nowrap` group of four figures separated by three
hairline dividers with 24px gaps. That comes to ~350px of content inside a
~335px container, so the fourth column -- "13 SCORED", the count of signals
that actually scored -- rendered with its right edge at 385px on a 375px
viewport and was simply not visible.

The fix tightens the gap and drops the dividers below 640px rather than letting
the row reflow into a ragged 2x2, which reads worse for four related counts.
Desktop is untouched: the rule is inside a max-width media query.

This pins the two halves together. The class on the markup and the rule in the
stylesheet are in different files, and either one alone silently does nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_PAGE = (_ROOT / "pages" / "1_Signal_Dashboard.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def built_css() -> str:
    from scripts.inject_boot_splash import build_global_css
    return build_global_css()


def test_the_stat_row_and_dividers_carry_their_hooks():
    assert 'class="ua-temp-stats"' in _PAGE, (
        "the market-temperature stat row lost its responsive class; the media "
        "query in utils/header.py then targets nothing and the fourth column "
        "goes back off-screen at 375px"
    )
    assert _PAGE.count('class="ua-temp-div"') == 3, (
        f"expected 3 hairline dividers marked with ua-temp-div, found "
        f"{_PAGE.count('class=\"ua-temp-div\"')}"
    )


def test_the_narrow_viewport_rule_exists_and_is_scoped(built_css):
    assert ".ua-temp-stats" in built_css, "no responsive rule for the stat row"
    assert ".ua-temp-stats .ua-temp-div" in built_css, (
        "the dividers are never hidden, so the row keeps its full width"
    )

    # The rule must live inside a max-width query, or it would strip the
    # dividers and tighten the gap on desktop too.
    block = built_css[: built_css.index(".ua-temp-stats")]
    last_media = block.rfind("@media")
    assert last_media != -1, "the stat-row rule is not inside any media query"
    prelude = built_css[last_media : last_media + 80]
    assert "max-width" in prelude, (
        f"the stat-row rule is not scoped to narrow viewports: {prelude!r}"
    )


def test_the_narrow_gap_is_smaller_than_the_desktop_gap(built_css):
    """A rule that does not actually shrink anything is decoration."""
    desktop = re.search(r'class="ua-temp-stats" style="[^"]*gap:(\d+)px', _PAGE)
    assert desktop, "could not read the desktop gap off the stat row markup"
    narrow = re.search(r"\.ua-temp-stats\s*\{[^}]*gap:\s*(\d+)px", built_css)
    assert narrow, "could not read the narrow-viewport gap out of the stylesheet"
    assert int(narrow.group(1)) < int(desktop.group(1)), (
        f"narrow gap {narrow.group(1)}px is not smaller than the desktop "
        f"{desktop.group(1)}px, so the row still overflows"
    )
