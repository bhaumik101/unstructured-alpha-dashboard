"""Sectors (www/sectors): economic exposure one GICS sector at a time.

What must hold: every index company has a sector and the slugs are unique;
a cell is the median of the sector's readings with counts of those that held
up each way; too few readings show a count, not a median; stocks outside the
index are left out, never guessed; empty sectors are noindex and unlisted;
the stock page links its sector.
"""

from __future__ import annotations

import pytest

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import sector_pages as sp


def test_every_index_company_has_a_sector_and_slugs_are_unique():
    import csv
    with open(sp.INDEX_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) >= 500 and all(r["sector"] for r in rows)
    assert len(sp.sectors()) == 11
    assert len({sp.slug(s) for s in sp.sectors()}) == 11
    assert sp.by_slug("information-technology") == "Information Technology"


@pytest.fixture
def energy(monkeypatch):
    sp.sector_by_ticker.cache_clear()
    monkeypatch.setattr(sp, "sector_by_ticker", lambda: {
        "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "OXY": "Energy",
        "JPM": "Financials", "BANK": "Financials"})
    return [_stock("XOM", "Exxon", oil=(2.4, "clear"), rates=(0.1, "indistinct")),
            _stock("CVX", "Chevron", oil=(1.9, "clear")),
            _stock("COP", "Conoco", oil=(1.2, "tentative")),
            _stock("OXY", "Occidental", oil=(-0.2, "indistinct")),
            _stock("JPM", "JPMorgan", rates=(1.1, "clear")),
            _stock("ZZZ", "Not in the index", oil=(9.0, "clear"))]


def test_a_cell_is_the_median_with_counts_of_what_held_up(energy):
    mem = sp.members_of("Energy", energy)
    c = sp.sector_cell(mem, "oil")
    assert c == {"n": 4, "median": (1.2 + 1.9) / 2, "up": 3, "down": 0}
    thin = sp.sector_cell(mem, "rates")
    assert thin["n"] == 1 and thin["median"] is None            # too few for a median


def test_stocks_outside_the_index_are_left_out(energy):
    assert "ZZZ" not in [m["ticker"] for m in sp.members_of("Energy", energy)]


def test_the_hub_and_a_sector_page(energy):
    hub = sp.sectors_hub_html(energy, "https://www.x", "https://app.x")
    from utils.exposure_pages import fmt_pct
    want = fmt_pct((1.2 + 1.9) / 2)
    assert f'<b>{want}</b><span class="shock">3↑ 0↓ held up, of 4</span>' in hub
    assert '1 measured' in hub and "noindex" not in hub
    page = sp.sector_page_html("Energy", energy, "https://www.x", "https://app.x")
    assert "4 of 4 companies on record" in page and 'href="/exposure/XOM"' in page
    assert 'href="/exposure/JPM"' not in page and "it is not a forecast" in page
    empty = sp.sector_page_html("Utilities", energy, "https://www.x", "https://app.x")
    assert 'content="noindex' in empty


def test_routes_sitemap_and_the_stock_page_link(client, energy):  # noqa: F811
    c, _one, lib, M = client
    assert c.get("/sectors/no-such-sector").status_code == 404
    assert c.get("/sectors/Energy", follow_redirects=False).headers["location"] == "/sectors/energy"
    assert "/sectors</loc>" not in c.get("/sitemap.xml").text
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    sm = c.get("/sitemap.xml").text
    assert "/sectors/financials</loc>" in sm and "/sectors/energy</loc>" not in sm
    assert c.get("/sectors/financials").status_code == 200
    assert 'href="/sectors/financials">Financials</a>' in c.get("/exposure/BANK").text


def test_a_stock_page_shows_its_sector_peers_median(energy):
    from utils.exposure_pages import fmt_pct, stock_page_html
    p = sp.peer_medians("XOM", energy)
    assert p["sector"] == "Energy" and p["peers"] == 3          # XOM itself left out
    assert p["medians"]["oil"] == 1.2                           # median of 1.9, 1.2, -0.2
    assert "rates" not in p["medians"]                          # too few peers measured
    html = stock_page_html("XOM", energy[0], [], [], "https://www.x", "https://app.x", peers=p)
    assert f'<a href="/sectors/energy">Energy</a> median {fmt_pct(1.2)}' in html
    assert sp.peer_medians("ZZZ", energy) is None               # outside the index


