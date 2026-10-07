# utils/changes_page.py
# Unstructured Alpha — what changed in this week's measurements
#
# The library re-measures every stock each week; each reading spans three
# years of weekly returns, so one new week moves it only a little. This page
# shows what moved anyway: readings that now hold up and did not before,
# readings that no longer hold up, and the largest shifts among readings that
# held up at either point.
#
# RULES
#   * Only like with like: a stock is compared only when its newest reading is
#     from the newest data week on record, against its own previous reading
#     (whose date is shown -- it may be more than a week earlier).
#   * A reading crossing the evidence line is reported as exactly that; the
#     page says such crossings are usually of readings already near the line.
#   * Past, not forecast; no advice.

from __future__ import annotations

from html import escape
from typing import Dict, Iterable, List

from utils.exposure_pages import STANDS_UP, _chip, _date, _shell, fmt_pct
from utils.force_pages import FORCE_BY_KEY

SHIFTS_SHOWN = 15


def changes(latest: Iterable[dict], previous: Iterable[dict]) -> dict:
    """Compare each stock's newest reading with its previous one.

    Returns {"as_of", "compared", "gained": [...], "lost": [...], "shifts": [...]};
    each row has ticker, name, key, now, before, before_as_of.
    """
    latest = list(latest)
    newest = max((str(s.get("as_of") or "")[:10] for s in latest), default="")
    prev: Dict[str, dict] = {p["ticker"]: p for p in previous}
    gained, lost, shifts = [], [], []
    compared = 0
    for s in latest:
        p = prev.get(s["ticker"])
        if not p or str(s.get("as_of") or "")[:10] != newest:
            continue
        compared += 1
        now_e, before_e = s.get("exposures") or {}, p.get("exposures") or {}
        for key in now_e.keys() & before_e.keys():
            if key not in FORCE_BY_KEY:
                continue
            now, before = now_e[key], before_e[key]
            row = {"ticker": s["ticker"], "name": s.get("name") or "", "key": key,
                   "now": now, "before": before, "before_as_of": str(p.get("as_of") or "")[:10]}
            up_now, up_before = now.get("evidence") in STANDS_UP, before.get("evidence") in STANDS_UP
            if up_now and not up_before:
                gained.append(row)
            elif up_before and not up_now:
                lost.append(row)
            if up_now or up_before:
                shifts.append(row)
    by_size = lambda r: (-abs(r["now"]["impact"]), r["ticker"], r["key"])   # noqa: E731
    gained.sort(key=by_size)
    lost.sort(key=lambda r: (-abs(r["before"]["impact"]), r["ticker"], r["key"]))
    shifts.sort(key=lambda r: (-abs(r["now"]["impact"] - r["before"]["impact"]), r["ticker"], r["key"]))
    return {"as_of": newest, "compared": compared, "gained": gained, "lost": lost,
            "shifts": shifts[:SHIFTS_SHOWN]}


_CSS = """<style>
.ch td{white-space:nowrap}.ch .arrow{color:var(--ink3);margin:0 6px}
.ch .was{color:var(--ink3)}.ch td .shock{white-space:normal;max-width:260px}
@media (max-width:640px){.ch .chip,.ch tbody th .shock{display:none}}
</style>"""


def _table(rows: List[dict], label: str) -> str:
    body = "".join(
        f'<tr><th scope="row"><a href="/exposure/{escape(r["ticker"])}">{escape(r["ticker"])}</a>'
        + (f'<span class="shock">{escape(r["name"])}</span>' if r["name"] else "") + '</th>'
        f'<td><a href="/forces/{r["key"]}">{escape(FORCE_BY_KEY[r["key"]].label)}</a></td>'
        f'<td><span class="was">{fmt_pct(r["before"]["impact"])}</span><span class="arrow" aria-label="to">→</span>'
        f'<b>{fmt_pct(r["now"]["impact"])}</b>'
        f'<span class="shock">was {escape(_label(r["before"]))} on {_date(r["before_as_of"])}; '
        f'now {escape(_label(r["now"]))}</span> {_chip(r["now"]["evidence"])}</td></tr>'
        for r in rows)
    return (f'<div class="card ch" tabindex="0" role="region" aria-label="{escape(label)}">'
            '<table><thead><tr><th scope="col">Stock</th><th scope="col">Force</th>'
            f'<th scope="col">Before → now</th></tr></thead><tbody>{body}</tbody></table></div>')


def _label(e: dict) -> str:
    from utils import exposure as ex
    return ex.EVIDENCE_LABELS.get(e.get("evidence"), str(e.get("evidence") or "")).lower()


def changes_page_html(latest: Iterable[dict], previous: Iterable[dict],
                      base_url: str, app_url: str) -> str:
    c = changes(latest, previous)
    canonical = f"{base_url}/changes"
    title = "What changed this week: stock exposure to rates, oil, the dollar and more"
    crumb = '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › What changed</nav>'
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "url": canonical}
    if not c["compared"]:
        desc = "Week-on-week changes in how U.S. stocks move with economic forces."
        body = (crumb + '<h1>What changed this week</h1><p class="lead">Nothing to compare yet: a '
                'stock needs two weeks of readings. Readings are added each week.</p>')
        return _shell(title, desc, canonical, ld, body, app_url, robots="noindex, follow")

    ng, nl = len(c["gained"]), len(c["lost"])
    desc = (f"Data through {_date(c['as_of'])}: across {c['compared']} stocks, {ng} readings now "
            f"hold up that did not before and {nl} no longer do.")
    parts = [_CSS, crumb, '<h1>What changed this week</h1>',
             f'<p class="meta">Data through {_date(c["as_of"])} · {c["compared"]} stocks compared with '
             'their previous reading</p>', f'<p class="lead">{escape(desc)}</p>',
             '<p class="lead">Each reading spans three years of weekly returns, so one new week moves '
             'it only a little. A reading that crosses the line between holding up and not was '
             'almost always close to it already: read these as edges moving, not as news about '
             'the companies.</p>']
    parts.append('<h2>Now holding up</h2>' + (_table(c["gained"], "Readings now holding up")
                 if c["gained"] else '<p class="lead">None this week.</p>'))
    parts.append('<h2>No longer holding up</h2>' + (_table(c["lost"], "Readings no longer holding up")
                 if c["lost"] else '<p class="lead">None this week.</p>'))
    if c["shifts"]:
        parts.append('<h2>Largest shifts</h2><p class="small">Among readings that held up before or '
                     'now, the largest changes in the typical weekly move.</p>'
                     + _table(c["shifts"], "Largest shifts"))
    parts.append('<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing '
                 'here is a recommendation to buy, sell or hold any security.</p>'
                 '<div class="actions"><a class="btn btn-primary" href="/exposure">Every stock on '
                 'record</a><a class="btn btn-secondary" href="/explore">What if? Move a force</a></div>')
    ld["dateModified"] = c["as_of"]
    ld["description"] = desc
    return _shell(title, desc, canonical, ld, "".join(parts), app_url)

