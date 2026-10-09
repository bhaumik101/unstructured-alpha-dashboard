# utils/list_page.py
# Unstructured Alpha — My list: the stocks you follow, kept in your browser
#
# A save button on every stock page and one page that reads them back: each
# saved stock's five core readings side by side, and what an equal-weight
# basket of them would have done. No account and nothing sent anywhere: the
# list lives in this browser's storage, and a link can carry it to another.
#
# RULES
#   * The basket line is the plain average of each stock's typical move,
#     which is what an equal-weight basket's own reading would be. It is shown
#     only when every stock on the list was measured on that force -- never
#     averaged over the ones that happen to have a reading.
#   * No range is shown for the basket: combining ranges needs how the stocks
#     move together, which these pages do not have. The app measures that.
#   * Held-up readings bold, the rest grey; past, not forecast; no advice.

from __future__ import annotations

import json
from html import escape
from typing import Iterable

from utils import exposure as ex
from utils.exposure_pages import STANDS_UP, _date, _shell
from utils.explore_page import JS_PCT

STORE_KEY = "ua-list"
MAX_ITEMS = 25


def list_data(stocks: Iterable[dict]) -> dict:
    """Per stock on record: name, sector, and each core force's typical move
    with 1 if it held up (null where not measured)."""
    from utils.sector_pages import sector_by_ticker
    secs = sector_by_ticker()
    keys = [f.key for f in ex.FACTORS]
    out, newest = {}, ""
    for s in stocks:
        if not s.get("ticker"):
            continue
        exps = s.get("exposures") or {}
        newest = max(newest, str(s.get("as_of") or "")[:10])
        out[s["ticker"]] = [s.get("name") or "", secs.get(s["ticker"], ""),
                            [[round(float(exps[k]["impact"]), 4), 1 if exps[k].get("evidence") in STANDS_UP else 0]
                             if k in exps else None for k in keys]]
    return {"f": [[f.key, f.label, f.shock_phrase] for f in ex.FACTORS], "s": out, "as_of": newest}


# The save button on a stock page. Works on any page that has the shell.
SAVE_SCRIPT = r"""
(function(){
  var b = document.getElementById('ls-save'), t = b.getAttribute('data-t'), say = document.getElementById('ls-said');
  function get(){ try { return JSON.parse(localStorage.getItem('__KEY__') || '[]'); } catch (e) { return []; } }
  function put(l){ try { localStorage.setItem('__KEY__', JSON.stringify(l)); return true; } catch (e) { return false; } }
  function draw(){ var on = get().indexOf(t) >= 0; b.setAttribute('aria-pressed', on ? 'true' : 'false');
    b.textContent = on ? '★ On my list' : '☆ Save to my list'; }
  b.hidden = false; draw();
  b.addEventListener('click', function(){
    var l = get(), i = l.indexOf(t);
    if (i >= 0) l.splice(i, 1); else { if (l.length >= __MAX__) { say.innerHTML = ' Your list is full (__MAX__).'; return; } l.push(t); }
    if (!put(l)) { say.textContent = ' This browser is not saving data.'; return; }
    draw(); say.innerHTML = i >= 0 ? ' Removed.' : ' Saved. <a href="/mylist">See my list</a>';
  });
})();
""".replace("__KEY__", STORE_KEY).replace("__MAX__", str(MAX_ITEMS))


def save_button_html(symbol: str) -> str:
    """Hidden until script runs: without storage there is nothing to save to."""
    return (f'<button type="button" class="btn btn-secondary" id="ls-save" data-t="{escape(symbol)}" '
            'aria-pressed="false" hidden>☆ Save to my list</button>'
            '<span class="small" id="ls-said" aria-live="polite"></span>'
            f'<script>{SAVE_SCRIPT}</script>')


