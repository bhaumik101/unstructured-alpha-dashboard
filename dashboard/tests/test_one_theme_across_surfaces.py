"""The landing page and the app read as one product, from the first paint.

Found on 2026-09-29 by measuring both surfaces rather than eyeballing them: the
app's full-screen container was still painted by the retired skin, the Sign In
popover matched no theme rule, buttons were rounder on one surface than the
other, and the landing page named a font it never loaded and wore the old
violet hexagon in its nav.
"""

from __future__ import annotations

import re
from pathlib import Path

from utils.app_theme import PRODUCT_CSS, _RADII

_ROOT = Path(__file__).resolve().parent.parent
_WEB = _ROOT / "unstructured-alpha-web" / "app"
_LANDING_CSS = (_WEB / "landing.css").read_text(encoding="utf-8")
_PAGE = (_WEB / "page.tsx").read_text(encoding="utf-8")
_LAYOUT = (_WEB / "layout.tsx").read_text(encoding="utf-8")


def _rule(selector_fragment: str) -> str:
    """Declarations of the first PRODUCT_CSS rule whose selector contains the fragment."""
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", PRODUCT_CSS):
        if selector_fragment in sel:
            return body
    raise AssertionError(f"no rule for {selector_fragment!r}")


def test_the_full_screen_container_wears_the_token_ground():
    body = _rule('[data-testid="stAppViewContainer"]')
    assert "background:var(--p-bg)!important" in body


def test_buttons_share_the_landing_pages_radius():
    landing = re.search(r"\.lp-btn \{[^}]*border-radius: (\d+px)", _LANDING_CSS).group(1)
    assert _RADII["r-btn"] == landing
    for testid in ("stBaseButton-primary", "stBaseButton-secondary",
                   "stBaseLinkButton-secondary", "stBaseLinkButton-primary"):
        assert "border-radius:var(--p-r-btn)" in _rule(f'[data-testid="{testid}"]'), testid


def test_the_sign_in_popover_is_themed():
    body = _rule('button[data-testid="stPopoverButton"]')
    assert "background:var(--p-surface)" in body and "color:var(--p-ink)" in body


def test_the_landing_nav_wears_the_apps_wordmark_not_the_old_logo():
    nav = _PAGE[_PAGE.index('className="lp-nav"'):_PAGE.index('className="lp-menu-btn"')]
    assert "UNSTRUCTURED <span>ALPHA</span>" in nav
    assert "logo.svg" not in nav


def test_the_landing_theme_toggle_names_the_theme_it_switches_to():
    assert "DARK</span>" in _PAGE and "LIGHT</span>" in _PAGE
    assert ':root[data-theme="dark"] .lp-theme-to-dark { display: none' in _LANDING_CSS


def test_the_landing_page_loads_the_font_it_names():
    from scripts.inject_boot_splash import INTER_HREF

    assert INTER_HREF in _LAYOUT, "landing and app must request the same Inter"


def test_captions_are_not_faded_below_contrast():
    """Streamlit's own opacity:.6 on captions took --p-ink3 to 2.45:1."""
    bodies = [body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", PRODUCT_CSS)
              if sel.strip().endswith('[data-testid="stCaptionContainer"]')]
    assert any("opacity:1!important" in b for b in bodies)
