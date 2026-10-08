# utils/force_pages.py
# Unstructured Alpha — one crawlable page per economic force
#
# WHY
# ---
# The stock library holds every S&P 500 company's reading on every force (the
# core five and the extras), refreshed weekly. The stock pages read it one
# company at a time; these read it one FORCE at a time: which stocks on record
# have moved up with oil, which moved down, and how many show no link at all.
# That is research a visitor gets without entering a portfolio, and a page a
# search engine can index for "stocks that move with oil".
#
# RULES
# -----
#   * Only readings that held up (Clear or Tentative) are ranked. The count of
#     stocks with no measurable link is stated, never hidden: most stocks have
#     no link to most forces, and that is a finding too.
#   * The population is "stocks on record", not "the market": the library is
#     the S&P 500 plus whatever visitors have opened, and the copy says so.
#   * No forecast and no advice. A ranking of past sensitivity is not a list
#     of stocks to buy when oil rises.
#   * Pure functions of their inputs, like utils/exposure_pages.py, whose
#     shell, styles and helpers these reuse.

from __future__ import annotations

from html import escape
from typing import Dict, Iterable, List, Optional, Tuple

from utils import exposure as ex
from utils.exposure_pages import STANDS_UP, _chip, _date, _shell, fmt_pct

GROUP_LABELS: Dict[str, str] = {"core": "The core five", **ex.EXTRA_GROUPS}
ALL_FORCES: Tuple[ex.Factor, ...] = tuple(ex.FACTORS) + tuple(ex.EXTRA_FACTORS)
FORCE_BY_KEY: Dict[str, ex.Factor] = {f.key: f for f in ALL_FORCES}


def _lower(f: ex.Factor) -> str:
    return ex.lower_label(f.label)


def force_stats(key: str, stocks: Iterable[dict]) -> dict:
    """Every stock on record with a reading on this force, sorted into up,
    down and no measurable link."""
    measured, up, down = [], [], []
    newest = ""
    for s in stocks:
        e = (s.get("exposures") or {}).get(key)
        if not e:
            continue
        row = dict(e, ticker=s["ticker"], name=s.get("name") or "")
        measured.append(row)
        newest = max(newest, str(e.get("as_of") or s.get("as_of") or "")[:10])
        if e.get("evidence") in STANDS_UP:
            (up if e["impact"] > 0 else down).append(row)
    up.sort(key=lambda r: -r["impact"])
    down.sort(key=lambda r: r["impact"])
    return {"measured": len(measured), "up": up, "down": down,
            "none": len(measured) - len(up) - len(down), "as_of": newest}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _control(f: ex.Factor) -> str:
    return "the stock market" if f.group == "core" else ex.CORE_CONTROL


def _bar_note(f: ex.Factor) -> str:
    if f.group == "core":
        return f"Clear needs |t| ≥ {ex.CLEAR_T:.2f}, shared across the five core forces"
    return f"Clear needs |t| ≥ {ex.EXTRA_CLEAR_T:.2f}, shared across every force tested"


