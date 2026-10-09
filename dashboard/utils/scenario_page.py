# utils/scenario_page.py
# Unstructured Alpha — build a scenario: move all five core forces at once
#
# What if? moves one force. Real weeks move several: an inflation scare lifts
# inflation expectations and Treasury yields together; a credit scare widens
# spreads and lifts the dollar. Here every core force gets its own slider (or
# a preset sets them), and each stock's figure is the sum of its typical
# moves, force by force -- which is what the joint measurement means, since
# the core five are measured together, each with the others held fixed.
#
# RULES
#   * Only stocks measured on all five are placed: a missing reading is never
#     treated as zero.
#   * A stock's figure is bold only when every force you moved has a reading
#     on it that held up; otherwise it is grey and says so. Every reading
#     still counts toward the sum -- each is the best estimate there is.
#   * No range on the sum: combining ranges needs how the estimates move
#     together, which these pages do not have. The app's scenario lab does.
#   * Presets are labelled as hypothetical moves, never as forecasts.

from __future__ import annotations

import json
from html import escape
from typing import Iterable

from utils import exposure as ex
from utils.explore_page import _CSS as XP_CSS, JS_PCT, MAX_MULTIPLE, _unit
from utils.exposure_pages import STANDS_UP, _date, _shell

# Moves in multiples of each force's standard move. Hypothetical, not forecasts.
PRESETS = (
    ("Inflation scare", {"inflation": 2, "rates": 2}),
    ("Oil shock", {"oil": 3}),
    ("Rates jump", {"rates": 2}),
    ("Strong dollar", {"dollar": 2}),
    ("Credit stress", {"credit": 2, "dollar": 1}),
    ("Easing", {"rates": -2, "credit": -1}),
)


def scenario_data(stocks: Iterable[dict]) -> dict:
    keys = [f.key for f in ex.FACTORS]
    rows, newest, partial = [], "", 0
    for s in stocks:
        exps = s.get("exposures") or {}
        if not s.get("ticker") or not exps:
            continue
        if not all(k in exps for k in keys):
            partial += 1
            continue
        newest = max(newest, str(s.get("as_of") or "")[:10])
        rows.append([s["ticker"], s.get("name") or "",
                     [round(float(exps[k]["impact"]), 4) for k in keys],
                     "".join("1" if exps[k].get("evidence") in STANDS_UP else "0" for k in keys)])
    rows.sort(key=lambda r: r[0])
    return {"f": [{"key": f.key, "label": f.label, "step": abs(f.shock), "unit": _unit(f),
                   "phrase": f.shock_phrase, "lower": ex.lower_label(f.label)} for f in ex.FACTORS],
            "s": rows, "partial": partial, "as_of": newest,
            "presets": [[name, {k: v for k, v in moves.items()}] for name, moves in PRESETS]}


_SC_CSS = """<style>
.sc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px 18px;background:var(--surface);
  border:1px solid var(--line);border-radius:12px;padding:16px;margin:8px 0 10px}
.sc-grid label{display:flex;justify-content:space-between;gap:8px;font-weight:650}
.sc-grid input[type=range]{width:100%;min-height:32px}
.sc-pre{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 6px}
.sc-pre button{min-height:40px}
.sc-pre button[aria-pressed=true]{outline:2px solid var(--accent)}
.sc-cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:760px){.sc-cols{grid-template-columns:1fr}}
.sc-mine{border-color:var(--accent)!important}
.sc-now{font-weight:750;white-space:nowrap;font-variant-numeric:tabular-nums;color:var(--accent)}
.xp-v .v-weak{font-weight:400}
.sc-grid label span:first-child{min-width:0}
</style>"""

