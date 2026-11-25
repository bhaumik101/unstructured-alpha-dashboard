"""Glossary tooltips and the dollar view on the report (utils/explain.py)."""

from __future__ import annotations

import re
from pathlib import Path

from utils import explain as xp
from utils import report_ui as ui

ROOT = Path(__file__).resolve().parent.parent

# Investor.gov pages confirmed to exist on 2026-11-25. A new link must be
# checked and added here; a guessed URL would send a beginner to a 404.
VERIFIED = {
    "investing-basics/glossary/exchange-traded-fund-etf",
    "investing-basics/glossary/mutual-funds",
    "investing-basics/glossary/index-fund",
    "investing-basics/glossary/bonds",
    "investing-basics/glossary/bond-funds-and-income-funds",
    "investing-basics/glossary/high-yield-bond-or-junk-bond",
    "investing-basics/what-risk",
    "getting-started/asset-allocation",
    "general-resources/news-alerts/alerts-bulletins/investor-bulletins-86",
}


def test_every_investor_gov_link_is_a_confirmed_page():
    for key, t in xp.GLOSSARY.items():
        if t.url:
            assert t.url.startswith(xp.IG + "/"), key
            assert t.url[len(xp.IG) + 1:] in VERIFIED, f"{key}: unverified link {t.url}"


def test_a_term_opens_its_definition_and_links_only_where_a_page_exists():
    html = xp.term("credit")
    assert 'class="ugl" tabindex="0"' in html and 'role="tooltip"' in html
    assert "extra interest companies pay" in html and "More on Investor.gov" in html
    assert 'rel="noopener"' in html
    own = xp.term("range90")
    assert "90% range" in own and "Investor.gov" not in own
    assert xp.term("nope", "a<b") == "a&lt;b"


_BANNED = re.compile(r"\b(will|predict\w*|forecast\w*|should|buy|sell|recommend\w*|guarantee\w*)\b", re.I)


def test_definitions_explain_words_and_never_advise():
    for key, t in xp.GLOSSARY.items():
        assert not _BANNED.search(t.text), f"{key}: {t.text}"
        assert len(t.text) < 260, key                     # a tooltip, not an essay


def _report():
    r = {"rates": -0.3, "dollar": -0.5555}
    readings = {k: {"label": {"rates": "Interest rates", "dollar": "U.S. dollar"}[k], "impact": v,
                    "low": v - 0.2, "high": v + 0.2, "evidence": "clear", "shock_phrase": "it moved",
                    "t": 3.0} for k, v in r.items()}
    return {"portfolio": {"readings": readings, "n_obs": 156, "start": "2023-12-01", "end": "2026-11-20"},
            "contributions": {}, "holdings": []}


def test_the_table_carries_dollar_figures_and_defined_force_names(monkeypatch):
    monkeypatch.setattr(ui, "_main_holding", lambda report, key: ("—", ""))
    monkeypatch.setattr(ui, "_top_name", lambda report, key: "")
    monkeypatch.setattr(ui, "ordered_keys", lambda report: ["dollar", "rates"])
    html = ui.exposure_table_html(_report())
    assert re.findall(r'class="uar-usd" data-pct="([-0-9.]+)"', html) == ["-0.5555", "-0.3000"]
    assert 'class="uusd"' in html and 'class="uusd-in"' in html
    assert "Trade-weighted U.S. dollar" in html and "10-year Treasury yield" in html   # tooltips on the names
    assert xp.GLOSSARY["range90"].text in html


def test_the_amount_box_is_not_a_react_controlled_input():
    # Streamlit renders this HTML as React elements: an input with a value
    # attribute and no handler snaps back after every keystroke.
    box = re.search(r"<input[^>]*>", xp.dollars_bar_html()).group(0)
    assert "value=" not in box and "placeholder=" in box


def test_the_styles_ride_in_the_single_style_block():
    # Streamlit's markdown keeps the first <style> of an element and drops a second.
    assert ui.REPORT_CSS.count("<style>") == 1 and ui.REPORT_CSS.count("</style>") == 1
    assert ".ugl-tip{" in ui.REPORT_CSS and ".uusd{" in ui.REPORT_CSS


def test_the_dollar_script_is_injected_into_every_page():
    import scripts.inject_boot_splash as inj
    runtime = inj._build_runtime()
    assert "__uaUsd" in runtime and ".uar-usd[data-pct]" in runtime
    assert "localStorage.setItem(KEY" in runtime                 # remembered in the browser only


def test_the_report_page_lists_the_words_it_used():
    page = (ROOT / "pages" / "60_Exposure_Report.py").read_text(encoding="utf-8")
    assert "_xp.glossary_html(" in page
    card = xp.glossary_html(["credit", "range90", "missing"])
    assert card.count('<li>') == 2 and "Words used in this report" in card
