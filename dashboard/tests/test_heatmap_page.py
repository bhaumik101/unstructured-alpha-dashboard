"""The market heatmap (www/heatmap): every stock as a tile, one force at a time.

What must hold: only held-up readings are coloured (a weak reading is a grey
tile, an unmeasured one hatched, whatever its size); the colour scale is the
95th percentile of held-up moves; tile text is black or white, whichever
reads better on the tile's actual colour; stocks outside the index get their
own block rather than a guessed sector; route, sitemap and proxy know it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import heatmap_page as hp


def test_only_held_up_readings_are_coloured():
    js = hp._SCRIPT
    assert "else if (!h){ cls += ' n';" in js                 # weak reading: grey, whatever its size
    assert "if (v === null){ cls += ' x';" in js              # not measured: hatched
    assert "Math.floor(0.95 * (held.length - 1))" in js       # scale: 95th percentile of held-up moves
    assert "r[4].charAt(fi) === '1'; })" in js                # ... of held-up moves only
    assert "'Outside the S&P 500'" in js                      # no guessed sector


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_tile_text_always_clears_contrast():
    src = hp._SCRIPT
    fn = src[src.index("  function lum(c)"):src.index("  function draw()")]
    js = ("var dark = {matches: false};" + fn.replace("function colour(v, scale){", "function colour(v, scale, d){ dark.matches = d;")
          + """
function hex(s){ var m = /rgb\\((\\d+),(\\d+),(\\d+)\\);color:(#\\w+)/.exec(s); return [[+m[1], +m[2], +m[3]], m[4]]; }
var worst = 99;
[false, true].forEach(function(d){ for (var v = -3; v <= 3; v += 0.05){
  var r = hex(colour(v, 3, d)), L = lum(r[0]), t = r[1] === '#fff' ? 1.05 / (L + 0.05) : (L + 0.05) / 0.05;
  worst = Math.min(worst, t); } });
console.log(worst);""")
    worst = float(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert worst >= 4.5, worst


def test_the_page_and_its_route(client):  # noqa: F811
    html = hp.heatmap_page_html([_stock("XOM", "Exxon", oil=(2.4, "clear"))], "https://www.x", "https://app.x")
    data = json.loads(re.search(r'<script type="application/json" id="hx-data">(.*?)</script>', html).group(1))
    assert data["s"][0][0] == "XOM" and "'__DEFAULT__'" not in html and "/*PCT*/" not in html
    assert "there is no market-cap weighting" in html and "not a forecast" in html
    assert "noindex" in hp.heatmap_page_html([], "https://www.x", "https://app.x")
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    assert c.get("/heatmap").status_code == 200 and "/heatmap</loc>" in c.get("/sitemap.xml").text
