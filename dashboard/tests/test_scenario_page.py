"""Build a scenario (www/scenario): move all five core forces at once.

What must hold: only stocks measured on all five are placed, never with a
missing reading taken as zero, and the page says how many were left out;
each stock carries which of its readings held up, and its figure is bold
only when every force moved held up; presets name only core forces and stay
within the sliders' range; an empty library is noindex; route, sitemap and
proxy know the page.
"""

from __future__ import annotations

import json
import re

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import exposure as ex
from utils import scenario_page as sc

FIVE = dict(rates=(1.0, "clear"), inflation=(0.5, "indistinct"), dollar=(-0.4, "tentative"),
            oil=(2.0, "clear"), credit=(-1.0, "clear"))


def test_only_stocks_measured_on_all_five_are_placed():
    d = sc.scenario_data([_stock("XOM", "Exxon", **FIVE), _stock("JPM", "JPMorgan", rates=(1.1, "clear"))])
    assert [r[0] for r in d["s"]] == ["XOM"] and d["partial"] == 1
    xom = d["s"][0]
    assert xom[2] == [1.0, 0.5, -0.4, 2.0, -1.0] and xom[3] == "10111"
    assert [f["key"] for f in d["f"]] == [f.key for f in ex.FACTORS]
    assert d["f"][2]["lower"] == "U.S. dollar"


def test_the_figure_sums_moved_forces_and_is_bold_only_when_all_held():
    js = sc._SCRIPT
    assert "moved.forEach(function(i){ v += s[2][i] * k[i]; });" in js
    assert "held: moved.every(function(i){ return s[3].charAt(i) === '1'; })" in js
    assert "D.partial" in js                                  # says how many were left out


def test_presets_name_core_forces_within_the_slider_range():
    keys = {f.key for f in ex.FACTORS}
    for name, moves in sc.PRESETS:
        assert moves and set(moves) <= keys, name
        assert all(abs(v) <= sc.MAX_MULTIPLE and v * 2 == int(v * 2) for v in moves.values()), name


def test_the_page_and_an_empty_library():
    html = sc.scenario_page_html([_stock("XOM", "Exxon", **FIVE)], "https://www.x", "https://app.x")
    assert "<h1>Build a scenario</h1>" in html and "noindex" not in html
    data = json.loads(re.search(r'<script type="application/json" id="sc-data">(.*?)</script>', html).group(1))
    assert data["s"][0][0] == "XOM"
    assert "hypothetical moves to explore, not forecasts" in html and "not a forecast" in html
    assert "/*PCT*/" not in html and "__MAX__" not in html
    empty = sc.scenario_page_html([_stock("JPM", "JPMorgan", rates=(1.1, "clear"))], "https://www.x", "https://app.x")
    assert "noindex" in empty and "No stock has been measured on all five" in empty


def test_route_and_sitemap(client):  # noqa: F811
    c, _one, lib, M = client
    assert "noindex" in c.get("/scenario").text and "/scenario</loc>" not in c.get("/sitemap.xml").text
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    r = c.get("/scenario")
    assert r.status_code == 200 and "/scenario</loc>" in c.get("/sitemap.xml").text
