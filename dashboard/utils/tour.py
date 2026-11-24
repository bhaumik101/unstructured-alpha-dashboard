# utils/tour.py
# Unstructured Alpha — the first-visit walkthrough on the report's front page
#
# A newcomer lands on a form and a strip of numbers and has to guess what the
# product does. The tour shows them in about a minute, by having them DO the
# one thing that makes it click: measure a real portfolio. It spotlights one
# element at a time on a dimmed page; two steps are "click it" steps that
# block everything but the highlighted control, so the visitor's own click
# moves the story forward (the sample loads, the report appears).
#
# RULES
#   * Runs in the served page (scripts/inject_boot_splash.py adds it to the
#     runtime), because Streamlit strips <script> from page content.
#   * Starts on its own once: on the front page, for a browser with no tour
#     record and no previously measured portfolio. "Take the tour" restarts
#     it. Esc or "Skip tour" ends it at any step, and the page works the same
#     without it (no storage, no script -> no tour, nothing breaks).
#   * Every step targets an element the page really renders; a step whose
#     target is absent is skipped, never pointed at empty space.
#   * The copy describes what the visitor is looking at and what it measures.
#     It never calls anything a forecast or a recommendation.
#   * Stored in this browser only (localStorage "ua-tour-v1").

from __future__ import annotations

import json

KEY = "ua-tour-v1"

# (id, CSS selector, title, body, mode). mode "next": read, then Next.
# mode "click": everything but the target is blocked; clicking it advances.
# mode "wait": a centred card while the target appears (after a click step).
STEPS: tuple[tuple[str, str, str, str, str], ...] = (
    ("welcome", "", "Welcome to Unstructured Alpha",
     "In about a minute you'll measure a real portfolio and see which economic forces move it: "
     "interest rates, inflation, the dollar, oil and credit.", "next"),
    ("strip", ".udb-tiles", "The record, at a glance",
     "How many stocks are kept on record week by week, the five forces measured, and the latest "
     "week of data everything here is computed from.", "next"),
    ("forces", ".st-key-uar_forces", "What the forces did",
     "The five economic series themselves over the latest measured window, from FRED. "
     "Each report asks how a portfolio moved when these did.", "next"),
    ("build", ".st-key-uar_build", "Your portfolio goes here",
     "Search by name or ticker, upload a statement, or paste a list. Nothing is saved unless "
     "you choose to save it.", "next"),
    ("sample", ".st-key-uar_sample_balanced button", "Try one now",
     "Click Balanced ETF portfolio to measure a classic stocks-and-bonds mix.", "click"),
    ("measuring", ".uar-tiles", "Measuring…",
     "Three years of weekly returns, fitted against the five forces with the market's own move "
     "taken out. A few seconds.", "wait"),
    ("tiles", ".uar-tiles", "The answer first",
     "The largest measured exposure, how many readings held up, how much the portfolio moves "
     "with the stock market, and the window measured.", "next"),
    ("take", ".uar-take", "In one sentence",
     "What the portfolio is clearly sensitive to, and which holding carries most of it.", "next"),
    ("table", ".uar-xcard", "Every force, on one scale",
     "Each bar is the typical weekly move when that force moved. Solid means Clear, lighter "
     "means Tentative, an outline means it could not be told apart from zero.", "next"),
    ("flow", ".uar-flow", "Where it comes from",
     "Each ribbon is a holding's share of an exposure: its weight times its own sensitivity.",
     "next"),
    ("edit", ".st-key-uar_edit button", "Make it yours",
     "Click Change holdings to swap in your own. The report re-measures with whatever you add.",
     "click"),
)

# Where the last card sends someone curious for more. Real routes (app.py).
EXPLORE = (("Look up one stock", "/stock"), ("What changed this week", "/what-changed"),
           ("Stress-test a scenario", "/scenarios"))

