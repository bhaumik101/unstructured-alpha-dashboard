"""The at-a-glance range chart on stock pages.

What must hold: every core reading is drawn to ONE shared scale (dot, 90%
range, zero line); held-up readings are drawn in colour and the rest hollow
(rc-f); the sector median marker appears only where a median exists; the
chart is decorative beside a table with the same figures; no readings, no
chart.
"""

from __future__ import annotations

import re

from tests.test_explore_page import _stock
from utils.exposure_pages import range_chart_html, stock_page_html


def _rec():
    rec = _stock("XOM", "Exxon", oil=(2.0, "clear"), rates=(-0.5, "indistinct"))
    for e in rec["exposures"].values():
        e["low"], e["high"] = e["impact"] - 1.0, e["impact"] + 1.0
    return rec


def _rows(html):
    return re.findall(r'<div class="rc-row([^"]*)" title="([^"]+)">(.*?)</span></div>', html)


def test_readings_share_one_scale_and_held_up_ones_stand_out():
    rec = _rec()
    html = range_chart_html(rec["exposures"], ["oil", "rates"])
    rows = _rows(html)
    assert [r[1].split(":")[0] for r in rows] == ["Oil and energy", "Interest rates"]
    assert rows[0][0] == "" and rows[1][0] == " rc-f"          # held up vs hollow
    # Span = largest |range end| (3.0) * 1.05 = 3.15: oil's dot at 50 + 50*2/3.15.
    assert 'class="rc-d u" style="left:81.75%"' in rows[0][2]
    assert 'class="rc-d d" style="left:42.06%"' in rows[1][2]
    # The range bar: oil 1.0..3.0 starts at 65.87% and is 31.75% wide.
    assert 'class="rc-r u" style="left:65.87%;width:31.75%"' in rows[0][2]
    assert "+3.2%" in html and "−3.2%" in html                # axis ends
    assert '<div aria-hidden="true">' in html and "Same figures in the table below." in html


def test_the_sector_median_is_marked_only_where_one_exists():
    rec = _rec()
    peers = {"sector": "Energy", "slug": "energy", "medians": {"oil": 1.0}, "peers": 4}
    rows = _rows(range_chart_html(rec["exposures"], ["oil", "rates"], peers))
    assert rows[0][2].count('class="rc-p"') == 1 and 'class="rc-p"' not in rows[1][2]
    assert "Energy median" in range_chart_html(rec["exposures"], ["oil"], peers)
    assert "median" not in range_chart_html(rec["exposures"], ["oil"])


def test_no_readings_no_chart_and_the_page_carries_it():
    assert range_chart_html({}, ["oil"]) == ""
    page = stock_page_html("XOM", _rec(), [], [], "https://www.x", "https://app.x")
    assert page.index('<figure class="card rc">') < page.index('aria-label="Exposure to each economic force"')
