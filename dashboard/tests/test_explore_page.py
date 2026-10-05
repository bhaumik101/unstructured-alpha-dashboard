"""What if? (www/explore): move one force, see which stocks moved most with it.

The page is hands-on without a portfolio, so it must: rank only readings that
held up and say how many showed no link; carry its data safely inside the
page; be served, linked from the force pages and listed in the sitemap once
there is anything to explore -- and be noindex and unlisted when there isn't.
"""

from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import create_engine

from utils import explore_page as xp


def _stock(ticker, name, **readings):
    return {"ticker": ticker, "name": name, "as_of": "2026-09-25",
            "exposures": {k: {"impact": v, "low": v - 1, "high": v + 1, "evidence": e,
                              "as_of": "2026-09-25"} for k, (v, e) in readings.items()}}


STOCKS = [_stock("XOM", "Exxon Mobil", oil=(2.4, "clear"), rates=(0.1, "indistinct")),
          _stock("DAL", "Delta Air Lines", oil=(-1.9, "tentative")),
          _stock("KO", "Coca-Cola", oil=(0.05, "indistinct"))]


def test_only_readings_that_held_up_are_ranked_and_the_rest_are_counted():
    d = xp.explore_data(STOCKS)
    oil = next(f for f in d["forces"] if f["key"] == "oil")
    assert sorted(r[0] for r in oil["rows"]) == ["DAL", "XOM"]
    assert oil["measured"] == 3 and oil["none"] == 1
    assert oil["step"] == 10.0 and oil["unit"] == "%"
    rates = next(f for f in d["forces"] if f["key"] == "rates")
    assert rates["rows"] == [] and rates["unit"] == "pp"
    assert not any(f["key"] == "gold" for f in d["forces"])     # nobody measured on gold


def test_the_data_cannot_close_its_script_tag():
    html = xp.explore_page_html([_stock("BAD", "</script><b>x", oil=(1.0, "clear"))],
                                "https://www.x", "https://app.x")
    blob = re.search(r'<script type="application/json" id="xp-data">(.*?)</script>', html, re.S).group(1)
    assert "</script" not in blob
    assert json.loads(blob)["forces"][0]["rows"][0][1] == "</script><b>x"


def test_the_page_states_its_limits():
    html = xp.explore_page_html(STOCKS, "https://www.x", "https://app.x", carry=0.32)
    assert 'max="3"' in html and 'min="-3"' in html
    assert "it is not a forecast" in html and "32% as large the following year" in html
    assert 'href="/evidence"' in html and 'for="xp-force"' in html and 'for="xp-move"' in html


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import seo.main as M
    from tests.test_extra_forces import _one
    from utils import db
    from utils import stock_library as lib

    engine = create_engine(f"sqlite:///{tmp_path / 'x.db'}")
    db.metadata.create_all(engine, tables=[db.stock_measurements, db.stock_exposures,
                                           db.research_results])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    monkeypatch.setattr(M, "_get_engine", lambda: (engine, None, None))
    monkeypatch.setattr(M, "_exposure_cache", {})
    return TestClient(M.app), _one, lib, M


def test_empty_library_is_noindex_and_unlisted(client):
    c, _one, lib, M = client
    r = c.get("/explore")
    assert r.status_code == 200 and 'content="noindex' in r.text
    assert "/explore</loc>" not in c.get("/sitemap.xml").text


def test_served_linked_and_listed_once_there_is_data(client):
    c, _one, lib, M = client
    rep = _one("BANK")
    assert lib.record(rep, "Bank Co")
    M._exposure_cache.clear()
    r = c.get("/explore")
    assert r.status_code == 200 and "noindex" not in r.text and "BANK" in r.text
    assert "/explore</loc>" in c.get("/sitemap.xml").text
    assert 'href="/explore#short_rates"' in c.get("/forces/short_rates").text
    assert 'href="/explore"' in c.get("/forces").text