TOUR_JS = r"""
(function(){
  var KEY = '__KEY__', STEPS = __STEPS__, EXPLORE = __EXPLORE__;
  var st = null, ui = null, timer = null, waitSince = 0;
  function load(){ try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; } }
  function save(s){ try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {} }
  function front(){ return (location.pathname || '/').replace(/\/+$/, '') === ''; }
  function q(sel){ if (!sel) return null; var e = document.querySelector(sel);
    if (!e) return null; var r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 ? e : null; }
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

  function css(){
    if (document.getElementById('uat-css')) return;
    var s = document.createElement('style'); s.id = 'uat-css';
    s.textContent = __CSS__;
    document.head.appendChild(s);
  }
  function build(){
    if (ui) return ui; css();
    ui = {
      ring: document.createElement('div'), card: document.createElement('div'),
      blocks: [0,1,2,3].map(function(){ var b = document.createElement('div'); b.className = 'uat-block'; return b; })
    };
    ui.ring.className = 'uat-ring';
    ui.card.className = 'uat-card'; ui.card.setAttribute('role', 'dialog'); ui.card.setAttribute('aria-modal', 'true');
    ui.card.setAttribute('aria-labelledby', 'uat-title');
    ui.blocks.forEach(function(b){ document.body.appendChild(b); });
    document.body.appendChild(ui.ring); document.body.appendChild(ui.card);
    ui.card.addEventListener('click', function(ev){
      var a = ev.target.closest('[data-uat]'); if (!a) return;
      var act = a.getAttribute('data-uat');
      if (act === 'next') go(st.i + 1);
      else if (act === 'skip' || act === 'close') end(act === 'skip' ? 'skipped' : 'done');
    });
    return ui;
  }
  function teardown(){
    if (!ui) return;
    ui.blocks.forEach(function(b){ b.remove(); }); ui.ring.remove(); ui.card.remove(); ui = null;
    if (timer) { clearInterval(timer); timer = null; }
    document.removeEventListener('keydown', onKey, true);
  }
  function end(how){ save({done: how, at: Date.now()}); st = null; teardown(); }
  function onKey(ev){ if (ev.key === 'Escape' && st) { ev.preventDefault(); end('skipped'); } }

  function go(i){
    // skip any step whose target the page does not render (wait steps wait instead)
    while (i < STEPS.length && STEPS[i][4] !== 'wait' && STEPS[i][1] && !q(STEPS[i][1])) i++;
    st = {i: i}; save({i: i});
    if (i >= STEPS.length) { finale(); return; }
    var s = STEPS[i], t = q(s[1]);
    if (s[4] === 'wait') waitSince = Date.now();
    if (t && s[4] !== 'wait') t.scrollIntoView({block: t.getBoundingClientRect().height > innerHeight * 0.55 ? 'start' : 'center',
                                                behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
    paint();
  }
  function dots(){
    var shown = STEPS.filter(function(s){ return s[4] !== 'wait'; }).length, k = 0;
    for (var j = 0; j < st.i; j++) if (STEPS[j][4] !== 'wait') k++;
    var h = ''; for (var d = 0; d < shown; d++) h += '<i class="' + (d < k ? 'on' : d === k ? 'now' : '') + '"></i>';
    return '<span class="uat-dots" aria-hidden="true">' + h + '</span><span class="uat-count">' + Math.min(k + 1, shown) + ' of ' + shown + '</span>';
  }
  function paint(){
    if (!st) return; build();
    var s = STEPS[st.i], t = s[4] === 'wait' ? null : q(s[1]);
    var center = !s[1] || s[4] === 'wait' || !t;
    ui.card.innerHTML =
      '<div class="uat-top">' + dots() + '<button type="button" class="uat-x" data-uat="skip" aria-label="Skip tour">Skip tour</button></div>'
      + '<h2 id="uat-title" class="uat-h">' + esc(s[2]) + '</h2><p class="uat-p">' + esc(s[3]) + '</p>'
      + (s[4] === 'click' ? '<p class="uat-hint"><span aria-hidden="true">●</span> Click the highlighted button to continue</p>'
         : s[4] === 'wait' ? '<p class="uat-hint uat-busy"><span aria-hidden="true"></span> Working</p>'
         : '<div class="uat-act"><button type="button" class="uat-next" data-uat="next">' + (st.i === 0 ? 'Show me' : 'Next') + '</button></div>');
    ui.card.classList.toggle('uat-center', center);
    place(t, s[4]);
    var b = ui.card.querySelector('.uat-next'); if (b) try { b.focus({preventScroll: true}); } catch (e) {}
  }
  function place(t, mode){
    var W = innerWidth, H = innerHeight, pad = 8;
    if (!t) {
      ui.ring.style.display = 'none';
      ui.blocks.forEach(function(b, k){ b.style.cssText = k ? 'display:none' : 'left:0;top:0;width:100%;height:100%;'; });
      ui.blocks[0].classList.add('uat-dim');
      ui.card.style.left = Math.max(16, (W - Math.min(440, W - 32)) / 2) + 'px'; ui.card.style.top = Math.max(16, H * 0.28) + 'px';
      return;
    }
    ui.blocks[0].classList.remove('uat-dim');
    var r = t.getBoundingClientRect();
    var x = Math.max(0, r.left - pad), y = Math.max(0, r.top - pad), w = Math.min(W, r.right + pad) - x, h = Math.min(H, r.bottom + pad) - y;
    ui.ring.style.cssText = 'display:block;left:' + x + 'px;top:' + y + 'px;width:' + w + 'px;height:' + h + 'px;';
    ui.ring.classList.toggle('uat-pulse', mode === 'click');
    // four blockers around the hole; on a "next" step the hole is blocked too
    var bl = ui.blocks;
    bl[0].style.cssText = 'left:0;top:0;width:100%;height:' + y + 'px;';
    bl[1].style.cssText = 'left:0;top:' + (y + h) + 'px;width:100%;height:' + Math.max(0, H - y - h) + 'px;';
    bl[2].style.cssText = 'left:0;top:' + y + 'px;width:' + x + 'px;height:' + h + 'px;';
    bl[3].style.cssText = mode === 'click'
      ? 'left:' + (x + w) + 'px;top:' + y + 'px;width:' + Math.max(0, W - x - w) + 'px;height:' + h + 'px;'
      : 'left:' + x + 'px;top:' + y + 'px;width:' + Math.max(0, W - x) + 'px;height:' + h + 'px;';
    // below the target, else above it, else beside it, else the corner that
    // covers least: a tall target (the exposure table) never hides under it
    var cw = Math.min(400, W - 32), ch = ui.card.offsetHeight || 200, top, left;
    var below = y + h + 14, above = y - 14 - ch;
    if (below + ch < H - 8) { top = below; left = r.left; }
    else if (above > 8) { top = above; left = r.left; }
    else if (x + w + cw + 28 < W) { left = x + w + 14; top = Math.min(Math.max(8, r.top), H - ch - 8); }
    else if (x - cw - 28 > 0) { left = x - cw - 14; top = Math.min(Math.max(8, r.top), H - ch - 8); }
    else { left = W - cw - 16; top = H - ch - 16; }
    left = Math.min(Math.max(16, left), W - cw - 16);
    ui.card.style.left = left + 'px'; ui.card.style.top = top + 'px';
  }
  function finale(){
    build(); st = {i: STEPS.length};
    ui.card.innerHTML = '<div class="uat-top"><span class="uat-count">Tour complete</span></div>'
      + '<h2 id="uat-title" class="uat-h">That’s the whole idea</h2>'
      + '<p class="uat-p">Measure anything you hold, any time. A few places worth a look next:</p>'
      + '<div class="uat-links">' + EXPLORE.map(function(e){ return '<a href="' + e[1] + '">' + esc(e[0]) + ' →</a>'; }).join('') + '</div>'
      + '<div class="uat-act"><button type="button" class="uat-next" data-uat="close">Done</button></div>';
    ui.card.classList.add('uat-center'); place(null, 'next');
    var b = ui.card.querySelector('.uat-next'); if (b) try { b.focus({preventScroll: true}); } catch (e) {}
  }
  function tick(){
    if (!st || st.i >= STEPS.length) return;
    var s = STEPS[st.i];
    if (s[4] === 'wait') {
      if (q(s[1])) { go(st.i + 1); return; }
      if (Date.now() - waitSince > 90000) { end('timeout'); return; }
      return;
    }
    var t = q(s[1]);
    if (!t) {
      // a click step's target went away: Streamlit is rerunning after the click
      if (s[4] === 'click') { go(st.i + 1); }
      return;
    }
    place(t, s[4]);
  }
  // the visitor's own click on a "click" step's target moves the tour on
  document.addEventListener('click', function(ev){
    if (!st || st.i >= STEPS.length) return;
    var s = STEPS[st.i]; if (s[4] !== 'click') return;
    var t = q(s[1]); if (t && (ev.target === t || t.contains(ev.target))) { setTimeout(function(){ if (st && STEPS[st.i] === s) go(st.i + 1); }, 60); }
  }, true);

  function start(at){
    st = {i: at || 0}; build(); document.addEventListener('keydown', onKey, true);
    if (!timer) timer = setInterval(tick, 250);
    go(st.i);
  }
  window.uaTour = function(){ start(0); };
  document.addEventListener('click', function(ev){
    var a = ev.target.closest && ev.target.closest('[data-ua-tour-start]');
    if (a) { ev.preventDefault(); start(0); }
  });

  // Resume a tour in progress (a click step reran the page), or start one on
  // a newcomer's first front-page visit once the builder is on screen.
  function boot(){
    var s = load();
    if (s && typeof s.i === 'number' && !s.done) { start(s.i); return true; }
    var seen = null; try { seen = localStorage.getItem('ua-last-portfolio'); } catch (e) {}
    if (!s && !seen && front() && q('.st-key-uar_build') && !/[?&](h|sample)=/.test(location.search)) { start(0); return true; }
    return false;
  }
  var tries = 0, bootT = setInterval(function(){ if (boot() || ++tries > 80) clearInterval(bootT); }, 500);
})();
"""