_CSS = """<style>
.ls-add{display:flex;flex-wrap:wrap;gap:10px;align-items:end;margin:6px 0 14px}
.ls-add label{display:block;font-weight:600;margin-bottom:4px}
.ls-add input{min-height:44px;font:inherit;border:1px solid var(--line);border-radius:10px;padding:0 10px;
  background:var(--bg);color:var(--ink);text-transform:uppercase;width:min(260px,100%)}
.ls-add input::placeholder{text-transform:none}
.ls-add .btn{min-height:44px}
.ls-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;list-style:none;margin:0;padding:0}
.ls-card{border:1px solid var(--line);border-radius:12px;background:var(--surface);padding:14px 16px}
.ls-card.ls-basket{border-color:var(--accent)}
.ls-h{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:6px}
.ls-h a{font-weight:750}
.ls-n,.ls-row,.ls-x,.ls-foot{font-size:.82rem}
.ls-n{color:var(--ink3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ls-row{display:grid;grid-template-columns:minmax(0,1fr) 38% 56px;gap:8px;align-items:center;padding:4px 0;
  border-top:1px solid var(--line)}
.ls-tr{position:relative;height:8px;background:var(--subtle);border-radius:4px}
.ls-tr::after{content:"";position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--ink3)}
.ls-br{position:absolute;top:0;bottom:0;border-radius:4px}
.ls-br.u{background:#2f6fbd}.ls-br.d{background:#b5651d}.ls-br.f{opacity:.35}
@media (prefers-color-scheme:dark){.ls-br.u{background:#5a8fd4}.ls-br.d{background:#c9822f}}
.ls-v{text-align:right;font-variant-numeric:tabular-nums}
.ls-x{border:0;background:none;color:var(--ink3);cursor:pointer;font-family:inherit;padding:4px 6px;min-height:32px}
.ls-x:hover{color:var(--ink)}
.ls-foot{margin-top:8px;display:flex;flex-wrap:wrap;gap:4px 12px}
.ls-empty{padding:18px;border:1px dashed var(--line);border-radius:12px;color:var(--ink2)}
.ls-share{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:12px}
</style>"""

