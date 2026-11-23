# utils/palette.py
# Unstructured Alpha — the command palette: jump anywhere from anywhere
#
# Press ⌘K, Ctrl+K or "/" (or tap a search button) on any public page or the
# landing, type a ticker, a company, a force or a question, and go. Your
# recently viewed stocks and your list come first, so a returning visitor is
# one keystroke from where they left off.
#
# ONE implementation for both surfaces: served as /palette.js by the SEO
# service (www proxies it, like /xray.json), included by the landing
# (layout.tsx) and by every server-rendered page (exposure_pages._shell).
#
# RULES
#   * Its lists come from the code's own sources -- forces from the engine,
#     tools from the tools page, questions from the When pages -- so it cannot
#     offer a page that does not exist. Stocks load from /xray.json on first
#     open; without the feed the palette still offers everything else.
#   * Browser only: it reads the stores the pages already keep (ua-seen-v1,
#     ua-list); it writes nothing and sends one tool_used ("palette") the
#     first time a visitor goes somewhere with it.
#   * An accessible combobox: role=dialog, aria-activedescendant, arrow keys,
#     Enter, Escape, focus returned on close.

from __future__ import annotations

import json
from functools import lru_cache


@lru_cache(maxsize=1)
def palette_data() -> dict:
    from utils import exposure as ex
    from utils.tools_page import _TOOLS
    from utils.when_pages import BY_SLUG, title_for

    forces = [[f.key, f.label, "core" if f in ex.FACTORS else "more"] for f in (*ex.FACTORS, *ex.EXTRA_FACTORS)]
    tools = [[href, title] for href, title, *_ in _TOOLS]
    when = [[slug, title_for(*v)] for slug, v in BY_SLUG.items()]
    return {"forces": forces, "tools": tools, "when": when}


