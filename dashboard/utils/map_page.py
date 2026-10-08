# utils/map_page.py
# Unstructured Alpha — the stock map: every stock on two forces at once
#
# The hub reads one force per column; this puts any two on axes. Each dot is a
# stock: how far right, its typical weekly move with one force; how far up,
# with the other. Oil against rates separates the energy names from the
# banks at a glance; the dollar against credit shows which stocks carried
# both. Pick the axes, light up a sector, find a ticker, open any dot.
#
# RULES
#   * A stock is placed only where BOTH readings were measured -- never at
#     zero for a missing one.
#   * Every dot shows how many of its two readings held up (both, one,
#     neither); the legend says so and readings that could not be told apart
#     from zero are drawn hollow, never hidden.
#   * A table of exactly what is plotted sits under the map for anyone who
#     cannot see it.
#   * Past, not forecast; no advice.

from __future__ import annotations

import json
from html import escape
from typing import Iterable

from utils import exposure as ex
from utils.explore_page import JS_PCT
from utils.exposure_pages import STANDS_UP, _date, _shell
from utils.force_pages import ALL_FORCES

DEFAULT_X, DEFAULT_Y = "rates", "oil"


def map_data(stocks: Iterable[dict]) -> dict:
    """Forces with any reading, sectors, and per stock: ticker, name, sector
    index (-1 outside the index), each force's typical move (null where not
    measured) and one character per force: "1" held up, "0" did not, "-"
    not measured."""
    from utils.sector_pages import sector_by_ticker, sectors
    stocks = [s for s in stocks if s.get("ticker")]
    forces = [f for f in ALL_FORCES if any(f.key in (s.get("exposures") or {}) for s in stocks)]
    secs = sectors()
    by_t = sector_by_ticker()
    rows, newest = [], ""
    for s in sorted(stocks, key=lambda s: s["ticker"]):
        exps = s.get("exposures") or {}
        newest = max(newest, str(s.get("as_of") or "")[:10])
        sec = by_t.get(s["ticker"])
        rows.append([s["ticker"], s.get("name") or "", secs.index(sec) if sec in secs else -1,
                     [round(float(exps[f.key]["impact"]), 4) if f.key in exps else None for f in forces],
                     "".join(("1" if exps[f.key].get("evidence") in STANDS_UP else "0") if f.key in exps
                             else "-" for f in forces)])
    return {"f": [[f.key, f.label, f.shock_phrase, ex.lower_label(f.label)] for f in forces], "sec": secs,
            "s": rows, "as_of": newest}


_CSS = """<style>
.mp-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px 14px;margin:6px 0 12px;align-items:end}
.mp-form label{display:block;font-weight:600;font-size:.88rem;margin-bottom:4px}
.mp-form select,.mp-form input{width:100%;min-height:44px;font:inherit;border:1px solid var(--line);border-radius:10px;
  padding:0 10px;background:var(--bg);color:var(--ink)}
.mp-form input{text-transform:uppercase}.mp-form input::placeholder{text-transform:none}
.mp-swap{min-height:44px}
.mp-wrap{position:relative;padding:8px}
.mp-svg{display:block;max-width:100%;height:auto;touch-action:manipulation}
.mp-svg text{fill:var(--ink3);font-size:12px;font-family:inherit}
.mp-svg .mp-q{font-size:12px;fill:var(--ink3)}
.mp-svg .mp-axis{stroke:var(--ink3);stroke-width:1}
.mp-svg .mp-grid{stroke:var(--line);stroke-width:1}
.mp-svg .mp-lab{fill:var(--ink);font-weight:600;font-size:13px}
.mp-dot{fill:var(--accent);stroke:var(--accent);stroke-width:1.5;cursor:pointer;transition:opacity .15s}
.mp-dot.h1{fill-opacity:.45}.mp-dot.h0{fill:var(--surface);fill-opacity:1;stroke:var(--ink3)}
.mp-dot.dim{opacity:.12}
.mp-dot.hit{stroke:var(--ink);stroke-width:3}
.mp-svg .mp-hitlab{fill:var(--ink);font-weight:700;font-size:13px;paint-order:stroke;stroke:var(--bg);stroke-width:4px}
.mp-tip{position:absolute;pointer-events:none;background:var(--ink);color:var(--bg);border-radius:8px;padding:6px 10px;
  font-size:.82rem;line-height:1.35;max-width:240px;box-shadow:0 4px 14px rgba(0,0,0,.18);z-index:2}
.mp-tip[hidden]{display:none}
.mp-legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.82rem;color:var(--ink2);margin:8px 0 0;padding:0;list-style:none}
.mp-legend svg{vertical-align:-2px;margin-right:6px}
.mp-say{min-height:1.4em;font-size:.92rem;color:var(--ink2);margin:6px 0 0}
.mp-table td{font-variant-numeric:tabular-nums}
details.mp-more{margin-top:12px}details.mp-more summary{cursor:pointer;font-weight:600}
</style>"""

