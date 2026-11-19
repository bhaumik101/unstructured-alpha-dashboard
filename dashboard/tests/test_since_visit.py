""""Since your last visit": changes in the stocks a visitor looked at.

What must hold:
  * a stock that did not change never shows as changed -- the stock page
    remembers readings in exactly the feed's encoding;
  * a link that started holding up, one that stopped, and a held reading that
    moved MOVE points or more are changes; noise in a reading that never held
    up, and smaller moves, are not;
  * "mark all as seen" clears them; a stock saved to My list without being
    opened is adopted at today's readings, never overwriting a real baseline;
  * the module loads before page bodies use it, every stock page remembers,
    and My list carries the panel after its data.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from tests.test_exposure_pages import _rec
from utils import since_visit as sv
from utils.list_page import list_data

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

F = [["rates", "Interest rates", "x"], ["inflation", "Inflation expectations", "x"], ["dollar", "U.S. dollar", "x"],
     ["oil", "Oil and energy", "x"], ["credit", "Credit spreads", "x"]]


def _feed(rows, as_of="2026-11-13"):
    return {"f": F, "s": {t: [t + " Inc", "", r] for t, r in rows.items()}, "as_of": as_of}


def _run(steps: str) -> dict:
    js = ("var store = {}; global.window = global;"
          "global.localStorage = {getItem: k => k in store ? store[k] : null, setItem: (k, v) => { store[k] = String(v); }};"
          + sv.since_js() + "var out = {};" + steps + "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=30, check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_a_stock_page_remembers_in_the_feeds_exact_encoding():
    rec = _rec("AAPL", name="Apple", as_of="2026-11-13")
    for i, e in enumerate((rec.get("exposures") or {}).values()):    # real readings carry full precision
        e["impact"] = 1.234567 + i / 7
    args = sv.remember_script("AAPL", rec).split("apply(null,")[1].split(");}catch")[0]
    feed = list_data([dict(rec, ticker="AAPL")])
    assert json.loads(args)[1] == feed["s"]["AAPL"][2]               # stored exactly as the feed encodes it
    out = _run(f"UAS.remember.apply(null, {args}); out.diff = UAS.diff({json.dumps(feed)}); out.n = UAS.count();")
    assert out == {"diff": [], "n": 1}


@needs_node
def test_what_counts_as_a_change():
    was = {"AAA": [[1.0, 0], [2.0, 1], [-1.5, 1], [0.3, 0], [1.0, 1]]}
    now = {"AAA": [[1.6, 1], [2.1, 0], [-2.2, 1], [0.95, 0], [1.3, 1]]}
    out = _run(f"var w = {json.dumps(_feed(was, '2026-11-06'))}, n = {json.dumps(_feed(now))};"
               "UAS.markSeen(w); UAS.adopt('AAA', w); UAS.remember('AAA', w.s.AAA[2], '2026-11-06');"
               "out.diff = UAS.diff(n).map(c => [c.label, c.kind]);"
               "out.text = UAS.diff(n).map(c => UAS.sentence(c));"
               "UAS.markSeen(n); out.after = UAS.diff(n);")
    assert out["diff"] == [["Interest rates", "gained"], ["Inflation expectations", "lost"],
                           ["U.S. dollar", "moved"]]          # oil: never held; credit: +0.3 < MOVE
    assert out["text"][0] == "now has a link to interest rates that holds up (+1.6%)"
    assert out["text"][1] == "its link to inflation expectations no longer holds up (was +2.0%)"
    assert out["after"] == []


@needs_node
def test_a_saved_stock_is_adopted_but_never_overwrites_what_was_seen():
    a = _feed({"AAA": [[1.0, 1], None, None, None, None]})
    b = _feed({"AAA": [[0.0, 0], None, None, None, None]})
    out = _run(f"UAS.adopt('AAA', {json.dumps(a)}); UAS.adopt('AAA', {json.dumps(b)});"
               f"out.diff = UAS.diff({json.dumps(b)}).map(c => c.kind); UAS.adopt('ZZZ', {json.dumps(b)}); out.n = UAS.count();")
    assert out == {"diff": ["lost"], "n": 1}                   # first baseline kept; unknown tickers ignored


@needs_node
def test_a_corrupt_store_is_a_fresh_start():
    out = _run("store[UAS._key] = '[1,2]'; out.n = UAS.count(); store[UAS._key] = '{bad'; out.m = UAS.count();")
    assert out == {"n": 0, "m": 0}


def test_wired_into_every_page_the_stock_pages_and_my_list():
    from utils import exposure_pages as ep
    from utils.list_page import list_page_html
    page = ep._shell("T", "D", "https://www.x/learn", {}, "<h1>T</h1>", "https://app.x")
    assert page.index("window.UAS = window.UAS ||") < page.index('<main id="main">')   # before any page body
    assert "fetch('/xray.json')" in page and ".since{position:fixed" in page
    rec = _rec("XOM", name="Exxon", as_of="2026-11-13")
    stock = ep.stock_page_html("XOM", rec, [rec], [], "https://www.x", "https://app.x")
    assert 'UAS.remember.apply(null,["XOM",' in stock
    mylist = list_page_html([rec], "https://www.x", "https://app.x")
    assert 'id="since"' in mylist
    assert mylist.index('id="ls-data"') < mylist.index("UAS.adopt(t, feed)")