_SCRIPT = r"""
(function(){
  var D = JSON.parse(document.getElementById('sc-data').textContent);
/*PCT*/
  var $ = function(id){ return document.getElementById(id); };
  var grid = $('sc-grid'), out = $('sc-out'), say = $('sc-say'), pre = $('sc-pre');
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function fmt(v, unit){ var s = (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(unit === '%' ? (Math.abs(v) < 1 ? 1 : 0) : 2);
    return v === 0 ? 'no change' : unit === '%' ? s + '%' : s + ' ' + unit; }
  var mine = []; try { mine = JSON.parse(localStorage.getItem('ua-list') || '[]'); } catch (e) {}
  var k = D.f.map(function(){ return 0; });
  grid.innerHTML = D.f.map(function(f, i){
    return '<div><label for="sc-' + f.key + '"><span>' + esc(f.label) + '</span><span class="sc-now" id="sc-v-' + f.key + '"></span></label>'
      + '<input type="range" id="sc-' + f.key + '" min="-__MAX__" max="__MAX__" step="0.5" value="0" data-i="' + i + '" '
      + 'aria-describedby="sc-h-' + f.key + '"><span class="xp-hint" id="sc-h-' + f.key + '">Standard move: ' + esc(f.phrase) + '</span></div>';
  }).join('');
  pre.innerHTML = D.presets.map(function(p, i){ return '<button type="button" class="btn btn-secondary" data-p="' + i + '" aria-pressed="false">' + esc(p[0]) + '</button>'; }).join('')
    + '<button type="button" class="btn btn-secondary" data-p="-1">Reset</button>';
  function list(rows, max, title){
    if (!rows.length) return '<div><h2>' + title + '</h2><p class="small">None.</p></div>';
    return '<div><h2>' + title + '</h2><ol class="xp-list">' + rows.map(function(r){
      var w = max ? Math.max(2, 100 * Math.abs(r.v) / max) : 2, on = mine.indexOf(r.t) >= 0;
      return '<li' + (on ? ' class="sc-mine"' : '') + '><a href="/exposure/' + encodeURIComponent(r.t) + '"><b>' + esc(r.t) + (on ? ' ★' : '') + '</b><span>' + esc(r.n) + '</span></a>'
        + '<span class="xp-track" aria-hidden="true"><span class="xp-bar ' + (r.v >= 0 ? 'xp-up' : 'xp-down') + '" style="width:' + w.toFixed(1) + '%"></span></span>'
        + '<span class="xp-v">' + (r.held ? pct(r.v) : '<span class="v-weak">' + pct(r.v) + '</span>') + '</span>'
        + '<span class="xp-t">' + (r.held ? '' : 'not all held up') + '</span></li>';
    }).join('') + '</ol></div>';
  }
  function draw(){
    D.f.forEach(function(f, i){ $('sc-v-' + f.key).textContent = fmt(k[i] * f.step, f.unit); });
    var moved = k.map(function(x, i){ return x !== 0 ? i : -1; }).filter(function(i){ return i >= 0; });
    var p = D.presets.findIndex(function(p){ return D.f.every(function(f, i){ return (p[1][f.key] || 0) === k[i]; }); });
    pre.querySelectorAll('[data-p]').forEach(function(b){ b.setAttribute('aria-pressed', String(+b.getAttribute('data-p') === p && p >= 0)); });
    try { history.replaceState(null, '', moved.length ? '#' + moved.map(function(i){ return D.f[i].key + ':' + k[i]; }).join(',') : location.pathname); } catch (e) {}
    if (!moved.length){ out.innerHTML = '<p class="lead">Move a slider or pick a scenario above.</p>'; say.textContent = ''; return; }
    var rows = D.s.map(function(s){
      var v = 0; moved.forEach(function(i){ v += s[2][i] * k[i]; });
      return {t: s[0], n: s[1], v: v, held: moved.every(function(i){ return s[3].charAt(i) === '1'; })};
    });
    rows.sort(function(a, b){ return b.v - a.v || (a.t < b.t ? -1 : 1); });
    var up = rows.filter(function(r){ return r.v > 0; }).slice(0, 10);
    var down = rows.filter(function(r){ return r.v < 0; }).reverse().slice(0, 10);
    var max = Math.max.apply(null, up.concat(down).map(function(r){ return Math.abs(r.v); }).concat([0]));
    var held = rows.filter(function(r){ return r.held; }).length;
    var mineRows = rows.filter(function(r){ return mine.indexOf(r.t) >= 0; });
    var mineHtml = mineRows.length ? list(mineRows, max, 'Your list') : '';
    out.innerHTML = mineHtml + '<div class="sc-cols">' + list(up, max, 'Rose most in weeks like this') + list(down, max, 'Fell most in weeks like this') + '</div>'
      + '<p class="small">Across ' + rows.length + ' stocks measured on all five forces. ' + held + ' have readings that held up on every force you moved; '
      + 'the rest are grey, because at least one of the readings behind their figure could not be told apart from zero.'
      + (D.partial ? ' ' + D.partial + ' more stocks lack a reading on one of the five and are left out.' : '') + '</p>';
    say.textContent = 'Scenario: ' + moved.map(function(i){ return D.f[i].lower + ' ' + fmt(k[i] * D.f[i].step, D.f[i].unit); }).join(', ') + '.';
  }
  function set(vals){ D.f.forEach(function(f, i){ k[i] = vals[i]; $('sc-' + f.key).value = String(vals[i]); }); draw(); }
  grid.addEventListener('input', function(e){ var i = e.target.getAttribute('data-i'); if (i === null) return; k[+i] = parseFloat(e.target.value); draw(); });
  pre.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('[data-p]'); if (!b) return;
    var p = D.presets[+b.getAttribute('data-p')];
    set(D.f.map(function(f){ return p ? (p[1][f.key] || 0) : 0; }));
  });
  // #rates:2,oil:-1 opens that scenario; anything unreadable is ignored.
  var start = D.f.map(function(){ return 0; });
  (location.hash || '').slice(1).split(',').forEach(function(part){
    var kv = part.split(':'), i = D.f.findIndex(function(f){ return f.key === kv[0]; }), v = parseFloat(kv[1]);
    if (i >= 0 && isFinite(v) && Math.abs(v) <= __MAX__ && Math.round(v * 2) === v * 2) start[i] = v;
  });
  set(start);
})();
""".replace("__MAX__", f"{MAX_MULTIPLE:g}")


