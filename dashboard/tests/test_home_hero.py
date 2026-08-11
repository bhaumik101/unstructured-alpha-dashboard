"""The masthead leads with the page, never with a second copy of the brand.

The landing page swaps the left masthead block for a value-prop headline via
render_header(hero_title=...). Originally every OTHER page fell back to the
brand wordmark, and this file asserted that fallback.

That fallback is gone. The argument that removed the wordmark from the landing
page -- the top nav already carries it, so repeating it is duplication -- held
just as well everywhere else, and the effect was worse there: at 1.8rem the
company name was the largest element on the Signal Dashboard, with the page's
own title 320px below it, behind ~640px of furniture identical on all 32 pages.

So the fallback is now empty and the page's own title leads. These tests guard
the new contract structurally (rendering needs a Streamlit runtime, so they
assert on the source and the call sites).
"""

from __future__ import annotations

from pathlib import Path

DASH = Path(__file__).resolve().parent.parent


def test_render_header_supports_hero_title_override():
    src = (DASH / "utils" / "header.py").read_text(encoding="utf-8")
    assert "def render_header(page_subtitle: str = \"\", hero_title: str = \"\", hero_sub: str = \"\")" in src
    # a hero title path exists
    assert 'class="ua-hero-title"' in src
    # and the masthead no longer repeats the brand on pages without one
    assert 'class="ua-wordmark">UNSTRUCTURED' not in src, (
        "the masthead is rendering the brand wordmark again; the top nav "
        "already carries it and repeating it pushed every page's own title "
        "below a screenful of identical chrome"
    )


def test_home_leads_with_value_prop_not_duplicate_wordmark():
    src = (DASH / "pages" / "home_page.py").read_text(encoding="utf-8")
    assert "hero_title=" in src
    assert "before you trade" in src.lower()


def test_only_the_landing_page_uses_a_hero_masthead():
    """A hero headline is a landing-page device.

    Other pages must not adopt it: their masthead is now empty and their own
    page title leads, which is the point. A page that starts adding hero copy is
    reintroducing the chrome this removed.
    """
    for page in ("11_Model_Validation.py", "48_Data_Trust.py", "3_Ticker_Deep_Dive.py"):
        src = (DASH / "pages" / page).read_text(encoding="utf-8")
        assert "hero_title=" not in src, f"{page} unexpectedly overrides the masthead"
