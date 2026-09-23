"""The app has to look like the site a visitor just came from.

The marketing page is navy, blue and gold with cards, colour-coded factors and
a hero band. The app was the older dark-purple Streamlit skin under a white
bar, so "Try a sample portfolio" landed people on something that read as a
different, rougher product. utils/app_theme.py closes that gap.

Two things about this stylesheet break SILENTLY, and both have happened:

  1. specificity — utils/header.py writes its rules as
     `html[data-ua-theme="light"] button[...]`, so a plain class selector loses
     and the sheet does nothing at all;
  2. source order — header.py injects ~124 KB of the old skin from the same
     function, and equal-specificity ties go to whichever came last. Injected
     too early, the theme lost in local dev and won in production, where the
     old skin is a cached <link> instead.

Neither shows up as an error, only as a page that looks wrong, so they are
pinned here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.app_theme import PRODUCT_CSS, FACTOR_HUES, is_product_page  # noqa: E402

HEADER = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")
PRODUCT_PAGES = ("60_Exposure_Report.py", "61_What_Changed.py", "62_Alerts.py",
                 "63_Methodology.py", "64_Research.py", "65_Pricing.py")


def test_only_the_redesigned_pages_carry_the_theme():
    for name in PRODUCT_PAGES:
        assert is_product_page(f"/app/pages/{name}"), name
    for legacy in ("1_Signal_Dashboard.py", "40_Stock_Recommender.py", "home_page.py"):
        assert not is_product_page(f"/app/pages/{legacy}"), legacy
    assert not is_product_page(None) and not is_product_page("")


def test_every_override_is_written_to_beat_the_old_skin():
    """A bare `.stApp button[...]` rule loses to header.py's themed selector.

    Checked in a browser the first time this was written: the stylesheet was in
    the DOM and changed nothing.
    """
    sheet = re.sub(r"/\*.*?\*/", "", PRODUCT_CSS, flags=re.S)
    rules = [r for r in re.findall(r"([^{}]+)\{[^{}]*\}", sheet)
             if "button[data-testid" in r or ".ua-topnav" in r]
    assert rules, "the button and nav overrides are gone"
    for selector in rules:
        for part in selector.split(","):
            part = part.strip()
            if not part or part.startswith(("@", "/*")):
                continue
            assert part.startswith(("html[", "html:not([")), (
                f"{part!r} has lower specificity than utils/header.py's "
                f"html[data-ua-theme] rules and will silently do nothing"
            )


def test_both_themes_are_covered_by_every_themed_override():
    """`html[data-ua-theme="light"]` alone leaves dark on the old skin."""
    light = PRODUCT_CSS.count('html[data-ua-theme="light"] .stApp button')
    dark = PRODUCT_CSS.count('html:not([data-ua-theme="light"]) .stApp button')
    assert light == dark and light >= 4, (light, dark)


def test_the_theme_is_injected_after_the_old_skin_not_before():
    body = HEADER.split("def render_header(", 1)[1].split("\ndef ", 1)[0]
    assert "st.markdown(_CSS, unsafe_allow_html=True)" in body, "re-point this test"
    assert body.index("st.markdown(_CSS") < body.index("st.markdown(_product_css"), (
        "the product theme must be injected LAST. CSS ties break on source "
        "order, so injecting it before the 124 KB legacy sheet means the nav "
        "and brand rules lose -- and lose only in local dev, because in "
        "production the legacy sheet is a <link> in index.html instead."
    )
    assert "is_product_page" in body


def test_font_sizes_come_from_tokens_not_fresh_literals():
    """tests/test_design_tokens.py ratchets raw font-size literals downward. A
    new stylesheet is exactly where a fresh crop of .82rem/.94rem values would
    come from, so this one declares its scale once and references it."""
    literals = re.findall(r"font-size:\s*([0-9.]+)(rem|px|em)", PRODUCT_CSS)
    assert not literals, f"use a --p-t-* token instead of {literals}"
    assert PRODUCT_CSS.count("font-size:var(--p-t-") >= 6


def test_the_hero_carries_the_landing_pages_navy_and_gold():
    assert "--p-navy:#0d223b" in PRODUCT_CSS and "--p-bright:#ffc24b" in PRODUCT_CSS
    assert ".ua-phero" in PRODUCT_CSS
    # The h1 must outrank .ua-page-title's own !important type, or the hero
    # title renders at the interior-page size on a navy band.
    rule = PRODUCT_CSS[PRODUCT_CSS.index(".stApp .ua-phero h1"):]
    rule = rule[: rule.index("}")]
    for prop in ("font-size", "color", "font-weight"):
        assert f"{prop}:" in rule and "!important" in rule, prop


def test_one_identity_colour_per_force_shared_with_the_report():
    from utils import report_ui as ui

    assert FACTOR_HUES == ui.FACTOR_COLORS, (
        "the app theme and the report drew the factors in different colours"
    )


def test_the_product_pages_all_use_the_hero_header():
    """One h1 per page, and it comes from the new emitter on every one of them."""
    for name in PRODUCT_PAGES:
        src = (_ROOT / "pages" / name).read_text(encoding="utf-8")
        assert "product_page_header(" in src, name
        assert "render_page_header" not in src, (
            f"{name} still calls the old plain-title header; two emitters would "
            f"put two <h1> elements on the page"
        )
        assert "hero_title" not in src, name


def test_the_hero_escapes_everything_it_is_given():
    src = (_ROOT / "utils" / "app_theme.py").read_text(encoding="utf-8")
    body = src[src.index("def product_page_header"):]
    for field in ("eyebrow", "title", "subtitle"):
        assert f"escape({field})" in body, field
    assert "escape(str(f))" in body, "facts are interpolated unescaped"