TOUR_CSS = (
    ".uat-block{position:fixed;z-index:2147483000;background:transparent;}"
    ".uat-block.uat-dim{background:rgba(4,8,14,.62);backdrop-filter:blur(2px);-webkit-backdrop-filter:blur(2px);}"
    ".uat-ring{position:fixed;z-index:2147483001;pointer-events:none;border-radius:16px;"
    "box-shadow:0 0 0 2px rgba(108,229,210,.95),0 0 0 9999px rgba(4,8,14,.62),0 0 34px 4px rgba(108,229,210,.45);"
    "transition:left .28s cubic-bezier(.2,.7,.2,1),top .28s cubic-bezier(.2,.7,.2,1),width .28s,height .28s;}"
    ".uat-ring.uat-pulse{animation:uat-pulse 1.6s ease-in-out infinite;}"
    "@keyframes uat-pulse{0%,100%{box-shadow:0 0 0 2px rgba(108,229,210,.95),0 0 0 9999px rgba(4,8,14,.62),0 0 24px 2px rgba(108,229,210,.35)}"
    "50%{box-shadow:0 0 0 4px rgba(108,229,210,1),0 0 0 9999px rgba(4,8,14,.62),0 0 46px 10px rgba(108,229,210,.6)}}"
    ".uat-card{position:fixed;z-index:2147483002;width:min(400px,calc(100vw - 32px));box-sizing:border-box;padding:18px 20px 16px;"
    "--uat-t-xs:12px;--uat-t-sm:13px;--uat-t-md:14px;--uat-t-base:15px;--uat-t-lg:19px;"
    "border-radius:18px;color:#eef3f9;font-family:Inter,system-ui,-apple-system,sans-serif;font-size:var(--uat-t-base);line-height:1.5;"
    "background:linear-gradient(180deg,rgba(255,255,255,.09),rgba(255,255,255,.02)),rgba(13,20,31,.88);"
    "border:1px solid rgba(148,180,210,.24);box-shadow:inset 0 1px 0 rgba(255,255,255,.1),0 30px 70px -20px rgba(0,0,0,.85);"
    "backdrop-filter:blur(18px) saturate(160%);-webkit-backdrop-filter:blur(18px) saturate(160%);"
    "transition:left .28s cubic-bezier(.2,.7,.2,1),top .28s cubic-bezier(.2,.7,.2,1);animation:uat-in .3s ease-out;}"
    ".uat-card.uat-center{width:min(440px,calc(100vw - 32px));}"
    "@keyframes uat-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}"
    ".uat-top{display:flex;align-items:center;gap:10px;margin-bottom:8px;}"
    ".uat-dots{display:inline-flex;gap:4px;}.uat-dots i{width:6px;height:6px;border-radius:50%;background:rgba(255,255,255,.2);}"
    ".uat-dots i.on{background:#6ce5d2;}.uat-dots i.now{background:#6ce5d2;box-shadow:0 0 0 3px rgba(108,229,210,.25);}"
    ".uat-count{font-family:ui-monospace,Menlo,monospace;font-weight:600;font-size:var(--uat-t-xs);letter-spacing:.06em;color:#a8b5c7;text-transform:uppercase;}"
    ".uat-x{margin-left:auto;border:0;background:none;color:#a8b5c7;font:inherit;font-size:var(--uat-t-sm);cursor:pointer;padding:6px 4px;}"
    ".uat-x:hover{color:#fff;text-decoration:underline;}"
    ".uat-h{margin:0 0 6px;font-size:var(--uat-t-lg);font-weight:700;letter-spacing:-.01em;color:#fff;}"
    ".uat-p{margin:0;color:#c9d5e6;}"
    ".uat-act{display:flex;justify-content:flex-end;margin-top:14px;}"
    ".uat-next{border:0;border-radius:11px;padding:9px 18px;font-family:inherit;font-weight:700;font-size:var(--uat-t-md);cursor:pointer;"
    "color:#04201c;background:linear-gradient(180deg,#8debdd,#6ce5d2);box-shadow:0 8px 22px -10px rgba(108,229,210,.8);}"
    ".uat-next:hover{filter:brightness(1.06);}"
    ".uat-next:focus-visible,.uat-x:focus-visible,.uat-links a:focus-visible{outline:2px solid #6ce5d2;outline-offset:2px;}"
    ".uat-hint{margin:12px 0 0;color:#6ce5d2;font-weight:650;font-size:var(--uat-t-md);display:flex;align-items:center;gap:8px;}"
    ".uat-hint span{animation:uat-blink 1.2s ease-in-out infinite;}"
    ".uat-busy span{width:14px;height:14px;border-radius:50%;border:2px solid rgba(108,229,210,.3);border-top-color:#6ce5d2;animation:uat-spin .8s linear infinite;}"
    "@keyframes uat-blink{50%{opacity:.25}}@keyframes uat-spin{to{transform:rotate(360deg)}}"
    ".uat-links{display:grid;gap:6px;margin-top:12px;}"
    ".uat-links a{display:block;padding:10px 12px;border-radius:11px;color:#eef3f9!important;text-decoration:none!important;font-weight:650;"
    "border:1px solid rgba(148,180,210,.2);background:rgba(255,255,255,.04);}"
    ".uat-links a:hover{border-color:rgba(108,229,210,.6);background:rgba(108,229,210,.08);}"
    "@media (prefers-reduced-motion:reduce){.uat-ring,.uat-card{transition:none;animation:none}.uat-ring.uat-pulse,.uat-hint span{animation:none}}"
)