_SCRIPT = r"""
(function(){
  var D = JSON.parse(document.getElementById('mp-data').textContent);
/*PCT*/
  var $ = function(id){ return document.getElementById(id); };
  var xs = $('mp-x'), ys = $('mp-y'), ss = $('mp-sec'), q = $('mp-q'), svg = $('mp-svg'),
      tip = $('mp-tip'), say = $('mp-say'), tbody = $('mp-rows'), cap = $('mp-cap');
  var W = 720, H = 520, L = 58, R = 16, T = 16, B = 52, NS = 'http://www.w3.org/2000/svg';
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function idx(k){ for (var i = 0; i < D.f.length; i++) if (D.f[i][0] === k) return i; return -1; }
  function fill(sel, v){ sel.innerHTML = D.f.map(function(f){ return '<option value="' + f[0] + '">' + esc(f[1]) + '</option>'; }).join(''); sel.value = v; }
  function slug(s){ return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }
  var armed = null;
  var st = {x: '__X__', y: '__Y__', s: '', q: ''};
  location.hash.slice(1).split('&').forEach(function(p){ var kv = p.split('='); if (kv.length === 2 && kv[0] in st) st[kv[0]] = decodeURIComponent(kv[1]); });
  if (idx(st.x) < 0) st.x = D.f[0][0]; if (idx(st.y) < 0) st.y = D.f[Math.min(1, D.f.length - 1)][0];
  fill(xs, st.x); fill(ys, st.y);
  ss.innerHTML = '<option value="">All sectors</option>' + D.sec.map(function(s){ return '<option value="' + slug(s) + '">' + esc(s) + '</option>'; }).join('');
  ss.value = st.s; if (ss.value !== st.s) st.s = ''; q.value = st.q;
  function nice(m, n){ var steps = [0.5, 1, 2, 2.5, 5, 10, 20, 25, 50]; for (var i = 0; i < steps.length; i++) if (m / steps[i] <= n) return steps[i]; return 100; }
  function draw(){
    var xi = idx(st.x), yi = idx(st.y), fx = D.f[xi], fy = D.f[yi], qq = st.q.trim().toUpperCase();
    // Drawn at the box's real pixel size, so text stays readable on a phone.
    W = Math.max(300, Math.round(svg.parentNode.clientWidth - 16)); H = Math.round(Math.min(560, Math.max(340, W * 0.72)));
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H); svg.setAttribute('width', W); svg.setAttribute('height', H);
    var pts = D.s.filter(function(r){ return r[3][xi] !== null && r[3][yi] !== null; });
    var mx = 0.5, my = 0.5;
    pts.forEach(function(r){ mx = Math.max(mx, Math.abs(r[3][xi])); my = Math.max(my, Math.abs(r[3][yi])); });
    mx *= 1.08; my *= 1.08;
    var px = function(v){ return L + (W - L - R) * (v + mx) / (2 * mx); }, py = function(v){ return T + (H - T - B) * (my - v) / (2 * my); };
    var o = '';
    [[mx, px, true], [my, py, false]].forEach(function(a){
      var step = nice(a[0], a[2] && W < 560 ? 2 : 4);
      for (var v = -Math.floor(a[0] / step) * step; v <= a[0] + 1e-9; v += step){
        var p = a[1](v), zero = Math.abs(v) < 1e-9, lab = zero ? '0' : pct(v);
        o += a[2] ? '<line class="' + (zero ? 'mp-axis' : 'mp-grid') + '" x1="' + p + '" x2="' + p + '" y1="' + T + '" y2="' + (H - B) + '"/>'
                  + '<text x="' + p + '" y="' + (H - B + 16) + '" text-anchor="middle">' + lab + '</text>'
                  : '<line class="' + (zero ? 'mp-axis' : 'mp-grid') + '" y1="' + p + '" y2="' + p + '" x1="' + L + '" x2="' + (W - R) + '"/>'
                  + '<text x="' + (L - 6) + '" y="' + (p + 4) + '" text-anchor="end">' + lab + '</text>';
      }
    });
    var xl = esc(fx[3]), yl = esc(fy[3]);
    o += '<text class="mp-q" x="' + (W - R - 6) + '" y="' + (T + 14) + '" text-anchor="end">Up with both</text>'
      + '<text class="mp-q" x="' + (L + 6) + '" y="' + (H - B - 8) + '">Down with both</text>'
      + '<text class="mp-lab" x="' + ((L + W - R) / 2) + '" y="' + (H - 10) + '" text-anchor="middle">' + esc(fx[1]) + ' →</text>'
      + '<text class="mp-lab" transform="rotate(-90)" x="' + (-(T + H - B) / 2) + '" y="14" text-anchor="middle">' + esc(fy[1]) + ' →</text>';
    var hits = [], dots = '', rows = [];
    pts.forEach(function(r, i){
      var held = (r[4][xi] === '1') + (r[4][yi] === '1');
      var inSec = !st.s || (r[2] >= 0 && slug(D.sec[r[2]]) === st.s);
      var hit = qq && (r[0] === qq);
      if (hit) hits.push(r);
      dots += '<circle data-i="' + D.s.indexOf(r) + '" class="mp-dot h' + held + (inSec ? '' : ' dim') + (hit ? ' hit' : '') + '" cx="' + px(r[3][xi]).toFixed(1)
        + '" cy="' + py(r[3][yi]).toFixed(1) + '" r="' + (hit ? 8 : 5.5) + '"/>';
      if (inSec) rows.push(r);
    });
    hits.forEach(function(r){
      dots += '<text class="mp-hitlab" x="' + (px(r[3][xi]) + 11).toFixed(1) + '" y="' + (py(r[3][yi]) + 4).toFixed(1) + '">' + esc(r[0]) + '</text>';
    });
    svg.innerHTML = o + '<g>' + dots + '</g>'; tip.hidden = true; armed = null;
    svg.setAttribute('aria-label', 'Scatter plot of ' + pts.length + ' stocks: typical weekly move with ' + xl
      + ' across, with ' + yl + ' up. The same figures are in the table below.');
    rows.sort(function(a, b){ return b[3][yi] - a[3][yi] || (a[0] < b[0] ? -1 : 1); });
    tbody.innerHTML = rows.map(function(r){
      function c(i){ var v = pct(r[3][i]); return '<td>' + (r[4][i] === '1' ? '<b>' + v + '</b>' : '<span class="v-weak">' + v + '</span>') + '</td>'; }
      return '<tr><th scope="row"><a href="/exposure/' + encodeURIComponent(r[0]) + '">' + esc(r[0]) + '</a></th>' + c(xi) + c(yi) + '</tr>';
    }).join('');
    $('mp-hx').textContent = fx[1]; $('mp-hy').textContent = fy[1];
    cap.textContent = rows.length + ' stocks' + (st.s ? ' in ' + ss.options[ss.selectedIndex].text : '') + ', by their move with ' + fy[3];
    var missing = D.s.length - pts.length;
    if (qq && !hits.length){
      var known = D.s.filter(function(r){ return r[0] === qq; })[0];
      say.textContent = known ? qq + ' has no reading on ' + (known[3][xi] === null ? xl : yl) + ', so it is not on this map.'
                              : qq + ' is not on record yet.';
    } else if (hits.length){
      var r = hits[0];
      say.textContent = r[0] + ': ' + pct(r[3][xi]) + ' with ' + xl + ', ' + pct(r[3][yi]) + ' with ' + yl + '.';
    } else {
      say.textContent = pts.length + ' stocks on this map' + (missing ? '; ' + missing + ' more lack one of the two readings.' : '.');
    }
    $('mp-xp').textContent = fx[2]; $('mp-yp').textContent = fy[2];
    var h = 'x=' + st.x + '&y=' + st.y + (st.s ? '&s=' + st.s : '') + (qq ? '&q=' + encodeURIComponent(qq) : '');
    try { history.replaceState(null, '', '#' + h); } catch (e) {}
  }
  function showTip(a){
    var r = D.s[+a.getAttribute('data-i')], xi = idx(st.x), yi = idx(st.y);
    function line(i){ return esc(D.f[i][1]) + ': <b>' + pct(r[3][i]) + '</b>' + (r[4][i] === '1' ? '' : ' (no clear link)'); }
    var open = matchMedia('(hover: none)').matches ? '<br><i>Tap again to open</i>' : '';
    tip.innerHTML = '<b>' + esc(r[0]) + '</b> ' + esc(r[1]) + (r[2] >= 0 ? '<br>' + esc(D.sec[r[2]]) : '') + '<br>' + line(xi) + '<br>' + line(yi) + open;
    tip.hidden = false;
    var box = svg.parentNode.getBoundingClientRect(), c = a.getBoundingClientRect();
    var x = c.left - box.left + c.width / 2, y = c.top - box.top;
    tip.style.left = Math.max(4, Math.min(box.width - tip.offsetWidth - 4, x - tip.offsetWidth / 2)) + 'px';
    tip.style.top = (y - tip.offsetHeight - 8 < 0 ? y + c.height + 8 : y - tip.offsetHeight - 8) + 'px';
  }
  // A mouse previews on hover and opens on click; a tap previews first and
  // opens on a second tap of the same dot.
  function dotOf(e){ return e.target.closest ? e.target.closest('circle[data-i]') : null; }
  svg.addEventListener('pointerover', function(e){ var a = dotOf(e); if (a && e.pointerType === 'mouse'){ showTip(a); armed = a; } });
  svg.addEventListener('pointerout', function(e){ if (e.pointerType === 'mouse' && dotOf(e)){ tip.hidden = true; armed = null; } });
  svg.addEventListener('click', function(e){
    var a = dotOf(e);
    if (!a){ tip.hidden = true; armed = null; return; }
    if (armed === a){ location.href = '/exposure/' + encodeURIComponent(D.s[+a.getAttribute('data-i')][0]); return; }
    armed = a; showTip(a);
  });
  var rt; window.addEventListener('resize', function(){ clearTimeout(rt); rt = setTimeout(function(){ tip.hidden = true; draw(); }, 120); });
  xs.addEventListener('change', function(){ st.x = xs.value; draw(); });
  ys.addEventListener('change', function(){ st.y = ys.value; draw(); });
  ss.addEventListener('change', function(){ st.s = ss.value; draw(); });
  q.addEventListener('input', function(){ st.q = q.value; draw(); });
  $('mp-swap').addEventListener('click', function(){ var t = st.x; st.x = st.y; st.y = t; xs.value = st.x; ys.value = st.y; draw(); });
  draw();
})();
"""


