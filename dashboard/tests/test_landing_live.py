"""The landing page's live demo (www/, fed by /landing.json).

What must hold: the feed lists only readings that held up, largest first
each side, capped per side, with the counts the page quotes; an empty
library gives no forces so the page hides the demo; the route is cached at
the edge and proxied on www; the page renders the demo and its links go to
pages that exist; its percent formatter matches the site's.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils.exposure_pages import fmt_pct
from utils.landing_data import PER_SIDE, landing_data

WEB = Path(__file__).resolve().parent.parent / "unstructured-alpha-web"
LIVE = (WEB / "app" / "LiveMovers.tsx").read_text(encoding="utf-8")
STATS = (WEB / "app" / "LiveStats.tsx").read_text(encoding="utf-8")
FEED = (WEB / "app" / "feed.ts").read_text(encoding="utf-8")


def test_only_held_up_readings_largest_first_with_counts():
    stocks = ([_stock(f"U{i}", f"Up {i}", oil=(1 + i, "clear")) for i in range(8)]
              + [_stock("D1", "Down", oil=(-2.0, "tentative")), _stock("Z", "Zero", oil=(0.3, "indistinct"))])
    d = landing_data(stocks)
    oil = next(f for f in d["forces"] if f["key"] == "oil")
    assert [r[0] for r in oil["up"]] == ["U7", "U6", "U5", "U4", "U3", "U2"]       # largest first, capped
    assert len(oil["up"]) == PER_SIDE and oil["held_up"] == 8
    assert oil["down"] == [["D1", "Down", -2.0, "tentative"]]
    assert "Z" not in str(oil["up"] + oil["down"]) and oil["none"] == 1 and oil["measured"] == 10
    assert oil["lower"] == "oil and energy" and d["stocks"] == 10
    assert next(f for f in landing_data([_stock("A", "", dollar=(1.0, "clear"))])["forces"])["lower"] == "U.S. dollar"


def test_an_empty_library_gives_no_forces():
    assert landing_data([])["forces"] == [] and landing_data([])["forces_measured"] == 0


def test_the_force_count_is_counted_from_the_readings_not_written_in():
    # The stats strip says how many forces have readings; it comes from the
    # library, so a force with no reading anywhere is not counted.
    d = landing_data([_stock("A", "", oil=(1.0, "clear"), gold=(0.2, "indistinct")),
                      _stock("B", "", oil=(0.5, "indistinct"))])
    assert d["forces_measured"] == 2
    assert "forces_measured" in STATS and not re.search(r"'\d+ economic forces'", STATS)


def test_route_is_cached_and_proxied(client):  # noqa: F811
    c, *_ = client
    r = c.get("/landing.json")
    assert r.status_code == 200 and r.json()["forces"] == []
    assert "s-maxage=600" in r.headers["cache-control"]
    cfg = (WEB / "next.config.ts").read_text(encoding="utf-8")
    assert re.search(r'source: "/landing\.json", destination: `\$\{SEO_ORIGIN\}/landing\.json`', cfg)


def test_the_page_renders_the_demo_and_hides_it_without_data():
    page = (WEB / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "import LiveMovers from './LiveMovers';" in page and "<LiveMovers />" in page
    assert "<LiveStats />" in page
    for part in (LIVE, STATS):
        assert "getFeed()" in part and "if (!feed) return null;" in part   # no data, nothing shown
    assert "d.forces.length" in FEED and ".catch(() => null)" in FEED      # empty or failed: no data
    assert FEED.count("fetch(") == 1 and "pending ??=" in FEED            # one request, shared
    for href in ("/explore#", "/scenario#", "/map", "/exposure/"):
        assert href in LIVE
    assert "it is not a forecast" in LIVE


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_its_percent_formatter_matches_the_site():
    src = re.search(r"export function pct\(v: number\): string \{.*?\n\}", LIVE, re.S).group(0)
    js = (src.replace("export function pct(v: number): string", "function pct(v)")
          .replace("`${(0).toFixed(d)}%`", "(0).toFixed(d) + '%'")
          .replace("`${v > 0 ? '+' : '−'}${s}%`", "(v > 0 ? '+' : '−') + s + '%'"))
    vals = [0, 0.004, -0.004, 0.0123, -0.36, 0.949, 0.951, -0.96, 1.04, 2.71, -3.33, 12.345, -0.0049]
    out = subprocess.run(["node", "-e", js + "\nconsole.log(JSON.stringify(%s.map(pct)))" % vals],
                         capture_output=True, text=True, check=True).stdout
    import json
    assert json.loads(out) == [fmt_pct(v) for v in vals]
