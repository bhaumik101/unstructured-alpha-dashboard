# utils/xray_page.py
# Unstructured Alpha — /xray: a portfolio's economic fingerprint in seconds
#
# Click stocks and funds (or a starter mix); the page shows how the mix has
# moved with interest rates, inflation, the dollar, oil and credit, which
# holding drives each, and hands the mix to the app's full report. Weights are
# equal by default, set by hand, or "balanced": the mix that, over the last
# three years, would have been least moved by the five forces.
#
# RULES
#   * The mix's figure for a force is the weighted average of each holding's
#     typical move -- what the blend's own reading would be over the same
#     weeks. A force is left out unless every holding has a reading on it.
#   * No range is shown for the blend: combining ranges needs how the holdings
#     move together, which only the full report (it measures the portfolio
#     itself) has. The page says how much of the weight comes from readings
#     that held up, and never bolds the blend.
#   * Funds that track the S&P 500 (VOO, VTI, ...) count as zero: every reading
#     is beyond the stock market's own move, and they are that move.
#   * "Balanced" is a calculation on past readings, labelled as one. It is not
#     a recommendation or a forecast, and the page never says buy or sell.

from __future__ import annotations

import json
from html import escape
from typing import Iterable

from utils.explore_page import JS_PCT
from utils.exposure_pages import _shell, app_link, tool_header_html
from utils.funds import MARKET_TRACKERS
from utils.list_page import list_data

PRESETS = (
    ("Big tech", "AAPL MSFT NVDA GOOGL AMZN META"),
    ("Dividend income", "SCHD VYM KO PG JNJ XLU"),
    ("Classic 60/40", "VTI AGG"),
    ("Real assets", "XLE GLD VNQ TIP"),
    ("Banks and rates", "JPM BAC KRE TLT"),
)
QUICK = "NVDA AAPL MSFT AMZN TSLA JPM XOM KO QQQ SCHD TLT GLD".split()
MAX_HOLDINGS = 20

_CSS = """<style>
.xr-pick{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0 4px}
.xr-pick input{min-height:44px;font:inherit;border:1px solid var(--line);border-radius:10px;padding:0 12px;
  background:var(--surface);color:var(--ink);flex:1 1 220px;max-width:360px}
.xr-row{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.xr-row .small{align-self:center;margin-right:4px}
.xr-chip{border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px;
  padding:6px 12px;font:inherit;cursor:pointer;min-height:36px}
.xr-chip:hover{border-color:var(--accent)}.xr-chip:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.xr-hold{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0;padding:0;list-style:none}
.xr-hold li{display:flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:12px;
  background:var(--surface);padding:6px 6px 6px 12px}
.xr-hold b{font-variant-numeric:tabular-nums}
.xr-hold button{all:unset;cursor:pointer;width:28px;height:28px;display:grid;place-items:center;border-radius:8px;color:var(--ink3)}
.xr-hold button:hover{background:var(--subtle);color:var(--ink)}.xr-hold button:focus-visible{outline:2px solid var(--accent)}
.xr-modes{display:inline-flex;border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:4px 0 8px}
.xr-modes button{all:unset;cursor:pointer;padding:10px 16px;min-height:24px;color:var(--ink2)}
.xr-modes button[aria-pressed=true]{background:var(--accent);color:var(--bg);font-weight:650}
.xr-modes button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.xr-out{margin-top:14px;padding:16px 18px}
.xr-head{line-height:1.4;margin:0 0 12px;font-weight:500}
.xr-bars{list-style:none;margin:0;padding:0}
.xr-bars li{display:grid;grid-template-columns:minmax(120px,190px) 1fr 72px;gap:12px;align-items:center;padding:10px 0;
  border-top:1px solid var(--line)}
.xr-bars li:first-child{border-top:0}
.xr-track{position:relative;height:14px;background:var(--subtle);border-radius:7px}
.xr-track i{position:absolute;top:0;bottom:0;border-radius:7px}
.xr-track:before{content:"";position:absolute;left:50%;top:-4px;bottom:-4px;width:1px;background:var(--ink3)}
.xr-v{text-align:right;font-variant-numeric:tabular-nums;font-weight:650}
.xr-why{grid-column:1/-1;color:var(--ink2)}
.xr-na{color:var(--ink3)}
.xr-adj summary{cursor:pointer;color:var(--accent);margin:10px 0}
.xr-adj label{display:grid;grid-template-columns:70px 1fr 56px;gap:10px;align-items:center;margin:6px 0}
.xr-adj input[type=range]{width:100%}
@media (max-width:560px){.xr-bars li{grid-template-columns:1fr 64px}.xr-track{grid-column:1/-1;order:3}}
</style>"""