# The app's light theme colours every h2, p, a and button with !important
# (html[data-ua-theme="light"] ...), and the card lives on that page. Measured
# live: a light-theme visitor saw a dark title on dark glass. Every text
# colour in the card is pinned here, more specific and !important.
TOUR_CSS += (
    "html body .uat-card,html body .uat-card *{text-shadow:none!important;}"
    "html body .uat-card h2.uat-h{color:#fff!important;}"
    "html body .uat-card p.uat-p{color:#c9d5e6!important;}"
    "html body .uat-card .uat-count{color:#a8b5c7!important;}"
    "html body .uat-card button.uat-x{color:#a8b5c7!important;background:none!important;border:0!important;box-shadow:none!important;}"
    "html body .uat-card button.uat-x:hover{color:#fff!important;}"
    "html body .uat-card p.uat-hint{color:#6ce5d2!important;}"
    "html body .uat-card button.uat-next{color:#04201c!important;background:linear-gradient(180deg,#8debdd,#6ce5d2)!important;border:0!important;}"
    "html body .uat-card .uat-links a{color:#eef3f9!important;}"
)


def tour_js() -> str:
    steps = [list(s) for s in STEPS]
    return (TOUR_JS.replace("__KEY__", KEY)
            .replace("__STEPS__", json.dumps(steps, ensure_ascii=False))
            .replace("__EXPLORE__", json.dumps([list(e) for e in EXPLORE]))
            .replace("__CSS__", json.dumps(TOUR_CSS)))
