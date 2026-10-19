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
#     from the page's data week, against its own previous reading (whose date
#     is shown -- it may be more than a week earlier). The page's week is the
#     one the most stocks can be compared in, not simply the newest date: a
#     stock a visitor opens mid-week is a week ahead of the library, and must
#     not turn the page into a report on that one stock.
#   * A reading crossing the evidence line is reported as exactly that; the
#     page says such crossings are usually of readings already near the line.
#   * Past, not forecast; no advice.

from __future__ import annotations

from html import escape
from typing import Dict, Iterable, List

from utils.exposure_pages import STANDS_UP, _date, _shell, fmt_pct
from utils.force_pages import FORCE_BY_KEY

SHIFTS_SHOWN = 15


def changes(latest: Iterable[dict], previous: Iterable[dict]) -> dict:
    """Compare each stock's newest reading with its previous one.

    Returns {"as_of", "compared", "gained": [...], "lost": [...], "shifts": [...]};
    each row has ticker, name, key, now, before, before_as_of.
    """
    latest = list(latest)
    prev: Dict[str, dict] = {p["ticker"]: p for p in previous}
    weeks: Dict[str, int] = {}
    for s in latest:
        if s["ticker"] in prev:
            w = str(s.get("as_of") or "")[:10]
            weeks[w] = weeks.get(w, 0) + 1
    # Most comparable stocks wins; a tie goes to the newer week.
    newest = max(weeks, key=lambda w: (weeks[w], w), default="")
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


SHOWN = 10          # rows shown per section before "Show all"

_CSS = """<style>
.ch-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:14px 0 6px;list-style:none;padding:0}
.ch-tiles li{border:1px solid var(--line);border-radius:12px;background:var(--surface);padding:14px 16px}
.ch-tiles b{display:block;font-size:1.25rem;font-variant-numeric:tabular-nums}.ch-tiles span{color:var(--ink2)}
.ch-list{list-style:none;margin:8px 0 0;padding:0;border:1px solid var(--line);border-radius:12px;background:var(--surface)}
.ch-list li{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr) minmax(120px,1.2fr) 130px;gap:12px;align-items:center;
  padding:9px 14px;border-top:1px solid var(--line)}
.ch-list li:first-child{border-top:0}
.ch-who{display:flex;flex-direction:column;min-width:0}.ch-who span,.ch-f{color:var(--ink3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ch-t{position:relative;height:18px}
.ch-t::before{content:"";position:absolute;left:0;right:0;top:8px;height:2px;background:var(--subtle)}
.ch-z{position:absolute;top:1px;bottom:1px;width:2px;margin-left:-1px;background:var(--ink3)}
.ch-ln{position:absolute;top:8px;height:2px;background:var(--ink3)}
.ch-b,.ch-n{position:absolute;top:3px;width:12px;height:12px;margin-left:-6px;border-radius:50%}
.ch-b{background:var(--surface);border:2px solid var(--ink3)}
.ch-n{background:var(--accent)}.ch-n.ch-weak{background:var(--surface);border:2px solid var(--accent)}
.ch-v{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.ch-v .was{color:var(--ink3)}
.ch-bars{list-style:none;margin:8px 0 0;padding:0;max-width:640px}
.ch-bars li{display:grid;grid-template-columns:minmax(0,1fr) 2fr auto;gap:10px;align-items:center;padding:4px 0}.ch-bars .small{white-space:nowrap}
.ch-bar{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--subtle)}
.ch-bar i{display:block;height:100%}.ch-bar .g{background:var(--accent)}.ch-bar .l{background:var(--ink3)}
.ch-key{display:flex;flex-wrap:wrap;gap:4px 16px;color:var(--ink3);margin-top:6px}
.ch-key i{display:inline-block;width:12px;height:12px;border-radius:50%;vertical-align:-2px;margin-right:5px}
details.ch-more{margin-top:8px}details.ch-more summary{cursor:pointer;font-weight:650}
@media (max-width:640px){.ch-list li{grid-template-columns:minmax(0,1fr) 120px}.ch-t,.ch-f{display:none}}
</style>"""


def _rows(rows: List[dict], scale: float) -> str:
    def pos(v: float) -> float:
        return 50 + 50 * max(-1.0, min(1.0, v / scale)) if scale > 0 else 50
    out = []
    for r in rows:
        b, n = r["before"]["impact"], r["now"]["impact"]
        lo, hi = sorted((pos(b), pos(n)))
        weak = "" if r["now"].get("evidence") in STANDS_UP else " ch-weak"
        out.append(
            f'<li><a class="ch-who" href="/exposure/{escape(r["ticker"])}"><b>{escape(r["ticker"])}</b>'
            + (f'<span>{escape(r["name"])}</span>' if r["name"] else "") + '</a>'
            f'<a class="ch-f" href="/forces/{r["key"]}">{escape(FORCE_BY_KEY[r["key"]].label)}</a>'
            f'<span class="ch-t" aria-hidden="true"><span class="ch-z" style="left:50%"></span>'
            f'<span class="ch-ln" style="left:{lo:.1f}%;width:{hi - lo:.1f}%"></span>'
            f'<span class="ch-b" style="left:{pos(b):.1f}%"></span><span class="ch-n{weak}" style="left:{pos(n):.1f}%"></span></span>'
            f'<span class="ch-v" title="was {escape(_label(r["before"]))} on {_date(r["before_as_of"])}; now {escape(_label(r["now"]))}">'
            f'<span class="was">{fmt_pct(b)}</span> → <b>{fmt_pct(n)}</b></span></li>')
    return "".join(out)