def scenario_page_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    data = scenario_data(stocks)
    canonical = f"{base_url}/scenario"
    title = "Build a scenario: move rates, inflation, the dollar, oil and credit at once"
    desc = ("Set interest rates, inflation expectations, the dollar, oil and credit spreads together — "
            "or pick a scenario like an inflation scare — and see which U.S. stocks rose and fell most "
            "in weeks like it.")
    crumb = '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Build a scenario</nav>'
    ld = {"@context": "https://schema.org", "@type": "WebApplication", "name": title,
          "description": desc, "url": canonical, "applicationCategory": "FinanceApplication",
          "isAccessibleForFree": True}
    if not data["s"]:
        body = (crumb + '<h1>Build a scenario</h1><p class="lead">No stock has been measured on all five '
                'core forces yet. Readings are added each week.</p>')
        return _shell(title, desc, canonical, ld, body, app_url, robots="noindex, follow")
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    body = (
        XP_CSS + _SC_CSS + crumb +
        '<h1>Build a scenario</h1>'
        f'<p class="meta">{len(data["s"]):,} stocks measured on all five'
        + (f' · data through {_date(data["as_of"])}' if data["as_of"] else "") + '</p>'
        f'<p class="lead">{escape(desc)}</p>'
        '<div class="sc-pre" id="sc-pre" role="group" aria-label="Scenarios"></div>'
        '<p class="small">Scenarios are hypothetical moves to explore, not forecasts. Each slider is in '
        f'steps of half that force&#39;s standard move, up to {MAX_MULTIPLE:g} times it either way.</p>'
        '<div class="sc-grid" id="sc-grid"></div>'
        '<p class="small" id="sc-say" aria-live="polite"></p>'
        '<div id="sc-out"><noscript><p class="lead">The scenario builder needs JavaScript. '
        '<a href="/forces">Each force on its own</a> works without it.</p></noscript></div>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Each figure adds up a '
        'stock&#39;s typical weekly move with each force you moved, beyond the market. The core five are '
        'measured together, each with the others held fixed, so adding them is what the measurement '
        'means; no range is shown, because combining ranges needs more than these pages carry. Stocks '
        'saved to <a href="/mylist">My list</a> are marked ★. Nothing here is a recommendation to buy, '
        'sell or hold any security.</p>'
        f'<div class="actions"><a class="btn btn-primary" href="{escape(app_url)}/scenarios">Run it on a whole '
        'portfolio, with ranges</a><a class="btn btn-secondary" href="/explore">One force at a time</a></div>'
        f'<script type="application/json" id="sc-data">{payload}</script>'
        f'<script>{_SCRIPT.replace("/*PCT*/", JS_PCT)}</script>')
    return _shell(title, desc, canonical, ld, body, app_url)
