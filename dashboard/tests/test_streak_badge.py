"""The streak badge in the bar: a returning learner sees their streak and level
on every public page, linking back to their path. A visitor who has not played
sees nothing -- an empty "0" badge would be noise, not a nudge.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from utils import exposure_pages as ep
from utils.progress import progress_js


def test_every_page_carries_the_badge_hidden_until_there_is_progress():
    page = ep._shell("T", "D", "https://www.x/learn", {}, "<h1>T</h1>", "https://app.x")
    assert '<a class="me" id="ua-me" href="/learn#path" hidden></a>' in page
    assert page.index("window.UAP = window.UAP ||") < page.index("getElementById('ua-me')")


def _run(progress):
    js = ("var store = {%s}; global.window = global;"
          "global.localStorage = {getItem: k => k in store ? store[k] : null, setItem: (k, v) => { store[k] = v; }};"
          "var el = {hidden: true, innerHTML: '', attrs: {}, setAttribute(k, v){ this.attrs[k] = v; }};"
          "global.document = {getElementById: id => id === 'ua-me' ? el : null};"
          % (f"'ua_progress_v1': {json.dumps(json.dumps(progress))}" if progress is not None else "")
          + progress_js() + ep._ME_JS
          + "process.stdout.write(JSON.stringify({hidden: el.hidden, html: el.innerHTML, label: el.attrs['aria-label'] || ''}));")
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30, check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_it_shows_the_streak_for_a_learner_and_nothing_for_a_newcomer():
    assert _run(None)["hidden"] is True
    assert _run({"d": {}, "l": {}})["hidden"] is True
    from datetime import date
    today = date.today().isoformat()
    out = _run({"d": {today: {"quiz": [7, 10]}}, "l": {"quiz": 1}})
    assert out["hidden"] is False and "1-day streak" in out["html"] and "Reader" in out["label"]
    out = _run({"d": {}, "l": {"learn": 1}})                      # path progress, no games yet
    assert out["hidden"] is False and "Level 1" in out["html"]


def test_links_in_the_header_band_are_light_on_navy():
    """Live check, Nov 19: tile links (a force page's largest movers and most
    linked sector) kept the body's dark blue on the navy band."""
    import re
    m = re.search(r"\.card\.sh a:not\(\.btn\)\{color:#([0-9a-f]{6})", ep._SH_CSS)
    assert m, "the band's links have no colour of their own"
    # Light on the near-black band (2026-11 brand: #8eebdc): every channel bright.
    assert all(int(m.group(1)[i:i + 2], 16) >= 0x80 for i in (0, 2, 4)), m.group(1)
