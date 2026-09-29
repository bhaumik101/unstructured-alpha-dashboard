"""One crawlable page per economic force: which stocks on record moved with it.

What must hold:
  * only readings that held up are ranked, and the count with no measurable
    link is stated, not hidden;
  * each side is sorted largest first, and a long list says it is cut;
  * a force nobody has a reading on yet is noindex and left out of the sitemap;
  * unknown keys are a 404, and there is one URL per force;
  * every database string is escaped, and nothing reads as a forecast.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import exposure as ex  # noqa: E402
from utils import force_pages as fp  # noqa: E402

B, A = "https://www.x", "https://app.x"


def _stock(ticker, name="", as_of="2026-09-11", **readings):
    return {"ticker": ticker, "name": name, "as_of": as_of,
            "exposures": {k: {"factor": k, "impact": v, "low": v - 1, "high": v + 1, "t": 3.0,
                              "evidence": e, "as_of": as_of}
                          for k, (v, e) in readings.items()}}


STOCKS = [
    _stock("XOM", "Exxon Mobil", oil=(2.7, "clear")),
    _stock("CVX", "Chevron", oil=(2.1, "tentative")),
    _stock("DAL", "Delta Air Lines", oil=(-1.9, "clear")),
    _stock("MSFT", "Microsoft", oil=(0.1, "indistinct")),
    _stock("AAPL", "Apple"),                                  # no oil reading at all
]


def test_stats_sort_into_up_down_and_no_link():
    st = fp.force_stats("oil", STOCKS)
    assert st["measured"] == 4 and st["none"] == 1
    assert [r["ticker"] for r in st["up"]] == ["XOM", "CVX"]
    assert [r["ticker"] for r in st["down"]] == ["DAL"]


def test_the_page_ranks_only_what_held_up_and_says_how_many_did_not():
    html = fp.force_page_html("oil", STOCKS, B, A)
    assert "Of 4 stocks on record, 2 moved up with oil and energy" in html
    assert "1 moved down with it. The other 1 showed no link" in html
    assert 'href="/exposure/XOM"' in html and 'href="/exposure/DAL"' in html
    assert 'href="/exposure/MSFT"' not in html, "a reading indistinguishable from zero was ranked"
    assert html.index("XOM") < html.index("CVX"), "largest first"


def test_a_long_side_says_it_was_cut():
    many = [_stock(f"S{i:03d}", oil=(1 + i / 100, "clear")) for i in range(40)]
    html = fp.force_page_html("oil", many, B, A, limit=25)
    assert "Showing the 25 largest of 40." in html
    assert "S039" in html and "S000" not in html


def test_a_force_with_no_readings_is_noindex_and_not_in_the_sitemap():
    html = fp.force_page_html("bitcoin", STOCKS, B, A)
    assert '<meta name="robots" content="noindex, follow">' in html
    assert "No stock on record has a reading on bitcoin yet" in html
    urls = "\n".join(fp.force_sitemap_urls(STOCKS, B))
    assert "/forces/bitcoin<" not in urls
    assert "<loc>https://www.x/forces/oil</loc><lastmod>2026-09-11</lastmod>" in urls
    assert "<loc>https://www.x/forces</loc>" in urls


def test_a_measured_force_is_indexable():
    assert "noindex" not in fp.force_page_html("oil", STOCKS, B, A)


def test_unknown_force_is_none():
    assert fp.force_page_html("astrology", STOCKS, B, A) is None


def test_the_hub_lists_every_force_in_its_group():
    html = fp.forces_hub_html(STOCKS, B, A)
    for f in fp.ALL_FORCES:
        assert f'href="/forces/{f.key}"' in html, f.key
    for label in fp.GROUP_LABELS.values():
        assert f"<h2>{label}</h2>" in html
    assert "3 of 4 stocks with a link that held up" in html


def test_extra_forces_state_their_stricter_bar_and_what_they_are_measured_beyond():
    html = fp.force_page_html("gold", [_stock("NEM", "Newmont", gold=(3.0, "clear"))], B, A)
    assert f"Clear needs |t| ≥ {ex.EXTRA_CLEAR_T:.2f}" in html
    assert "the five core forces" in html
    core = fp.force_page_html("oil", STOCKS, B, A)
    assert f"Clear needs |t| ≥ {ex.CLEAR_T:.2f}, shared across the five core forces" in core
    assert "shared across every force tested" in html and "every force tested" not in core


def test_database_strings_are_escaped():
    bad = "<script>alert(1)</script>"
    html = fp.force_page_html("oil", [_stock("XOM", bad, oil=(2.0, "clear"))], B, A)
    assert bad not in html and "&lt;script&gt;" in html


def test_nothing_reads_as_a_forecast_or_a_pick():
    html = fp.force_page_html("oil", STOCKS, B, A) + fp.forces_hub_html(STOCKS, B, A)
    text = re.sub(r"<[^>]+>", " ", html).lower().replace("recommendation to buy, sell or hold", "")
    for word in ("will rise", "will fall", "buy ", "sell ", "bullish", "bearish", "target price"):
        assert word not in text, word


def test_stock_pages_link_each_force_to_its_page():
    from utils import exposure_pages as ep

    rec = STOCKS[0]
    html = ep.stock_page_html("XOM", rec, [rec], [], B, A)
    assert '<a href="/forces/oil">Oil and energy</a>' in html


# ── the routes ──────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import seo.main as M
    from tests.test_extra_forces import _one
    from utils import db
    from utils import stock_library as lib

    engine = create_engine(f"sqlite:///{tmp_path / 'f.db'}")
    db.metadata.create_all(engine, tables=[db.stock_measurements, db.stock_exposures])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    monkeypatch.setattr(M, "_get_engine", lambda: (engine, None, None))
    monkeypatch.setattr(M, "_exposure_cache", {})
    assert lib.record(_one("BANK"), "Bank Co")
    return TestClient(M.app)


def test_a_force_page_is_served_from_the_library(client):
    r = client.get("/forces/short_rates")
    assert r.status_code == 200 and 'href="/exposure/BANK"' in r.text
    assert client.get("/forces").status_code == 200


def test_unknown_force_is_a_404_and_case_redirects(client):
    assert client.get("/forces/astrology").status_code == 404
    r = client.get("/forces/OIL", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/forces/oil"


def test_the_sitemap_lists_force_pages(client):
    xml = client.get("/sitemap.xml").text
    assert "/forces</loc>" in xml and "/forces/short_rates</loc>" in xml
