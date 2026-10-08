"""The dot strip on force pages: every stock on record on one force.

What must hold: every stock with a reading is a dot, and no two dots
overlap; a dot's position follows its value on a symmetric scale, so the
zero line is the centre; held-up readings are coloured by direction and the
rest hollow; dots shrink as the library grows so the strip stays a strip;
fewer than two readings, no strip.
"""

from __future__ import annotations

import random
import re

from tests.test_explore_page import _stock
from utils import force_pages as fp


def test_no_two_dots_overlap_and_x_follows_the_value():
    random.seed(7)
    vals = [random.gauss(0, 1) for _ in range(300)] + [0.0] * 40      # a pile-up at zero
    r = 3.0
    pts = fp.swarm_layout(vals, span=4.0, r=r)
    assert len(pts) == len(vals)
    d = 2 * r + fp.SWARM_GAP
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            (x1, y1), (x2, y2) = pts[i], pts[j]
            assert (x1 - x2) ** 2 + (y1 - y2) ** 2 >= (d - 0.15) ** 2     # rounding to 0.1
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    xs = [pts[i][0] for i in order]
    assert xs == sorted(xs)
    assert pts[-1][0] == fp.SWARM_W / 2                               # zero sits on the centre line


def test_the_scale_is_symmetric_about_zero():
    pts = fp.swarm_layout([-2.0, 2.0, 1.0], span=2.0, r=4.5)
    half = fp.SWARM_W / 2 - 4.5
    assert pts[0] == (round(fp.SWARM_W / 2 - half, 1), 0.0)
    assert pts[1] == (round(fp.SWARM_W / 2 + half, 1), 0.0)
    assert pts[2][0] == round(fp.SWARM_W / 2 + half / 2, 1)


def test_each_dot_says_what_it_is_and_held_up_ones_are_coloured():
    stocks = [_stock("XOM", "Exxon", oil=(2.4, "clear")), _stock("DAL", "Delta", oil=(-1.9, "tentative")),
              _stock("AAPL", "Apple", oil=(0.1, "indistinct")), _stock("MSFT", "Microsoft")]
    html = fp.swarm_html("oil", stocks)
    dots = dict(re.findall(r'<circle class="(fs-[udn])"[^>]*data-t="([A-Z]+)"', html)[i][::-1]
                for i in range(3))
    assert dots == {"XOM": "fs-u", "DAL": "fs-d", "AAPL": "fs-n"}          # MSFT not measured: no dot
    assert 'data-say="XOM · Exxon: +2.4% (clear)"' in html
    assert "Could not be told apart from zero (1)" in html
    assert "−2.5%" in html and "+2.5%" in html                            # 2.4 * 1.05, symmetric


def test_dots_shrink_as_the_library_grows():
    few = fp.swarm_html("oil", [_stock(f"T{i}", "", oil=(i / 10, "indistinct")) for i in range(100)])
    many = fp.swarm_html("oil", [_stock(f"T{i}", "", oil=(i / 100, "indistinct")) for i in range(500)])
    rf = float(re.search(r' r="([\d.]+)" data-t', few).group(1))
    rm = float(re.search(r' r="([\d.]+)" data-t', many).group(1))
    assert rf == fp.SWARM_R and rm < rf


def test_too_few_readings_no_strip_and_the_page_carries_it():
    assert fp.swarm_html("oil", [_stock("XOM", "Exxon", oil=(2.4, "clear"))]) == ""
    stocks = [_stock("XOM", "Exxon", oil=(2.4, "clear")), _stock("DAL", "Delta", oil=(-1.9, "tentative"))]
    page = fp.force_page_html("oil", stocks, "https://www.x", "https://app.x")
    assert page.index('<figure class="card fs" id="fs">') < page.index("<h2>Moved up with")
