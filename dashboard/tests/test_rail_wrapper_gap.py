"""The rails' wrappers must cancel their row-gap, not be removed.

The page's vertical block is display:flex with row-gap:16px, so every child
collects 16px whether or not it paints. #131 pulled the SPA proxy rail out of
flow and #132 hid the containers that cannot paint -- but the gap is not
charged to the rail, it is charged to the stLayoutWrapper Streamlit puts
AROUND it, which is an ordinary in-flow flex child. Both rails were still
paying 16px each on every page.

display:none is not available here: unlike the empty markdown containers #132
hides, these two wrap elements that must stay in the DOM and keep their
stacking context -- 33 clickable SPA proxy links and a sticky section rail.
Cancelling the gap leaves position, stacking and clickability untouched.

Measured live before the rule was written: 32px off every page, h1 rises 32px,
top nav does not move, section rail keeps its 152px height and stays
unclipped, all 33 proxy links still present.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_HEADER_SRC = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")

PROXY_RAIL = "st-key-ua_spa_proxy_rail"
SECTION_RAIL = "st-key-ua_page_section_rail"


def _rule_for(key: str) -> str:
    """The CSS declaration block whose selector mentions `key` and a wrapper."""
    src = re.sub(r"/\*.*?\*/", "", _HEADER_SRC, flags=re.S)
    for match in re.finditer(r"([^{}]*stLayoutWrapper[^{}]*)\{([^}]*)\}", src):
        if key in match.group(1):
            return match.group(0)
    return ""


def test_both_rail_wrappers_cancel_their_gap():
    for key in (PROXY_RAIL, SECTION_RAIL):
        rule = _rule_for(key)
        assert rule, f"no stLayoutWrapper rule covers {key}"
        assert re.search(r"margin-bottom:\s*-16px", rule), (
            f"the {key} wrapper must cancel the 16px row-gap it collects; "
            f"found: {rule.strip()[:160]!r}"
        )


def test_the_rails_are_never_removed_from_flow_by_this_rule():
    """display:none / visibility:hidden here would break both rails.

    The proxy rail's 33 links must stay clickable -- that is the entire SPA
    navigation mechanism, and #131's comment records that an element hidden
    either way cannot be reliably clicked. The section rail is sticky and
    painted.
    """
    for key in (PROXY_RAIL, SECTION_RAIL):
        rule = _rule_for(key)
        body = rule[rule.find("{") :]
        for banned in ("display: none", "display:none",
                       "visibility: hidden", "visibility:hidden"):
            assert banned not in body, (
                f"{key}: `{banned}` breaks the rail. #131 measured that a "
                f"hidden proxy link cannot be reliably clicked."
            )


def test_the_top_nav_container_is_left_alone():
    """It is 0px too, and it must stay.

    Its st.html holds a <style> AND the <nav> itself; the nav is position:fixed,
    which is why the container measures 0. #132's rule already excludes it, and
    the wrapper rule must not reach it either -- a selector keyed on
    "st.html containing only style" looks right and is wrong, because the nav
    lives in that same element.
    """
    src = re.sub(r"/\*.*?\*/", "", _HEADER_SRC, flags=re.S)
    wrapper_rules = [
        m.group(0)
        for m in re.finditer(r"([^{}]*stLayoutWrapper[^{}]*)\{([^}]*)\}", src)
        if "margin-bottom: -16px" in m.group(2) or "margin-bottom:-16px" in m.group(2)
    ]
    assert wrapper_rules, "expected the gap-cancelling wrapper rule"
    for rule in wrapper_rules:
        selector = rule[: rule.find("{")]
        assert "stHtml" not in selector, (
            "this rule must not reach st.html containers -- the top nav is one "
            "of them, and it is fixed, so it reads as 0px and looks eligible"
        )
        keys = re.findall(r"st-key-[\w-]+", selector)
        assert set(keys) <= {PROXY_RAIL, SECTION_RAIL}, (
            f"only the two rails may be targeted; found {sorted(set(keys))}"
        )
