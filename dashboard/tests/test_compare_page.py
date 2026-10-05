"""Compare (www/compare): two stocks side by side, force by force.

What must hold: a force is called a clear difference only when the two 90%
ranges do not overlap; readings that did not hold up are shown greyed, not
dropped; bad or unknown tickers get a plain answer, never a 500 or an echo of
raw input; only the bare page is indexable, every pair is noindex.
"""

from __future__ import annotations

import re

import pytest

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import compare_page as cp

XOM = _stock("XOM", "Exxon Mobil", oil=(2.4, "clear"), rates=(0.3, "indistinct"), gold=(0.2, "tentative"))
DAL = _stock("DAL", "Delta Air Lines", oil=(-1.9, "tentative"), rates=(0.1, "indistinct"))
CVX = _stock("CVX", "Chevron", oil=(1.9, "clear"))
STOCKS = [XOM, DAL, CVX]


def test_a_difference_is_clear_only_when_the_ranges_do_not_overlap():
    rows = {r["key"]: r for r in cp.compare_rows(XOM, DAL)}
    assert rows["oil"]["apart"]                    # 1.4..3.4 vs -2.9..-0.9
    assert not rows["rates"]["apart"]              # -0.7..1.3 vs -0.9..1.1
    assert rows["gold"]["b"] is None and not rows["gold"]["apart"]
    assert not {r["key"]: r for r in cp.compare_rows(XOM, CVX)}["oil"]["apart"]   # 1.4..3.4 vs 0.9..2.9


def test_a_pair_names_the_widest_clear_gap_and_is_noindex():
    html = cp.compare_page_html(STOCKS, "xom", " dal ", "https://www.x", "https://app.x")
    assert "XOM and DAL clearly differ on 1 of 3 forces" in html
    assert "XOM typically moved +2.4% and DAL −1.9%" in html.replace("&#x27;", "'")
    assert 'content="noindex' in html and "it is not a forecast" in html
    assert 'class="v-weak"' in html or "class=v-weak" in html      # rates shown greyed, not dropped


def test_overlapping_everywhere_says_so():
    html = cp.compare_page_html(STOCKS, "XOM", "CVX", "https://www.x", "https://app.x")
    assert "their 90% ranges overlap every time" in html


@pytest.mark.parametrize("a,b,said", [
    ("XOM", "XOM", "Pick two different stocks."),
    ("XOM", "", "Pick a second stock to compare with XOM."),
    ("XOM", "ZZZZ", "ZZZZ is not on record yet."),
    ("<script>", "XOM", "Pick a second stock to compare with XOM."),
])
def test_bad_input_gets_a_plain_answer(a, b, said):
    html = cp.compare_page_html(STOCKS, a, b, "https://www.x", "https://app.x")
    assert said in html and "<script>" not in html.split("<body")[-1].replace("<script type=", "")
    assert 'content="noindex' in html


def test_bare_page_is_indexable_only_with_data():
    assert 'content="noindex' not in cp.compare_page_html(STOCKS, "", "", "https://www.x", "https://app.x")
    assert 'content="noindex' in cp.compare_page_html([], "", "", "https://www.x", "https://app.x")


def test_served_listed_and_linked_from_the_stock_page(client):  # noqa: F811
    c, _one, lib, M = client
    assert "/compare</loc>" not in c.get("/sitemap.xml").text
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    r = c.get("/compare", params={"a": "BANK", "b": "NOPE"})
    assert r.status_code == 200 and "NOPE is not on record yet" in r.text
    assert "/compare</loc>" in c.get("/sitemap.xml").text
    assert 'href="/compare?a=BANK"' in c.get("/exposure/BANK").text


def test_the_bare_page_offers_three_examples_that_are_on_record():
    held = [_stock(t, t, oil=(1.0, "clear")) for t in ("AAPL", "DAL", "CVX", "BAC", "AMT", "XOM")]
    html = cp.compare_page_html(held, "", "", "https://www.x", "https://app.x")
    shown = html.count('href="/compare?a=')
    assert shown == 3 and "a=XOM&amp;b=DAL" in html and "a=CVX&amp;b=DAL" in html
    assert "a=JPM" not in html and "b=MSFT" not in html           # not on record


def test_bars_diverge_from_centre_scale_to_the_largest_move_and_fade_when_weak():
    html = cp.compare_page_html(STOCKS, "XOM", "DAL", "https://www.x", "https://app.x")
    bars = re.findall(r'class="cp-bar ([^"]+)" style="(left|right):50%;width:([0-9.]+)%"', html)
    by = {}
    for c, side, w in bars:
        by[(c, side)] = max(by.get((c, side), 0.0), float(w))
    assert by[("cp-up", "left")] == 50.0                         # XOM oil +2.4, the largest
    assert by[("cp-down", "right")] == round(50 * 1.9 / 2.4, 1)   # DAL oil -1.9
    assert any("cp-faint" in c for c, _, _ in bars)               # indistinct rates
