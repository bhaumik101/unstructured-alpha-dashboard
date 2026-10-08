# utils/sector_pages.py
# Unstructured Alpha — economic exposure by sector
#
# The stock and force pages read the library one company or one force at a
# time; these read it one SECTOR at a time: how the energy companies on record
# moved with oil, how the banks moved with rates. Sectors are the S&P 500's
# own GICS sectors, from the checked-in index list (cron/sp500.csv).
#
# RULES
#   * Each cell is the MEDIAN typical move of the sector's stocks on record,
#     with how many of them held up each way beside it -- a median of
#     readings, many of which could not be told apart from zero, says that.
#   * A sector with too few stocks on record shows its count, not a median.
#   * Stocks outside the index (opened by a visitor) have no sector and are
#     left out, never guessed.
#   * Past, not forecast; no advice.

from __future__ import annotations

import csv
import re
from functools import lru_cache
from html import escape
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Optional

from utils import exposure as ex
from utils.exposure_pages import STANDS_UP, _date, _shell, fmt_pct, hub_grid_html

INDEX_CSV = Path(__file__).resolve().parent.parent / "cron" / "sp500.csv"
MIN_FOR_MEDIAN = 3


def slug(sector: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sector.lower()).strip("-")


@lru_cache(maxsize=1)
def sector_by_ticker() -> Dict[str, str]:
    with open(INDEX_CSV, newline="", encoding="utf-8") as fh:
        return {r["ticker"].strip().upper(): r["sector"].strip()
                for r in csv.DictReader(fh) if r.get("sector")}


def sectors() -> List[str]:
    return sorted(set(sector_by_ticker().values()))


def by_slug(s: str) -> Optional[str]:
    return next((x for x in sectors() if slug(x) == s), None)


def sector_cell(members: List[dict], key: str) -> dict:
    """Median typical move on one force among a sector's stocks, with counts."""
    readings = [m["exposures"][key] for m in members if key in (m.get("exposures") or {})]
    held = [e for e in readings if e.get("evidence") in STANDS_UP]
    return {"n": len(readings),
            "median": median(e["impact"] for e in readings) if len(readings) >= MIN_FOR_MEDIAN else None,
            "up": sum(1 for e in held if e["impact"] > 0),
            "down": sum(1 for e in held if e["impact"] < 0)}


def members_of(sector: str, stocks: Iterable[dict]) -> List[dict]:
    m = sector_by_ticker()
    return [s for s in stocks if m.get(s["ticker"]) == sector]


def peer_medians(symbol: str, stocks: Iterable[dict]) -> Optional[dict]:
    """The stock's sector and, per force, the median typical move of its
    sector PEERS on record (the stock itself left out), where at least
    MIN_FOR_MEDIAN peers were measured. None outside the index."""
    sector = sector_by_ticker().get(symbol)
    if not sector:
        return None
    peers = [s for s in members_of(sector, stocks) if s["ticker"] != symbol]
    medians = {}
    for f in tuple(ex.FACTORS) + tuple(ex.EXTRA_FACTORS):
        c = sector_cell(peers, f.key)
        if c["median"] is not None:
            medians[f.key] = c["median"]
    return {"sector": sector, "slug": slug(sector), "medians": medians, "peers": len(peers)}


def sectors_on_force_html(key: str, stocks: Iterable[dict]) -> str:
    """For one force page: every sector's median move on that force, largest
    first, with how many of its stocks held up each way. "" with no data."""
    stocks = list(stocks)
    rows = []
    for sec in sectors():
        c = sector_cell(members_of(sec, stocks), key)
        if c["n"]:
            rows.append((sec, c))
    if not rows:
        return ""
    rows.sort(key=lambda r: (r[1]["median"] is None, -(r[1]["median"] or 0.0), r[0]))
    scale = max((abs(c["median"]) for _, c in rows if c["median"] is not None), default=0.0)
    body = "".join(
        f'<tr><th scope="row"><a href="/sectors/{slug(sec)}">{escape(sec)}</a></th>{_cell_html(c, scale)}</tr>'
        for sec, c in rows)
    f = next(x for x in tuple(ex.FACTORS) + tuple(ex.EXTRA_FACTORS) if x.key == key)
    label = f"By sector: {ex.lower_label(f.label)}"
    return (f'<h2>{escape(label[:1].upper() + label[1:])}</h2>'
            f'<div class="card" tabindex="0" role="region" aria-label="{escape(label)}">'
            '<table><thead><tr><th scope="col">Sector</th><th scope="col">Median move</th></tr></thead>'
            f'<tbody>{body}</tbody></table><div class="foot">{_FOOT} {_SHADE}</div></div>' + _HM_CSS)


