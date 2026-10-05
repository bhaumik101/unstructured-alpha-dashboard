# utils/explore_page.py
# Unstructured Alpha — "What if?": move one force, see which stocks moved with it
#
# Hands-on without a portfolio: pick a force, drag a slider for the size of the
# move, and the stocks on record that moved most with it -- up and down -- are
# ranked as you drag. No account, no upload, plain HTML plus a few lines of
# script, so it works on the public site where the Streamlit app cannot.
#
# RULES
#   * Only readings that held up (Clear or Tentative) are ranked; how many
#     stocks showed no measurable link is stated beside them.
#   * A stock's figure is its measured weekly sensitivity times the move, so it
#     is linear in the move. The slider stops at three standard moves; past
#     that the data has little to say.
#   * Past, not forecast; the track record's carry-over sits beside the result.

from __future__ import annotations

import json
from html import escape
from typing import Iterable, Optional

from utils import exposure as ex
from utils.exposure_pages import _date, _shell
from utils.force_pages import ALL_FORCES, GROUP_LABELS, force_stats

UNITS = {"volatility": "pts"}          # everything else follows its transform
MAX_MULTIPLE = 3.0


def _unit(f: ex.Factor) -> str:
    return UNITS.get(f.key) or ("%" if f.transform == "pct" else "pp")


def explore_data(stocks: Iterable[dict]) -> dict:
    """What the page's script needs: each force's standard move and unit, and
    the stocks whose reading on it held up (ticker, name, impact per move)."""
    stocks = list(stocks)
    forces, newest = [], ""
    for f in ALL_FORCES:
        st = force_stats(f.key, stocks)
        if not st["measured"]:
            continue
        newest = max(newest, st["as_of"])
        rows = [[r["ticker"], r.get("name") or "", round(float(r["impact"]), 4), r["evidence"]]
                for r in st["up"] + st["down"]]
        forces.append({"key": f.key, "label": f.label, "group": GROUP_LABELS.get(f.group, ""),
                       "step": abs(f.shock), "unit": _unit(f), "phrase": f.shock_phrase,
                       "measured": st["measured"], "none": st["none"], "rows": rows})
    return {"forces": forces, "as_of": newest}


