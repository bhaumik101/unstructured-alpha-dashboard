# utils/heatmap_page.py
# Unstructured Alpha — the market heatmap: every stock, one force, at a glance
#
# Modelled on the sector-grouped market maps of Finviz and others, but
# coloured by exposure instead of price change: pick a force and every stock
# on record becomes a tile in its sector's block, blue where it typically
# rose with that force, orange where it fell, the depth of colour the size of
# the move. Hover or focus a tile for its figures; select it to open its page.
#
# RULES
#   * Only readings that held up are coloured. A reading that could not be
#     told apart from zero is a grey tile, whatever its size -- never a pale
#     blue or orange that would read as a weak link.
#   * A stock not measured on the chosen force is drawn hatched and says so.
#   * Colour depth is scaled to the 95th percentile of held-up moves on that
#     force, so one outlier cannot wash out the rest; the scale is shown.
#   * Tiles are equal size: no market-cap weighting, so a small company's
#     reading counts as much as a large one's.
#   * Past, not forecast; no advice.

from __future__ import annotations

import json
from html import escape
from typing import Iterable

from utils.explore_page import JS_PCT
from utils.exposure_pages import _shell, data_chips, tool_header_html
from utils.map_page import map_data

DEFAULT_FORCE = "oil"

_CSS = """<style>
.hx-bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:6px 0 12px}
.hx-bar label{font-weight:600}
.hx-bar select{min-height:44px;font:inherit;border:1px solid var(--line);border-radius:10px;padding:0 10px;background:var(--surface);color:var(--ink)}
.hx-scale{display:flex;align-items:center;gap:8px;color:var(--ink3)}
.hx-ramp{width:180px;height:10px;border-radius:5px;background:linear-gradient(90deg,#9a5214,var(--subtle),#2f6fbd)}
.hx{columns:3 300px;column-gap:14px}
.hx-sec{break-inside:avoid;margin:0 0 14px;border:1px solid var(--line);border-radius:12px;background:var(--surface);padding:10px 12px}
.hx-sec h2{margin:0 0 6px;display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.hx-sec h2 a{color:var(--ink);text-decoration:none}.hx-sec h2 span{color:var(--ink3);font-weight:400}
.hx-tiles{display:flex;flex-wrap:wrap;gap:3px}
.hx-t{display:grid;place-items:center;min-width:52px;padding:0 4px;height:30px;border-radius:4px;color:var(--ink);text-decoration:none;
  font-weight:700;letter-spacing:.01em;overflow:hidden;white-space:nowrap}
.hx-t:hover,.hx-t:focus-visible{outline:2px solid var(--ink);outline-offset:1px;z-index:1}
.hx-t.n{background:var(--subtle);color:var(--ink2);font-weight:500}
.hx-t.x{background:repeating-linear-gradient(45deg,var(--subtle),var(--subtle) 4px,transparent 4px,transparent 8px);color:var(--ink2);font-weight:500}
.hx-tip{position:fixed;pointer-events:none;z-index:5;background:var(--ink);color:var(--bg);border-radius:8px;padding:6px 10px;max-width:260px;line-height:1.35}
.hx-tip[hidden]{display:none}
.hx-key{display:flex;flex-wrap:wrap;gap:4px 16px;color:var(--ink3);margin:4px 0 10px}
.hx-key i{display:inline-block;width:14px;height:10px;border-radius:2px;vertical-align:-1px;margin-right:5px}
</style>"""

