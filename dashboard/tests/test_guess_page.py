"""Whose fingerprint? (www/guess): match a mystery stock's profile, daily.

What must hold: every mystery stock is measured on all five core forces with
at least two readings that held up; the profile shown is exactly its
readings; decoys come from the farther half of profiles; no stock appears
twice in a day; the rounds are the same all day and change by day; a small
library gives no game (noindex); route and sitemap know the page.
"""

from __future__ import annotations

import random
from datetime import date

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import exposure as ex
from utils import guess_page as gp

KEYS = [f.key for f in ex.FACTORS]


def _library(n=40, seed=3):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        readings = {}
        for k in KEYS:
            v = round(rng.gauss(0, 1.5), 2)
            readings[k] = (v, "clear" if abs(v) > 1.2 else "indistinct")
        out.append(_stock(f"S{i:02d}", f"Stock {i}", **readings))
    out.append(_stock("PART", "Partly measured", oil=(3.0, "clear"), rates=(-2.0, "clear")))
    return out


def test_mystery_stocks_are_fully_measured_and_distinctive_and_shown_as_measured():
    lib = _library()
    by = {s["ticker"]: s for s in lib}
    rounds = gp.guess_rounds(lib, date(2026, 10, 12))
    assert len(rounds) == gp.ROUNDS
    for r in rounds:
        ans = by[r["choices"][r["answer"]][0]]
        assert ans["ticker"] != "PART"
        exps = ans["exposures"]
        assert sum(1 for k in KEYS if exps[k]["evidence"] in ("clear", "tentative")) >= gp.MIN_HELD
        assert [p[0] for p in r["profile"]] == [f.label for f in ex.FACTORS]
        assert [p[1] for p in r["profile"]] == [round(exps[k]["impact"], 3) for k in KEYS]
        assert [p[4] for p in r["profile"]] == [1 if exps[k]["evidence"] in ("clear", "tentative") else 0 for k in KEYS]
        assert len(r["choices"]) == gp.CHOICES


def test_decoys_are_far_and_no_stock_repeats_in_a_day():
    lib = _library()
    by = {s["ticker"]: s for s in lib}
    rounds = gp.guess_rounds(lib, date(2026, 10, 12))
    seen = [c[0] for r in rounds for c in r["choices"]]
    assert len(seen) == len(set(seen)) and "PART" not in seen
    everyone = gp._everyone(lib)
    spread = {}
    for k in KEYS:
        xs = [s["exposures"][k]["impact"] for s in everyone]
        m = sum(xs) / len(xs)
        spread[k] = (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5

    def d(a, b):
        return sum(((a["exposures"][k]["impact"] - b["exposures"][k]["impact"]) / spread[k]) ** 2 for k in KEYS) ** 0.5
    for r in rounds:
        ans = by[r["choices"][r["answer"]][0]]
        all_d = sorted(d(ans, s) for s in everyone if s is not ans)
        median = all_d[len(all_d) // 2 - 1]
        for c in r["choices"]:
            if c[0] != ans["ticker"]:
                assert d(ans, by[c[0]]) >= median


def test_same_all_day_different_next_day():
    lib = _library()
    a = gp.guess_rounds(lib, date(2026, 10, 12))
    assert gp.guess_rounds(lib, date(2026, 10, 12)) == a
    assert gp.guess_rounds(lib, date(2026, 10, 13)) != a


def test_a_small_library_gives_no_game():
    small = _library(n=8)
    assert gp.guess_rounds(small, date(2026, 10, 12)) == []
    html = gp.guess_page_html(small, "https://www.x", "https://app.x", date(2026, 10, 12))
    assert "noindex" in html and "Not enough stocks" in html
    full = gp.guess_page_html(_library(), "https://www.x", "https://app.x", date(2026, 10, 12))
    assert "noindex" not in full and 'id="gs-data"' in full and "/*PCT*/" not in full


def test_route_and_sitemap(client):  # noqa: F811
    c, *_ = client
    r = c.get("/guess")
    assert r.status_code == 200 and "Whose fingerprint?" in r.text
    assert "/guess</loc>" in c.get("/sitemap.xml").text or "noindex" in r.text


def test_only_distinctive_profiles_are_ever_the_answer():
    flat = [_stock(f"F{i:02d}", "", **{k: (0.1 * (i + j), "indistinct") for j, k in enumerate(KEYS)})
            for i in range(30)]
    one = [_stock(f"O{i}", "", **{k: ((2.0 if j == 0 else 0.1), "clear" if j == 0 else "indistinct")
                                  for j, k in enumerate(KEYS)}) for i in range(15)]
    sharp = [_stock(f"Q{i}", "", **{k: ((2.0 + i if j < 2 else 0.1), "clear" if j < 2 else "indistinct")
                                    for j, k in enumerate(KEYS)}) for i in range(5)]
    rounds = gp.guess_rounds(flat + one + sharp, date(2026, 10, 12))
    assert sorted(r["choices"][r["answer"]][0] for r in rounds) == [f"Q{i}" for i in range(5)]
