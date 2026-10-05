"""Quiz (www/quiz): ten questions a day, "rose, fell, or no clear link".

What must hold: "rose"/"fell" answers come only from Clear readings and "no
clear link" only from readings whose 90% range includes zero, with tentative
ones never asked; everyone gets the same round on a given day; no stock is
asked twice; too thin a library gives a noindex page, not a broken quiz.
"""

from __future__ import annotations

import json
import re
from datetime import date

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import quiz_page as qz
from utils.force_pages import ALL_FORCES

KEYS = [f.key for f in ALL_FORCES]


def _library(n=40):
    out = []
    for i in range(n):
        k1, k2 = KEYS[i % len(KEYS)], KEYS[(i * 7 + 3) % len(KEYS)]
        ev = ("clear", "clear", "indistinct", "tentative")[i % 4]
        v = (1.5 if i % 2 else -1.5) if ev != "indistinct" else 0.2
        out.append(_stock(f"T{i}", f"Co {i}", **{k1: (v, ev), k2: (0.1, "indistinct")}))
    return out


def test_answers_come_only_from_clear_or_zero_including_readings():
    lib = _library()
    lib.append(_stock("TENT", "Tentative Co", oil=(3.0, "tentative")))
    lib.append(_stock("ODD", "Odd Co", gold=(2.0, "indistinct")))   # range 1..3: excludes zero
    rounds = qz.quiz_rounds(lib, date(2026, 10, 5))
    assert len(rounds) == qz.ROUNDS
    assert not any(r[0] in ("TENT", "ODD") for r in rounds)
    by = {s["ticker"]: s for s in lib}
    for t, _, key, *_rest, side in rounds:
        e = by[t]["exposures"][key]
        if side == "none":
            assert e["evidence"] == "indistinct" and e["low"] <= 0 <= e["high"]
        else:
            assert e["evidence"] == "clear" and (e["impact"] > 0) == (side == "up")
    assert sorted(r[8] for r in rounds).count("none") == qz.MIX["none"]


def test_same_round_all_day_a_new_one_tomorrow_and_no_stock_twice():
    lib = _library()
    a = qz.quiz_rounds(lib, date(2026, 10, 5))
    assert a == qz.quiz_rounds(list(reversed(lib)), date(2026, 10, 5))   # order of the library is irrelevant
    assert a != qz.quiz_rounds(lib, date(2026, 10, 6))
    assert len({r[0] for r in a}) == len(a)


def test_the_page_carries_its_round_safely_and_states_its_rules():
    lib = [dict(s, name="</script><b>") for s in _library()]
    html = qz.quiz_page_html(lib, "https://www.x", "https://app.x", date(2026, 10, 5))
    blob = re.search(r'<script type="application/json" id="qz-data">(.*?)</script>', html, re.S).group(1)
    assert "</script" not in blob and len(json.loads(blob)) == qz.ROUNDS
    assert json.loads(blob)[0][1] == "</script><b>"
    assert "Tentative readings are left out" in html and "it is not a forecast" in html
    assert "noindex" not in html


def test_too_few_stocks_is_noindex(client):  # noqa: F811
    c, _one, lib, M = client
    r = c.get("/quiz")
    assert r.status_code == 200 and 'content="noindex' in r.text and 'id="qz-data"' not in r.text
    assert "/quiz</loc>" not in c.get("/sitemap.xml").text


def test_a_reading_that_excludes_zero_is_never_a_no_link_answer():
    pool = qz._pool([_stock("ODD", "Odd Co", gold=(2.0, "indistinct"), oil=(0.2, "indistinct"))])
    assert [r[2] for r in pool["none"]] == ["oil"]


def test_no_stock_is_asked_twice_even_when_each_has_many_readings():
    lib = [_stock(f"S{i}", "", **{k: ((1.0 if j % 2 else -1.0), "clear") if j % 3 else (0.1, "indistinct")
                                  for j, k in enumerate(KEYS)}) for i in range(12)]
    for d in range(1, 15):
        r = qz.quiz_rounds(lib, date(2026, 10, d))
        assert len(r) == qz.ROUNDS and len({x[0] for x in r}) == qz.ROUNDS
