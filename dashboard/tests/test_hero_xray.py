"""The landing hero's live Portfolio X-ray.

What must hold: /xray.json serves what the X-ray page embeds and is proxied on
www; the card's starter mixes are /xray's; without the feed the hero shows its
static example, never invented numbers; and its arithmetic (app/blend.ts)
gives the same answers as the rules in utils/xray_page.py -- a weighted
average, a force left out when any holding lacks it, S&P 500 trackers zero.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_explore_page import client  # noqa: F401  (fixture)
from utils import xray_page as xp

WEB = Path(__file__).resolve().parent.parent / "unstructured-alpha-web"
HERO = (WEB / "app" / "HeroXray.tsx").read_text(encoding="utf-8")


def test_the_feed_is_served_cached_and_proxied(client):  # noqa: F811
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank")
    M._exposure_cache.clear()
    r = c.get("/xray.json")
    d = r.json()
    assert r.status_code == 200 and "BANK" in d["s"] and "VOO" in d["mkt"] and len(d["f"]) == 5
    assert "s-maxage" in r.headers["cache-control"]
    assert 'source: "/xray.json"' in (WEB / "next.config.ts").read_text(encoding="utf-8")


def test_the_starter_mixes_are_the_xray_pages():
    hero = re.findall(r'\["([^"]+)", \[([^\]]+)\]\]', HERO)
    assert [(n, " ".join(re.findall(r'"([A-Z]+)"', ts))) for n, ts in hero] == list(xp.PRESETS)


def test_the_hero_is_a_dated_sample_and_the_live_xray_never_invents_numbers():
    """The hero shows a real stored report, dated on screen (2026-11 redesign);
    the live X-ray sits below it, and without its feed it offers a link, not
    figures."""
    assert "if (!feed) return <>{fallback}</>;" in HERO
    page = (WEB / "app" / "page.tsx").read_text(encoding="utf-8")
    hero = page[page.index('<header className="lp-wrap lp-hero">'):page.index("<LiveStats />")]
    assert "<SamplePanel />" in hero
    assert "Sample report · data through {SAMPLE.asOf}" in page and 'asOf: "' in page
    fallback = page[page.index("<HeroXray fallback={"):page.index("/>", page.index("<HeroXray fallback={"))]
    assert 'href="/xray"' in fallback and "%" not in fallback


FEED = {"f": [["rates", "Interest rates", "r"], ["oil", "Oil and energy", "o"]],
        "s": {"AAA": ["A", "", [[-2.0, 1], [1.0, 0]]], "BBB": ["B", "", [[1.0, 0], None]]},
        "mkt": ["VOO"], "as_of": "2026-11-06"}


def _python(holdings):
    out = []
    for i, (key, *_r) in enumerate(FEED["f"]):
        vals = [0.0 if t in FEED["mkt"] else (FEED["s"][t][2][i][0] if FEED["s"][t][2][i] else None) for t in holdings]
        out.append(None if None in vals else round(sum(vals) / len(vals), 6))
    return out


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_the_hero_arithmetic_matches_the_xray_rules(tmp_path):
    runner = tmp_path / "run.ts"
    runner.write_text(
        f"import {{ blend }} from '{(WEB / 'app' / 'blend.ts').as_posix()}';\n"
        f"const feed = {json.dumps(FEED)};\n"
        "const cases = [['AAA', 'BBB'], ['AAA', 'VOO'], ['AAA']];\n"
        "console.log(JSON.stringify(cases.map(h => blend(feed, h).map(r => r.ok ? Math.round(r.value * 1e6) / 1e6 : null))));\n")
    r = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", str(runner)],
                       capture_output=True, text=True)
    if r.returncode and "experimental-strip-types" in r.stderr:
        pytest.skip("this node cannot run TypeScript directly")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got == [_python(["AAA", "BBB"]), _python(["AAA", "VOO"]), _python(["AAA"])]
    assert got[0] == [-0.5, None] and got[1] == [-1.0, 0.5]       # BBB lacks oil; VOO counts zero
