"""Download (www/exposure.csv): every reading on record, one row per stock and force.

What must hold: the figures are the pages' figures with their evidence label;
nothing unmeasured gets a row; names with commas survive; it downloads as a
file, is cached at the edge, and the stock list links to it.
"""

from __future__ import annotations

import csv
import io

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)


def test_one_row_per_reading_with_its_evidence(client, monkeypatch):  # noqa: F811
    c, _one, lib, M = client
    stocks = [_stock("XOM", "Exxon, Mobil", oil=(2.4, "clear"), rates=(-0.3, "indistinct")),
              _stock("AAA", "A Co", gold=(0.5, "tentative"))]
    monkeypatch.setattr(M, "_exposure_stocks", lambda: stocks)
    r = c.get("/exposure.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "s-maxage=3600" in r.headers["cache-control"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert [(x["ticker"], x["force"]) for x in rows] == [("AAA", "gold"), ("XOM", "rates"), ("XOM", "oil")]
    xom_oil = rows[2]
    assert xom_oil["name"] == "Exxon, Mobil" and xom_oil["evidence"] == "clear"
    assert xom_oil["typical_weekly_move_pct"] == "2.4000" and xom_oil["range90_low_pct"] == "1.4000"
    assert xom_oil["shock"] == "the price of oil rose 10%" and xom_oil["data_through"] == "2026-09-25"


def test_the_stock_list_links_to_it(client):  # noqa: F811
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    assert 'href="/exposure.csv" download' in c.get("/exposure").text
