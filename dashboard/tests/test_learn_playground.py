"""The label playground on /learn: drag a figure and its range, see its label.

What must hold: the page's label rule is the engine's (evidence_for), at the
engine's thresholds, across a grid that includes values on both sides of each
threshold; the explanation follows the label; the server-rendered starting
state is the one the script computes.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from utils import exposure as ex
from utils import learn_page as lp


def _grid():
    ms = [round(-3 + 0.1 * i, 1) for i in range(61)]
    hs = [round(0.2 + 0.1 * i, 1) for i in range(29)]
    return [(m, h) for m in ms for h in hs]


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_the_page_labels_exactly_as_the_engine_does():
    grid = _grid()
    js = (f"var Z90 = {ex.Z90!r}, CLEAR = {ex.CLEAR_T!r};" + lp.LABEL_JS
          + f"\nconsole.log(JSON.stringify({json.dumps(grid)}.map(function(p){{ return label(p[0], p[1])[0]; }})))")
    got = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    want = [ex.evidence_for(m / (h / ex.Z90), ex.MIN_WEEKS) for m, h in grid]
    assert got == want
    assert {"clear", "tentative", "indistinct"} <= set(want)          # the grid crosses both thresholds


def test_the_script_uses_the_engine_thresholds_and_the_label_drives_the_text():
    html = lp.learn_page_html("https://www.x", "https://app.x")
    assert f"var Z90 = {ex.Z90!r}, CLEAR = {ex.CLEAR_T!r}" in html
    assert "var crosses = r[0] === 'indistinct';" in html
    assert "/*LABEL*/" not in html and "__Z90__" not in html


def test_the_starting_state_matches_the_rule():
    m, h = 1.6, 1.2
    assert ex.evidence_for(m / (h / ex.Z90), ex.MIN_WEEKS) == "tentative"
    html = lp.learn_page_html("https://www.x", "https://app.x")
    assert 'value="1.6"' in html and 'value="1.2"' in html
    assert 'id="lp-chip" class="chip chip-tentative">Tentative' in html
    assert f"|t| = {m / (h / ex.Z90):.2f}" in html
