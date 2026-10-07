"""How to read these pages (www/learn): one plain-English guide to every figure.

What must hold: the numbers it quotes are the engine's own (window, bars,
shocks), so the guide cannot drift from the method; the worked example is
labelled an illustration; the page is served, listed, and linked from every
page's footer and from the main tables.
"""

from __future__ import annotations

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import exposure as ex
from utils.learn_page import learn_page_html


def test_it_quotes_the_engines_own_numbers():
    html = learn_page_html("https://www.x", "https://app.x")
    assert f"last {ex.WINDOW_WEEKS // 52} years" in html
    assert f"|t| ≥ {ex.CLEAR_T:.2f}" in html and f"|t| ≥ {ex.Z90:.2f}" in html
    assert f"|t| ≥ {ex.EXTRA_CLEAR_T:.2f}" in html
    for f in ex.FACTORS:
        assert f.shock_phrase in html
    assert "Illustration, not a real stock" in html and "not a forecast" in html


def test_served_listed_and_linked(client):  # noqa: F811
    c, _one, lib, M = client
    assert c.get("/learn").status_code == 200
    assert "/learn</loc>" in c.get("/sitemap.xml").text
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    page = c.get("/exposure/BANK").text
    body = page.split('<main id="main">')[1].split("</main>")[0]
    assert 'href="/learn"' in body                       # under the table, not only the footer
    assert 'href="/learn"' in c.get("/exposure").text.split("</main>")[0]
    assert 'href="/learn">How to read these pages' in page    # footer
