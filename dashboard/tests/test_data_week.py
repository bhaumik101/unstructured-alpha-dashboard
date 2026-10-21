"""'Data through' on a page of many stocks is the week they share.

A stock a visitor opens mid-week is measured on fresher data than the weekly
library. Live on 2026-10-19 one such stock (SOXL, through Oct 9) made pages
covering 499 stocks say "data through Oct 9" while 498 were through Oct 2.
The date a page shows is the week the most of its stocks are through; the
sitemap's lastmod still uses the newest, since the page did change.
"""

from __future__ import annotations

import copy

from tests.test_explore_page import _stock
from utils import force_pages as fp
from utils import list_page as lp
from utils import map_page as mp
from utils import scenario_page as scp
from utils import sector_pages as sp
from utils.exposure_pages import data_week

ALL5 = dict(rates=(0.5, "clear"), inflation=(0.2, "indistinct"), dollar=(0.1, "indistinct"),
            oil=(1.0, "clear"), credit=(0.3, "indistinct"))


def _at(stock, as_of):
    s = copy.deepcopy(stock)
    s["as_of"] = as_of
    for e in s["exposures"].values():
        e["as_of"] = as_of
    return s


LIBRARY = [_at(_stock(t, t, **ALL5), "2026-10-02") for t in ("XOM", "CVX", "DAL")]
AHEAD = _at(_stock("SOXL", "Leveraged", **ALL5), "2026-10-09")
STOCKS = LIBRARY + [AHEAD]


def test_the_shared_week_wins_and_a_tie_goes_to_the_newer():
    assert data_week(["2026-10-02", "2026-10-02", "2026-10-09"]) == "2026-10-02"
    assert data_week(["2026-10-02", "2026-10-09"]) == "2026-10-09"
    assert data_week(["", None]) == "" and data_week([]) == ""


def test_force_pages_show_the_shared_week_and_the_sitemap_the_newest():
    st = fp.force_stats("oil", STOCKS)
    assert st["as_of"] == "2026-10-02" and st["newest"] == "2026-10-09"
    html = fp.force_page_html("oil", STOCKS, "https://www.x", "https://app.x")
    assert "Data through Oct 2, 2026" in html and "Oct 9, 2026" not in html
    assert any("<lastmod>2026-10-09</lastmod>" in u and "/forces/oil" in u
               for u in fp.force_sitemap_urls(STOCKS, "https://www.x"))


def test_the_map_scenario_and_list_feeds_carry_the_shared_week():
    assert mp.map_data(STOCKS)["as_of"] == "2026-10-02"
    assert scp.scenario_data(STOCKS)["as_of"] == "2026-10-02"
    assert lp.list_data(STOCKS)["as_of"] == "2026-10-02"


def test_sector_pages_show_the_shared_week(monkeypatch):
    monkeypatch.setattr(sp, "sector_by_ticker", lambda: {s["ticker"]: "Energy" for s in STOCKS})
    page = sp.sector_page_html("Energy", STOCKS, "https://www.x", "https://app.x")
    assert "data through Oct 2, 2026" in page and "Oct 9, 2026" not in page
    hub = sp.sectors_hub_html(STOCKS, "https://www.x", "https://app.x")
    assert "Data through Oct 2, 2026" in hub