_SCRIPT = r"""
(function(){
  var D = JSON.parse(document.getElementById('ls-data').textContent);
/*PCT*/
  var KEY = '__KEY__', MAX = __MAX__;
  var $ = function(id){ return document.getElementById(id); };
  var out = $('ls-out'), say = $('ls-say'), inp = $('ls-t'), share = $('ls-share');
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function get(){ try { var l = JSON.parse(localStorage.getItem(KEY) || '[]'); return Array.isArray(l) ? l : []; } catch (e) { return []; } }
  function put(l){ try { localStorage.setItem(KEY, JSON.stringify(l)); } catch (e) { say.textContent = 'This browser is not saving data, so the list lasts only while this page is open.'; } mem = l; }
  var mem = get();
  // A shared link (#t=XOM,DAL) is offered, never applied silently over a list already here.
  var h = /^#t=([A-Z0-9.,\-]+)$/i.exec(location.hash), offered = null;
  if (h){ offered = h[1].toUpperCase().split(',').filter(function(t, i, a){ return t && a.indexOf(t) === i; }).slice(0, MAX); }
  if (!mem.length){ try { var old = (localStorage.getItem('xp-mine') || '').toUpperCase().split(/[\s,;]+/)
      .filter(function(t){ return D.s[t]; }); if (old.length && !offered){ mem = old.slice(0, MAX); put(mem); } } catch (e) {} }
  function bars(cells, max){
    return D.f.map(function(f, i){
      var c = cells[i];
      if (!c) return '<div class="ls-row"><span title="In weeks when ' + esc(f[2]) + '">' + esc(f[1]) + '</span><span></span><span class="ls-v v-weak">—</span></div>';
      var w = max ? 50 * Math.min(1, Math.abs(c[0]) / max) : 0;
      return '<div class="ls-row"><span title="In weeks when ' + esc(f[2]) + '">' + esc(f[1]) + '</span>'
        + '<span class="ls-tr" aria-hidden="true"><span class="ls-br ' + (c[0] >= 0 ? 'u' : 'd') + (c[1] ? '' : ' f')
        + '" style="' + (c[0] >= 0 ? 'left' : 'right') + ':50%;width:' + w.toFixed(1) + '%"></span></span>'
        + '<span class="ls-v">' + (c[1] === 2 ? pct(c[0]) : c[1] ? '<b>' + pct(c[0]) + '</b>' : '<span class="v-weak">' + pct(c[0]) + '</span>') + '</span></div>';
    }).join('');
  }
  function draw(){
    var l = mem.filter(function(t){ return D.s[t]; }), gone = mem.filter(function(t){ return !D.s[t]; });
    var max = 0;
    l.forEach(function(t){ D.s[t][2].forEach(function(c){ if (c) max = Math.max(max, Math.abs(c[0])); }); });
    var html = '';
    if (offered){
      html += '<div class="ls-empty" role="region" aria-label="Shared list"><p>Someone shared a list of ' + offered.length + ' stocks: <b>'
        + esc(offered.join(', ')) + '</b>.</p><div class="ls-share"><button type="button" class="btn btn-primary" id="ls-take">Use this list</button>'
        + (mem.length ? '<button type="button" class="btn btn-secondary" id="ls-merge">Add them to mine</button>' : '')
        + '<button type="button" class="btn btn-secondary" id="ls-skip">No thanks</button></div></div>';
    }
    if (!l.length){
      html += '<p class="ls-empty">Your list is empty. Add a ticker above, or press <b>☆ Save to my list</b> on any '
        + '<a href="/exposure">stock page</a>.</p>';
    } else {
      // Equal-weight basket: the plain average, only where every stock was measured.
      var basket = D.f.map(function(f, i){
        var cs = l.map(function(t){ return D.s[t][2][i]; });
        if (cs.some(function(c){ return !c; })) return null;
        return [cs.reduce(function(a, c){ return a + c[0]; }, 0) / cs.length, 2];   // 2: an average, never tested
      });
      html += '<ul class="ls-grid">';
      if (l.length > 1){
        html += '<li class="ls-card ls-basket"><div class="ls-h"><b>Your ' + l.length + ' stocks, equal weight</b></div>'
          + bars(basket, max)
          + '<p class="small">The average of the typical moves below, held up or not; an average is not itself tested. A dash: not every stock was measured on that force. '
          + 'No range: combining ranges needs how the stocks move together, which the '
          + '<a href="__APP__/">app measures</a>.</p></li>';
      }
      l.forEach(function(t, k){
        var s = D.s[t];
        html += '<li class="ls-card"><div class="ls-h"><a href="/exposure/' + encodeURIComponent(t) + '">' + esc(t) + '</a>'
          + '<span class="ls-n">' + esc(s[0]) + (s[1] ? ' · ' + esc(s[1]) : '') + '</span></div>' + bars(s[2], max)
          + '<div class="ls-foot">'
          + (l.length > 1 ? '<a href="/compare?a=' + encodeURIComponent(t) + '&amp;b=' + encodeURIComponent(l[(k + 1) % l.length]) + '">Compare with ' + esc(l[(k + 1) % l.length]) + '</a>' : '<a href="/compare?a=' + encodeURIComponent(t) + '">Compare</a>')
          + '<button type="button" class="ls-x" data-x="' + esc(t) + '" aria-label="Remove ' + esc(t) + ' from my list">Remove</button></div></li>';
      });
      html += '</ul>';
    }
    if (gone.length) html += '<p class="small">Not on record any more, kept in case it returns: ' + esc(gone.join(', ')) + '.</p>';
    out.innerHTML = html;
    share.hidden = !l.length;
    var link = location.origin + location.pathname + '#t=' + l.join(',');
    $('ls-link').value = link;
    $('ls-count').textContent = l.length ? l.length + ' of ' + MAX : '';
    function act(id, fn){ var e = $(id); if (e) e.addEventListener('click', fn); }
    act('ls-take', function(){ put(offered.slice()); offered = null; history.replaceState(null, '', location.pathname); draw(); });
    act('ls-merge', function(){ var m = mem.slice(); offered.forEach(function(t){ if (m.indexOf(t) < 0 && m.length < MAX) m.push(t); });
      put(m); offered = null; history.replaceState(null, '', location.pathname); draw(); });
    act('ls-skip', function(){ offered = null; history.replaceState(null, '', location.pathname); draw(); });
  }
  out.addEventListener('click', function(e){
    var x = e.target.closest && e.target.closest('[data-x]'); if (!x) return;
    var t = x.getAttribute('data-x'); put(mem.filter(function(u){ return u !== t; }));
    say.textContent = t + ' removed.'; draw(); inp.focus();
  });
  $('ls-form').addEventListener('submit', function(e){
    e.preventDefault();
    var ts = inp.value.toUpperCase().split(/[\s,;]+/).filter(Boolean), added = [], miss = [];
    var m = mem.slice();
    ts.forEach(function(t){ if (!D.s[t]) miss.push(t); else if (m.indexOf(t) < 0 && m.length < MAX){ m.push(t); added.push(t); } });
    put(m); inp.value = '';
    say.textContent = (added.length ? 'Added ' + added.join(', ') + '. ' : '')
      + (miss.length ? miss.join(', ') + (miss.length === 1 ? ' is' : ' are') + ' not on record yet. ' : '')
      + (m.length >= MAX ? 'The list holds ' + MAX + ' stocks.' : '');
    draw();
  });
  $('ls-copy').addEventListener('click', function(){
    var f = $('ls-link'); f.select();
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(f.value).then(function(){ say.textContent = 'Link copied.'; }, function(){});
    else say.textContent = 'Selected: press Ctrl+C or Cmd+C.';
  });
  draw();
})();
""".replace("__KEY__", STORE_KEY).replace("__MAX__", str(MAX_ITEMS))


