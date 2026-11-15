"""/xray: click holdings, see the mix's economic fingerprint.

What must hold: the page ships every stock and fund on record plus the S&P 500
trackers (counted as zero beyond the market); the blend is never bolded or
given a range; "balanced" weights are labelled a calculation on past readings,
not a recommendation; the mix travels to the app's full report in the link
format the app parses; it is served, listed, proxied and on the nav bar.
"""

from __future__ import annotations

import json
import re

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import xray_page as xp
from utils.report_ui import parse_holdings_param

STOCKS = [_stock("XOM", "Exxon", oil=(2.4, "clear")), _stock("TLT", "Bonds", rates=(-3.8, "clear"))]


def _data(html):
    return json.loads(re.search(r'<script type="application/json" id="xr-data">(.*?)</script>', html).group(1))


def test_the_page_ships_the_library_and_the_market_trackers():
    html = xp.xray_page_html(STOCKS, "https://www.x", "https://app.x")
    d = _data(html)
    assert {"XOM", "TLT"} <= set(d["s"]) and "VOO" in d["mkt"] and "VTI" in d["mkt"]
    assert "Funds that track the S&amp;P 500 count as zero" in html


def test_balanced_weights_are_labelled_a_calculation_not_advice():
    html = xp.xray_page_html(STOCKS, "https://www.x", "https://app.x")
    assert "A calculation on past readings, not a recommendation." in html
    assert "the balanced weights included, is a recommendation to buy, sell or hold" in html
    assert not re.search(r"\b(you should|we recommend|buy now)\b", html, re.I)


def test_the_link_format_is_the_one_the_app_parses():
    assert "t + ':' + (Math.round(1000 * (weights[t] || 0)) / 10)" in xp._SCRIPT
    rows = parse_holdings_param("JPM:42.9,TLT:50")
    assert rows == [{"ticker": "JPM", "weight_pct": 42.9}, {"ticker": "TLT", "weight_pct": 50.0}]


def test_served_listed_and_first_on_the_nav(client):  # noqa: F811
    from utils.exposure_pages import NAV
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank")
    M._exposure_cache.clear()
    r = c.get("/xray")
    assert r.status_code == 200 and '"BANK"' in r.text and 'page:"X-ray"' in r.text
    assert "/xray</loc>" in c.get("/sitemap.xml").text
    assert NAV[0] == ("/xray", "X-ray")
