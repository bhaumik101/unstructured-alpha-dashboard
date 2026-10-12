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
