"""Pages the redesign superseded must say so.

~25 pages left the navigation on 2026-09-20 but stayed routable so old links
resolve. They still sell the retired product: Confluence Scores, "the macro
backdrop before you trade", signal lead times. Someone arriving from a search
result or an old bookmark would read the pitch we withdrew, with nothing
pointing at the product that replaced it — and outreach is about to put links
in front of exactly those people.

These tests pin that the notice appears on those pages, never on the current
ones, and that the list cannot drift away from the navigation's own list of
deliberately unlinked routes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.legacy_pages import LEGACY_PAGE_FILES, NOTICE_HTML, is_legacy_page  # noqa: E402

APP = (_ROOT / "app.py").read_text(encoding="utf-8")
HEADER = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")

CURRENT_PAGES = (
    "60_Exposure_Report.py", "61_What_Changed.py", "62_Alerts.py",
    "63_Methodology.py", "64_Research.py", "65_Pricing.py",
)


def test_every_named_page_actually_exists():
    missing = sorted(f for f in LEGACY_PAGE_FILES if not (_ROOT / "pages" / f).is_file())
    assert not missing, f"the list names pages that are gone: {missing}"


def test_the_pages_a_visitor_uses_carry_no_notice():
    for name in CURRENT_PAGES:
        assert not is_legacy_page(f"/app/pages/{name}"), name
    for evidence in ("11_Model_Validation.py", "30_Track_Record_Live.py", "48_Data_Trust.py"):
        assert not is_legacy_page(f"/app/pages/{evidence}"), (
            f"{evidence} is linked from the Research menu and describes testing, "
            f"not a retired pitch"
        )


def test_a_superseded_page_is_recognised_by_its_path():
    assert is_legacy_page("/anywhere/pages/40_Stock_Recommender.py")
    assert is_legacy_page("pages/1_Signal_Dashboard.py")
    assert not is_legacy_page(None) and not is_legacy_page("")


def test_the_notice_says_what_changed_and_where_to_go():
    assert "no longer maintained" in NOTICE_HTML
    assert 'href="/"' in NOTICE_HTML and 'href="/methodology"' in NOTICE_HTML
    assert "exposed to" in NOTICE_HTML


def test_superseded_pages_ask_not_to_be_indexed():
    """A page we no longer stand behind should stop collecting search traffic.

    The meta tag is set by the injected runtime script, NOT from st.html:
    Streamlit sanitises <script> out of injected HTML, so a tag added that way
    never runs. Checked in a browser before moving it."""
    from scripts.inject_boot_splash import _build_runtime, legacy_slugs

    assert "<script" not in NOTICE_HTML, (
        "a script in st.html is stripped; this belongs in the runtime injector"
    )
    runtime = _build_runtime()
    assert "noindex,follow" in runtime
    assert "__UA_LEGACY_SLUGS__" not in runtime, "the slug list was never filled in"

    slugs = legacy_slugs()
    assert "stock-recommender" in slugs and "signal-dashboard" in slugs
    for current in ("methodology", "research", "pricing", "what-changed", "alerts"):
        assert current not in slugs, f"{current} is the live product, not a retired page"
    for slug in slugs:
        assert f'"{slug}"' in runtime


def test_the_slug_list_is_generated_not_hand_copied():
    """Two hand-written copies of the same decision drift, and the failure mode
    is a retired page quietly collecting search traffic."""
    from scripts.inject_boot_splash import legacy_slugs

    src = (_ROOT / "scripts" / "inject_boot_splash.py").read_text(encoding="utf-8")
    body = src[src.index("def legacy_slugs"):src.index("def _build_splash")]
    assert "LEGACY_PAGE_FILES" in body and "app.py" in body
    assert len(legacy_slugs()) >= 20


def test_the_header_renders_it_without_each_page_opting_in():
    body = HEADER.split("def render_header(", 1)[1].split("\ndef ", 1)[0]
    assert "is_legacy_page" in body
    assert "st.html(NOTICE_HTML)" in body
    assert body.index("_render_topnav()") < body.index("is_legacy_page")


def test_the_list_matches_the_navigations_own_hidden_routes():
    """Two lists describe the same decision; they must not drift apart."""
    from tests.test_nav_reaches_every_page import _HIDDEN_IN_REDESIGN

    slug_to_file = {
        m.group(3): m.group(1)
        for m in re.finditer(r'st\.Page\("pages/([^"]+)"[^)]*?title="([^"]+)"[^)]*?url_path="([^"]+)"', APP)
    }
    # home_page.py is registered with url_path="home".
    hidden_files = {slug_to_file[s] for s in _HIDDEN_IN_REDESIGN if s in slug_to_file}
    evidence = {"11_Model_Validation.py", "30_Track_Record_Live.py", "48_Data_Trust.py"}

    missing = sorted(hidden_files - LEGACY_PAGE_FILES - evidence)
    assert not missing, (
        "these routes were hidden by the redesign but carry no notice, so a "
        f"visitor arriving from an old link sees the retired pitch: {missing}"
    )
