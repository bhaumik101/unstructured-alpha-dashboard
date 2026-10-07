"""Share previews: every public page carries a 1200x630 og:image, and a stock
page carries its own, drawn from its stored readings.

What must hold: the image is a real 1200x630 PNG; a reading that held up is
drawn bright and one that did not is dimmed; the route redirects lower case,
404s the unmeasured and non-tickers, caches by stock and week, and tells
crawlers to keep it for a day; pages without their own image fall back to
the site's.
"""

from __future__ import annotations

import io

from PIL import Image

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import og_image as og
from utils.exposure_pages import hub_page_html, stock_page_html

REC = _stock("XOM", "Exxon Mobil", oil=(2.4, "clear"), rates=(-2.4, "indistinct"))


def _png(b: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(b))
    im.load()
    return im.convert("RGB")


def test_the_image_is_a_1200_by_630_png():
    im = Image.open(io.BytesIO(og.stock_og_png("XOM", REC)))
    assert im.format == "PNG" and im.size == (og.W, og.H)


def test_a_held_up_bar_is_bright_and_one_that_did_not_is_dim():
    im = _png(og.stock_og_png("XOM", REC))
    hexcol = lambda xy: "#%02x%02x%02x" % im.getpixel(xy)   # noqa: E731
    # Bars sit on rows 0 (rates) and 3 (oil); both are the largest move, so full half-width.
    rates_y, oil_y = 262 + 0 * 58 + 26, 262 + 3 * 58 + 26
    assert hexcol((700, rates_y)) == og.DOWN_FAINT        # indistinct, down: faint
    assert hexcol((860, oil_y)) == og.UP                  # clear, up: bright


def test_every_page_has_a_large_preview_and_stock_pages_have_their_own():
    stock = stock_page_html("XOM", REC, [], [], "https://www.x", "https://app.x")
    assert '<meta property="og:image" content="https://www.x/og/XOM.png">' in stock
    assert '<meta name="twitter:card" content="summary_large_image">' in stock
    hub = hub_page_html([REC], "https://www.x", "https://app.x")
    assert '<meta property="og:image" content="https://www.x/og-image.png">' in hub


def test_the_route(client):  # noqa: F811
    c, _one, lib, M = client
    M._og_cache.clear()
    assert c.get("/og/BANK.png").status_code == 404
    assert lib.record(_one("BANK"), "Bank Co")
    r = c.get("/og/BANK.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "public, max-age=86400"
    assert _png(r.content).size == (1200, 630)
    assert len(M._og_cache) == 1 and c.get("/og/BANK.png").content == r.content
    r = c.get("/og/bank.png", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/og/BANK.png"
    assert c.get("/og/BANK.jpg").status_code == 404
    assert c.get("/og/%3Cx%3E.png").status_code == 404