def _cell_html(c: dict, scale: float = 0.0, link: str = "") -> str:
    """One sector-by-force cell. With a scale, shaded by the median's size
    against the largest median shown (a heatmap); with a link, the figure
    opens the stocks behind it."""
    if c["median"] is None:
        return f'<td class="v-weak">{c["n"]} measured</td>' if c["n"] else '<td class="v-weak">—</td>'
    inner = (f'<b>{fmt_pct(c["median"])}</b>'
             f'<span class="shock">{c["up"]}↑ {c["down"]}↓ held up, of {c["n"]}</span>')
    if link:
        inner = f'<a class="hm-a" href="{escape(link)}">{inner}</a>'
    shade = ""
    if scale > 0 and c["median"]:
        side = "hm-up" if c["median"] > 0 else "hm-down"
        shade = f' class="hm {side}" style="--a:{min(1.0, abs(c["median"]) / scale):.2f}"'
    return f'<td data-v="{c["median"]:.4f}"{shade}>{inner}</td>'


_SHADE = ('Shading is darker the larger the median move, blue for up and orange for down; it '
          'shows size, not how well the reading held up.')

_HM_CSS = """<style>
td.hm-up{background:rgba(47,111,189,calc(.06 + var(--a) * .30))}
td.hm-down{background:rgba(181,101,29,calc(.06 + var(--a) * .32))}
@media (prefers-color-scheme:dark){td.hm-up{background:rgba(90,143,212,calc(.06 + var(--a) * .34))}
  td.hm-down{background:rgba(201,130,47,calc(.06 + var(--a) * .34))}}
td.hm .shock{color:var(--ink2)}
a.hm-a{display:block;color:var(--ink);text-decoration:none;border-radius:6px;margin:-4px;padding:4px}
a.hm-a:hover,a.hm-a:focus-visible{outline:2px solid var(--accent);outline-offset:0}
a.hm-a[aria-current]{outline:2px solid var(--accent);background:var(--surface)}
tr:target{outline:2px solid var(--accent)}
.hm-panel{padding:16px 18px;margin-top:12px}
.hm-panel h2{margin:0 0 4px}.hm-panel .hm-x{float:right;margin-left:12px}
.hm-list{list-style:none;margin:10px 0 0;padding:0}
.hm-list li{display:grid;grid-template-columns:minmax(0,1fr) minmax(120px,40%) 64px;gap:12px;align-items:center;
  padding:6px 0;border-top:1px solid var(--line)}
.hm-list a{text-decoration:none;color:var(--ink);display:flex;flex-direction:column;min-width:0}
.hm-list a span{font-size:.82rem;color:var(--ink3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hm-tr{position:relative;height:10px;background:var(--subtle);border-radius:5px}
.hm-tr::after{content:"";position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:var(--ink3)}
.hm-br{position:absolute;top:0;bottom:0;border-radius:5px}
.hm-br.u{background:#2f6fbd}.hm-br.d{background:#b5651d}.hm-br.f{opacity:.35}
@media (prefers-color-scheme:dark){.hm-br.u{background:#5a8fd4}.hm-br.d{background:#c9822f}}
.hm-v{text-align:right;font-variant-numeric:tabular-nums}
@media (max-width:640px){.hm-list li{grid-template-columns:minmax(0,1fr) 64px}.hm-tr{display:none}}
</style>"""