def list_page_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    data = list_data(stocks)
    canonical = f"{base_url}/mylist"
    title = "My list: the stocks you follow, against rates, oil, the dollar and credit"
    desc = ("Save stocks as you browse and see them side by side: how each has moved with interest "
            "rates, inflation, the dollar, oil and credit, and what an equal-weight basket of them did.")
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    opts = "".join(f'<option value="{escape(t)}">' for t in sorted(data["s"]))
    script = _SCRIPT.replace("/*PCT*/", JS_PCT).replace("__APP__", escape(app_url))
    body = (
        _CSS +
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › My list</nav>'
        '<h1>My list</h1>'
        + (f'<p class="meta">Data through {_date(data["as_of"])}</p>' if data["as_of"] else "")
        + f'<p class="lead">{escape(desc)} Kept in this browser only: no account, nothing sent anywhere.</p>'
        '<form class="ls-add" id="ls-form"><div><label for="ls-t">Add stocks</label>'
        '<input id="ls-t" list="ls-tickers" autocomplete="off" spellcheck="false" placeholder="e.g. AAPL, XOM"></div>'
        f'<button class="btn btn-primary" type="submit">Add</button><span class="small" id="ls-count"></span>'
        f'<datalist id="ls-tickers">{opts}</datalist></form>'
        '<p class="small" id="ls-say" aria-live="polite"></p>'
        '<div id="ls-out"><noscript><p class="ls-empty">My list needs JavaScript and browser storage. '
        '<a href="/exposure">Every stock on record</a> works without them.</p></noscript></div>'
        '<div class="ls-share" id="ls-share" hidden><label for="ls-link" class="small">Share this list</label>'
        '<input id="ls-link" readonly style="flex:1;min-width:200px;min-height:40px;font:13px ui-monospace,monospace;'
        'border:1px solid var(--line);border-radius:8px;padding:0 8px;background:var(--bg);color:var(--ink)">'
        '<button type="button" class="btn btn-secondary" id="ls-copy">Copy link</button></div>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Bold figures held up; '
        'grey ones could not be told apart from zero. Nothing here is a recommendation to buy, sell or '
        'hold any security.</p>'
        f'<div class="actions"><a class="btn btn-primary" href="{escape(app_url)}/">Measure it as a portfolio</a>'
        '<a class="btn btn-secondary" href="/map">Stock map</a><a class="btn btn-secondary" href="/explore">What if?</a></div>'
        f'<script type="application/json" id="ls-data">{payload}</script>'
        f'<script>{script}</script>')
    ld = {"@context": "https://schema.org", "@type": "WebApplication", "name": title,
          "description": desc, "url": canonical, "applicationCategory": "FinanceApplication",
          "isAccessibleForFree": True}
    # Personal and script-drawn: nothing here for a search engine to read.
    return _shell(title, desc, canonical, ld, body, app_url, robots="noindex, follow")
