"""Coming back: "Your desk" on the landing and the command palette everywhere.

  * The desk's XP, levels and path mirror utils/progress.py exactly -- a
    returning visitor must see the same level on the landing as on /learn.
  * The palette offers only pages that exist: its forces, tools and
    questions come from the code's own lists, never typed in.
  * Every server-rendered page and the landing load the same /palette.js.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.test_explore_page import client  # noqa: F401  (fixture)
from utils import progress as pr

WEB = Path(__file__).resolve().parent.parent / "unstructured-alpha-web" / "app"
DESK_TS = (WEB / "desk.ts").read_text(encoding="utf-8")


def test_the_desk_mirrors_the_progress_rules():
    steps = re.findall(r'\["(\w+)", "([^"]+)", "([^"]+)"\]', DESK_TS.split("export const STEP_XP")[0])
    assert [(k, label, href) for k, label, href in steps] == [(s[0], s[1], s[3]) for s in pr.STEPS]
    assert f"STEP_XP = {pr.STEP_XP};" in DESK_TS
    levels = [(int(n), name) for n, name in re.findall(r'\[(\d+), "([^"]+)"\]', DESK_TS.split("export const LEVELS")[1].split(";")[0])]
    assert levels == list(pr.LEVELS)
    games = dict((g, (int(a), int(b))) for g, a, b in re.findall(r'(\w+): \[(\d+), (\d+)\]', DESK_TS.split("export const GAME_XP")[1].split(";")[0]))
    assert games == pr.GAME_XP


def test_the_desk_shows_only_to_a_returning_visitor_and_never_on_the_server():
    comp = (WEB / "Desk.tsx").read_text(encoding="utf-8")
    assert "useSyncExternalStore(subscribe, snapshot, () => null)" in comp
    assert "if (!d || !d.returning) return null;" in comp
    page = (WEB / "page.tsx").read_text(encoding="utf-8")
    assert "<Desk />" in page and page.index("<Desk />") < page.index('aria-labelledby="sample-title"')


def test_the_palette_offers_only_pages_that_exist():
    from utils import exposure as ex
    from utils.palette import palette_data, palette_js
    from utils.tools_page import _TOOLS
    from utils.when_pages import BY_SLUG

    d = palette_data()
    assert [f[0] for f in d["forces"]] == [f.key for f in (*ex.FACTORS, *ex.EXTRA_FACTORS)]
    assert [t[0] for t in d["tools"]] == [t[0] for t in _TOOLS]
    assert {w[0] for w in d["when"]} == set(BY_SLUG)
    js = palette_js()
    assert "__DATA__" not in js and json.dumps(d, separators=(",", ":")) in js
    # reads the visitor's own stores, writes none of them
    assert "localStorage.getItem('ua-seen-v1')" in js and "localStorage.setItem" not in js


def test_the_palette_is_served_and_loaded_everywhere(client):  # noqa: F811
    c = client[0]
    r = c.get("/palette.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/javascript")
    assert "max-age" in r.headers["cache-control"]
    from utils.exposure_pages import _shell
    html = _shell("t", "d", "https://www.x/forces", {}, "<p>x</p>", "https://app.x")
    assert '<script src="/palette.js" defer></script>' in html and "data-ua-palette-input" in html
    layout = (WEB / "layout.tsx").read_text(encoding="utf-8")
    assert '<Script src="/palette.js"' in layout
    cfg = (WEB.parent / "next.config.ts").read_text(encoding="utf-8")
    assert 'source: "/palette.js", destination: `${SEO_ORIGIN}/palette.js`' in cfg