def test_the_stock_route_passes_its_peers(client, monkeypatch):  # noqa: F811
    c, _one, lib, M = client
    peers = [_stock(t, t, oil=(v, "clear")) for t, v in (("P1", 1.0), ("P2", 2.0), ("P3", 3.0))]
    monkeypatch.setattr(sp, "sector_by_ticker", lambda: {"BANK": "Energy", "P1": "Energy",
                                                         "P2": "Energy", "P3": "Energy"})
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    real = M._exposure_stocks
    monkeypatch.setattr(M, "_exposure_stocks", lambda: real() + peers)
    from utils.exposure_pages import fmt_pct
    assert f'<a href="/sectors/energy">Energy</a> median {fmt_pct(2.0)}' in c.get("/exposure/BANK").text


def test_a_force_page_ranks_sectors_by_their_median(energy):
    from utils.force_pages import force_page_html
    stocks = energy + [_stock("BANK", "Bank", oil=(-1.0, "clear"))]
    sp_map = sp.sector_by_ticker()
    assert sp_map["BANK"] == "Financials"
    html = force_page_html("oil", iter(stocks), "https://www.x", "https://app.x")
    assert "By sector: oil and energy" in html
    energy_at, fin_at = html.index('href="/sectors/energy"'), html.index('href="/sectors/financials"')
    assert energy_at < fin_at                     # +1.55% median ranks above a single -1.0% reading
    assert "1 measured" in html                   # Financials: too few for a median
    assert 'href="/exposure/XOM"' in html         # the stock ranking still renders from the same iterator


@pytest.fixture
def two_sectors(monkeypatch):
    sp.sector_by_ticker.cache_clear()
    monkeypatch.setattr(sp, "sector_by_ticker", lambda: {
        "XOM": "Energy", "CVX": "Energy", "COP": "Energy",
        "JPM": "Financials", "BAC": "Financials", "WFC": "Financials"})
    return [_stock("XOM", "Exxon", oil=(2.4, "clear")),
            _stock("CVX", "Chevron", oil=(2.0, "clear")),
            _stock("COP", "Conoco", oil=(-0.3, "indistinct")),
            _stock("JPM", "JPMorgan", oil=(-0.5, "indistinct"), rates=(1.0, "clear")),
            _stock("BAC", "BofA", oil=(-0.6, "tentative")),
            _stock("WFC", "Wells", oil=(-0.4, "indistinct")),
            _stock("ZZZ", "Not in the index", oil=(9.0, "clear"))]


def test_the_hub_is_a_heatmap_shaded_by_size_against_the_largest_median(two_sectors):
    import re
    hub = sp.sectors_hub_html(two_sectors, "https://www.x", "https://app.x")
    # Energy on oil has the largest median (+2.0%): full strength, blue.
    assert re.search(r'<td data-v="2\.0000" class="hm hm-up" style="--a:1\.00">'
                     r'<a class="hm-a" href="/sectors/energy#f-oil">', hub)
    # Financials on oil (-0.5%) a quarter of that, orange.
    assert 'class="hm hm-down" style="--a:0.25"><a class="hm-a" href="/sectors/financials#f-oil">' in hub
    # Too few readings: a count, no shade and nothing to open.
    assert '<td class="v-weak">1 measured</td>' in hub
    assert "Shading is darker the larger the median move" in hub


def test_each_hub_cell_opens_the_stocks_behind_it(two_sectors):
    import json
    import re
    hub = sp.sectors_hub_html(two_sectors, "https://www.x", "https://app.x")
    data = json.loads(re.search(r'<script type="application/json" id="hm-data">(.*?)</script>', hub).group(1))
    assert data["k"] == ["rates", "inflation", "dollar", "oil", "credit"]
    energy = data["s"]["energy"]
    assert energy[0] == "Energy" and [r[0] for r in energy[1]] == ["COP", "CVX", "XOM"]
    oil = data["k"].index("oil")
    by = {r[0]: r[2] for r in energy[1]}
    assert by["XOM"][oil] == [2.4, 1] and by["COP"][oil] == [-0.3, 0]   # held up, or not
    assert by["XOM"][data["k"].index("rates")] is None                  # not measured: null, never 0
    assert "ZZZ" not in hub.split('id="hm-data"')[1].split("</script>")[0]
    assert 'id="hm-panel"' in hub and "pct(" in hub and "/*PCT*/" not in hub


def test_a_sector_page_anchors_each_force_for_the_heatmap_links(two_sectors):
    page = sp.sector_page_html("Energy", two_sectors, "https://www.x", "https://app.x")
    assert '<tr id="f-oil">' in page
    assert 'class="hm hm-up" style="--a:1.00"' in page
