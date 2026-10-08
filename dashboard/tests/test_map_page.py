"""The stock map (www/map): every stock on any two forces at once.

What must hold: a stock is placed only where both readings were measured,
never at zero for a missing one; each reading carries whether it held up;
stocks outside the index carry no sector rather than a guessed one; the page
holds a table of what is plotted; an empty library is noindex; the route,
sitemap, nav and proxy all know the page.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import map_page as mp
from utils import sector_pages as sp


@pytest.fixture
def stocks(monkeypatch):
    sp.sector_by_ticker.cache_clear()
    monkeypatch.setattr(sp, "sector_by_ticker", lambda: {"XOM": "Energy", "JPM": "Financials"})
    return [_stock("XOM", "Exxon", oil=(2.4, "clear"), rates=(0.1, "indistinct")),
            _stock("JPM", "JPMorgan", rates=(1.1, "tentative")),
            _stock("ZZZ", "Not in the index", oil=(-0.4, "indistinct"), rates=(-0.2, "clear"))]


def _payload(html: str) -> dict:
    return json.loads(re.search(r'<script type="application/json" id="mp-data">(.*?)</script>', html).group(1))


def test_each_stock_carries_its_readings_with_null_where_not_measured(stocks):
    d = mp.map_data(stocks)
    keys = [f[0] for f in d["f"]]
    assert keys == ["rates", "oil"]                       # only forces with a reading, in order
    assert d["f"][0][3] == "interest rates"               # a lower-case label for sentences
    rows = {r[0]: r for r in d["s"]}
    assert rows["XOM"][3] == [0.1, 2.4] and rows["XOM"][4] == "01"
    assert rows["JPM"][3] == [1.1, None] and rows["JPM"][4] == "1-"   # never 0 for "not measured"
    assert d["sec"][rows["XOM"][2]] == "Energy"
    assert rows["ZZZ"][2] == -1                           # outside the index: no sector, not a guess


def test_the_script_plots_only_where_both_readings_exist():
    # The filter that keeps a stock off the map unless both axes were measured.
    assert "r[3][xi] !== null && r[3][yi] !== null" in mp._SCRIPT


def test_the_page(stocks):
    html = mp.map_page_html(stocks, "https://www.x", "https://app.x")
    assert "<h1>Stock map</h1>" in html and "noindex" not in html
    assert _payload(html)["s"][0][0] == "JPM"
    assert "'__X__'" not in html and "x: 'rates', y: 'oil'" in html
    assert 'id="mp-rows"' in html and "as a table" in html      # what is plotted, for anyone who cannot see it
    assert "Neither could be told apart from zero" in html
    assert "not a forecast" in html and "/*PCT*/" not in html


def test_an_empty_library_is_noindex():
    html = mp.map_page_html([], "https://www.x", "https://app.x")
    assert "noindex" in html and "Not enough stocks" in html


def test_route_sitemap_and_nav(client):  # noqa: F811
    from utils.exposure_pages import NAV
    c, _one, lib, M = client
    assert "noindex" in c.get("/map").text and "/map</loc>" not in c.get("/sitemap.xml").text
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    r = c.get("/map")
    assert r.status_code == 200 and "noindex" not in r.text and '"BANK"' in r.text
    assert "/map</loc>" in c.get("/sitemap.xml").text
    assert ("/map", "Map") in NAV and 'href="/map"' in r.text