def xray_data(stocks: Iterable[dict]) -> dict:
    d = list_data(stocks)
    d["mkt"] = sorted(MARKET_TRACKERS)
    return d


def xray_page_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    data = xray_data(stocks)
    canonical = f"{base_url}/xray"
    title = "Portfolio X-ray: how your stocks and funds move with rates, inflation, oil and the dollar"
    desc = ("Click the stocks and ETFs you own and see, in seconds, how the mix has moved with interest "
            "rates, inflation, the dollar, oil and credit, and which holding drives each.")
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    opts = "".join(f'<option value="{escape(t)}">{escape(v[0])}</option>' for t, v in sorted(data["s"].items()))
    opts += "".join(f'<option value="{t}">Tracks the S&amp;P 500</option>' for t in data["mkt"])
    presets = "".join(f'<button type="button" class="xr-chip" data-preset="{escape(p)}">{escape(n)}</button>'
                      for n, p in PRESETS)
    quick = "".join(f'<button type="button" class="xr-chip" data-add="{t}">+ {t}</button>'
                    for t in QUICK if t in data["s"])
    script = _SCRIPT.replace("/*PCT*/", JS_PCT).replace("__MAX__", str(MAX_HOLDINGS))
    body = (
        _CSS + '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Portfolio X-ray</nav>'
        + tool_header_html("Portfolio X-ray", [f"{len(data['s']):,} stocks and ETFs", "No account needed",
                                               "Nothing leaves your browser"],
                           "Click what you own. See how the mix has moved with the economy, beyond the stock "
                           "market&#39;s own move, and which holding drives it.")
        + '<div class="xr-row"><span class="small">Start from a mix:</span>' + presets + '</div>'
        + '<form class="xr-pick" id="xr-form" onsubmit="return false">'
          '<label for="xr-q" class="small">Add a stock or ETF</label>'
          '<input id="xr-q" list="xr-list" autocomplete="off" spellcheck="false" placeholder="Ticker, e.g. NVDA">'
          f'<datalist id="xr-list">{opts}</datalist>'
          '<button type="submit" class="btn btn-primary" id="xr-add">Add</button></form>'
        + '<div class="xr-row"><span class="small">Popular:</span>' + quick + '</div>'
        + '<ul class="xr-hold" id="xr-hold" aria-label="Your holdings"></ul>'
        + '<p class="small" id="xr-say" aria-live="polite"></p>'
        + '<div class="xr-modes" role="group" aria-label="How to weight the holdings">'
          '<button type="button" data-mode="equal" aria-pressed="true">Equal weight</button>'
          '<button type="button" data-mode="balance" aria-pressed="false">Balance the forces</button>'
          '<button type="button" data-mode="manual" aria-pressed="false">Set my own</button></div>'
        + '<p class="small" id="xr-mode-note"></p>'
        + '<details class="xr-adj" id="xr-adj"><summary>Adjust weights</summary><div id="xr-sliders"></div></details>'
        + '<section class="card xr-out" id="xr-out" aria-live="polite"><p class="small">Add two or more holdings, '
          'or start from a mix above.</p></section>'
        + '<p class="small">Each figure is the mix&#39;s typical weekly move, beyond the stock market&#39;s own '
          'move, in weeks when that force moved by its standard amount: the weighted average of each '
          'holding&#39;s own reading over the last three years. Funds that track the S&amp;P 500 count as zero. '
          'The full report measures the portfolio itself, with a 90% range and an evidence label on every '
          'number.</p>'
        + '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here, the '
          'balanced weights included, is a recommendation to buy, sell or hold any security.</p>'
        + '<div class="actions">'
          f'<a class="btn btn-primary" id="xr-report" href="{escape(app_link(app_url, "/", canonical))}">'
          'Get the full report, free</a>'
          '<button type="button" class="btn btn-secondary" id="xr-share">Copy a link to this mix</button>'
          '<a class="btn btn-secondary" href="/learn">How to read this</a></div>'
        + f'<script type="application/json" id="xr-data">{payload}</script><script>{script}</script>')
    ld = {"@context": "https://schema.org", "@type": "WebApplication", "name": title, "description": desc,
          "url": canonical, "applicationCategory": "FinanceApplication", "isAccessibleForFree": True}
    return _shell(title, desc, canonical, ld, body, app_url)


