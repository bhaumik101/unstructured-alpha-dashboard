"""The landing masthead leads with the value proposition, not a second copy of
the brand wordmark (which the top nav already carries).

render_header(hero_title=...) swaps the left masthead block for a value-prop
headline; without it, every other page keeps the wordmark. These guard that
contract structurally (rendering needs a Streamlit runtime, so we assert on the
source + the call site).
"""

from __future__ import annotations

from pathlib import Path

DASH = Path(__file__).resolve().parent.parent


def test_render_header_supports_hero_title_override():
    src = (DASH / "utils" / "header.py").read_text(encoding="utf-8")
    assert "def render_header(page_subtitle: str = \"\", hero_title: str = \"\", hero_sub: str = \"\")" in src
    # the wordmark is still the default (other pages unchanged)
    assert 'class="ua-wordmark"' in src
    # and a hero title path exists
    assert 'class="ua-hero-title"' in src


def test_home_leads_with_value_prop_not_duplicate_wordmark():
    src = (DASH / "pages" / "home_page.py").read_text(encoding="utf-8")
    assert "hero_title=" in src
    assert "before you trade" in src.lower()


def test_other_pages_keep_the_wordmark_default():
    """A sampling of non-home pages must NOT pass hero_title, so they still show
    the brand wordmark masthead."""
    for page in ("11_Model_Validation.py", "48_Data_Trust.py", "3_Ticker_Deep_Dive.py"):
        src = (DASH / "pages" / page).read_text(encoding="utf-8")
        assert "hero_title=" not in src, f"{page} unexpectedly overrides the masthead"