_SCRIPT = r"""
(function(){
  var D = JSON.parse(document.getElementById('hx-data').textContent);
/*PCT*/
  var $ = function(id){ return document.getElementById(id); };
  var sel = $('hx-force'), box = $('hx'), tip = $('hx-tip'), say = $('hx-say');
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function slug(s){ return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }
  sel.innerHTML = D.f.map(function(f){ return '<option value="' + f[0] + '">' + esc(f[1]) + '</option>'; }).join('');
  var want = (location.hash || '').slice(1); sel.value = D.f.some(function(f){ return f[0] === want; }) ? want : '__DEFAULT__';
  if (sel.selectedIndex < 0) sel.selectedIndex = 0;
  var dark = matchMedia('(prefers-color-scheme: dark)');
  // The tile's actual colour (the hue blended over the card), and whichever
  // of black or white reads better on it -- so every label passes contrast.
  function lum(c){ return c.map(function(x){ x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); })
    .reduce(function(s, x, i){ return s + x * [0.2126, 0.7152, 0.0722][i]; }, 0); }
  function colour(v, scale){
    var a = 0.18 + 0.82 * Math.min(1, Math.abs(v) / scale), up = v >= 0;
    var hue = dark.matches ? (up ? [90, 143, 212] : [201, 130, 47]) : (up ? [47, 111, 189] : [154, 82, 20]);
    var base = dark.matches ? [18, 29, 47] : [255, 255, 255];
    var c = hue.map(function(h, i){ return Math.round(base[i] * (1 - a) + h * a); });
    // Pure black or pure white: on any colour one of them clears 4.5:1.
    var L = lum(c), onWhite = 1.05 / (L + 0.05), onBlack = (L + 0.05) / 0.05;
    return 'background:rgb(' + c.join(',') + ');color:' + (onWhite > onBlack ? '#fff' : '#000');
  }
  function draw(){
    var fi = sel.selectedIndex, f = D.f[fi];
    try { history.replaceState(null, '', '#' + f[0]); } catch (e) {}
    var held = D.s.filter(function(r){ return r[3][fi] !== null && r[4].charAt(fi) === '1'; })
      .map(function(r){ return Math.abs(r[3][fi]); }).sort(function(a, b){ return a - b; });
    var scale = held.length ? held[Math.min(held.length - 1, Math.floor(0.95 * (held.length - 1)))] : 1;
    if (!(scale > 0)) scale = 1;
    $('hx-lo').textContent = pct(-scale); $('hx-hi').textContent = pct(scale);
    var groups = D.sec.map(function(name){ return {name: name, rows: []}; }).concat([{name: 'Outside the S&P 500', rows: []}]);
    D.s.forEach(function(r){ groups[r[2] >= 0 ? r[2] : groups.length - 1].rows.push(r); });
    var up = 0, down = 0, none = 0, missing = 0;
    box.innerHTML = groups.filter(function(g){ return g.rows.length; }).map(function(g){
      g.rows.sort(function(a, b){
        var x = a[3][fi], y = b[3][fi];
        if (x === null) return 1; if (y === null) return -1;
        var hx = a[4].charAt(fi) === '1', hy = b[4].charAt(fi) === '1';
        if (hx !== hy) return hx ? -1 : 1;
        return y - x;
      });
      var inSec = 0;
      var tiles = g.rows.map(function(r, i){
        var v = r[3][fi], h = r[4].charAt(fi) === '1', cls = 'hx-t', style = '', what;
        if (v === null){ cls += ' x'; what = 'not measured on ' + f[3]; missing++; }
        else if (!h){ cls += ' n'; what = pct(v) + ', could not be told apart from zero'; none++; }
        else { style = ' style="' + colour(v, scale) + '"'; what = pct(v) + ', held up'; if (v > 0) { up++; inSec++; } else { down++; inSec++; } }
        return '<a class="' + cls + '" href="/exposure/' + encodeURIComponent(r[0]) + '"' + style
          + ' data-i="' + D.s.indexOf(r) + '" aria-label="' + esc(r[0] + ': ' + what) + '">' + esc(r[0]) + '</a>';
      }).join('');
      var link = g.name === 'Outside the S&P 500' ? esc(g.name) : '<a href="/sectors/' + slug(g.name) + '">' + esc(g.name) + '</a>';
      return '<section class="hx-sec"><h2>' + link + '<span class="small">' + inSec + ' of ' + g.rows.length + ' held up</span></h2>'
        + '<div class="hx-tiles">' + tiles + '</div></section>';
    }).join('');
    say.textContent = up + ' stocks rose with ' + f[3] + ' in a way that held up, ' + down + ' fell, ' + none
      + ' showed no link that could be told apart from zero' + (missing ? ', ' + missing + ' not measured' : '') + '.';
    $('hx-phrase').textContent = f[2];
  }
  function show(a){
    var r = D.s[+a.getAttribute('data-i')], fi = sel.selectedIndex, v = r[3][fi], h = r[4].charAt(fi) === '1';
    tip.innerHTML = '<b>' + esc(r[0]) + '</b> ' + esc(r[1]) + '<br>' + (v === null ? 'Not measured' : '<b>' + pct(v) + '</b> '
      + (h ? '(held up)' : '(could not be told apart from zero)'));
    tip.hidden = false;
    var b = a.getBoundingClientRect(), w = tip.offsetWidth, hgt = tip.offsetHeight;
    tip.style.left = Math.max(4, Math.min(innerWidth - w - 4, b.left + b.width / 2 - w / 2)) + 'px';
    tip.style.top = (b.top - hgt - 8 < 0 ? b.bottom + 8 : b.top - hgt - 8) + 'px';
  }
  box.addEventListener('pointerover', function(e){ var a = e.target.closest && e.target.closest('a[data-i]'); if (a) show(a); });
  box.addEventListener('pointerout', function(e){ if (!e.relatedTarget || !box.contains(e.relatedTarget)) tip.hidden = true; });
  box.addEventListener('focusin', function(e){ var a = e.target.closest && e.target.closest('a[data-i]'); if (a) show(a); });
  box.addEventListener('focusout', function(){ tip.hidden = true; });
  addEventListener('scroll', function(){ tip.hidden = true; }, {passive: true});
  sel.addEventListener('change', draw);
  if (dark.addEventListener) dark.addEventListener('change', draw);
  draw();
})();
"""


