"""The sitewide visual pass: each rule here fixes something measured in the
browser on 2026-09-29, not a taste change.

- Sign In hung off the nav's bottom edge as a stray white box on every page.
- An UNselected radio drew a solid near-black dot (the retired skin's #0b0d12)
  and looked more selected than the selected one, which was the retired violet.
- Checked checkboxes and the selected tab's underline were the retired violet.
- Pricing's three cards were three heights, so their buttons sat at three
  heights too; signed out, Investor Pro had a notice where a button should be.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _rules(css: str):
    return re.findall(r"([^{}]+)\{([^{}]*)\}", css)


def _bodies(fragment: str):
    from utils.app_theme import PRODUCT_CSS

    return [body for sel, body in _rules(PRODUCT_CSS) if fragment in sel]


def test_sign_in_sits_in_the_band_above_the_nav():
    header = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")
    css = header[header.index(".st-key-ua_account_row{position:absolute"):]
    css = css[:css.index("</style>")]
    assert "top:-46px" in css and "right:0" in css, "flush with the nav's right edge, above it"
    assert "[data-testid='stColumn']:first-child{display:none" in css, "the spacer column goes"
    assert "margin-top:-30px" not in header, "the old pull-up under the nav is gone"


def test_an_unselected_radio_is_a_hollow_ring_and_a_selected_one_the_accent():
    off = _bodies('[data-testid="stRadio"] label > div:first-of-type > div:first-of-type')
    assert any("background:var(--p-surface)" in b and "border:1.5px solid var(--p-ink3)" in b for b in off)
    dot_off = _bodies('[data-testid="stRadio"] label > div:first-of-type > div:first-of-type > div')
    assert any("background:transparent" in b for b in dot_off), "no dot when not selected"
    on = _bodies('[data-testid="stRadio"] label:has(input:checked) > div:first-of-type > div:first-of-type')
    assert any("background:var(--p-accent)" in b for b in on)


def test_checkboxes_and_tabs_wear_the_accent_not_the_retired_violet():
    assert any("background:var(--p-accent)" in b
               for b in _bodies('[data-testid="stCheckbox"] label:has(input:checked) > div:first-of-type'))
    assert any("background:var(--p-accent)" in b
               for b in _bodies('[role="tab"][aria-selected="true"] > div:last-child'))
    for sel, _ in _rules(__import__("utils.app_theme", fromlist=["PRODUCT_CSS"]).PRODUCT_CSS):
        if 'stCheckbox"] label:has(input:checked)' in sel:
            assert "#stFloatingOverlayPortal" in sel, "the sign-in form's checkbox is in the portal"
            break


def test_pricing_stretches_every_plan_to_one_height():
    src = (_ROOT / "pages" / "65_Pricing.py").read_text(encoding="utf-8")
    assert 'st.container(key="pricing_tiers")' in src
    assert "align-items:stretch" in src and ":has(.uar-tier){flex:1 1 auto" in src
    assert "margin-top:16px!important;height:calc(100% - 16px)" in src, "badge offset on every card"


def test_signed_out_investor_pro_still_ends_in_a_button(monkeypatch):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from tests.conftest import DASHBOARD_ROOT

    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    at = AppTest.from_file(str(DASHBOARD_ROOT / "pages/65_Pricing.py"), default_timeout=120)
    at.run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    assert not [i for i in at.info if "Sign in" in i.value], "no notice before anything is clicked"
    at.button(key="price_pro_signin").click().run()
    assert any("Sign in or create a free account first" in i.value for i in at.info)