_SCRIPT = r"""
(function(){
  var D = JSON.parse(document.getElementById('xp-data').textContent);
  var sel = document.getElementById('xp-force'), sl = document.getElementById('xp-move');
  var out = document.getElementById('xp-out'), say = document.getElementById('xp-say');
  function fmt(v, unit){ var s = (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(unit === '%' ? (Math.abs(v) < 1 ? 1 : 0) : 2);
    return unit === '%' ? s + '%' : s + ' ' + unit; }
  function pct(v){ var a = Math.abs(v); return (v > 0 ? '+' : v < 0 ? '−' : '') + (a < 10 ? a.toFixed(1) : a.toFixed(0)) + '%'; }
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function bars(rows, k, max, title){
    if (!rows.length) return '<h2>' + title + '</h2><p class="small">No stock on record moved this way in a way that held up.</p>';
    return '<h2>' + title + '</h2><ol class="xp-list">' + rows.map(function(r){
      var v = r[2] * k, w = max ? Math.max(2, 100 * Math.abs(v) / max) : 2;
      return '<li><a href="/exposure/' + encodeURIComponent(r[0]) + '"><b>' + esc(r[0]) + '</b><span>' + esc(r[1]) + '</span></a>'
        + '<span class="xp-track" aria-hidden="true"><span class="xp-bar ' + (v >= 0 ? 'xp-up' : 'xp-down') + '" style="width:' + w.toFixed(1) + '%"></span></span>'
        + '<span class="xp-v">' + pct(v) + '</span>'
        + '<span class="xp-t">' + (r[3] === 'tentative' ? 'tentative' : '') + '</span></li>';
    }).join('') + '</ol>';
  }
  function draw(){
    var f = D.forces[sel.selectedIndex], k = parseFloat(sl.value), move = k * f.step;
    document.getElementById('xp-move-label').textContent = f.label + ' ' + fmt(move, f.unit);
    if (k === 0){ out.innerHTML = '<p class="lead">Move the slider to see which stocks moved most with ' + esc(f.label.toLowerCase()) + '.</p>'; say.textContent = ''; return; }
    var rows = f.rows.map(function(r){ return [r[0], r[1], r[2], r[3]]; });
    rows.sort(function(a, b){ return b[2] * k - a[2] * k; });
    var up = rows.filter(function(r){ return r[2] * k > 0; }).slice(0, 10);
    var down = rows.filter(function(r){ return r[2] * k < 0; }).reverse().slice(0, 10);
    var max = Math.max.apply(null, up.concat(down).map(function(r){ return Math.abs(r[2] * k); }).concat([0]));
    out.innerHTML = bars(up, k, max, 'Rose most in weeks like this') + bars(down, k, max, 'Fell most in weeks like this')
      + '<p class="small">' + f.none + ' of ' + f.measured + ' stocks on record showed no link to '
      + esc(f.label.toLowerCase()) + ' that could be told apart from noise, so they are not ranked.</p>';
    say.textContent = 'With ' + f.label.toLowerCase() + ' ' + fmt(move, f.unit) + ': ' + up.length + ' stocks shown rising and ' + down.length + ' falling.';
  }
  D.forces.forEach(function(f, i){ var o = document.createElement('option'); o.value = f.key; o.textContent = f.label + ' (' + f.group + ')'; sel.appendChild(o); });
  // The hash carries the force and, optionally, the move: #oil or #oil:-1.5,
  // so a link opens the same scenario. Anything unreadable falls back.
  var parts = decodeURIComponent((location.hash || '').slice(1)).split(':'), want = parts[0];
  var k0 = parseFloat(parts[1]);
  if (parts.length > 1 && isFinite(k0) && Math.abs(k0) <= parseFloat(sl.max) && Math.round(k0 * 2) === k0 * 2) sl.value = String(k0);
  var at = D.forces.findIndex(function(f){ return f.key === want; });
  if (at >= 0) sel.selectedIndex = at; else { at = D.forces.findIndex(function(f){ return f.key === 'oil'; }); if (at >= 0) sel.selectedIndex = at; }
  function remember(){ history.replaceState(null, '', '#' + D.forces[sel.selectedIndex].key + ':' + parseFloat(sl.value)); }
  sel.addEventListener('change', function(){ remember(); draw(); });
  sl.addEventListener('input', function(){ remember(); draw(); });
  draw();
})();
"""

_CSS = """<style>
.xp-form{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:16px;align-items:end;
  background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px;margin:8px 0 6px}
.xp-form label{display:block;font-weight:650;font-size:.92rem;margin-bottom:6px}
.xp-form select,.xp-form input{width:100%;min-height:44px;font:inherit}
.xp-form select{border:1px solid var(--line);border-radius:10px;padding:0 10px;background:var(--bg);color:var(--ink)}
.xp-now{font-size:1.25rem;font-weight:750;font-variant-numeric:tabular-nums}
.xp-ticks{display:flex;justify-content:space-between;font-size:.82rem;color:var(--ink3)}
.xp-list{list-style:none;margin:0;padding:0;border:1px solid var(--line);border-radius:12px;background:var(--surface)}
.xp-list li{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1.5fr) 64px 64px;gap:12px;align-items:center;
  padding:9px 12px;border-bottom:1px solid var(--line)}
.xp-list li:last-child{border-bottom:0}
.xp-list a{text-decoration:none;color:var(--ink);display:flex;flex-direction:column;min-width:0}
.xp-list a span{font-size:.82rem;color:var(--ink3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.xp-track{height:12px;background:var(--subtle);border-radius:6px;position:relative}
.xp-bar{position:absolute;left:0;top:0;bottom:0;border-radius:6px}
.xp-up{background:#2f6fbd}.xp-down{background:#b5651d}
@media (prefers-color-scheme:dark){.xp-up{background:#5a8fd4}.xp-down{background:#c9822f}}
.xp-v{text-align:right;font-weight:700;font-variant-numeric:tabular-nums}
.xp-t{font-size:.78rem;color:var(--ink3)}
@media (max-width:640px){.xp-form{grid-template-columns:1fr}.xp-list li{grid-template-columns:minmax(0,1fr) 64px}.xp-track,.xp-t{display:none}}
</style>"""