_HM_SCRIPT = r"""
(function(){
  var D = JSON.parse(document.getElementById('hm-data').textContent);
/*PCT*/
  var panel = document.getElementById('hm-panel'), cur = null;
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function open(a, scroll){
    var m = /\/sectors\/([^#]+)#f-(.+)$/.exec(a.getAttribute('href')); if (!m) return false;
    var sec = D.s[m[1]], fi = D.k.indexOf(m[2]); if (!sec || fi < 0) return false;
    var f = D.f[fi], rows = sec[1].filter(function(r){ return r[2][fi]; })
      .sort(function(x, y){ return y[2][fi][0] - x[2][fi][0] || (x[0] < y[0] ? -1 : 1); });
    var max = rows.reduce(function(a, r){ return Math.max(a, Math.abs(r[2][fi][0])); }, 0);
    var held = rows.filter(function(r){ return r[2][fi][1]; }).length;
    panel.innerHTML = '<button type="button" class="btn btn-secondary hm-x">Close</button>'
      + '<h2 tabindex="-1">' + esc(sec[0]) + ': ' + esc(f[0]) + '</h2>'
      + '<p class="small">Each stock&#39;s typical weekly move in weeks when ' + esc(f[1]) + ', beyond the market. '
      + held + ' of ' + rows.length + ' held up (bold); grey ones could not be told apart from zero.</p>'
      + '<ol class="hm-list">' + rows.map(function(r){
        var v = r[2][fi][0], strong = r[2][fi][1], w = max ? 50 * Math.abs(v) / max : 0;
        return '<li><a href="/exposure/' + encodeURIComponent(r[0]) + '"><b>' + esc(r[0]) + '</b><span>' + esc(r[1]) + '</span></a>'
          + '<span class="hm-tr" aria-hidden="true"><span class="hm-br ' + (v >= 0 ? 'u' : 'd') + (strong ? '' : ' f')
          + '" style="' + (v >= 0 ? 'left' : 'right') + ':50%;width:' + w.toFixed(1) + '%"></span></span>'
          + '<span class="hm-v">' + (strong ? '<b>' + pct(v) + '</b>' : '<span class="v-weak">' + pct(v) + '</span>') + '</span></li>';
      }).join('') + '</ol>'
      + '<p class="small"><a href="/sectors/' + m[1] + '">Everything on ' + esc(sec[0]) + ' →</a> · '
      + '<a href="/forces/' + m[2] + '">Every stock on ' + esc(f[0].toLowerCase()) + ' →</a></p>';
    panel.hidden = false;
    if (cur) cur.removeAttribute('aria-current');
    cur = a; a.setAttribute('aria-current', 'true');
    panel.querySelector('.hm-x').addEventListener('click', close);
    if (scroll){ panel.scrollIntoView({block: 'nearest', behavior: 'smooth'}); panel.querySelector('h2').focus({preventScroll: true}); }
    return true;
  }
  function close(){ panel.hidden = true; panel.innerHTML = '';
    if (cur){ cur.removeAttribute('aria-current'); cur.focus(); cur = null; }
    try { history.replaceState(null, '', location.pathname); } catch (e) {} }
  document.getElementById('hm').addEventListener('click', function(e){
    var a = e.target.closest && e.target.closest('a.hm-a');
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
    if (open(a, true)){ e.preventDefault();
      try { history.replaceState(null, '', '#' + a.getAttribute('href').split('/sectors/')[1].replace('#f-', ':')); } catch (x) {} }
  });
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape' && !panel.hidden) close(); });
  var h = /^#([a-z0-9-]+):([a-z0-9_]+)$/.exec(location.hash);
  if (h){ var a = document.querySelector('a.hm-a[href="/sectors/' + h[1] + '#f-' + h[2] + '"]'); if (a) open(a, true); }
})();
"""


def _hm_script(grid) -> str:
    """The data behind every cell: each sector's stocks with their readings
    on the core five ([impact, held up] or null), and the script that opens it."""
    import json
    from utils.explore_page import JS_PCT
    keys = [f.key for f in ex.FACTORS]
    data = {"k": keys, "f": [[f.label, f.shock_phrase] for f in ex.FACTORS],
            "s": {slug(sec): [sec, [[m["ticker"], m.get("name") or "",
                                     [([round(float(e["impact"]), 4), 1 if e.get("evidence") in STANDS_UP else 0]
                                       if (e := (m.get("exposures") or {}).get(k)) else None) for k in keys]]
                                    for m in sorted(mem, key=lambda m: m["ticker"])]]
                  for sec, mem, _ in grid if mem}}
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return (f'<script type="application/json" id="hm-data">{payload}</script>'
            f'<script>{_HM_SCRIPT.replace("/*PCT*/", JS_PCT)}</script>')


_FOOT = ('Each figure is the median typical weekly move of the sector&#39;s stocks on record when that '
         'force moved by its standard amount, after the stock market&#39;s own move. Beneath it: how '
         'many of those stocks moved up (↑) or down (↓) with the force in a way that held up. The '
         'median includes readings that could not be told apart from zero; the counts say how many '
         'did not. Fewer than three stocks on record shows the count, not a median.')


