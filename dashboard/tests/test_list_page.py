"""My list (www/mylist): saved stocks side by side, kept in the browser.

What must hold: each stock carries its core readings with null where not
measured, never zero, and whether each held up; the equal-weight basket is
drawn only where every stock on the list was measured, and is styled as an
untested average, not a held-up reading; a shared link is offered, never
applied over an existing list silently; the page is noindex; every stock
page carries the save button; the route, proxy and nav know the page.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import list_page as lp
from utils import sector_pages as sp


@pytest.fixture
def stocks(monkeypatch):
    sp.sector_by_ticker.cache_clear()
    monkeypatch.setattr(sp, "sector_by_ticker", lambda: {"XOM": "Energy"})
    return [_stock("XOM", "Exxon", oil=(2.4, "clear"), rates=(0.1, "indistinct")),
            _stock("JPM", "JPMorgan", rates=(1.1, "tentative"))]


def test_each_stock_carries_its_core_readings_with_null_where_not_measured(stocks):
    d = lp.list_data(stocks)
    keys = [f[0] for f in d["f"]]
    assert keys == ["rates", "inflation", "dollar", "oil", "credit"]
    xom = d["s"]["XOM"]
    assert xom[:2] == ["Exxon", "Energy"]
    assert xom[2][keys.index("oil")] == [2.4, 1] and xom[2][keys.index("rates")] == [0.1, 0]
    assert xom[2][keys.index("dollar")] is None                     # not measured: null, never 0
    assert d["s"]["JPM"][1] == ""                                   # no sector, not a guess


def test_the_basket_is_drawn_only_where_every_stock_was_measured_and_never_as_held_up():
    js = lp._SCRIPT
    assert "if (cs.some(function(c){ return !c; })) return null;" in js
    assert "/ cs.length, 2]" in js                                  # flagged as an average
    assert "c[1] === 2 ? pct(c[0])" in js                            # drawn plain, not bold
    assert "an average is not itself tested" in js


def test_a_shared_link_is_offered_not_applied(stocks):
    js = lp._SCRIPT
    assert "Use this list" in js and "No thanks" in js
    # Nothing writes the offered list until a button is pressed.
    before_draw = js.split("function bars(")[0]
    assert "put(offered" not in before_draw


def test_the_page_is_noindex_and_carries_the_data(stocks):
    html = lp.list_page_html(stocks, "https://www.x", "https://app.x")
    assert 'content="noindex' in html and "<h1>My list</h1>" in html
    payload = json.loads(re.search(r'<script type="application/json" id="ls-data">(.*?)</script>', html).group(1))
    assert set(payload["s"]) == {"XOM", "JPM"}
    assert "/*PCT*/" not in html and "__KEY__" not in html and "__APP__" not in html
    assert "nothing sent anywhere" in html and "not a forecast" in html


def test_every_stock_page_has_the_save_button():
    from utils.exposure_pages import stock_page_html
    page = stock_page_html("XOM", _stock("XOM", "Exxon", oil=(2.4, "clear")), [], [],
                           "https://www.x", "https://app.x")
    assert 'id="ls-save" data-t="XOM"' in page and " hidden>" in page   # hidden until script runs
    assert "localStorage.setItem('ua-list'" in page


def test_route_and_nav(client):  # noqa: F811
    from utils.exposure_pages import NAV
    c, *_ = client
    r = c.get("/mylist")
    assert r.status_code == 200 and "My list" in r.text and 'content="noindex' in r.text
    assert ("/mylist", "My list") in NAV
