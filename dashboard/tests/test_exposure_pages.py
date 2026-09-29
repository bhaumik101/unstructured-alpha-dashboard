"""Crawlable exposure pages: one server-rendered page per measured stock.

The pages search engines index were /ticker/{SYMBOL}, the retired signal
product's Confluence Score -- the "stock pick" framing the product disclaims.
/exposure/{SYMBOL} is the current product, read from the stock library.

What must hold:
  * only a measured stock has a page; anything else is a 404, never estimated;
  * one URL per stock (lowercase redirects to the canonical);
  * every database string is escaped;
  * a stock is only said to be "exposed to" a force on a reading that held up,
    and stocks that moved the other way are not listed as if they moved with it.
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

from utils import exposure_pages as ep  # noqa: E402


def _exp(ticker, factor, impact, evidence, as_of="2026-09-11"):
    return {"ticker": ticker, "as_of": as_of, "factor": factor, "impact": impact,
            "low": impact - 1.0, "high": impact + 1.0, "t": 2.0, "evidence": evidence}


def _rec(ticker="XOM", name="Exxon Mobil", as_of="2026-09-11", **factors):
    factors = factors or {"oil": (2.7, "clear"), "rates": (-0.04, "indistinct"),
                          "inflation": (0.89, "tentative")}
    return {"ticker": ticker, "as_of": as_of, "name": name, "market_beta": 0.73,
            "r2": 0.4, "n_obs": 156, "window_weeks": 156,
            "exposures": {k: _exp(ticker, k, v, e, as_of) for k, (v, e) in factors.items()}}


# ── the words ───────────────────────────────────────────────────────────────

def test_the_summary_names_what_held_up_and_what_did_not():
    s = ep.summary_sentence("XOM", _rec())
    assert s.startswith("Over the 156 weeks to Sep 11, 2026, XOM has been clearly sensitive to oil")
    assert "tentatively sensitive to inflation expectations" in s
    assert "No measurable link to interest rates." in s
    assert "0.73 times as much as the U.S. stock market" in s


def test_nothing_that_held_up_is_said_plainly():
    s = ep.summary_sentence("KO", _rec("KO", rates=(0.1, "indistinct")))
    assert "shows no clear sensitivity to any of the economic forces" in s
    assert "sensitive to interest" not in s


def test_fmt_pct_matches_the_app():
    from utils import report_ui as ui

    for x in (None, float("nan"), 0.0, 0.004, -0.004, 0.5, -0.5, 0.949, 0.95, 2.7, -12.34):
        assert ep.fmt_pct(x) == ui.fmt_pct(x), x


def test_no_forecast_language_outside_the_caveat():
    html = ep.stock_page_html("XOM", _rec(), [_rec()], [], "https://www.x", "https://app.x")
    text = re.sub(r"<[^>]+>", " ", html).lower()
    for word in ("will ", "expect to", "buy ", "target price", "bullish", "bearish",
                 "confluence"):
        text_wo_caveat = text.replace("recommendation to buy, sell or hold", "")
        assert word not in text_wo_caveat, word


def test_every_database_string_is_escaped():
    bad = '<script>alert(1)</script>'
    rec = _rec(name=bad)
    related = [dict(_exp("A&B", "oil", 1.5, "clear"), name=bad)]
    html = ep.stock_page_html("XOM", rec, [rec, _rec(as_of="2026-09-04")], related,
                              "https://www.x", "https://app.x")
    assert bad not in html and "&lt;script&gt;" in html
    hub = ep.hub_page_html([rec], "https://www.x", "https://app.x")
    assert bad not in hub


def test_json_ld_cannot_close_its_script_tag():
    html = ep.stock_page_html("XOM", _rec(name="</script><b>x"), [], [], "https://www.x", "https://app.x")
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    assert "</" not in ld


# ── related stocks ──────────────────────────────────────────────────────────

def test_the_lead_force_is_one_that_held_up():
    rec = _rec(rates=(-5.0, "indistinct"), oil=(1.2, "tentative"))
    assert ep.lead_factor(rec) == "oil", "a bigger reading that did not hold up is not the lead"
    assert ep.lead_factor(_rec(rates=(-5.0, "indistinct"))) is None


def test_related_stocks_are_split_by_direction():
    related = [dict(_exp("CVX", "oil", 2.1, "clear"), name="Chevron"),
               dict(_exp("MSFT", "oil", -0.8, "clear"), name="Microsoft")]
    html = ep.stock_page_html("XOM", _rec(), [_rec()], related, "https://www.x", "https://app.x")
    up = html.index("Moved up with oil and energy")
    down = html.index("Moved down with oil and energy")
    assert up < html.index("CVX · Chevron") < down < html.index("MSFT · Microsoft")


def test_no_related_section_without_a_reading_that_held_up():
    related = [dict(_exp("CVX", "oil", 2.1, "clear"), name="Chevron")]
    html = ep.stock_page_html("KO", _rec("KO", rates=(0.1, "indistinct")), [], related,
                              "https://www.x", "https://app.x")
    assert "Other stocks exposed" not in html


# ── the history table ───────────────────────────────────────────────────────

def test_an_unmeasured_week_is_a_dash_not_a_zero():
    new = _rec(as_of="2026-09-11")
    old = _rec(as_of="2026-09-04", oil=(2.5, "clear"))   # no inflation or rates that week
    html = ep.stock_page_html("XOM", new, [new, old], [], "https://www.x", "https://app.x")
    assert '<td title="Not measured that week">—</td>' in html
    assert "XOM week by week" in html


def test_one_week_has_no_history_table():
    html = ep.stock_page_html("XOM", _rec(), [_rec()], [], "https://www.x", "https://app.x")
    assert "week by week" not in html


# ── sitemap ─────────────────────────────────────────────────────────────────

def test_sitemap_lists_the_hub_and_each_stock_with_its_own_date():
    urls = ep.sitemap_urls([_rec("XOM", as_of="2026-09-11"), _rec("KO", as_of="2026-09-04"),
                            _rec("<bad>")], "https://www.x")
    joined = "\n".join(urls)
    assert "<loc>https://www.x/exposure</loc><lastmod>2026-09-11</lastmod>" in joined
    assert "<loc>https://www.x/exposure/KO</loc><lastmod>2026-09-04</lastmod>" in joined
    assert "bad" not in joined
    assert len(urls) == 3


# ── the routes ──────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import seo.main as M
    from utils import db
    from utils import stock_library as lib
    from tests.test_exposure import _report

    engine = create_engine(f"sqlite:///{tmp_path / 'seo.db'}")
    db.metadata.create_all(engine, tables=[db.stock_measurements, db.stock_exposures])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    monkeypatch.setattr(M, "_get_engine", lambda: (engine, None, None))
    monkeypatch.setattr(M, "_exposure_cache", {})
    assert lib.record(_report(holdings=[{"ticker": "XOM", "weight_pct": 100}]), "Exxon Mobil")
    return TestClient(M.app)


def test_a_measured_stock_has_a_page(client):
    r = client.get("/exposure/XOM")
    assert r.status_code == 200
    assert "Exxon Mobil (XOM): economic exposure" in r.text
    assert '<link rel="canonical" href="' in r.text and '/exposure/XOM"' in r.text


def test_an_unmeasured_stock_is_a_404_not_an_estimate(client):
    assert client.get("/exposure/ZZZZ").status_code == 404
    assert client.get("/exposure/%3Cscript%3E").status_code == 404


def test_lowercase_redirects_to_the_one_canonical_url(client):
    r = client.get("/exposure/xom", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/exposure/XOM"


def test_the_hub_and_sitemap_list_the_measured_stock(client):
    assert 'href="/exposure/XOM"' in client.get("/exposure").text
    assert "/exposure/XOM</loc>" in client.get("/sitemap.xml").text


# ── the retired /ticker pages ───────────────────────────────────────────────
# They show the old Confluence Score -- the "stock pick" framing the product
# disclaims. A measured stock's old URL moves permanently to its exposure page
# so its ranking carries over; the rest stay reachable but out of the index.

def test_a_measured_stocks_ticker_page_moves_to_its_exposure_page(client):
    r = client.get("/ticker/XOM", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/exposure/XOM"
    r = client.get("/ticker/xom", follow_redirects=False)
    assert r.headers["location"] == "/exposure/XOM"


def test_an_unmeasured_ticker_page_is_kept_out_of_the_index(client, monkeypatch):
    import seo.main as M

    monkeypatch.setattr(M, "_latest_ticker_score", lambda *a: None)
    monkeypatch.setattr(M, "_latest_signal_statuses", lambda *a: {})
    symbol = next(t for t in sorted(M._get_config()[0]) if t != "XOM")
    r = client.get(f"/ticker/{symbol}", follow_redirects=False)
    assert r.status_code == 200
    assert r.headers["x-robots-tag"] == "noindex, follow"
    assert '<meta name="robots" content="noindex, follow">' in r.text


def test_the_sitemap_no_longer_lists_ticker_pages(client):
    xml = client.get("/sitemap.xml").text
    assert "/ticker/" not in xml
    assert "/exposure/XOM</loc>" in xml


def test_a_library_outage_leaves_the_old_pages_up(monkeypatch):
    import seo.main as M

    def down():
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(M, "_exposure_stocks", down)
    assert M._measured("XOM") is False