def _rank_table(rows: List[dict], label: str) -> str:
    body = "".join(
        f'<tr><th scope="row"><a href="/exposure/{escape(r["ticker"])}">{escape(r["ticker"])}</a>'
        + (f'<span class="shock">{escape(r["name"])}</span>' if r.get("name") else "")
        + f'</th><td><b>{fmt_pct(r["impact"])}</b></td>'
        f'<td>{fmt_pct(r["low"])} to {fmt_pct(r["high"])}</td><td>{_chip(r["evidence"])}</td></tr>'
        for r in rows)
    return (f'<div class="card" tabindex="0" role="region" aria-label="{escape(label)}">'
            '<table><thead><tr><th scope="col">Stock</th><th scope="col">Typical weekly move</th>'
            '<th scope="col">90% range</th><th scope="col">Evidence</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


SWARM_W, SWARM_R, SWARM_GAP = 600, 4.5, 1.0


def swarm_layout(values: List[float], span: float, w: int = SWARM_W, r: float = SWARM_R) -> List[tuple]:
    """A beeswarm: each value at its x on a symmetric scale of +/- span, nudged
    up or down (closest free offset first) until it touches no dot already
    placed. Returns (x, y-offset) per value, in the input order."""
    d = 2 * r + SWARM_GAP
    order = sorted(range(len(values)), key=lambda i: (values[i], i))
    placed: List[tuple] = []
    out: List[Optional[tuple]] = [None] * len(values)
    for i in order:
        x = w / 2 + (w / 2 - r) * max(-1.0, min(1.0, values[i] / span))
        near = [(px, py) for px, py in placed if abs(px - x) < d]
        k = 0
        while True:
            y = ((k + 1) // 2) * d * (1 if k % 2 else -1) * 0.5 if k else 0.0
            if all((px - x) ** 2 + (py - y) ** 2 >= d * d for px, py in near):
                break
            k += 1
        placed.append((x, y))
        out[i] = (round(x, 1), round(y, 1))
    return out


_SWARM_CSS = """<style>
.fs{padding:14px 16px 10px;margin:6px 0 14px}
.fs svg{display:block;width:100%;height:auto}
.fs .fs-z{stroke:var(--ink3);stroke-width:1.5}
.fs circle{stroke-width:1.5;cursor:pointer}
.fs .fs-u{fill:#2f6fbd;stroke:#2f6fbd}.fs .fs-d{fill:#b5651d;stroke:#b5651d}
.fs .fs-n{fill:var(--surface);stroke:var(--ink3)}
.fs circle:hover,.fs circle.on{stroke:var(--ink);stroke-width:3}
@media (prefers-color-scheme:dark){.fs .fs-u{fill:#5a8fd4;stroke:#5a8fd4}.fs .fs-d{fill:#c9822f;stroke:#c9822f}}
.fs-ax{display:flex;justify-content:space-between;font-size:.78rem;color:var(--ink3);margin-top:2px}
.fs-say{min-height:1.4em;margin:6px 0 0}
.fs-key{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:.78rem;color:var(--ink3);margin-top:6px}
.fs-key svg{display:inline;width:12px;height:12px;vertical-align:-2px;margin-right:5px}
</style>"""

_SWARM_SCRIPT = r"""
(function(){
  var box = document.getElementById('fs'), say = document.getElementById('fs-say'), on = null, base = say.textContent;
  function show(c){ if (on) on.classList.remove('on'); on = c; c.classList.add('on');
    say.textContent = c.getAttribute('data-say'); }
  box.addEventListener('pointerover', function(e){ var c = e.target.closest('circle[data-t]'); if (c) show(c); });
  box.addEventListener('pointerleave', function(){ if (on) on.classList.remove('on'); on = null; say.textContent = base; });
  box.addEventListener('click', function(e){
    var c = e.target.closest('circle[data-t]'); if (!c) return;
    if (on === c || !matchMedia('(hover: none)').matches) location.href = '/exposure/' + encodeURIComponent(c.getAttribute('data-t'));
    else show(c);
  });
})();
"""


def swarm_html(key: str, stocks: List[dict]) -> str:
    """Every stock on record with a reading on this force, one dot each, on
    one scale: coloured where the reading held up, hollow where it could not
    be told apart from zero. Hover (or tap) names a dot; click opens it.
    Decorative for screen readers: the tables below list the held-up ones,
    and the summary above counts the rest."""
    rows = [(s["ticker"], s.get("name") or "", s["exposures"][key]) for s in stocks
            if key in (s.get("exposures") or {})]
    if len(rows) < 2:
        return ""
    vals = [float(e["impact"]) for _, _, e in rows]
    span = max(abs(v) for v in vals) * 1.05 or 1.0
    # Smaller dots as the library fills in, so 500 stocks stay a strip, not a tower.
    r = round(max(2.6, min(SWARM_R, SWARM_R * (250 / len(vals)) ** 0.5)), 2)
    pts = swarm_layout(vals, span, r=r)
    top = max(abs(y) for _, y in pts) + r + 3
    h = 2 * top
    dots = []
    for (t, name, e), (x, y) in zip(rows, pts):
        strong = e.get("evidence") in STANDS_UP
        cls = ("fs-u" if e["impact"] > 0 else "fs-d") if strong else "fs-n"
        label = ex.EVIDENCE_LABELS.get(e.get("evidence"), "")
        said = f'{t}{" · " + name if name and name != t else ""}: {fmt_pct(e["impact"])} ({label.lower()})'
        dots.append(f'<circle class="{cls}" cx="{x}" cy="{top + y:.1f}" r="{r}" '
                    f'data-t="{escape(t)}" data-say="{escape(said)}"><title>{escape(said)}</title></circle>')
    tick = fmt_pct(span)
    held = sum(1 for _, _, e in rows if e.get("evidence") in STANDS_UP)
    hint = f"Each dot is one of the {len(rows)} stocks on record. Hover or tap a dot to name it; select it to open its page."
    dot = '<svg viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" class="{}" stroke-width="1.5"/></svg>'
    return (_SWARM_CSS
            + '<figure class="card fs" id="fs">'
            + f'<svg viewBox="0 0 {SWARM_W} {h:.0f}" aria-hidden="true">'
              f'<line class="fs-z" x1="{SWARM_W / 2}" x2="{SWARM_W / 2}" y1="0" y2="{h:.0f}"/>{"".join(dots)}</svg>'
            + f'<div class="fs-ax" aria-hidden="true"><span>−{tick[1:]}</span><span>0</span><span>{tick}</span></div>'
            + f'<p class="small fs-say" id="fs-say" aria-live="polite">{escape(hint)}</p>'
            + '<figcaption class="fs-key">'
              f'<span>{dot.format("fs-u")}Moved up, held up</span>'
              f'<span>{dot.format("fs-d")}Moved down, held up</span>'
              f'<span>{dot.format("fs-n")}Could not be told apart from zero ({len(rows) - held})</span>'
              '</figcaption></figure>'
            + f'<script>{_SWARM_SCRIPT}</script>')


def _by_sector(key: str, stocks: List[dict]) -> str:
    from utils.sector_pages import sectors_on_force_html
    return sectors_on_force_html(key, stocks)


def force_page_html(key: str, stocks: Iterable[dict], base_url: str, app_url: str,
                    limit: int = 25) -> Optional[str]:
    """The page for one force, or None if the key is not a force."""
    f = FORCE_BY_KEY.get(key)
    if f is None:
        return None
    stocks = list(stocks)
    st = force_stats(key, stocks)
    force = _lower(f)
    canonical = f"{base_url}/forces/{key}"
    title = f"Stocks exposed to {force}: which moved up and down with it"
    n, nu, nd = st["measured"], len(st["up"]), len(st["down"])

    if n == 0:
        lead = (f"No stock on record has a reading on {force} yet. Readings are added each week "
                "as the S&P 500 is measured, and whenever a stock is opened.")
        body_tables = ""
    else:
        lead = (f"Of {_plural(n, 'stock')} on record, {nu} moved up with {force} in a way that held "
                f"up and {nd} moved down with it. The other {st['none']} showed no link that could "
                "be told apart from noise.")
        body_tables = ""
        for rows, side, verb in ((st["up"], "up", "Moved up with"), (st["down"], "down", "Moved down with")):
            heading = f"{verb} {force}"
            if rows:
                shown = rows[:limit]
                more = (f'<p class="small">Showing the {len(shown)} largest of {len(rows)}.</p>'
                        if len(rows) > len(shown) else "")
                body_tables += f'<h2>{escape(heading)}</h2>{_rank_table(shown, heading)}{more}'
            else:
                body_tables += (f'<h2>{escape(heading)}</h2><p class="lead">No stock on record '
                                f'{verb.lower()} {escape(force)} in a way that held up.</p>')

    siblings = [g for g in ALL_FORCES if g.group == f.group and g.key != key]
    sib_html = ("<h2>Other forces in this group</h2><ul class=\"related\">"
                + "".join(f'<li><a href="/forces/{g.key}">{escape(g.label)}</a></li>' for g in siblings)
                + "</ul>") if siblings else ""

    body = (
        f'<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › '
        f'<a href="/forces">Economic forces</a> › {escape(f.label)}</nav>'
        f'<h1>Stocks exposed to {escape(force)}</h1>'
        f'<p class="meta">{escape(GROUP_LABELS.get(f.group, ""))}'
        + (f' · data through {_date(st["as_of"])}' if st["as_of"] else "") + '</p>'
        f'<p class="lead">{escape(lead)}</p>'
        f'<p class="lead">{escape(f.why)}</p>'
        f'{swarm_html(key, stocks)}{body_tables}{_by_sector(key, stocks)}'
        f'<p class="small">Each figure is a stock&#39;s typical move in a week when {escape(f.shock_phrase)}, '
        f'after accounting for {escape(_control(f))}, over three years of weekly returns. Only readings '
        f'that held up are ranked ({_bar_note(f)}). The '
        f'stocks on record are the S&amp;P 500, measured weekly, plus any stock a visitor has opened.</p>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> A stock that moved '
        f'with {escape(force)} over the last three years may not do so over the next three, and nothing '
        'here is a recommendation to buy, sell or hold any security.</p>'
        f'{sib_html}'
        '<div class="actions">'
        f'<a class="btn btn-primary" href="/explore#{key}">Try a move in {escape(force)}</a>'
        f'<a class="btn btn-secondary" href="{escape(app_url)}/">Measure your own portfolio</a>'
        '<a class="btn btn-secondary" href="/forces">All economic forces</a></div>'
        f'<p class="small"><a href="{escape(app_url)}/methodology">Full methodology</a>.</p>')

    description = (f"Which U.S. stocks have moved with {force}? {nu} up and {nd} down among {n} "
                   f"measured, each with a 90% range and an evidence label." if n else
                   f"Which U.S. stocks have moved with {force}.")
    json_ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title,
               "description": description, "url": canonical,
               "isPartOf": {"@type": "WebSite", "name": "Unstructured Alpha", "url": base_url}}
    if st["as_of"]:
        json_ld["dateModified"] = st["as_of"]
    return _shell(title, description, canonical, json_ld, body, app_url,
                  robots="" if n else "noindex, follow")


def forces_hub_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    stocks = list(stocks)
    sections = []
    for group, label in GROUP_LABELS.items():
        items = []
        for f in (g for g in ALL_FORCES if g.group == group):
            st = force_stats(f.key, stocks)
            held = len(st["up"]) + len(st["down"])
            note = (f'{held} of {st["measured"]} stocks with a link that held up'
                    if st["measured"] else "not measured yet")
            items.append(f'<li><a href="/forces/{f.key}">{escape(f.label)}</a>'
                         f'<span class="shock">{escape(note)}</span></li>')
        sections.append(f'<h2>{escape(label)}</h2><ul class="forces">{"".join(items)}</ul>')
    total = len(ALL_FORCES)
    title = "Which stocks move with rates, oil, gold, the dollar and more"
    desc = (f"{total} economic forces, from interest rates and oil to gold, bitcoin and the yen, "
            "and the U.S. stocks that have moved with each — with a 90% range and an evidence label "
            "on every reading.")
    body = (
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Economic forces</nav>'
        f'<h1>Economic forces</h1><p class="lead">{escape(desc)}</p>'
        '<p class="lead">The core five are measured together, with the stock market held fixed. '
        'Every other force is measured beyond those five, so it shows only what they don&#39;t '
        'already explain.</p>'
        + "".join(sections)
        + f'<div class="actions"><a class="btn btn-primary" href="/explore">What if? Move a force</a>'
          f'<a class="btn btn-secondary" href="{escape(app_url)}/">Measure your own portfolio</a>'
          '<a class="btn btn-secondary" href="/exposure">Every stock on record</a></div>')
    json_ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title,
               "description": desc, "url": f"{base_url}/forces"}
    return _shell(title, desc, f"{base_url}/forces", json_ld, body, app_url)


def force_sitemap_urls(stocks: Iterable[dict], base_url: str) -> List[str]:
    """The hub, then each force that has at least one reading, with its real date."""
    stocks = list(stocks)
    urls, newest = [], ""
    for f in ALL_FORCES:
        st = force_stats(f.key, stocks)
        if not st["measured"]:
            continue   # an empty force page is noindex; don't advertise it
        newest = max(newest, st["as_of"])
        urls.append(f"  <url><loc>{base_url}/forces/{f.key}</loc>"
                    + (f"<lastmod>{st['as_of']}</lastmod>" if st["as_of"] else "")
                    + "<changefreq>weekly</changefreq><priority>0.8</priority></url>")
    hub = (f"  <url><loc>{base_url}/forces</loc>" + (f"<lastmod>{newest}</lastmod>" if newest else "")
           + "<changefreq>weekly</changefreq><priority>0.8</priority></url>")
    return [hub] + urls

