"""Every public page leads to the product: measuring a whole portfolio.

What must hold: the band sits on every page built with the shell, links into
the app with the sending page named (utm_content) and a sample report; with
two or more stocks on My list it offers to measure exactly those, through the
app's own ?h= link format; My list and Compare hand their stocks over too.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from tests.test_compare_page import STOCKS
from tests.test_explore_page import _stock
from utils import compare_page as cp
from utils import exposure_pages as ep
from utils import list_page as lp
from utils.report_ui import HOLDINGS_PARAM, parse_holdings_param


def test_app_link_names_the_sending_page():
    u = urlsplit(ep.app_link("https://app.x", "/", "https://www.x/sectors/energy", sample="balanced"))
    q = parse_qs(u.query)
    assert u.netloc == "app.x" and q["sample"] == ["balanced"]
    assert q["utm_source"] == ["public_tools"] and q["utm_content"] == ["sectors"]


def test_every_shell_page_ends_on_the_product():
    page = ep.stock_page_html("XOM", _stock("XOM", "Exxon", oil=(2.4, "clear")), [], [],
                              "https://www.x", "https://app.x")
    band = page.split('<section class="pband"')[1].split("</section>")[0]
    assert "Your portfolio, measured the same way" in band
    assert 'id="pb-own" href="https://app.x/?utm_source=public_tools' in band
    assert "sample=balanced" in band and 'id="pb-mine" hidden' in band
    assert page.index('<section class="pband"') > page.index("</main>")
    assert page.index('<section class="pband"') < page.index('<footer class="site-foot"')


def test_the_band_measures_my_list_through_the_apps_own_link_format():
    js = ep._BAND_SCRIPT
    assert "localStorage.getItem('ua-list')" in js and f"searchParams.set('{HOLDINGS_PARAM}', l.join(','))" in js
    assert "if (l.length < 2) return;" in js
    # The format the band writes is the one the app reads.
    assert [r["ticker"] for r in parse_holdings_param("XOM,DAL,AAPL")] == ["XOM", "DAL", "AAPL"]


def test_my_list_and_compare_hand_their_stocks_to_the_app():
    assert f"u.searchParams.set('{HOLDINGS_PARAM}', l.join(','))" in lp._SCRIPT
    assert 'id="ls-measure"' in lp.list_page_html(STOCKS, "https://www.x", "https://app.x")
    html = cp.compare_page_html(STOCKS, "XOM", "DAL", "https://www.x", "https://app.x")
    assert f"https://app.x/?{HOLDINGS_PARAM}=XOM%2CDAL&amp;utm_source=public_tools" in html
    assert "Measure XOM and DAL together" in html
