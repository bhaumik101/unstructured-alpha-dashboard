"""Embed card (www/embed/XOM): one stock's card that other sites can iframe.

What must hold: the card keeps the stock page's honesty (held-up bold, the
rest grey, a dash where not measured, the date, "not a forecast"); it is
noindex with the stock page as canonical; it carries no script; database
strings are escaped; the route redirects lower case, 404s the unmeasured;
and the stock page offers the exact code to paste.
"""

from __future__ import annotations

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import embed_page as em


REC = _stock("XOM", "Exxon Mobil", oil=(2.4, "clear"), rates=(-0.3, "indistinct"))


def test_the_card_keeps_the_stock_pages_honesty():
    html = em.embed_card_html("XOM", REC, "https://www.x")
    assert "<b>+2.4%</b>" in html and "<span class=w>−0.30%</span>" in html
    assert html.count('class="v w">—') == 3                  # inflation, dollar, credit unmeasured
    assert "Data through Sep 25, 2026" in html and "not a forecast" in html
    assert 'class="br d f"' in html                           # a weak reading's bar is faint


def test_the_card_never_competes_with_the_page_it_summarises():
    html = em.embed_card_html("XOM", REC, "https://www.x")
    assert '<meta name="robots" content="noindex, follow">' in html
    assert '<link rel="canonical" href="https://www.x/exposure/XOM">' in html
    assert 'href="https://www.x/exposure/XOM" target="_blank" rel="noopener"' in html
    assert "<script" not in html


def test_database_strings_are_escaped():
    html = em.embed_card_html("XOM", dict(REC, name="<script>x</script>"), "https://www.x")
    assert "<script>x" not in html and "&lt;script&gt;x" in html


def test_the_route_serves_redirects_and_404s(client):  # noqa: F811
    c, _one, lib, M = client
    assert c.get("/embed/BANK").status_code == 404           # not measured yet
    assert lib.record(_one("BANK"), "Bank Co")
    r = c.get("/embed/BANK")
    assert r.status_code == 200 and "BANK" in r.text and "noindex" in r.text
    r = c.get("/embed/bank", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/embed/BANK"
    assert c.get("/embed/%3Cx%3E").status_code == 404


def test_the_stock_page_offers_the_exact_code(client):  # noqa: F811
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank Co")
    html = c.get("/exposure/BANK").text
    code = em.embed_code("BANK", M.BASE_URL)
    assert code.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;") in html
    assert 'id="embed-copy"' in html
