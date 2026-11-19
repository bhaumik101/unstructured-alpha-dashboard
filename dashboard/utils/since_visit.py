# utils/since_visit.py
# Unstructured Alpha — "since your last visit": what changed in the stocks you looked at
#
# A reason to come back between weekly emails. When a visitor opens a stock
# page, the browser remembers that stock's five core readings as they were
# shown. On a later visit, those are compared with the current week's: a
# link that started holding up, one that stopped, or a held reading that
# moved noticeably. A small card on any page says how many changed; the full
# list is on My list, with "mark all as seen".
#
# RULES
#   * Browser only (localStorage): no account, nothing sent anywhere.
#   * Readings are compared in the exact form the X-ray feed and My list use
#     (utils.list_page.list_data: [impact rounded to 4dp, 1 if it held up]),
#     so a stock that did not change can never show as changed.
#   * "Held up" means the site's own STANDS_UP labels. A move counts only when
#     the reading held up and shifted by MOVE points or more; noise inside a
#     reading that never held up is not news.
#   * It describes the past; it never says what to do.

from __future__ import annotations

import json

from utils.explore_page import JS_PCT

MOVE = 0.5           # percentage points, for a held reading to count as moved
MAX_REMEMBERED = 40

SINCE_JS = r"""
window.UAS = window.UAS || (function(){
  var K = 'ua-seen-v1', MAX = __MAX__, MOVE = __MOVE__;
  function load(){ try { var o = JSON.parse(localStorage.getItem(K) || '{}');
    return o && typeof o === 'object' && !Array.isArray(o) ? o : {}; } catch (e) { return {}; } }
  function save(o){
    Object.keys(o).sort(function(a, b){ return (o[b].t || 0) - (o[a].t || 0); }).slice(MAX).forEach(function(k){ delete o[k]; });
    try { localStorage.setItem(K, JSON.stringify(o)); } catch (e) {}
  }
  function remember(t, r, a){ var o = load(); o[t] = {r: r, a: a, t: Date.now()}; save(o); }
  function adopt(t, feed){ var o = load(); if (o[t] || !feed.s[t]) return; o[t] = {r: feed.s[t][2], a: feed.as_of, t: Date.now()}; save(o); }
  // feed: {f: [[key, label, phrase]], s: {T: [name, sector, [[impact, held] | null, ...]]}, as_of}
  function diff(feed){
    var o = load(), out = [];
    Object.keys(o).forEach(function(t){
      var b = o[t], cur = feed.s[t];
      if (!cur || !b || !Array.isArray(b.r)) return;
      feed.f.forEach(function(f, i){
        var was = b.r[i], now = cur[2][i];
        if (!was || !now) return;
        var kind = now[1] && !was[1] ? 'gained' : was[1] && !now[1] ? 'lost'
                 : now[1] && Math.abs(now[0] - was[0]) >= MOVE ? 'moved' : '';
        if (kind) out.push({t: t, name: cur[0], label: f[1], kind: kind, was: was[0], now: now[0], since: b.a || ''});
      });
    });
    var rank = {gained: 0, lost: 1, moved: 2};
    out.sort(function(a, b){ return rank[a.kind] - rank[b.kind] || Math.abs(b.now - b.was) - Math.abs(a.now - a.was) || (a.t < b.t ? -1 : 1); });
    return out;
  }
  function markSeen(feed){
    var o = load();
    Object.keys(o).forEach(function(t){ if (feed.s[t]) { o[t].r = feed.s[t][2]; o[t].a = feed.as_of; o[t].t = Date.now(); } });
    save(o);
  }
  function count(){ return Object.keys(load()).length; }
  function lower(l){ return l.indexOf('U.S.') === 0 ? l : l.charAt(0).toLowerCase() + l.slice(1); }
  /*PCT*/
  // One change, as a plain sentence. Escaped by the caller's esc().
  function sentence(c){
    var f = lower(c.label);
    return c.kind === 'gained' ? 'now has a link to ' + f + ' that holds up (' + pct(c.now) + ')'
         : c.kind === 'lost' ? 'its link to ' + f + ' no longer holds up (was ' + pct(c.was) + ')'
         : 'with ' + f + ': ' + pct(c.was) + ' → ' + pct(c.now);
  }
  return {remember: remember, adopt: adopt, diff: diff, markSeen: markSeen, count: count, sentence: sentence, _key: K};
})();
"""


def since_js() -> str:
    return (SINCE_JS.replace("__MAX__", str(MAX_REMEMBERED)).replace("__MOVE__", repr(MOVE))
            .replace("/*PCT*/", JS_PCT))


def remember_script(symbol: str, rec: dict) -> str:
    """On a stock page: remember its readings exactly as the feed encodes them."""
    from utils.list_page import list_data
    row = list_data([dict(rec, ticker=symbol)])
    r = row["s"][symbol][2]
    args = json.dumps([symbol, r, str(rec.get("as_of") or "")[:10]], separators=(",", ":")).replace("</", "<\\/")
    return f"<script>try{{window.UAS&&UAS.remember.apply(null,{args});}}catch(e){{}}</script>"


