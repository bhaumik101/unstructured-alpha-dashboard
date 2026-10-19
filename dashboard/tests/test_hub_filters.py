"""Filters on the stocks table (www/exposure): sector and "held up" filters.

What must hold: every row carries its sector (empty outside the index, never
guessed) and one mark per core force -- u/d only where the reading held up
that way, n where it did not, - where it was not measured; the hub page
offers both filters and a sector page (one sector already) does not; the
script filters on those marks and keeps the choice in the URL.
"""

from __future__ import annotations

import re

import pytest

from tests.test_explore_page import _stock
from utils import exposure_pages as ep
from utils import sector_pages as sp


@pytest.fixture
def stocks(monkeypatch):
    sp.sector_by_ticker.cache_clear()
    monkeypatch.setattr(sp, "sector_by_ticker", lambda: {"XOM": "Energy", "DAL": "Industrials"})
    return [_stock("XOM", "Exxon", oil=(2.4, "clear"), rates=(0.1, "indistinct")),
            _stock("DAL", "Delta", oil=(-1.9, "tentative"), dollar=(-0.5, "clear")),
            _stock("ZZZ", "Not in the index", credit=(0.4, "clear"))]


def _rows(html):
    return {m[0]: (m[1], m[2]) for m in re.findall(
        r'<tr data-k="[^"]*" data-s="([^"]*)" data-h="([^"]*)"><th scope="row"><a href="/exposure/([A-Z]+)"', html)
        for m in [(m[2], m[0], m[1])]}


def test_each_row_carries_its_sector_and_a_mark_per_force(stocks):
    html = ep.hub_grid_html(stocks, filters=True)
    rows = _rows(html)
    order = list(ep._ORDER)
    xom_s, xom_h = rows["XOM"]
    assert xom_s == "energy" and xom_h[order.index("oil")] == "u" and xom_h[order.index("rates")] == "n"
    assert xom_h[order.index("dollar")] == "-"                         # not measured
    dal_s, dal_h = rows["DAL"]
    assert dal_s == "industrials" and dal_h[order.index("oil")] == "d" and dal_h[order.index("dollar")] == "d"
    assert rows["ZZZ"][0] == "" and rows["ZZZ"][1][order.index("credit")] == "u"     # no sector, not a guess


def test_the_hub_offers_both_filters_and_a_sector_page_does_not(stocks):
    hub = ep.hub_page_html(stocks, "https://www.x", "https://app.x")
    assert 'id="hub-sec"' in hub and 'id="hub-held"' in hub
    assert '<option value="energy">Energy</option>' in hub
    oil = list(ep._ORDER).index("oil")
    assert f'<option value="{oil}:u">Moved up with oil and energy</option>' in hub
    page = sp.sector_page_html("Energy", stocks, "https://www.x", "https://app.x")
    assert 'id="hub-sec"' not in page and 'id="hub-held"' not in page


def test_the_script_filters_on_the_marks_and_keeps_the_choice_in_the_url():
    js = ep._HUB_SCRIPT
    assert "(r.getAttribute('data-h') || '').charAt(hi) === hd" in js
    assert "r.getAttribute('data-s') === sv" in js
    assert "history.replaceState" in js


def _cards(html):
    """{force label: (no clear link text, up, down, up preset, down preset)}"""
    return {m[0]: m[1:] for m in re.findall(
        r'<li><h2>([^<]+)</h2><p class="small">([^<]+)</p>.*?'
        r'<a href="#h=[^"]+" data-hv="([^"]+)"><span><i class="u"></i>Moved up</span><b>(\d+)</b></a>'
        r'<a href="#h=[^"]+" data-hv="([^"]+)"><span><i class="d"></i>Moved down</span><b>(\d+)</b></a></li>', html)}


def test_the_overview_counts_only_readings_that_held_up(stocks):
    cards = _cards(ep.hub_page_html(stocks, "https://www.x", "https://app.x"))
    order = list(ep._ORDER)
    oil = ep._FACTOR["oil"].label
    # XOM up (clear), DAL down (tentative): both held up; nothing else measured on oil.
    assert cards[oil] == ("No clear link: 0 of 2", f"{order.index('oil')}:u", "1",
                          f"{order.index('oil')}:d", "1")
    # XOM's rates reading did not hold up: it is counted as no clear link, not as up.
    assert cards[ep._FACTOR["rates"].label][0] == "No clear link: 1 of 1"
    assert cards[ep._FACTOR["rates"].label][2] == "0"
    # Every core force measured gets a card; the presets match the filter's option values.
    hub = ep.hub_page_html(stocks, "https://www.x", "https://app.x")
    for _, up_v, _, down_v, _ in [(c[0], c[1], c[2], c[3], c[4]) for c in cards.values()]:
        assert f'<option value="{up_v}">' in hub and f'<option value="{down_v}">' in hub


def test_a_force_nobody_was_measured_on_gets_no_card(stocks):
    stocks = [s for s in stocks if s["ticker"] == "ZZZ"]
    cards = _cards(ep.hub_overview_html(stocks))
    assert list(cards) == [ep._FACTOR["credit"].label]


def test_the_presets_drive_the_held_up_filter():
    js = ep._HUB_SCRIPT
    assert "held.value = held.value === v ? '' : v; filter();" in js
