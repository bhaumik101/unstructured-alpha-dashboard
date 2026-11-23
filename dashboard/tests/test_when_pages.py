""""Which stocks went up when ... ?" -- measured, not predicted.

What must hold:
  * the falling page is the rising reading with its sign turned over (and its
    range flipped), never re-estimated; the page says the readings are linear;
  * "went up"/"went down" count only readings that held up; the rest are
    counted, never ranked;
  * past tense only -- no forecast or advice words;
  * a thin page (fewer than MIN_HELD held up) is noindex and not in the sitemap;
  * every slug resolves, unknown ones 404, and force pages link both ways.
"""

from __future__ import annotations

import re

from tests.test_explore_page import STOCKS, client  # noqa: F401  (fixture)
from utils import when_pages as wp


def _stock(t, impact, ev="clear", key="rates"):
    return {"ticker": t, "name": t + " Co", "as_of": "2026-11-13",
            "exposures": {key: {"impact": impact, "low": impact - 0.4, "high": impact + 0.4, "evidence": ev}}}


LIB = ([_stock(f"U{i}", 1.0 + i / 10) for i in range(6)] + [_stock(f"D{i}", -2.0 - i / 10) for i in range(4)]
       + [_stock("N1", 0.3, "indistinct"), _stock("N2", -0.2, "indistinct")])


def test_falling_is_the_rising_reading_with_its_sign_turned_over():
    up = wp.scenario("rates", 1, LIB)
    down = wp.scenario("rates", -1, LIB)
    assert [r["ticker"] for r in up["up"]][:1] == ["U5"] and len(up["up"]) == 6 and len(up["down"]) == 4
    assert [r["ticker"] for r in down["up"]][:1] == ["D3"] and len(down["up"]) == 4 and len(down["down"]) == 6
    d3 = down["up"][0]
    assert round(d3["move"], 6) == 2.3 and round(d3["low"], 6) == 1.9 and round(d3["high"], 6) == 2.7
    assert up["none"] == down["none"] == 2                       # never ranked, only counted


def test_the_page_answers_in_the_past_tense_and_says_how():
    html = wp.when_page_html("rates-fall", LIB, "https://www.x", "https://app.x")
    assert "<h1>Stocks that went up when interest rates fell</h1>" in html
    assert "the 10-year Treasury yield fell 0.25 percentage points" in html
    assert "The readings are linear" in html and 'href="/when/rates-rise"' in html
    text = re.sub(r"<[^>]+>", " ", html.split("<main")[1]).lower()
    for word in ("poised", "benefit", "should buy", "will rise", "expected to"):
        assert word not in text, word
    assert 'href="/exposure/D3"' in html


def test_thin_pages_are_noindex_and_left_out_of_the_sitemap():
    thin = LIB[:3]                                              # 3 held up < MIN_HELD
    assert 'content="noindex' in wp.when_page_html("rates-rise", thin, "https://www.x", "https://app.x")
    assert 'content="noindex' not in wp.when_page_html("rates-rise", LIB, "https://www.x", "https://app.x")
    urls = "\n".join(wp.when_sitemap_urls(LIB, "https://www.x"))
    assert "/when/rates-rise</loc>" in urls and "/when/rates-fall</loc>" in urls
    assert "/when/oil-rises</loc>" not in urls                  # nothing measured on oil here


def test_every_slug_resolves_and_the_set_is_symmetric():
    assert len(wp.BY_SLUG) == 2 * len(wp.SCENARIOS)
    for slug, (key, sign) in wp.BY_SLUG.items():
        assert wp.slug_for(key, sign) == slug
        assert (" fell " in wp.shock_phrase(key, sign) or " narrowed " in wp.shock_phrase(key, sign)) == (sign < 0)
    assert wp.when_page_html("nope", LIB, "https://www.x", "https://app.x") is None


def test_routes_hub_sitemap_and_force_page_links(client):  # noqa: F811
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    assert c.get("/when").status_code == 200 and 'href="/when/rates-fall"' in c.get("/when").text
    assert c.get("/when/rates-fall").status_code == 200
    assert c.get("/when/Rates-Fall", follow_redirects=False).status_code == 301
    assert c.get("/when/nope").status_code == 404
    assert 'href="/when/rates-rise"' in c.get("/forces/rates").text
    assert "/when</loc>" in c.get("/sitemap.xml").text


def test_natural_gas_waits_for_its_re_measure():
    """Readings from before the switch to futures carry a notice and stay out of
    search; once the weekly job re-measures them, the notice goes."""
    old = [_stock(f"G{i}", 1.0 + i / 10, key="natgas") for i in range(10)]
    html = wp.when_page_html("natural-gas-rises", old, "https://www.x", "https://app.x")
    assert "Being re-measured" in html and 'content="noindex' in html
    assert "/when/natural-gas-rises</loc>" not in "\n".join(wp.when_sitemap_urls(old, "https://www.x"))
    new = [dict(s, as_of="2026-11-20") for s in old]
    html = wp.when_page_html("natural-gas-rises", new, "https://www.x", "https://app.x")
    assert "Being re-measured" not in html and 'content="noindex' not in html


def test_long_lists_fold_but_stay_in_the_page():
    """Ten at once, the rest one click away -- and still in the HTML, so search
    engines and find-in-page see every listed stock."""
    import re
    from utils import when_pages as wp
    stocks = [_stock(f"T{i:02d}", -(i + 1) * 1.0) for i in range(30)]
    html = wp.when_page_html("rates-fall", stocks, "https://x", "https://app.x")
    table = html[html.index('aria-label="Went up"'):]
    first = table[:table.index("</table>")]
    assert first.count('href="/exposure/T') == wp.SHOW_UP
    assert "Show 15 more" in html
    assert len(set(re.findall(r'href="/exposure/(T\d\d)"', html))) == wp.TOP_UP
    assert "Showing the 25 largest of 30." in html


def test_the_page_draws_the_split_and_the_largest_moves():
    """The answer at a glance: every stock measured in one strip (no clear
    link included), then the largest moves on one shared axis."""
    stocks = ([_stock(f"U{i}", -(i + 1) * 0.5) for i in range(12)] + [_stock(f"D{i}", (i + 1) * 0.4) for i in range(6)]
              + [_stock(f"N{i}", 0.1, "indistinct") for i in range(20)])
    html = wp.when_page_html("rates-fall", stocks, "https://x", "https://app.x")
    assert "<b>12</b> <i>went up</i>" in html and "<b>20</b> <i>no clear link</i>" in html and "<b>6</b> <i>went down</i>" in html
    svg = html[html.index('class="card wp-rank"'):]
    svg = svg[:svg.index("</figure>")]
    assert svg.count('<a href="/exposure/') == 10 + 5
    assert svg.count('class="wp-ax"') == 3                       # one scale, labelled once
    assert "N0" not in svg                                        # no clear link: counted, never ranked