def map_page_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    data = map_data(stocks)
    canonical = f"{base_url}/map"
    title = "Stock map: how U.S. stocks move with two economic forces at once"
    desc = ("Every stock on record placed by how it has moved with two economic forces at once — "
            "interest rates against oil, the dollar against credit, any pair. Pick the axes, light "
            "up a sector, find a ticker.")
    crumb = '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Stock map</nav>'
    ld = {"@context": "https://schema.org", "@type": "WebApplication", "name": title,
          "description": desc, "url": canonical, "applicationCategory": "FinanceApplication",
          "isAccessibleForFree": True}
    if len(data["f"]) < 2 or not data["s"]:
        body = (crumb + '<h1>Stock map</h1><p class="lead">Not enough stocks have been measured to '
                'draw the map yet. Readings are added each week.</p>')
        return _shell(title, desc, canonical, ld, body, app_url, robots="noindex, follow")
    keys = [f[0] for f in data["f"]]
    x = DEFAULT_X if DEFAULT_X in keys else keys[0]
    y = DEFAULT_Y if DEFAULT_Y in keys and DEFAULT_Y != x else next(k for k in keys if k != x)
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    script = _SCRIPT.replace("/*PCT*/", JS_PCT)
    script = script.replace("__X__", x).replace("__Y__", y)
    dot = '<svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="5" class="mp-dot {}"/></svg>'
    body = (
        _CSS + crumb +
        '<h1>Stock map</h1>'
        f'<p class="meta">{len(data["s"]):,} U.S. stocks on record'
        + (f' · data through {_date(data["as_of"])}' if data["as_of"] else "") + '</p>'
        f'<p class="lead">{escape(desc)}</p>'
        '<form class="mp-form" onsubmit="return false">'
        '<div><label for="mp-x">Across</label><select id="mp-x"></select></div>'
        '<div><label for="mp-y">Up</label><select id="mp-y"></select></div>'
        '<div><label for="mp-sec">Light up a sector</label><select id="mp-sec"></select></div>'
        '<div><label for="mp-q">Find a stock</label><input id="mp-q" type="search" autocomplete="off" '
        'spellcheck="false" placeholder="e.g. XOM"></div>'
        '<div><button type="button" class="btn btn-secondary mp-swap" id="mp-swap">Swap axes</button></div>'
        '</form>'
        '<div class="card mp-wrap"><svg id="mp-svg" class="mp-svg" viewBox="0 0 720 520" role="img" '
        'aria-label="Scatter plot of stocks"></svg><div class="mp-tip" id="mp-tip" hidden></div>'
        '<noscript><p class="lead">The map needs JavaScript. <a href="/exposure">Every stock on record</a> '
        'has the same figures in a table.</p></noscript></div>'
        '<p class="mp-say" id="mp-say" aria-live="polite"></p>'
        '<ul class="mp-legend">'
        f'<li>{dot.format("h2")}Both readings held up</li>'
        f'<li>{dot.format("h1")}One held up</li>'
        f'<li>{dot.format("h0")}Neither could be told apart from zero</li></ul>'
        '<p class="small">Across: the typical weekly move in weeks when <span id="mp-xp"></span>. Up: '
        'in weeks when <span id="mp-yp"></span>. Both after the stock market&#39;s own move. A stock '
        'appears only where both were measured. Hover or tap a dot for its figures; select it to open '
        'its page (on a touch screen, tap twice).</p>'
        '<details class="mp-more"><summary>The figures on this map, as a table</summary>'
        '<div class="card mp-table" tabindex="0" role="region" aria-labelledby="mp-cap">'
        '<table><caption id="mp-cap" class="small"></caption><thead><tr><th scope="col">Stock</th>'
        '<th scope="col" id="mp-hx"></th><th scope="col" id="mp-hy"></th></tr></thead>'
        '<tbody id="mp-rows"></tbody></table></div></details>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here is a '
        'recommendation to buy, sell or hold any security.</p>'
        '<div class="actions"><a class="btn btn-primary" href="/explore">What if? Move a force</a>'
        '<a class="btn btn-secondary" href="/sectors">By sector</a>'
        '<a class="btn btn-secondary" href="/learn">How to read this</a></div>'
        f'<script type="application/json" id="mp-data">{payload}</script>'
        f'<script>{script}</script>')
    return _shell(title, desc, canonical, ld, body, app_url)
