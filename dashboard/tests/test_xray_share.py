"""A shared Portfolio X-ray previews as itself.

What must hold:
  * the share link carries the mix in ?p= (crawlers never see a #fragment),
    and old #p= links still open;
  * only tickers on record are read from ?p=; nothing else is echoed;
  * the blend matches the page's and the landing hero's arithmetic;
  * a shared mix gets its own title, description and card, with the
    canonical left on /xray;
  * the card is a real 1200x630 PNG; a mix of nothing on record is a 404.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_explore_page import client  # noqa: F401  (fixture)
from tests.test_hero_xray import FEED, WEB
from utils import xray_page as xp
from utils import xray_share as xs


def test_only_tickers_on_record_are_read_and_weights_normalise():
    assert xs.parse_mix("aaa,BBB", FEED) == [("AAA", 0.5), ("BBB", 0.5)]
    assert xs.parse_mix("AAA:75,BBB:25", FEED) == [("AAA", 0.75), ("BBB", 0.25)]
    assert xs.parse_mix("AAA:30,BBB", FEED) == [("AAA", 0.75), ("BBB", 0.25)]     # missing weight -> 10
    mix = xs.parse_mix("AAA:-1,BBB:nan,<script>,ZZZ,AAA:5,VOO:1", FEED)     # bad entries dropped, not fatal
    assert [(t, round(w, 4)) for t, w in mix] == [("AAA", 0.8333), ("VOO", 0.1667)]
    assert xs.parse_mix("", FEED) == [] and xs.parse_mix("ZZZ", FEED) == []
    many = {"s": {f"T{i}": ["", "", [[1.0, 1]]] for i in range(40)}, "mkt": [], "f": FEED["f"][:1]}
    assert len(xs.parse_mix(",".join(many["s"]), many)) == xp.MAX_HOLDINGS


def test_the_blend_follows_the_xray_rules():
    rows = xs.blend(FEED, [("AAA", 0.5), ("VOO", 0.5)])
    assert [r["ok"] for r in rows] == [True, True]
    assert [round(r["value"], 6) for r in rows] == [-1.0, 0.5]                    # VOO counts zero
    rows = xs.blend(FEED, [("AAA", 0.5), ("BBB", 0.5)])
    assert rows[1]["ok"] is False and xs.biggest(rows)["key"] == FEED["f"][0][0]  # BBB lacks the 2nd force
    rows = xs.blend(FEED, [("AAA", 0.75), ("BBB", 0.25)])
    assert round(rows[0]["value"], 6) == -1.25                                     # weights, not equal


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_equal_weights_match_the_landing_heros_blend(tmp_path):
    runner = tmp_path / "run.ts"
    runner.write_text(
        f"import {{ blend }} from '{(WEB / 'app' / 'blend.ts').as_posix()}';\n"
        f"const feed = {json.dumps(FEED)};\n"
        "console.log(JSON.stringify([['AAA','BBB'],['AAA','VOO']].map(h => blend(feed, h).map(r => r.ok ? Math.round(r.value*1e6)/1e6 : null))));\n")
    r = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", str(runner)],
                       capture_output=True, text=True)
    if r.returncode and "experimental-strip-types" in r.stderr:
        pytest.skip("this node cannot run TypeScript directly")
    ours = [[round(x["value"], 6) if x["ok"] else None for x in xs.blend(FEED, xs.parse_mix(",".join(h), FEED))]
            for h in (["AAA", "BBB"], ["AAA", "VOO"])]
    assert json.loads(r.stdout) == ours


def test_the_page_shares_with_a_query_and_still_opens_old_links():
    html = xp.xray_page_html([], "https://www.x", "https://app.x")
    assert "'?p=' + h" in html and "'#p=' + h" not in html
    assert "location.search" in html and "#p=" in html                            # old links still open


def _seed(client):
    c, _one, lib, M = client
    for t, name in (("BANK", "Bank Co"), ("PLAIN", "Plain Co")):
        assert lib.record(_one(t), name)
    M._exposure_cache.clear()
    return c


def test_a_shared_mix_gets_its_own_title_and_card(client):  # noqa: F811
    c = _seed(client)
    plain = c.get("/xray").text
    shared = c.get("/xray?p=BANK:60,PLAIN:40,<b>,NOPE").text
    assert "Portfolio X-ray: BANK, PLAIN" in shared and "Portfolio X-ray: BANK, PLAIN" not in plain
    assert "biggest driver" in shared
    assert '<link rel="canonical" href="https://' in shared and '/xray">' in shared   # canonical unchanged
    assert 'og:image" content="' in shared and "/xray/og.png?p=BANK:60,PLAIN:40" in shared
    assert "<b>" not in shared.split("<body")[0] and "NOPE" not in shared            # nothing echoed


def test_the_card_is_a_png_and_nonsense_is_a_404(client):  # noqa: F811
    c = _seed(client)
    r = c.get("/xray/og.png?p=BANK:60,PLAIN:40")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = int.from_bytes(r.content[16:20], "big"), int.from_bytes(r.content[20:24], "big")
    assert (w, h) == (1200, 630)
    assert "max-age=86400" in r.headers["cache-control"]
    assert c.get("/xray/og.png?p=NOPE").status_code == 404
    assert c.get("/xray/og.png").status_code == 404


def test_www_proxies_the_card():
    cfg = (WEB / "next.config.ts").read_text()
    assert 'source: "/xray/og.png"' in cfg