PALETTE_JS = r"""
(function(){
  if (window.__uaPalette) return; window.__uaPalette = 1;
  var DATA = __DATA__, feed = null, loading = null, box, input, list, items = [], active = 0, opener = null, used = false;
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function load(){
    loading = loading || fetch('/xray.json').then(function(r){ return r.ok ? r.json() : null; })
      .then(function(d){ feed = d && d.s ? d : null; if (box && box.classList.contains('open')) draw(); }).catch(function(){});
    return loading;
  }
  function seen(){
    var out = [];
    try { var o = JSON.parse(localStorage.getItem('ua-seen-v1') || '{}');
      out = Object.keys(o).sort(function(a, b){ return (o[b].t || 0) - (o[a].t || 0); }); } catch (e) {}
    try { (JSON.parse(localStorage.getItem('ua-list') || '[]') || []).forEach(function(t){ if (out.indexOf(t) < 0) out.push(t); }); } catch (e) {}
    return out.slice(0, 6);
  }
  function stockItem(t, why){
    var s = feed && feed.s[t];
    return {kind: 'stock', href: '/exposure/' + encodeURIComponent(t), t: t, title: s ? s[0] : '', sub: why || (s ? s[1] : '')};
  }
  function score(q, text){
    text = text.toLowerCase(); if (!q) return 1;
    if (text === q) return 100; if (text.indexOf(q) === 0) return 60;
    var i = text.indexOf(' ' + q); if (i >= 0) return 40; return text.indexOf(q) >= 0 ? 20 : 0;
  }
  function build(qraw){
    var q = qraw.trim().toLowerCase(), groups = [];
    var recent = seen();
    if (!q && recent.length) groups.push(['Pick up where you left off', recent.map(function(t){ return stockItem(t, 'Recently viewed'); })]);
    var stocks = [];
    if (q && feed){
      Object.keys(feed.s).forEach(function(t){
        var s = feed.s[t], sc = Math.max(score(q, t) * 2, score(q, s[0]));
        if (sc) stocks.push([sc + (recent.indexOf(t) >= 0 ? 15 : 0), stockItem(t)]);
      });
      stocks.sort(function(a, b){ return b[0] - a[0] || (a[1].t < b[1].t ? -1 : 1); });
      if (stocks.length) groups.push(['Stocks and ETFs', stocks.slice(0, 7).map(function(x){ return x[1]; })]);
    }
    if (q && !feed) groups.push(['Stocks and ETFs', [{kind: 'go', href: '/go?t=' + encodeURIComponent(qraw.trim().toUpperCase()), t: qraw.trim().toUpperCase(), title: 'Look up this ticker', sub: ''}]]);
    var forces = DATA.forces.map(function(f){ return [score(q, f[1]), {kind: 'force', href: '/forces/' + f[0], title: 'Stocks exposed to ' + f[1].toLowerCase().replace('u.s.', 'the U.S.'), sub: f[2] === 'core' ? 'Core force' : 'More forces'}]; })
      .filter(function(x){ return x[0]; });
    if (!q) forces = forces.filter(function(x, i){ return i < 5; });
    if (forces.length) groups.push(['Economic forces', forces.sort(function(a, b){ return b[0] - a[0]; }).slice(0, q ? 5 : 5).map(function(x){ return x[1]; })]);
    if (q){
      var when = DATA.when.map(function(w){ return [score(q, w[1].replace('Stocks that went up when ', '')) || score(q, w[1]), {kind: 'when', href: '/when/' + w[0], title: w[1], sub: 'What moved when'}]; })
        .filter(function(x){ return x[0]; }).sort(function(a, b){ return b[0] - a[0]; });
      if (when.length) groups.push(['Questions', when.slice(0, 4).map(function(x){ return x[1]; })]);
    }
    var tools = DATA.tools.map(function(t){ return [score(q, t[1]), {kind: 'tool', href: t[0], title: t[1], sub: 'Tool'}]; }).filter(function(x){ return x[0]; });
    if (tools.length) groups.push(['Tools', tools.sort(function(a, b){ return b[0] - a[0]; }).slice(0, q ? 5 : 6).map(function(x){ return x[1]; })]);
    return groups;
  }
  var ICON = {stock: '<path d="M4 17l5-5 4 3 7-8"/>', go: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4-4"/>',
    force: '<circle cx="12" cy="12" r="3"/><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/>', when: '<path d="M4 18h16M7 14l3-4 3 2 4-6"/>',
    tool: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 12h6"/>'};
  function draw(){
    var groups = build(input.value), html = '', n = 0; items = [];
    groups.forEach(function(g){
      html += '<li class="uap-g" role="presentation">' + esc(g[0]) + '</li>';
      g[1].forEach(function(it){
        items.push(it);
        html += '<li role="option" id="uap-o' + n + '" class="uap-o" data-i="' + n + '" aria-selected="false">'
          + '<svg viewBox="0 0 24 24" aria-hidden="true">' + ICON[it.kind] + '</svg>'
          + (it.t ? '<b>' + esc(it.t) + '</b>' : '') + '<span class="uap-title">' + esc(it.title || '') + '</span>'
          + '<span class="uap-sub">' + esc(it.sub || '') + '</span></li>';
        n++;
      });
    });
    if (!n) html = '<li class="uap-none" role="presentation">Nothing matches' + (feed ? '' : ' yet') + '. Try a ticker like XOM, a company, or a force like oil.</li>';
    list.innerHTML = html; active = 0; mark();
  }
  function mark(){
    var os = list.querySelectorAll('.uap-o');
    os.forEach(function(o, i){ o.setAttribute('aria-selected', String(i === active)); });
    if (os[active]){ input.setAttribute('aria-activedescendant', os[active].id); os[active].scrollIntoView({block: 'nearest'}); }
    else input.removeAttribute('aria-activedescendant');
  }
  function go(i){
    var it = items[i]; if (!it) return;
    if (!used){ used = true;
      try { var body = JSON.stringify({event: 'tool_used', page: window.__uaPage || 'Landing', tool: 'palette', internal: window.__uaInternal || undefined});
        if (navigator.sendBeacon) navigator.sendBeacon('/api/track', new Blob([body], {type: 'application/json'})); } catch (e) {} }
    location.href = it.href;
  }
  function make(){
    var css = document.createElement('style');
    css.textContent = '#uap{--uap-t-xs:11px;--uap-t-sm:12px;--uap-t-md:13px;--uap-t-base:14px;--uap-t-in:17px;position:fixed;inset:0;z-index:2147483000;display:none;align-items:flex-start;justify-content:center;padding:12vh 16px 16px;background:rgba(4,8,14,.62);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);font-family:Inter,"SF Pro Text","Segoe UI",system-ui,sans-serif}'
      + '#uap.open{display:flex}'
      + '#uap .uap-card{width:100%;max-width:640px;max-height:70vh;display:flex;flex-direction:column;border-radius:16px;overflow:hidden;background:#0f1724;color:#f3f6fa;border:1px solid #2c3b52;box-shadow:0 30px 80px -20px rgba(0,0,0,.8),inset 0 1px 0 rgba(255,255,255,.05)}'
      + '#uap .uap-in{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid #1f2b3d}'
      + '#uap .uap-in svg{width:18px;height:18px;flex:none;stroke:#6ce5d2;fill:none;stroke-width:2}'
      + '#uap input{flex:1;min-width:0;border:0;background:transparent;color:#f3f6fa;font:inherit;font-size:var(--uap-t-in);outline:none}'
      + '#uap input::placeholder{color:#7f8da3}'
      + '#uap kbd{font-family:ui-monospace,Menlo,monospace;font-size:var(--uap-t-xs);color:#a8b5c7;border:1px solid #2c3b52;border-radius:5px;padding:2px 6px}'
      + '#uap ul{list-style:none;margin:0;padding:6px;overflow:auto}'
      + '#uap .uap-g{padding:10px 10px 4px;font-size:var(--uap-t-xs);letter-spacing:.07em;text-transform:uppercase;color:#7f8da3;font-weight:600}'
      + '#uap .uap-o{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:9px;cursor:pointer;min-height:24px}'
      + '#uap .uap-o svg{width:16px;height:16px;flex:none;stroke:#8794a8;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}'
      + '#uap .uap-o b{font-family:ui-monospace,Menlo,monospace;font-weight:600;font-size:var(--uap-t-md);color:#bff4ec;min-width:48px}'
      + '#uap .uap-title{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:var(--uap-t-base)}'
      + '#uap .uap-sub{font-size:var(--uap-t-sm);color:#7f8da3;white-space:nowrap}'
      + '#uap .uap-o[aria-selected=true]{background:rgba(108,229,210,.12);box-shadow:inset 0 0 0 1px rgba(108,229,210,.35)}'
      + '#uap .uap-o[aria-selected=true] svg{stroke:#6ce5d2}'
      + '#uap .uap-none{padding:18px 12px;color:#a8b5c7;font-size:var(--uap-t-base)}'
      + '#uap .uap-foot{display:flex;gap:14px;padding:9px 14px;border-top:1px solid #1f2b3d;font-size:var(--uap-t-xs);color:#7f8da3}'
      + '@media (max-width:640px){#uap{padding:10px}#uap .uap-sub{display:none}#uap .uap-card{max-height:85vh}}'
      + '@media (prefers-reduced-motion:no-preference){#uap.open .uap-card{animation:uap-in .18s ease-out}}'
      + '@keyframes uap-in{from{opacity:0;transform:translateY(-6px) scale(.985)}to{opacity:1;transform:none}}';
    document.head.appendChild(css);
    box = document.createElement('div'); box.id = 'uap';
    box.innerHTML = '<div class="uap-card" role="dialog" aria-modal="true" aria-label="Search Unstructured Alpha">'
      + '<div class="uap-in"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="M20 20l-4-4"/></svg>'
      + '<input id="uap-q" type="text" role="combobox" aria-expanded="true" aria-controls="uap-l" aria-autocomplete="list" autocomplete="off" spellcheck="false" placeholder="Search a stock, a company, a force or a question">'
      + '<kbd>esc</kbd></div><ul id="uap-l" role="listbox" aria-label="Results"></ul>'
      + '<div class="uap-foot"><span>&uarr;&darr; to move</span><span>&crarr; to open</span><span>&#8984;K or / anywhere</span></div></div>';
    document.body.appendChild(box);
    input = box.querySelector('input'); list = box.querySelector('ul');
    input.addEventListener('input', draw);
    input.addEventListener('keydown', function(e){
      if (e.key === 'ArrowDown'){ e.preventDefault(); active = Math.min(items.length - 1, active + 1); mark(); }
      else if (e.key === 'ArrowUp'){ e.preventDefault(); active = Math.max(0, active - 1); mark(); }
      else if (e.key === 'Enter'){ e.preventDefault(); go(active); }
      else if (e.key === 'Escape'){ e.preventDefault(); close(); }
    });
    list.addEventListener('click', function(e){ var o = e.target.closest('.uap-o'); if (o) go(+o.getAttribute('data-i')); });
    list.addEventListener('mousemove', function(e){ var o = e.target.closest('.uap-o'); if (o && +o.getAttribute('data-i') !== active){ active = +o.getAttribute('data-i'); mark(); } });
    box.addEventListener('mousedown', function(e){ if (e.target === box) close(); });
  }
  function open(){
    if (!box) make();
    opener = document.activeElement; load();
    box.classList.add('open'); input.value = ''; draw(); input.focus();
  }
  function close(){
    if (!box) return; box.classList.remove('open');
    // Back to where focus was -- except the header's search box, which would reopen us.
    if (opener && opener.focus && !(opener.hasAttribute && opener.hasAttribute('data-ua-palette-input'))) opener.focus();
  }
  window.uaPalette = open;
  document.addEventListener('keydown', function(e){
    var typing = /^(input|textarea|select)$/i.test((e.target && e.target.tagName) || '') || (e.target && e.target.isContentEditable);
    if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')){ e.preventDefault(); (box && box.classList.contains('open')) ? close() : open(); }
    else if (e.key === '/' && !typing && !(box && box.classList.contains('open'))){ e.preventDefault(); open(); }
  });
  document.addEventListener('click', function(e){ var t = e.target.closest && e.target.closest('[data-ua-palette]'); if (t){ e.preventDefault(); open(); } });
  // The header's ticker box: still a plain form without JavaScript; with it,
  // focusing the box opens the palette carrying whatever was typed.
  document.addEventListener('focusin', function(e){
    var t = e.target; if (!t || !t.hasAttribute || !t.hasAttribute('data-ua-palette-input')) return;
    var v = t.value; t.blur(); open(); if (v){ input.value = v; draw(); }
  });
})();
"""


def palette_js() -> str:
    return PALETTE_JS.replace("__DATA__", json.dumps(palette_data(), separators=(",", ":")))