def _section(rows: List[dict], label: str, scale: float) -> str:
    """The first SHOWN rows, the rest behind "Show all"."""
    head, rest = rows[:SHOWN], rows[SHOWN:]
    html = f'<ol class="ch-list" aria-label="{escape(label)}">{_rows(head, scale)}</ol>'
    if rest:
        html += (f'<details class="ch-more"><summary>Show all {len(rows)}</summary>'
                 f'<ol class="ch-list" aria-label="{escape(label)}, continued">{_rows(rest, scale)}</ol></details>')
    return html


def _by_force(c: dict) -> str:
    """How many crossings each force had, gained and lost, largest first."""
    counts: Dict[str, List[int]] = {}
    for side, i in (("gained", 0), ("lost", 1)):
        for r in c[side]:
            counts.setdefault(r["key"], [0, 0])[i] += 1
    if not counts:
        return ""
    top = max(g + l for g, l in counts.values())
    rows = sorted(counts.items(), key=lambda kv: (-(kv[1][0] + kv[1][1]), FORCE_BY_KEY[kv[0]].label))
    items = "".join(
        f'<li><a href="/forces/{k}">{escape(FORCE_BY_KEY[k].label)}</a>'
        f'<span class="ch-bar" aria-hidden="true"><i class="g" style="width:{100 * g / top:.1f}%"></i>'
        f'<i class="l" style="width:{100 * l / top:.1f}%"></i></span>'
        f'<span class="small">{g} in · {l} out</span></li>' for k, (g, l) in rows)
    return ('<h2>Which forces moved</h2><p class="small">For each force, how many readings started holding '
            'up (blue) and how many stopped (grey).</p>' f'<ul class="ch-bars">{items}</ul>')


def _label(e: dict) -> str:
    from utils import exposure as ex
    return ex.EVIDENCE_LABELS.get(e.get("evidence"), str(e.get("evidence") or "")).lower()


def _n(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


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
    desc = (f"Data through {_date(c['as_of'])}: across {_n(c['compared'], 'stock')}, {ng} readings now "
            f"hold up that did not before and {nl} no longer do.")
    every = c["gained"] + c["lost"] + c["shifts"]
    scale = max([abs(r[w]["impact"]) for r in every for w in ("before", "now")] + [0.5]) * 1.05
    parts = [_CSS, crumb, '<h1>What changed this week</h1>',
             f'<p class="meta">Data through {_date(c["as_of"])} · {_n(c["compared"], "stock")} compared with '
             'their previous reading</p>', f'<p class="lead">{escape(desc)}</p>',
             '<ul class="ch-tiles">'
             f'<li><b>{c["compared"]}</b><span>{"stock" if c["compared"] == 1 else "stocks"} compared</span></li>'
             f'<li><b>{ng}</b><span>readings now hold up</span></li>'
             f'<li><b>{nl}</b><span>no longer hold up</span></li></ul>',
             '<p class="lead">Each reading spans three years of weekly returns, so one new week moves '
             'it only a little. A reading that crosses the line between holding up and not was '
             'almost always close to it already: read these as edges moving, not as news about '
             'the companies.</p>',
             '<p class="ch-key"><span><i style="border:2px solid var(--ink3)"></i>Before</span>'
             '<span><i style="background:var(--accent)"></i>Now, held up</span>'
             '<span><i style="border:2px solid var(--accent)"></i>Now, did not hold up</span>'
             '<span>All on one scale; the line is zero.</span></p>']
    parts.append(_by_force(c))
    parts.append('<h2>Now holding up</h2>' + (_section(c["gained"], "Readings now holding up", scale)
                 if c["gained"] else '<p class="lead">None this week.</p>'))
    parts.append('<h2>No longer holding up</h2>' + (_section(c["lost"], "Readings no longer holding up", scale)
                 if c["lost"] else '<p class="lead">None this week.</p>'))
    if c["shifts"]:
        parts.append('<h2>Largest shifts</h2><p class="small">Among readings that held up before or '
                     'now, the largest changes in the typical weekly move.</p>'
                     + _section(c["shifts"], "Largest shifts", scale))
    parts.append('<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing '
                 'here is a recommendation to buy, sell or hold any security.</p>'
                 '<div class="actions"><a class="btn btn-primary" href="/exposure">Every stock on '
                 'record</a><a class="btn btn-secondary" href="/explore">What if? Move a force</a></div>')
    ld["dateModified"] = c["as_of"]
    ld["description"] = desc
    return _shell(title, desc, canonical, ld, "".join(parts), app_url)