def heatmap_page_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    data = map_data(stocks)
    canonical = f"{base_url}/heatmap"
    title = "Market heatmap: which stocks move with oil, rates, the dollar and more"
    desc = ("Every U.S. stock on record as a tile in its sector, coloured by how it has moved with the "
            "economic force you pick: oil, interest rates, the dollar, gold, bitcoin and more.")
    crumb = '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Market heatmap</nav>'
    ld = {"@context": "https://schema.org", "@type": "WebApplication", "name": title,
          "description": desc, "url": canonical, "applicationCategory": "FinanceApplication",
          "isAccessibleForFree": True}
    if not data["s"] or not data["f"]:
        body = (crumb + '<h1>Market heatmap</h1><p class="lead">No stock has been measured yet. '
                'Readings are added each week.</p>')
        return _shell(title, desc, canonical, ld, body, app_url, robots="noindex, follow")
    keys = [f[0] for f in data["f"]]
    default = DEFAULT_FORCE if DEFAULT_FORCE in keys else keys[0]
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    body = (
        _CSS + crumb
        + tool_header_html("Market heatmap", data_chips(len(data["s"]), "stocks on record", data["as_of"]),
                           escape(desc))
        + '<div class="hx-bar"><label for="hx-force">Economic force</label><select id="hx-force"></select>'
        '<span class="hx-scale small" aria-hidden="true"><span id="hx-lo"></span><span class="hx-ramp"></span>'
        '<span id="hx-hi"></span></span></div>'
        '<p class="small">Each tile is one stock&#39;s typical weekly move, beyond the market, in weeks when '
        '<span id="hx-phrase"></span>.</p>'
        '<p class="hx-key small"><span><i style="background:#2f6fbd"></i>Rose with it, held up</span>'
        '<span><i style="background:#9a5214"></i>Fell with it, held up</span>'
        '<span><i style="background:var(--subtle)"></i>Could not be told apart from zero</span>'
        '<span><i style="background:repeating-linear-gradient(45deg,var(--subtle),var(--subtle) 3px,transparent 3px,transparent 6px)"></i>Not measured</span>'
        '<span>Deeper colour, larger move; the scale tops out at the 95th percentile.</span></p>'
        '<p class="small" id="hx-say" aria-live="polite"></p>'
        '<div class="hx" id="hx"><noscript><p class="lead">The heatmap needs JavaScript. '
        '<a href="/sectors">The sector table</a> has the same readings.</p></noscript></div>'
        '<div class="hx-tip" id="hx-tip" hidden></div>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Tiles are equal size: '
        'there is no market-cap weighting. Nothing here is a recommendation to buy, sell or hold any '
        'security.</p>'
        '<div class="actions"><a class="btn btn-primary" href="/sectors">Sector medians</a>'
        '<a class="btn btn-secondary" href="/map">Two forces at once</a>'
        '<a class="btn btn-secondary" href="/scenario">Build a scenario</a></div>'
        f'<script type="application/json" id="hx-data">{payload}</script>'
        f'<script>{_SCRIPT.replace("/*PCT*/", JS_PCT).replace("__DEFAULT__", default)}</script>')
    return _shell(title, desc, canonical, ld, body, app_url)