_SCRIPT = r"""
(function(){
  /*PCT*/
  var D = JSON.parse(document.getElementById('xr-data').textContent), MAX = __MAX__;
  var MKT = {}; D.mkt.forEach(function(t){ MKT[t] = 1; });
  var $ = function(id){ return document.getElementById(id); };
  var held = [], mode = 'equal', manual = {}, weights = {};
  function known(t){ return !!D.s[t] || !!MKT[t]; }
  function name(t){ return D.s[t] ? D.s[t][0] : (MKT[t] ? 'Tracks the S&P 500' : t); }
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  // A holding's vector over the five forces: its typical moves, zeros for a
  // market tracker, null where a force was not measured.
  function vec(t){ return MKT[t] ? D.f.map(function(){ return [0, 1]; }) : D.s[t][2]; }

  // Balanced weights: minimise the squared length of the mix's exposure
  // vector over the forces every holding has, each weight between 5% and 60%
  // (100% for one holding). Projected gradient onto the bounded simplex.
  function project(w, lo, hi){
    var a = -10, b = 10;
    for (var k = 0; k < 60; k++){ var m = (a + b) / 2, s = 0;
      w.forEach(function(x){ s += Math.min(hi, Math.max(lo, x - m)); });
      if (s > 1) a = m; else b = m; }
    var m2 = (a + b) / 2; return w.map(function(x){ return Math.min(hi, Math.max(lo, x - m2)); });
  }
  function balance(ts){
    var n = ts.length; if (n === 1) return [1];
    var lo = n * 0.05 <= 1 ? 0.05 : 0, hi = Math.max(0.6, 1 / n);
    var ks = D.f.map(function(_, i){ return i; }).filter(function(i){ return ts.every(function(t){ return vec(t)[i]; }); });
    var B = ts.map(function(t){ return ks.map(function(i){ return vec(t)[i][0]; }); });
    var w = ts.map(function(){ return 1 / n; }), lr = 0.02;
    var scale = 0; B.forEach(function(r){ r.forEach(function(x){ scale = Math.max(scale, Math.abs(x)); }); });
    if (!scale || !ks.length) return w;
    for (var it = 0; it < 4000; it++){
      var e = ks.map(function(_, j){ var s = 0; for (var i = 0; i < n; i++) s += w[i] * B[i][j]; return s; });
      var g = B.map(function(r){ var s = 0; for (var j = 0; j < r.length; j++) s += 2 * r[j] * e[j]; return s; });
      w = project(w.map(function(x, i){ return x - lr * g[i] / (scale * scale); }), lo, hi);
    }
    return w;
  }
  function computeWeights(){
    weights = {};
    if (!held.length) return;
    if (mode === 'balance'){ var b = balance(held); held.forEach(function(t, i){ weights[t] = b[i]; }); return; }
    if (mode === 'manual'){ var s = 0; held.forEach(function(t){ s += (manual[t] == null ? 10 : manual[t]); });
      held.forEach(function(t){ weights[t] = s ? (manual[t] == null ? 10 : manual[t]) / s : 1 / held.length; }); return; }
    held.forEach(function(t){ weights[t] = 1 / held.length; });
  }

  function drawHoldings(){
    $('xr-hold').innerHTML = held.map(function(t){
      return '<li><span><b>' + esc(t) + '</b> <span class="small">' + esc(name(t)) + '</span></span>'
        + '<b>' + Math.round(100 * (weights[t] || 0)) + '%</b>'
        + '<button type="button" data-x="' + esc(t) + '" aria-label="Remove ' + esc(t) + '">×</button></li>';
    }).join('');
    $('xr-sliders').innerHTML = held.map(function(t){
      var v = Math.round(100 * (weights[t] || 0));
      return '<label><b>' + esc(t) + '</b><input type="range" min="0" max="100" step="1" value="' + v
        + '" data-w="' + esc(t) + '" aria-label="Weight of ' + esc(t) + '"><span>' + v + '%</span></label>';
    }).join('');
    var notes = {equal: 'Every holding gets the same weight.',
      balance: 'The weights that, over the last three years, would have left this mix least moved by the five forces (each between 5% and 60%). A calculation on past readings, not a recommendation.',
      manual: 'Drag the sliders under "Adjust weights"; they are scaled to add up to 100%.'};
    $('xr-mode-note').textContent = held.length ? notes[mode] : '';
  }

  function drawResult(){
    var out = $('xr-out');
    if (!held.length){ out.innerHTML = '<p class="small">Add two or more holdings, or start from a mix above.</p>'; return; }
    var rows = D.f.map(function(f, i){
      var v = 0, ok = true, heldW = 0, parts = [];
      held.forEach(function(t){ var r = vec(t)[i]; if (!r){ ok = false; return; }
        var c = weights[t] * r[0]; v += c; if (r[1]) heldW += weights[t]; if (!MKT[t]) parts.push([t, c]); });
      parts.sort(function(a, b){ return Math.abs(b[1]) - Math.abs(a[1]); });
      return {f: f, ok: ok, v: v, heldW: heldW, parts: parts.slice(0, 2)};
    });
    var good = rows.filter(function(r){ return r.ok; });
    var scale = Math.max.apply(null, good.map(function(r){ return Math.abs(r.v); }).concat([0.25]));
    var top = good.slice().sort(function(a, b){ return Math.abs(b.v) - Math.abs(a.v); })[0];
    var head = top ? '<h2 class="xr-head">The biggest driver: <b>' + esc(top.f[1].toLowerCase().replace('u.s.', 'U.S.')) + '</b>. In weeks when '
      + esc(top.f[2]) + ', this mix has typically moved <b>' + pct(top.v) + '</b> beyond the market.</h2>' : '';
    var bars = rows.map(function(r){
      if (!r.ok) return '<li><span>' + esc(r.f[1]) + '</span><span class="xr-na">Not measured for every holding</span><span></span></li>';
      var w = 50 * Math.abs(r.v) / scale, color = r.v >= 0 ? '#2f6fbd' : '#b5651d';
      var bar = r.v >= 0 ? 'left:50%;width:' + w.toFixed(1) + '%' : 'left:' + (50 - w).toFixed(1) + '%;width:' + w.toFixed(1) + '%';
      var who = r.parts.filter(function(p){ return Math.abs(p[1]) > 0.005; }).map(function(p){ return esc(p[0]) + ' ' + pct(p[1]); }).join(', ');
      return '<li><span>' + esc(r.f[1]) + '</span><span class="xr-track" aria-hidden="true"><i style="' + bar + ';background:' + color + '"></i></span>'
        + '<span class="xr-v">' + pct(r.v) + '</span><span class="xr-why small">In weeks when ' + esc(r.f[2]) + '. '
        + Math.round(100 * r.heldW) + '% of the weight comes from readings that held up'
        + (who ? '. Most of it from ' + who : '') + '.</span></li>';
    }).join('');
    out.innerHTML = head + '<ul class="xr-bars">' + bars + '</ul>';
  }

  function sync(){
    computeWeights(); drawHoldings(); drawResult(); links();
  }
  // The share link and the full report's link carry the mix and its weights.
  function links(){
    var h = held.map(function(t){ return t + ':' + (Math.round(1000 * (weights[t] || 0)) / 10); }).join(',');
    try { history.replaceState(null, '', held.length ? '#p=' + h : location.pathname); } catch (e) {}
    var a = $('xr-report'), u = new URL(a.href);
    if (held.length) u.searchParams.set('h', h); else u.searchParams.delete('h');
    a.href = u.toString(); a.textContent = held.length > 1 ? 'Get the full report on these ' + held.length + ', free' : 'Get the full report, free';
  }
  function add(t, quiet){
    t = String(t || '').trim().toUpperCase().replace(/^\$/, '');
    if (!t) return;
    if (!known(t)){ if (!quiet) $('xr-say').textContent = t + ' is not on record yet. Opening it in the app measures it.'; return; }
    if (held.indexOf(t) >= 0){ if (!quiet) $('xr-say').textContent = t + ' is already in the mix.'; return; }
    if (held.length >= MAX){ $('xr-say').textContent = 'Up to ' + MAX + ' holdings.'; return; }
    held.push(t); if (!quiet) $('xr-say').textContent = t + ' added.';
  }

  $('xr-form').addEventListener('submit', function(){ $('xr-q').value.split(/[\s,]+/).forEach(function(t){ add(t); }); $('xr-q').value = ''; sync(); });
  document.addEventListener('click', function(e){
    var el = e.target.closest && e.target.closest('[data-add],[data-preset],[data-x],[data-mode]');
    if (!el) return;
    if (el.hasAttribute('data-add')){ add(el.getAttribute('data-add')); }
    else if (el.hasAttribute('data-preset')){ held = []; manual = {}; el.getAttribute('data-preset').split(' ').forEach(function(t){ add(t, true); });
      $('xr-say').textContent = el.textContent + ': ' + held.join(', ') + '.'; }
    else if (el.hasAttribute('data-x')){ var t = el.getAttribute('data-x'); held = held.filter(function(u){ return u !== t; }); delete manual[t];
      $('xr-say').textContent = t + ' removed.'; }
    else { mode = el.getAttribute('data-mode');
      document.querySelectorAll('[data-mode]').forEach(function(b){ b.setAttribute('aria-pressed', String(b === el)); });
      if (mode === 'manual'){ held.forEach(function(t){ manual[t] = Math.round(100 * (weights[t] || 0)); }); $('xr-adj').open = true; } }
    sync();
  });
  $('xr-sliders').addEventListener('input', function(e){
    var t = e.target.getAttribute('data-w'); if (!t) return;
    manual[t] = +e.target.value; e.target.nextSibling.textContent = e.target.value + '%';
    if (mode !== 'manual'){ held.forEach(function(u){ if (manual[u] == null) manual[u] = Math.round(100 * (weights[u] || 0)); });
      mode = 'manual'; document.querySelectorAll('[data-mode]').forEach(function(b){ b.setAttribute('aria-pressed', String(b.getAttribute('data-mode') === 'manual')); }); }
    computeWeights(); drawResult(); links();
    document.querySelectorAll('#xr-hold li').forEach(function(li, i){ li.children[1].textContent = Math.round(100 * (weights[held[i]] || 0)) + '%'; });
  });
  $('xr-share').addEventListener('click', function(){
    var link = location.href;
    if (navigator.clipboard) navigator.clipboard.writeText(link).then(function(){ $('xr-say').textContent = 'Link copied.'; }, function(){ $('xr-say').textContent = link; });
    else $('xr-say').textContent = link;
  });
  // A shared link opens the same mix and weights.
  var m = /#p=([^&]+)/.exec(location.hash);
  if (m){ decodeURIComponent(m[1]).split(',').forEach(function(p){ var kv = p.split(':'); add(kv[0], true);
      if (kv[1] && held.indexOf(kv[0].toUpperCase()) >= 0) manual[kv[0].toUpperCase()] = +kv[1]; });
    if (Object.keys(manual).length){ mode = 'manual'; document.querySelectorAll('[data-mode]').forEach(function(b){ b.setAttribute('aria-pressed', String(b.getAttribute('data-mode') === 'manual')); }); } }
  sync();
})();
"""
