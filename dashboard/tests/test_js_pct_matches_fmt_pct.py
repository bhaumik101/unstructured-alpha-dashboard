"""The public pages' script formats percentages exactly as the server does.

Three copies of a JS formatter once drifted from exposure_pages.fmt_pct and
printed a Clear −0.036% reading as "−0.0%" on the live quiz. Now there is one,
JS_PCT, and it must agree with fmt_pct digit for digit.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess

import pytest

from tests.test_explore_page import STOCKS, _stock
from utils.explore_page import JS_PCT, explore_page_html, stock_whatif_html
from utils.exposure_pages import fmt_pct
from utils.quiz_page import quiz_page_html

VALUES = [0.0, 0.001, -0.004, 0.005, -0.036, 0.04, 0.5, -0.949, 0.95, -0.951, 0.9549, 1.0,
          -1.04, 2.25, -2.35, 0.125, -0.375, 1.15, 0.285, 0.005, 3.45, -9.99, 10.0, 12.345, -100.0]
# Impacts are stored rounded to four decimals, so exact ties are real inputs.
_rng = random.Random(7)
VALUES += [round(_rng.uniform(-12, 12), 4) for _ in range(400)]
VALUES += [round(_rng.choice([-1, 1]) * _rng.randrange(0, 4000) / 1000, 4) for _ in range(100)]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_pct_agrees_with_fmt_pct():
    script = JS_PCT + f"console.log(JSON.stringify({json.dumps(VALUES)}.map(pct)));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30, check=True)
    got = json.loads(out.stdout)
    assert got == [fmt_pct(v) for v in VALUES]


def test_every_page_ships_the_formatter_not_the_placeholder():
    from tests.test_quiz_page import _library
    pages = [explore_page_html(STOCKS, "https://w", "https://a"),
             stock_whatif_html("XOM", _stock("XOM", "Exxon", oil=(2.4, "clear"))),
             quiz_page_html(_library(), "https://w", "https://a")]
    for html in pages:
        assert "/*PCT*/" not in html and html.count("function pct(") == 1