def explore_page_html(stocks: Iterable[dict], base_url: str, app_url: str,
                      carry: Optional[float] = None) -> str:
    data = explore_data(stocks)
    canonical = f"{base_url}/explore"
    title = "What if? Move an economic force and see which stocks moved with it"
    desc = ("Pick a force — oil, interest rates, the dollar, gold and more — choose the size of the "
            "move, and see which U.S. stocks have risen and fallen most in weeks like it.")
    n_stocks = max((f["measured"] for f in data["forces"]), default=0)
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    carry_note = (f' In the published <a href="/evidence">track record</a>, readings measured this way '
                  f'were on average about {100 * carry:.0f}% as large the following year.'
                  if carry is not None and 0 < carry < 1.5 else "")
    if not data["forces"]:
        body = ('<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › What if?</nav>'
                '<h1>What if?</h1><p class="lead">No stock has been measured yet, so there is '
                'nothing to explore. Readings are added each week.</p>')
        return _shell(title, desc, canonical, {"@context": "https://schema.org", "@type": "WebPage",
                                               "name": title, "url": canonical},
                      body, app_url, robots="noindex, follow")
    body = (
        _CSS +
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › What if?</nav>'
        '<h1>What if?</h1>'
        f'<p class="meta">{n_stocks:,} U.S. stocks on record'
        + (f' · data through {_date(data["as_of"])}' if data["as_of"] else "") + '</p>'
        f'<p class="lead">{escape(desc)}</p>'
        '<form class="xp-form" onsubmit="return false">'
        '<div><label for="xp-force">Economic force</label><select id="xp-force"></select></div>'
        '<div><label for="xp-move">Size of the move: <span class="xp-now" id="xp-move-label"></span></label>'
        f'<input type="range" id="xp-move" min="{-MAX_MULTIPLE:g}" max="{MAX_MULTIPLE:g}" step="0.5" value="2" '
        'aria-describedby="xp-ticks">'
        '<div class="xp-ticks" id="xp-ticks"><span>Fell</span><span>No change</span><span>Rose</span></div></div>'
        '</form>'
        '<p class="sr-only" aria-live="polite" id="xp-say" style="position:absolute;left:-9999px"></p>'
        '<div id="xp-out"></div>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Each figure is a '
        'stock&#39;s measured weekly sensitivity to the force, after the stock market&#39;s own move, '
        'times the size of the move you chose — so it scales in a straight line, and the slider stops '
        f'at three times the standard move.{carry_note} Nothing here is a recommendation to buy, sell '
        'or hold any security.</p>'
        f'<div class="actions"><a class="btn btn-primary" href="{escape(app_url)}/scenarios">Try a move on a '
        'whole portfolio</a><a class="btn btn-secondary" href="/quiz">Daily quiz</a><a class="btn btn-secondary" href="/forces">Every economic force</a></div>'
        f'<script type="application/json" id="xp-data">{payload}</script>'
        f'<script>{_SCRIPT}</script>')
    json_ld = {"@context": "https://schema.org", "@type": "WebApplication", "name": title,
               "description": desc, "url": canonical, "applicationCategory": "FinanceApplication",
               "isAccessibleForFree": True}
    return _shell(title, desc, canonical, json_ld, body, app_url)


# ── One stock: the same slider, on its own page ──────────────────────────────

