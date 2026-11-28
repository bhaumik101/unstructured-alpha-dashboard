"""The walk-forward charts, the stock-library landscape, and the theme on every page."""

from __future__ import annotations

import re
from pathlib import Path

from utils import app_theme, explain as xp, exposure as ex
from utils import stock_ui as sui
from utils import walkforward_ui as wf

ROOT = Path(__file__).resolve().parent.parent


# ── walk-forward charts ─────────────────────────────────────────────────────

def test_the_force_chart_agrees_with_the_engine_and_the_extra_records():
    names = {f.label: f.key for f in ex.FACTORS + ex.EXTRA_FACTORS}
    aliases = {"Small vs large": "size", "Value vs growth": "value", "Volatility": "volatility",
               "Emerging markets": "emerging", "Mortgage rates": "mortgage"}
    for name, pct, n, kind in wf.FORCES:
        key = aliases.get(name) or names.get(name)
        assert key, name
        if kind == "extra":
            assert xp.EXTRA_TRACK[key] == (pct, n), name           # one set of numbers, not two
    must = {aliases.get(n) or names.get(n) for n in wf.EXTRA_TESTED}
    assert must == set(ex.OOS_REQUIRED)                             # the flag matches the rule


def test_the_research_record_holds_every_charted_number():
    doc = (ROOT / "docs" / "RESEARCH_2026-11.md").read_text(encoding="utf-8")
    for label, f, s in wf.TIERS:
        for v in (f, s):
            if v is not None:
                assert f"{v}%" in doc, (label, v)
    for name, pct, _, _ in wf.FORCES:
        assert f"{pct}%" in doc, name


def test_each_bar_has_its_number_a_word_and_the_coin_flip_line():
    html = wf.forces_html()
    assert html.count('class="wf-frow"') == len(wf.FORCES)
    assert html.count('class="wf-coin"') == len(wf.FORCES)
    assert "90%</b><span class=\"wf-word wf-w-ok\">holds up" in html
    assert "50%</b><span class=\"wf-word wf-w-bad\">coin flip" in html
    assert html.count("must pass on new weeks") == len(wf.EXTRA_TESTED)
    assert wf._tone(70)[0] == "ok" and wf._tone(69)[0] == "mid" and wf._tone(54)[0] == "bad"
    tiers = wf.tiers_html()
    assert "not measured" in tiers and tiers.count('class="wf-coin"') == 7


def test_the_charts_never_forecast_or_advise():
    text = re.sub(r"<[^>]+>", " ", wf.section_html() + sui.landscape_html(_stocks()))
    text = re.sub(r"(?:is|are) not a forecast", "", text)
    assert not re.search(r"\b(will|predict\w*|forecast\w*|should|buy|sell|recommend\w*)\b", text, re.I)


def test_the_evidence_page_always_shows_the_studies():
    page = (ROOT / "pages" / "71_Evidence.py").read_text(encoding="utf-8")
    assert "wf.section_html()" in page and page.index("wf.section_html()") < page.index("tr.latest()")


# ── the stock-library landscape ─────────────────────────────────────────────

def _stocks(n=30):
    out = []
    for i in range(n):
        out.append({"ticker": f"S{i}", "exposures": {
            "rates": {"impact": -0.5, "evidence": "clear" if i < 12 else "tentative"},
            "value": {"impact": 0.4 if i % 2 else -0.4, "evidence": "clear"},
            "oil": {"impact": 0.9, "evidence": "indistinct"}}})
    return out


def test_the_landscape_counts_clear_readings_by_direction():
    html = sui.landscape_html(_stocks())
    assert "What 30 stocks moved with" in html
    assert re.search(r'title="Interest rates: 0 stocks rose with it, 12 fell', html)
    assert re.search(r'title="Value vs growth: 15 stocks rose with it, 15 fell', html)
    assert "Oil and energy" not in html                              # nothing Clear, no row
    assert "<b>100%</b> have at least one Clear link" in html
    assert sui.landscape_html(_stocks(10)) == ""                     # too few to draw


def test_the_stock_landing_draws_it():
    page = (ROOT / "pages" / "69_Stock.py").read_text(encoding="utf-8")
    assert "sui.landscape_html(lib.latest(limit=5000))" in page


# ── one theme everywhere ────────────────────────────────────────────────────

def test_account_legal_and_evidence_pages_carry_the_product_theme():
    for name in ("11_Model_Validation.py", "30_Track_Record_Live.py", "48_Data_Trust.py", "32_Profile.py",
                 "37_Legal.py", "47_Account_Setup.py", "29_Upgrade.py"):
        assert app_theme.is_product_page(str(ROOT / "pages" / name)), name
    assert not app_theme.is_product_page(str(ROOT / "pages" / "1_Signal_Dashboard.py"))


def test_the_section_menu_and_form_buttons_are_restyled_for_it():
    css = app_theme.PRODUCT_CSS
    assert css.count("<style>") == 1
    assert "body:has(.st-key-ua_page_section_rail) .ua-topnav{left:0!important" in css
    assert ".stFormSubmitButton > button{" in css and "var(--p-accent)" in css


def test_old_page_titles_become_the_glass_band_on_themed_pages():
    import inspect

    from utils import header
    src = inspect.getsource(header.render_page_header)
    assert "is_product_page(" in src and "product_page_header(title, subtitle)" in src
    setup = (ROOT / "pages" / "47_Account_Setup.py").read_text(encoding="utf-8")
    assert "st.markdown(PRODUCT_CSS, unsafe_allow_html=True)" in setup
