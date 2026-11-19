"""What a ticker without a page gets instead of a bare JSON error.

What must hold:
  * a ticker not on record is still a 404 (never an estimate), but an HTML
    page, noindex, that offers to measure it and lists near matches;
  * an S&P 500 tracker (SPY, VOO...) gets a real, indexable page saying why it
    has no readings -- and the ticker box sends it there, not into the app;
  * a stock whose reading is well behind the library says it is no longer
    being updated; one that is current says nothing.
"""

from __future__ import annotations

from tests.test_exposure_pages import _rec, client  # noqa: F401  (fixture)
from utils import exposure_pages as ep
from utils import ticker_fallback as tf


def test_an_unmeasured_ticker_is_an_html_404_that_offers_to_measure_it(client):  # noqa: F811
    r = client.get("/exposure/ZZZZ")
    assert r.status_code == 404 and r.headers["content-type"].startswith("text/html")
    assert '"detail"' not in r.text
    assert '<meta name="robots" content="noindex, follow">' in r.text
    assert "ZZZZ has not been measured yet" in r.text
    assert "Measure ZZZZ in the app, free" in r.text and "/stock?t=ZZZZ" in r.text
    assert r.text.count("<h1") == 1


def test_a_typo_lists_the_stock_on_record(client):  # noqa: F811
    r = client.get("/exposure/XOMM")
    assert r.status_code == 404 and 'href="/exposure/XOM"' in r.text


def test_near_matches_are_typos_and_prefixes_not_guesses():
    lib = [_rec(t) for t in ("XOM", "XOMA", "BRK-B", "BRK-A", "AAPL", "KO", "KHC")]
    assert [s["ticker"] for s in tf.near_matches("BRK", lib)] == ["BRK-A", "BRK-B"]
    assert [s["ticker"] for s in tf.near_matches("AAPK", lib)] == ["AAPL"]
    assert [s["ticker"] for s in tf.near_matches("XOM", lib)] == ["XOMA"]        # never itself
    assert tf.near_matches("Q", lib) == []


def test_an_index_tracker_gets_a_page_that_says_why_it_has_no_readings(client):  # noqa: F811
    for t in ("SPY", "VOO"):
        r = client.get(f"/exposure/{t}")
        assert r.status_code == 200, t
        assert "noindex" not in r.text
        assert f'/exposure/{t}"' in r.text                                      # its own canonical
        assert "zero by" in r.text and "construction" in r.text
        assert "Typical weekly move" not in r.text                              # no readings table
        assert r.text.count("<h1") == 1
    assert "measured with SPY itself" in client.get("/exposure/SPY").text
    assert "VOO moves almost exactly with it" in client.get("/exposure/VOO").text


def test_the_ticker_box_sends_a_tracker_to_its_page(client):  # noqa: F811
    for t in ("SPY", "voo"):
        r = client.get(f"/go?t={t}", follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == f"/exposure/{t.upper()}"
    r = client.get("/go?t=ZZZZ", follow_redirects=False)
    assert r.headers["location"].endswith("/stock?t=ZZZZ")                     # others still go to the app


def test_a_reading_well_behind_the_library_says_it_is_no_longer_updated():
    assert tf.stale_notice_html("2026-10-02", "2026-11-13").startswith('<p class="caveat"')
    assert "Oct 2, 2026" in tf.stale_notice_html("2026-10-02", "2026-11-13")
    assert tf.stale_notice_html("2026-11-06", "2026-11-13") == ""             # one week behind: fine
    assert tf.stale_notice_html("2026-11-13", "") == ""

    rec = _rec("PSKY", as_of="2026-10-02")
    stale = ep.stock_page_html("PSKY", rec, [rec], [], "https://s", "https://a", library_week="2026-11-13")
    fresh = ep.stock_page_html("PSKY", rec, [rec], [], "https://s", "https://a", library_week="2026-10-02")
    assert "no longer being updated" in stale and "no longer being updated" not in fresh


def test_the_tracker_pages_are_in_the_sitemap(client):  # noqa: F811
    body = client.get("/sitemap.xml").text
    from utils.funds import MARKET_TRACKERS
    for t in MARKET_TRACKERS:
        assert f"/exposure/{t}</loc>" in body
    assert "/exposure/ZZZZ" not in body
