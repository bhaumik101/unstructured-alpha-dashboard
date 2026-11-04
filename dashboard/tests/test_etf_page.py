"""/etfs: widely held funds by kind, against the five core forces.

What must hold: funds are grouped by their category in cron/etfs.csv, bonds
first; a group's takeaway names only a reading that held up, the largest; a
group with none says so; stocks that are not funds are not listed; no funds
means a noindex page; the route is served, listed and proxied on www.
"""

from __future__ import annotations

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import etf_page as ep

B, A = "https://www.x", "https://app.x"
STOCKS = [_stock("TLT", "iShares 20+ Year Treasury Bond ETF", rates=(-3.9, "clear"), oil=(0.2, "indistinct")),
          _stock("SHY", "iShares 1-3 Year Treasury Bond ETF", rates=(-0.4, "tentative")),
          _stock("XLE", "Energy Select Sector SPDR Fund", oil=(2.1, "clear"), rates=(9.9, "indistinct")),
          _stock("GLD", "SPDR Gold Shares", oil=(0.1, "indistinct")),
          _stock("XOM", "Exxon Mobil", oil=(2.4, "clear"))]


def test_funds_are_grouped_bonds_first_and_stocks_are_left_out():
    html = ep.etfs_page_html(STOCKS, B, A)
    assert html.index('id="bonds"') < html.index('id="sector"') < html.index('id="commodities"')
    assert "/exposure/TLT" in html and "/exposure/XOM" not in html


def test_the_takeaway_is_the_largest_reading_that_held_up():
    bonds = [s for s in STOCKS if s["ticker"] in ("TLT", "SHY")]
    t = ep.takeaway(bonds)
    assert "/exposure/TLT" in t and "−3.9%" in t
    # XLE's +9.9% rates reading did not hold up: the takeaway is its oil reading.
    assert "+2.1%" in ep.takeaway([STOCKS[2]]) and "9.9" not in ep.takeaway([STOCKS[2]])
    assert ep.takeaway([STOCKS[3]]) is None
    assert "No reading in this group held up." in ep.etfs_page_html(STOCKS, B, A)


def test_no_funds_is_a_noindex_page():
    html = ep.etfs_page_html([STOCKS[-1]], B, A)
    assert 'content="noindex' in html


def test_served_listed_and_measured(client, monkeypatch):  # noqa: F811
    from utils import funds
    c, _one, lib, M = client
    fake = {"BANK": ("A bond fund", "Bonds")}               # a ticker the synthetic world has prices for
    monkeypatch.setattr(funds, "funds", lambda: fake)
    monkeypatch.setattr(ep, "funds", lambda: fake)
    assert lib.record(_one("BANK"), "A bond fund")
    M._exposure_cache.clear()
    r = c.get("/etfs")
    assert r.status_code == 200 and "/exposure/BANK" in r.text and 'page:"ETFs"' in r.text
    assert "/etfs</loc>" in c.get("/sitemap.xml").text