def sectors_hub_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    stocks = list(stocks)
    grid, newest = [], ""
    for sec in sectors():
        mem = members_of(sec, stocks)
        newest = max([newest] + [str(m.get("as_of") or "")[:10] for m in mem])
        grid.append((sec, mem, [sector_cell(mem, f.key) for f in ex.FACTORS]))
    scale = max((abs(c["median"]) for _, _, cs in grid for c in cs if c["median"] is not None), default=0.0)
    rows = []
    for sec, mem, cs in grid:
        cells = "".join(_cell_html(c, scale, f"/sectors/{slug(sec)}#f-{f.key}")
                        for f, c in zip(ex.FACTORS, cs))
        rows.append(f'<tr><th scope="row"><a href="/sectors/{slug(sec)}">{escape(sec)}</a>'
                    f'<span class="shock">{len(mem)} stocks on record</span></th>{cells}</tr>')
    head = "".join(f'<th scope="col" title="In weeks when {escape(f.shock_phrase)}">{escape(f.label)}</th>'
                   for f in ex.FACTORS)
    title = "Which sectors move with interest rates, oil, the dollar and credit"
    desc = ("How each S&P 500 sector's stocks have moved with interest rates, inflation expectations, "
            "the dollar, oil and credit spreads: the median move, and how many held up each way.")
    body = (
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Sectors</nav>'
        '<h1>Economic exposure by sector</h1>'
        + (f'<p class="meta">Data through {_date(newest)}</p>' if newest else "")
        + f'<p class="lead">{escape(desc)}</p>'
        + _HM_CSS +
        '<p class="small hm-tip">Pick any figure to see the stocks behind it.</p>'
        '<div class="card" tabindex="0" role="region" aria-label="Each sector against the five core forces">'
        f'<table id="hm"><thead><tr><th scope="col">Sector</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
        f'<div class="foot">{_FOOT} {_SHADE}</div></div>'
        '<section id="hm-panel" class="card hm-panel" aria-live="polite" hidden></section>'
        + _hm_script(grid)
        + '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here is a '
        'recommendation to buy, sell or hold any security.</p>'
        '<div class="actions"><a class="btn btn-primary" href="/exposure">Every stock on record</a>'
        '<a class="btn btn-secondary" href="/forces">Every economic force</a></div>')
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title,
          "description": desc, "url": f"{base_url}/sectors"}
    any_measured = any(members_of(s, stocks) for s in sectors())
    return _shell(title, desc, f"{base_url}/sectors", ld, body, app_url,
                  robots="" if any_measured else "noindex, follow")


def sector_page_html(sector: str, stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    stocks = list(stocks)
    mem = members_of(sector, stocks)
    total = sum(1 for v in sector_by_ticker().values() if v == sector)
    canonical = f"{base_url}/sectors/{slug(sector)}"
    title = f"{sector} stocks: exposure to interest rates, oil, the dollar and more"
    newest = max((str(m.get("as_of") or "")[:10] for m in mem), default="")
    if not mem:
        desc = f"How {sector} stocks have moved with economic forces."
        body = ('<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › '
                f'<a href="/sectors">Sectors</a> › {escape(sector)}</nav><h1>{escape(sector)}</h1>'
                f'<p class="lead">None of the {total} {escape(sector)} companies in the S&amp;P 500 has '
                'been measured yet. Readings are added each week.</p>')
        return _shell(title, desc, canonical, {"@context": "https://schema.org", "@type": "WebPage",
                                               "name": title, "url": canonical},
                      body, app_url, robots="noindex, follow")
    cells = [(f, sector_cell(mem, f.key)) for f in tuple(ex.FACTORS) + tuple(ex.EXTRA_FACTORS)]
    cells = [(f, c) for f, c in cells if c["n"]]
    scale = max((abs(c["median"]) for _, c in cells if c["median"] is not None), default=0.0)
    summary = "".join(
        f'<tr id="f-{f.key}"><th scope="row"><a href="/forces/{f.key}">{escape(f.label)}</a>'
        f'<span class="shock">In weeks when {escape(f.shock_phrase)}</span></th>'
        f'{_cell_html(c, scale)}</tr>'
        for f, c in cells)
    desc = (f"How {len(mem)} of the {total} {sector} companies in the S&P 500 have moved with interest "
            "rates, oil, the dollar and more: the sector's median move and every stock's own reading.")
    others = "".join(f'<li><a href="/sectors/{slug(s)}">{escape(s)}</a></li>' for s in sectors() if s != sector)
    body = (
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › '
        f'<a href="/sectors">Sectors</a> › {escape(sector)}</nav>'
        f'<h1>{escape(sector)}</h1>'
        f'<p class="meta">{len(mem)} of {total} companies on record'
        + (f' · data through {_date(newest)}' if newest else "") + '</p>'
        f'<p class="lead">{escape(desc)}</p>'
        f'<h2>The sector as a whole</h2>'
        f'<div class="card" tabindex="0" role="region" aria-label="{escape(sector)}: median move on each force">'
        f'<table><thead><tr><th scope="col">Economic force</th><th scope="col">Median move</th></tr></thead>'
        f'<tbody>{summary}</tbody></table><div class="foot">{_FOOT} {_SHADE}</div></div>' + _HM_CSS +
        f'<h2>Every {escape(sector)} stock on record</h2>'
        + hub_grid_html(mem, f"{sector} stocks against the five core forces")
        + '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here is a '
          'recommendation to buy, sell or hold any security.</p>'
        f'<h2>Other sectors</h2><ul class="related">{others}</ul>')
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title,
          "description": desc, "url": canonical}
    if newest:
        ld["dateModified"] = newest
    return _shell(title, desc, canonical, ld, body, app_url)