# The card on every page. Fetches the X-ray feed only for someone who has
# looked at stocks before; shows nothing when nothing changed, on My list
# (which has the full panel), or once dismissed this session.
CARD_JS = r"""
(function(){
  try {
    if (!window.UAS || !UAS.count() || location.pathname === '/mylist') return;
    try { if (sessionStorage.getItem('ua-since-x')) return; } catch (e) {}
    fetch('/xray.json').then(function(r){ return r.ok ? r.json() : null; }).then(function(feed){
      if (!feed || !feed.s) return;
      var ch = UAS.diff(feed); if (!ch.length) return;
      var esc = function(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); };
      var el = document.createElement('aside');
      el.className = 'since'; el.setAttribute('aria-label', 'Since your last visit');
      el.innerHTML = '<p class="since-k">Since your last visit</p>'
        + '<p class="since-h">' + ch.length + (ch.length === 1 ? ' change' : ' changes') + ' in stocks you looked at</p>'
        + '<p class="since-s"><b>' + esc(ch[0].t) + '</b> ' + esc(UAS.sentence(ch[0])) + (ch.length > 1 ? ', and more.' : '.') + '</p>'
        + '<div class="since-a"><a class="btn btn-primary" href="/mylist#since">See what changed</a>'
        + '<button type="button" class="since-x" aria-label="Dismiss">×</button></div>';
      document.body.appendChild(el);
      el.querySelector('.since-x').addEventListener('click', function(){
        el.remove(); try { sessionStorage.setItem('ua-since-x', '1'); } catch (e) {}
      });
    }).catch(function(){});
  } catch (e) {}
})();
"""

CARD_CSS = (
    '.since{position:fixed;z-index:30;right:max(16px,env(safe-area-inset-right,0px));'
    'bottom:calc(16px + env(safe-area-inset-bottom,0px));width:min(360px,calc(100vw - 32px));padding:16px 18px;'
    'border-radius:16px;color:#e6edf7;box-shadow:0 18px 50px -18px rgba(5,15,30,.65);'
    'background:radial-gradient(400px 160px at 100% 0%,rgba(255,194,75,.16),transparent 60%),'
    'linear-gradient(160deg,var(--navy),var(--navy2));background-color:var(--navy);animation:since-in .35s ease-out}'
    '.since p{margin:0}.since-k{color:var(--bright);text-transform:uppercase;letter-spacing:.07em;font-size:var(--fs-xs);font-weight:800}'
    '.since-h{color:#fff;font-weight:800;margin:4px 0 6px}.since-s{color:#c9d5e6;font-size:var(--fs-sm)}'
    '.since-a{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:12px}'
    '.since-x{border:0;background:rgba(255,255,255,.08);color:#fff;width:36px;height:36px;border-radius:50%;cursor:pointer;font:inherit}'
    '.since-x:hover{background:rgba(255,255,255,.16)}'
    '@keyframes since-in{from{transform:translateY(12px);opacity:0}to{transform:none;opacity:1}}'
    '@media (prefers-reduced-motion:reduce){.since{animation:none}}'
)


# The full list, on My list. Uses the page's own embedded data (ls-data, the
# same shape as the feed); stocks saved to the list without ever being opened
# are adopted at today's readings, so their changes show from next week.
PANEL_HTML = ('<section class="card ls-since" id="since" aria-labelledby="since-h" hidden>'
              '<h2 id="since-h">Since your last visit</h2><div id="since-body"></div></section>')

PANEL_JS = r"""
(function(){
  try {
    if (!window.UAS) return;
    var feed = JSON.parse(document.getElementById('ls-data').textContent);
    var list = []; try { list = JSON.parse(localStorage.getItem('ua-list') || '[]'); } catch (e) {}
    (Array.isArray(list) ? list : []).forEach(function(t){ UAS.adopt(t, feed); });
    var n = UAS.count(); if (!n) return;
    var box = document.getElementById('since'), body = document.getElementById('since-body');
    var esc = function(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); };
    function draw(){
      var ch = UAS.diff(feed);
      body.innerHTML = ch.length
        ? '<ul class="since-list">' + ch.map(function(c){
            return '<li class="since-' + c.kind + '"><a href="/exposure/' + encodeURIComponent(c.t) + '"><b>' + esc(c.t) + '</b></a> '
              + esc(UAS.sentence(c)) + '</li>'; }).join('') + '</ul>'
          + '<p class="small">Compared with the readings when you last looked at each stock. A change is a link '
          + 'that started or stopped holding up, or a held reading that moved __MOVE__ points or more. The past, not a forecast.</p>'
          + '<button type="button" class="btn btn-secondary" id="since-seen">Mark all as seen</button>'
        : '<p>No changes in the ' + n + (n === 1 ? ' stock' : ' stocks') + ' you have looked at, since you last did. '
          + 'Most weeks most links hold steady, and that is an answer too.</p>';
      var b = document.getElementById('since-seen');
      if (b) b.addEventListener('click', function(){ UAS.markSeen(feed); draw(); });
    }
    box.hidden = false; draw();
  } catch (e) {}
})();
"""

PANEL_CSS = (
    '.ls-since{padding:18px 20px;margin:0 0 18px}.ls-since h2{margin:0 0 10px}'
    '.since-list{list-style:none;margin:0 0 10px;padding:0;display:grid;gap:8px}'
    '.since-list li{padding:8px 0 8px 12px;border-left:3px solid var(--line);color:var(--ink2)}'
    '.since-list .since-gained{border-left-color:#2e9d6a}.since-list .since-lost{border-left-color:#c9824a}'
    '.since-list .since-moved{border-left-color:var(--accent)}'
)


def panel_html() -> str:
    """The panel's place on My list (hidden until its script fills it)."""
    return f"<style>{PANEL_CSS}</style>{PANEL_HTML}"


def panel_script() -> str:
    """Must come after the page's ls-data."""
    return f"<script>{PANEL_JS.replace('__MOVE__', repr(MOVE))}</script>"