_STOCK_SCRIPT = r"""
(function(){
  var D = JSON.parse(document.getElementById('sw-data').textContent);
  var sel = document.getElementById('sw-force'), sl = document.getElementById('sw-move');
  var out = document.getElementById('sw-out');
  function sgn(v){ return v > 0 ? '+' : v < 0 ? '−' : ''; }
  function fmt(v, unit){ var a = Math.abs(v), s = sgn(v) + a.toFixed(unit === '%' ? (a < 1 ? 1 : 0) : 2);
    return unit === '%' ? s + '%' : s + ' ' + unit; }
  function pct(v){ var a = Math.abs(v); return sgn(v) + (a < 10 ? a.toFixed(1) : a.toFixed(0)) + '%'; }
  function draw(){
    var f = D.forces[sel.selectedIndex], k = parseFloat(sl.value), move = k * f.step;
    document.getElementById('sw-move-label').textContent = f.label + ' ' + fmt(move, f.unit);
    document.getElementById('sw-all').href = '/explore#' + f.key;
    if (k === 0){ out.textContent = 'Move the slider to size the move.'; return; }
    var a = f.low * k, b = f.high * k;
    out.innerHTML = 'In weeks like that, ' + D.ticker + ' typically moved <b>' + pct(f.impact * k)
      + '</b> beyond the market (90% range ' + pct(Math.min(a, b)) + ' to ' + pct(Math.max(a, b)) + ').'
      + (f.evidence === 'tentative' ? ' The evidence is tentative.' : '');
  }
  D.forces.forEach(function(f){ var o = document.createElement('option'); o.value = f.key; o.textContent = f.label; sel.appendChild(o); });
  sel.addEventListener('change', draw); sl.addEventListener('input', draw);
  draw();
})();
"""


def stock_whatif_data(symbol: str, rec: dict) -> dict:
    """The forces this stock's reading held up on, largest first, with the
    figures the slider scales. Readings that did not hold up are left out:
    sizing a move on a figure indistinguishable from zero would invent one."""
    from utils.exposure_pages import STANDS_UP
    from utils.force_pages import FORCE_BY_KEY
    exps = rec.get("exposures") or {}
    forces = []
    for key, e in sorted(exps.items(), key=lambda kv: -abs(kv[1].get("impact") or 0)):
        f = FORCE_BY_KEY.get(key)
        if f is None or e.get("evidence") not in STANDS_UP:
            continue
        forces.append({"key": key, "label": f.label, "step": abs(f.shock), "unit": _unit(f),
                       "impact": round(float(e["impact"]), 4), "low": round(float(e["low"]), 4),
                       "high": round(float(e["high"]), 4), "evidence": e["evidence"]})
    return {"ticker": symbol, "forces": forces}


def stock_whatif_html(symbol: str, rec: dict) -> str:
    """A slider card for the stock page, or "" when no reading held up."""
    data = stock_whatif_data(symbol, rec)
    if not data["forces"]:
        return ""
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return (
        _CSS +
        '<h2>What if?</h2>'
        '<form class="xp-form" onsubmit="return false">'
        '<div><label for="sw-force">Economic force</label><select id="sw-force"></select></div>'
        '<div><label for="sw-move">Size of the move: <span class="xp-now" id="sw-move-label"></span></label>'
        f'<input type="range" id="sw-move" min="{-MAX_MULTIPLE:g}" max="{MAX_MULTIPLE:g}" step="0.5" value="2" '
        'aria-describedby="sw-ticks">'
        '<div class="xp-ticks" id="sw-ticks"><span>Fell</span><span>No change</span><span>Rose</span></div></div>'
        '</form>'
        '<p class="lead" id="sw-out" aria-live="polite"></p>'
        '<p class="small">Only the forces whose reading held up are offered. The figure scales in a '
        'straight line with the move and describes the past; it is not a forecast. '
        f'<a id="sw-all" href="/explore#{escape(data["forces"][0]["key"])}">See every stock on record for a move like this</a>.</p>'
        f'<script type="application/json" id="sw-data">{payload}</script>'
        f'<script>{_STOCK_SCRIPT}</script>')
