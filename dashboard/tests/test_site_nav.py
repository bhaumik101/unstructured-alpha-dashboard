"""Site navigation: every public page carries the same header and footer.

What must hold: every tool in the header, the footer and /tools is a route
that answers; the page being viewed is marked current; the header's ticker
box sends a stock on record to its page, any other ticker to the app (which
measures it), and anything else to the stock list.
"""

from __future__ import annotations

import re

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import exposure_pages as ep
from utils.tools_page import TOOLS


def test_every_page_has_the_header_footer_and_search():
    html = ep.hub_page_html([_stock("XOM", "Exxon", oil=(1.0, "clear"))], "https://www.x", "https://app.x")
    nav = re.search(r'<nav class="site-nav".*?</nav>', html, re.S).group(0)
    assert [h for h, _ in ep.NAV] == re.findall(r'href="([^"]+)"', nav)
    assert '<form class="go" action="/go" method="get" role="search">' in html
    assert 'for="go-t"' in html and '<footer class="site-foot">' in html
    assert all(f'href="{h}"' in html for h, _ in ep.MORE)


def test_the_page_being_viewed_is_marked_current():
    def current(canonical):
        html = ep._site_nav(canonical)
        return re.findall(r'href="([^"]+)" aria-current="page"', html)
    assert current("https://www.x/exposure") == ["/exposure"]
    assert current("https://www.x/exposure/XOM") == ["/exposure"]
    assert current("https://www.x/sectors/energy") == ["/sectors"]
    assert current("https://www.x/evidence") == []
    assert current("https://www.x/explorer-nope") == []        # a prefix is not a section


def test_every_linked_tool_answers(client):  # noqa: F811
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    hrefs = {h for h, _ in ep.NAV} | {h for h, _ in ep.MORE} | {h for h, _, _ in TOOLS}
    for h in sorted(hrefs):
        assert c.get(h).status_code == 200, h
    tools = c.get("/tools").text
    assert all(f'href="{h}"' in tools for h, _, _ in TOOLS)
    assert "/tools</loc>" in c.get("/sitemap.xml").text


def test_the_ticker_box_goes_to_the_right_place(client):  # noqa: F811
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()

    def where(q):
        return c.get("/go", params={"t": q}, follow_redirects=False).headers["location"]
    assert where("bank") == "/exposure/BANK"
    assert where(" brk.b ") == f"{M.APP_URL}/stock?t=BRK-B"          # not on record: the app measures it
    assert where("<script>") == "/exposure" and where("") == "/exposure"
