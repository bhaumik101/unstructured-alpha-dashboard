#!/usr/bin/env python3
"""
Build-time: inject a branded dark boot splash into Streamlit's served index.html.

WHY: Streamlit ships a single-page app whose ~MB JS bundle downloads BEFORE any of
our Python runs. During that window the browser shows a blank (dark, via our theme)
screen. Nothing in our app code can paint there — the only lever is the HTML page
Streamlit itself serves. This injects a full-viewport, on-brand loader (exact app
background #0B0D12, logo, animated bar) right after <body>. The loader remains
until Streamlit has rendered real page content, its run/spinner indicators are
gone, and the DOM has settled; a hard timeout ensures it can never cover an error
forever.

SAFETY:
- Repeatable (updates an existing current or legacy injection in-place).
- Fully wrapped in try/except and ALWAYS exits 0 — a failure here must never fail
  the build or leave a half-written file (writes only after a successful transform).
- Trivially reversible: remove this step from render.yaml's buildCommand; the next
  deploy reinstalls a pristine Streamlit index.html.

Run from buildCommand AFTER `pip install`:  python scripts/inject_boot_splash.py
"""
import json
import hashlib
import os
import re
import sys

# Render runs this as `python scripts/inject_boot_splash.py`, so the dashboard
# root is not on sys.path and `utils` does not import. This used to happen as a
# side effect of loading the splash's macro facts; when those went, every later
# step (legacy slugs, meta, the global stylesheet) lost its imports and main()
# skipped the whole injection. Explicit, and first, so nothing depends on order.
_DASHBOARD_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

MARKER = "ua-boot-splash"
START_MARKER = "<!-- ua-boot-splash:start -->"
END_MARKER = "<!-- ua-boot-splash:end -->"

# The always-on runtime, under its own markers. It used to live inside the
# splash markers, which made "remove the splash" and "remove the theme
# bootstrap, client-side navigation and the proxy links' a11y marking" the same
# edit. This file now injects five independent blocks, each separately
# removable: ua-runtime, ua-boot-splash, ua-meta, ua-seo, ua-global-css.
RUNTIME_START = "<!-- ua-runtime:start -->"
RUNTIME_END = "<!-- ua-runtime:end -->"


def _build_runtime() -> str:
    """Scripts that must run on every page, splash or no splash.

    Theme bootstrap, the client-side navigation proxy and the proxy links'
    accessibility marking. None of it is about the splash; it lived inside
    the splash markers only because that is where the first injected
    <script> happened to go. Deleting the splash would have taken the theme
    (dark-to-light flash on every load), client-side navigation (full
    reload per click) and the proxy links' aria-hidden/tabindex with it.

    Injected under its own markers so the splash can be removed on its own.
    """
    import json as _json

    return (RUNTIME_START + "\n" + r"""<script>
/* Theme init — runs before first paint so there is no dark-to-light flash.
   This has to live here rather than in utils/header.py: st.markdown does NOT
   execute script tags, and a Streamlit component would run inside a sandboxed
   iframe where it cannot style the parent document. This file is injected into
   the served index.html, so its script really runs and owns the html element.

   Theme choice is explicit and durable. Enter with ?theme=light or ?theme=dark;
   the choice persists so in-app navigation keeps it without a first-paint
   flash in the opposite palette. */
(function(){
  try{
    var q=null;
    try{ q=new URLSearchParams(window.location.search).get('theme'); }catch(e){}
    if(q==='light'||q==='dark'){ try{ localStorage.setItem('ua-theme',q); }catch(e){} }
    var t=q;
    if(!t){ try{ t=localStorage.getItem('ua-theme'); }catch(e){} }
    /* Light is the default since 2026-09-14: advisers print and screen-share. */
    if(t!=='dark'){ document.documentElement.setAttribute('data-ua-theme','light'); }
    else { document.documentElement.removeAttribute('data-ua-theme'); }
  }catch(e){}
  /* ── Reopen the portfolio you last measured ───────────────────────────
     A visitor measured a portfolio, closed the tab, and came back a week
     later to an empty form and the same typing again. That is the retention
     hole in an anonymous-first product: there is nothing to come back TO.

     The report is already fully described by its ?h= parameter, so the whole
     mechanic is: remember that parameter, and on a bare visit to the front
     door, reopen it. The portfolio is stored ONLY in this browser, is never
     sent anywhere by this code, and the page says so.

     Rules, each one earned:
       - only the bare front door. A real ?h= link, a ?sample=, a ?theme= or
         any other query is the visitor being explicit, and beats a memory.
       - once per tab (sessionStorage). Otherwise "Start fresh" would bounce
         straight back to the portfolio it just cleared.
       - ?fresh=1 forgets. That is what the page's own "Start fresh" links to,
         because Streamlit cannot reach localStorage itself.
       - a crawler has neither storage nor a saved portfolio, so it always
         sees the real front door. */
  try{
    var UAP='ua-last-portfolio';
    /* The report writes its own ?h= through Streamlit, which rewrites the URL
       WITHOUT a page load — so a one-shot read at boot saw the URL the visitor
       arrived on and never the portfolio they went on to measure. Measured:
       build a portfolio from scratch, and nothing was remembered at all.
       history.replaceState fires no event, so this is a cheap poll. */
    function uaRemember(){
      try{
        var h=new URLSearchParams(window.location.search).get('h');
        if(h && h !== localStorage.getItem(UAP)){ localStorage.setItem(UAP, h); }
      }catch(e){}
    }
    try{ setInterval(uaRemember, 1500); }catch(e){}
    var uaQ=new URLSearchParams(window.location.search);
    if(uaQ.get('fresh')){
      try{ localStorage.removeItem(UAP); sessionStorage.setItem('ua-reopened','1'); }catch(e){}
      window.location.replace('/');
    } else {
      var uaH=uaQ.get('h');
      if(uaH){
        uaRemember();
      } else if((location.pathname||'/').replace(/\/+$/,'') === '' && !uaQ.toString()){
        var uaSaved=null, uaDone=null;
        try{ uaSaved=localStorage.getItem(UAP); uaDone=sessionStorage.getItem('ua-reopened'); }catch(e){}
        if(uaSaved && !uaDone){
          try{ sessionStorage.setItem('ua-reopened','1'); }catch(e){}
          window.location.replace('/?h='+encodeURIComponent(uaSaved)+'&reopened=1');
        }
      }
    }
  }catch(e){}

  /* ── Client-side navigation proxy ──────────────────────────────────────
     The visible top nav is raw <a href> markup, so a click is a FULL browser
     navigation: 135 JS files re-parsed, new websocket, fresh Python session.
     st.page_link instead renders an anchor with a React onClick handler that
     navigates client-side. render_header emits one hidden page-link per
     destination, so forwarding the click to the matching one keeps the design
     and skips the reload.

     Two things learned the hard way and encoded here:
       - A synthetic MouseEvent does NOT work; React ignores it. Only a real
         .click() on the element triggers the handler.
       - history.pushState + popstate does NOT work either; Streamlit's frontend
         ignores it, changing the URL without re-rendering. There is no
         URL-based shortcut -- it must go through the element.

     Everything degrades safely: any miss falls through to the anchor's real
     href, i.e. today's behaviour. */
  document.addEventListener('click', function(ev){
    try{
      /* Any internal link, not just the nav. Measured on production: 23 of 27
         internal anchors sat inside the nav and were already client-side, but
         the logo and footer links still forced a full reload. Matching on
         href is safe because a link only gets proxied when a page_link with
         that exact slug exists -- SEO-service paths like /ticker/AAPL are not
         Streamlit pages, find no proxy, and fall through untouched. */
      var a = ev.target && ev.target.closest && ev.target.closest('a[href^="/"]');
      if(!a) return;
      /* A page_link is ALREADY client-side -- it carries React's onClick. Let
         it handle its own click instead of forwarding to a different element
         that does the same thing. (Only reachable now that the visible
         page_links on Signal Research are no longer hidden by the CSS.) */
      if(a.closest('[data-testid="stPageLink-NavLink"]')) return;
      if(ev.defaultPrevented || ev.button !== 0) return;
      if(ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;  /* open-in-new-tab */
      if(a.target && a.target !== '_self') return;
      var href = a.getAttribute('href') || '';
      if(!href || href.charAt(0) !== '/') return;                        /* external */
      var slug = href.replace(/^\/+|\/+$/g, '');

      var links = document.querySelectorAll('[data-testid="stPageLink-NavLink"]');
      for(var i=0;i<links.length;i++){
        var lh = (links[i].getAttribute('href')||'').replace(/^\/+|\/+$/g, '');
        if(lh === slug){
          ev.preventDefault();
          links[i].click();      /* real click -> React handler -> SPA nav */
          return;
        }
      }
      /* No proxy found: do nothing and let the browser follow the href. */
    }catch(e){ /* never block navigation */ }
  }, true);

  /* Only the rail's proxies. Unscoped, this also stamped tabindex=-1 and
     aria-hidden=true onto the real, visible page_links on Signal Research --
     pulling them out of the tab order and hiding them from screen readers.
     The proxy links are clipped out of view but still focusable, which would
     drop ~33 invisible stops into the keyboard tab order on every page. There
     is no server-side wrapper to fix this with (two st.markdown calls cannot
     span a container), so mark them here in the real DOM. Streamlit re-renders
     them on every navigation, hence the observer. Cheap by construction: the
     callback is debounced to an animation frame and only touches elements not
     already marked. */
  function uaMarkProxyLinks(){
    try{
      var links = document.querySelectorAll(
        '.st-key-ua_spa_proxy_rail [data-testid="stPageLink-NavLink"]:not([data-ua-proxy])');
      for(var i=0;i<links.length;i++){
        links[i].setAttribute('data-ua-proxy','1');
        links[i].setAttribute('tabindex','-1');
        links[i].setAttribute('aria-hidden','true');
      }
    }catch(e){}
  }
  /* Scheduling matters more than it looks. A browser freezes
     requestAnimationFrame in a background tab, and throttles setTimeout there
     too, so a page opened with middle-click or "open link in new tab" could
     paint its proxy links and never mark them -- leaving ~40 invisible stops
     in the keyboard tab order for exactly the user who needs the tab order to
     be sane. Belt and braces: a frame if one comes, a timer if it does not,
     and a re-check when the tab is actually shown. Marking is idempotent
     (:not([data-ua-proxy])), so running it more than once costs nothing. */
  var uaMarkQueued=false;
  function uaRunMark(){ uaMarkQueued=false; uaMarkProxyLinks(); }
  function uaQueueMark(){
    if(uaMarkQueued) return;
    uaMarkQueued=true;
    try{ requestAnimationFrame(uaRunMark); }catch(e){}
    setTimeout(uaRunMark, 120);
  }
  try{
    document.addEventListener('visibilitychange', function(){
      if(document.visibilityState === 'visible'){ uaMarkProxyLinks(); }
    });
    addEventListener('pageshow', uaMarkProxyLinks);
    addEventListener('focus', uaMarkProxyLinks);
  }catch(e){}
  /* ── Streamlit's false "Page not found" on a valid deep link ─────────────
     Observed live on /signal-dashboard while signed in, and on /track-record:
     a large overlay reading "The page that you have requested does not seem to
     exist. Running the app's main page." -- and then the correct page renders
     underneath it.

     It is a cold-start race, not a routing bug. st.navigation() is already the
     first Streamlit call in app.py, but on a freshly started process the
     frontend resolves the URL before the page list exists. Warm loads never
     show it, which is why it survived this long: it greets the FIRST visitor
     after every deploy and every idle spin-down, on a link that works.

     Self-limiting by construction. The message is only removed when the
     current path has a registered route, proven by the presence of a proxy
     page_link with that exact slug -- the same list render_header emits. A
     genuine 404 has no matching proxy, so the real message still shows. */
  /* axe: scrollable-region-focusable. A container that scrolls but cannot be
     focused is unreachable by keyboard -- you can see the overflow and have no
     way to move it without a mouse. Streamlit generates these wrappers itself
     (stElementContainer around wide tables and chart blocks), so there is no
     Python-side hook; found by axe against the live app, 7 nodes on Market
     Overview and 1 on Sector View.

     tabindex="0" on the scroller is the fix the rule asks for. Skipped when the
     region already contains something focusable, so we do not add a redundant
     tab stop in front of controls that are already reachable. */
  function uaFocusableScrollers(){
    try{
      var nodes = document.querySelectorAll(
        '[data-testid="stElementContainer"], [data-testid="stDataFrame"]');
      for(var i=0;i<nodes.length;i++){
        var el = nodes[i];
        if(el.hasAttribute('tabindex')) continue;
        var scrolls = el.scrollHeight > el.clientHeight + 2 ||
                      el.scrollWidth  > el.clientWidth  + 2;
        if(!scrolls) continue;
        var style = window.getComputedStyle(el);
        if(!/(auto|scroll)/.test(style.overflowX + ' ' + style.overflowY)) continue;
        if(el.querySelector('a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])')) continue;
        el.setAttribute('tabindex','0');
      }
    }catch(e){}
  }

  function uaLabelUploads(){
    /* Streamlit renders the file uploader's label as a sibling <div> and never
       associates it with the hidden <input type=file>, so axe reports a real
       "form element has no label" failure on every page with an uploader. The
       label text is right there in the DOM; this connects the two.

       It lives here rather than in CSS because only an attribute fixes it, and
       rather than in Python because Streamlit owns that markup. */
    try{
      var inputs = document.querySelectorAll(
        'input[data-testid="stFileUploaderDropzoneInput"]:not([aria-label])');
      for(var i=0;i<inputs.length;i++){
        var input = inputs[i];
        var widget = input.closest('[data-testid="stFileUploader"]');
        var label = widget && widget.querySelector('[data-testid="stWidgetLabel"]');
        var text = (label && label.innerText || '').trim().replace(/\s+/g,' ');
        input.setAttribute('aria-label', text ? text.slice(0,180) : 'Choose a file to upload');
      }
    }catch(e){}
  }

  /* The client summary's "Print or save as PDF" link. st.markdown strips
     <script> and a Streamlit button runs Python on a server that cannot open
     the visitor's print dialog, so the page renders a plain link and this
     turns it into window.print(). */
  try{
    document.addEventListener('click', function(ev){
      var link = ev.target && ev.target.closest && ev.target.closest('[data-ua-print]');
      if(!link) return;
      ev.preventDefault();
      try{ window.print(); }catch(e){}
    });
  }catch(e){}

  function uaDropFalse404(){
    try{
      var slug = location.pathname.replace(/^\/+|\/+$/g, '');
      if(!slug) return;                    /* home is always valid */
      var registered = false;
      var links = document.querySelectorAll(
        '.st-key-ua_spa_proxy_rail [data-testid="stPageLink-NavLink"]');
      for(var i=0;i<links.length;i++){
        if((links[i].getAttribute('href')||'').replace(/^\/+|\/+$/g,'') === slug){
          registered = true; break;
        }
      }
      if(!registered) return;              /* real 404 -- leave it alone */

      var nodes = document.querySelectorAll('div,span,p');
      for(var j=0;j<nodes.length;j++){
        var n = nodes[j];
        if(n.children.length) continue;    /* leaf text only */
        if(!/does not seem to exist/i.test(n.textContent||'')) continue;
        /* Walk up to the alert/toast/dialog Streamlit wrapped it in and drop
           that, rather than guessing a testid that changes between releases. */
        var box = n;
        for(var k=0;k<6 && box.parentElement;k++){
          box = box.parentElement;
          var tid = box.getAttribute('data-testid') || '';
          if(/stToast|stAlert|stDialog|stModal|stNotification/i.test(tid)){
            box.remove(); return;
          }
        }
        n.closest('div') && n.closest('div').remove();
        return;
      }
    }catch(e){}
  }

  try{
    uaQueueMark();
    uaDropFalse404();
    uaFocusableScrollers();
    uaLabelUploads();
    new MutationObserver(function(){
      uaQueueMark(); uaDropFalse404(); uaFocusableScrollers(); uaLabelUploads();
    }).observe(document.documentElement, {childList:true, subtree:true});
  }catch(e){}

  /* Handle for the real toggle button once every page is migrated. */
  /* ── noindex for the routes the redesign superseded ────────────────────
     Those pages still describe the retired signal product. They stay routable
     so old links resolve, but they should stop collecting search traffic.
     The visible notice lives in utils/legacy_pages.py; this half has to be
     here because Streamlit sanitises <script> out of st.html, so a meta tag
     added from Python never runs. The slug list is generated from app.py's
     own registry at injection time, so it cannot drift from the router. */
  try{
    var uaLegacy = __UA_LEGACY_SLUGS__;
    var uaPath = (location.pathname||'/').replace(/^\/+|\/+$/g,'');
    if(uaLegacy.indexOf(uaPath) !== -1 &&
       !document.querySelector('meta[name="robots"][data-ua-legacy]')){
      var uaM=document.createElement('meta');
      uaM.setAttribute('name','robots');
      uaM.setAttribute('content','noindex,follow');
      uaM.setAttribute('data-ua-legacy','1');
      document.head.appendChild(uaM);
    }
  }catch(e){}

  /* ── Accessibility wiring (2026-09-29 keyboard / screen-reader audit) ──
     Streamlit renders no <main>, puts an invisible cookie-manager iframe in
     the tab order, and its markup cannot carry aria state that changes. This
     keeps all of that right as Streamlit re-renders, idempotently:
       - [data-testid=stMain] becomes the main landmark, target of the skip link
       - the cookie iframe leaves the tab order and the accessibility tree
       - the nav's Research / Account disclosures report aria-expanded, and
         Escape closes one while focus is inside it
       - the mobile menu button opens the CSS checkbox menu and reports it */
  function uaA11y(){
    try{
      var m = document.querySelector('[data-testid="stMain"]');
      if(m && m.id !== 'ua-main'){ m.id = 'ua-main'; m.setAttribute('role','main'); }
      var f = document.querySelectorAll('iframe[title*="cookie_manager"]:not([tabindex="-1"])');
      for(var i=0;i<f.length;i++){ f[i].setAttribute('tabindex','-1'); f[i].setAttribute('aria-hidden','true'); }
      var burger = document.querySelector('.ua-tnav-burger:not([data-ua-a11y])');
      if(burger){
        burger.setAttribute('data-ua-a11y','1');
        var box = document.getElementById('ua-tnav-toggle');
        burger.setAttribute('aria-expanded', box && box.checked ? 'true' : 'false');
        burger.addEventListener('click', function(ev){
          ev.preventDefault();
          var b = document.getElementById('ua-tnav-toggle');
          if(b){ b.checked = !b.checked; burger.setAttribute('aria-expanded', b.checked ? 'true' : 'false'); }
        });
      }
    }catch(e){}
  }
  try{
    uaA11y();
    var uaA11yQueued = false;
    new MutationObserver(function(){
      if(uaA11yQueued) return; uaA11yQueued = true;
      requestAnimationFrame(function(){ uaA11yQueued = false; uaA11y(); });
    }).observe(document.documentElement, {childList:true, subtree:true});

    function uaGroupState(group, open){
      var t = group && group.querySelector('.ua-tnav-trigger');
      if(t) t.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    document.addEventListener('focusin', function(ev){
      var g = ev.target && ev.target.closest && ev.target.closest('.ua-tnav-group');
      var all = document.querySelectorAll('.ua-tnav-group');
      for(var i=0;i<all.length;i++){ if(all[i] !== g){ all[i].classList.remove('ua-closed'); uaGroupState(all[i], false); } }
      if(g && !g.classList.contains('ua-closed')) uaGroupState(g, true);
    });
    document.addEventListener('keydown', function(ev){
      if(ev.key !== 'Escape') return;
      var g = document.activeElement && document.activeElement.closest && document.activeElement.closest('.ua-tnav-group');
      if(!g) return;
      g.classList.add('ua-closed'); uaGroupState(g, false);
      var t = g.querySelector('.ua-tnav-trigger'); if(t) t.focus();
    });
    document.addEventListener('click', function(ev){
      var t = ev.target && ev.target.closest && ev.target.closest('.ua-tnav-trigger');
      if(t){
        var g = t.closest('.ua-tnav-group');
        var open = t.getAttribute('aria-expanded') === 'true' && !g.classList.contains('ua-closed');
        g.classList.toggle('ua-closed', open); uaGroupState(g, !open);
        return;
      }
      var skip = ev.target && ev.target.closest && ev.target.closest('a.ua-skip');
      if(skip){
        ev.preventDefault();
        var m = document.getElementById('ua-main');
        if(m){ if(!m.hasAttribute('tabindex')) m.setAttribute('tabindex','-1'); m.focus(); m.scrollTop = 0; }
      }
    }, true);
  }catch(e){}

  window.uaSetTheme=function(t){
    try{ localStorage.setItem('ua-theme',t); }catch(e){}
    if(t==='light'){ document.documentElement.setAttribute('data-ua-theme','light'); }
    else { document.documentElement.removeAttribute('data-ua-theme'); }
  };
})();
</script>
""".rstrip().replace("__UA_LEGACY_SLUGS__", _json.dumps(legacy_slugs()))
            + "\n" + RUNTIME_END + "\n")


def legacy_slugs() -> list[str]:
    """URL slugs of the pages the 2026-09-20 redesign superseded.

    Read from app.py's own registry and utils/legacy_pages.py rather than
    hand-listed here: two hand-written copies of the same decision drift, and
    the failure mode is a retired page quietly collecting search traffic.
    """
    import re as _re
    from pathlib import Path as _Path

    from utils.legacy_pages import LEGACY_PAGE_FILES

    app_py = (_Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    slugs = []
    for match in _re.finditer(
        r'st\.Page\("pages/([^"]+)"[^)]*?url_path="([^"]+)"', app_py
    ):
        if match.group(1) in LEGACY_PAGE_FILES:
            slugs.append(match.group(2))
    return sorted(slugs)


def product_slugs() -> list[str]:
    """URL slugs of the pages that carry the product theme ("" is the default page).

    The splash waits for that theme before lifting -- but only on these routes.
    The retired pages never receive it, and a global wait would hold them
    behind the splash until the 45-second hard timeout.
    """
    import re as _re
    from pathlib import Path as _Path

    from utils.app_theme import is_product_page

    app_py = (_Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    slugs = []
    for match in _re.finditer(r'st\.Page\("pages/([^"]+)"([^)]*)\)', app_py):
        name, args = match.group(1), match.group(2)
        if not is_product_page(name):
            continue
        slug = _re.search(r'url_path="([^"]+)"', args)
        slugs.append(slug.group(1) if slug else "" if "default=True" in args else None)
    return sorted(s for s in slugs if s is not None)


def _build_splash() -> str:
    # Raw string: the JS below contains regex literals such as /^\/+|\/+$/ and
    # Python reads "\/" as an invalid escape sequence. Today that is only a
    # SyntaxWarning, but it is scheduled to become a SyntaxError. There are no
    # intentional Python escapes in this blob, so r"" is a safe, exact no-op.
    #
    # The current brand, not the retired one. Until 2026-09-29 this painted a
    # violet hexagon on lavender with rotating macro trivia ("yield-curve
    # inversions have led downturns by 6 to 18 months") -- the old signal
    # product's look, and forecasting talk the exposure product disclaims, on
    # every single load. Now: the nav's own wordmark on its navy band, the six
    # factor colours as the progress strip, the page's own ground behind it.
    return r"""
<!-- ua-boot-splash:start -->
<div id="ua-boot-splash" role="status" aria-label="Loading Unstructured Alpha">
  <div class="ua-boot-inner">
    <div class="ua-boot-mark">UNSTRUCTURED <span>ALPHA</span></div>
    <div class="ua-boot-bar"><div class="ua-boot-bar-fill"></div></div>
    <div class="ua-boot-sub">Loading…</div>
  </div>
</div>
<style>
#ua-boot-splash{position:fixed;inset:0;z-index:2147483647;background:#0b1422;
  display:flex;align-items:center;justify-content:center;
  transition:opacity .35s ease;
  font-family:Inter,"SF Pro Text","Segoe UI",system-ui,-apple-system,sans-serif;}
#ua-boot-splash.ua-hide{opacity:0;pointer-events:none;}
#ua-boot-splash .ua-boot-inner{text-align:center;}
#ua-boot-splash .ua-boot-mark{display:inline-block;padding:12px 20px;border-radius:12px;
  background:linear-gradient(135deg,#0d223b,#15375d);color:#eef3fa;
  font-size:1.05rem;font-weight:800;letter-spacing:-.01em;
  box-shadow:0 10px 30px rgba(13,34,59,.28);}
#ua-boot-splash .ua-boot-mark span{color:#ffc24b;}
#ua-boot-splash .ua-boot-bar{margin:18px auto 0;width:168px;height:3px;border-radius:3px;
  background:rgba(143,155,177,.25);overflow:hidden;}
#ua-boot-splash .ua-boot-bar-fill{height:100%;width:40%;border-radius:3px;
  background:linear-gradient(90deg,#3b7ddd,#7c5ce0,#e0664a,#d99018,#1a9a70,#1497b0);
  animation:ua-boot-slide 1.1s infinite ease-in-out;}
#ua-boot-splash .ua-boot-sub{margin-top:12px;font-size:.75rem;color:#8f9bb1;}
@keyframes ua-boot-slide{0%{transform:translateX(-120%)}100%{transform:translateX(320%)}}
@media (prefers-reduced-motion: reduce){#ua-boot-splash .ua-boot-bar-fill{animation:none;width:100%;}}
/* Light theme: the splash is the very first thing painted, so it wears the
   same ground the page will (--p-bg), or a light visitor gets a dark flash. */
html[data-ua-theme="light"] #ua-boot-splash{background:#fafaf8;}
html[data-ua-theme="light"] #ua-boot-splash .ua-boot-bar{background:#dfe5ee;}
html[data-ua-theme="light"] #ua-boot-splash .ua-boot-sub{color:#5b6780;}
</style>
<script>
(function(){
  function hide(){
    var s=document.getElementById('ua-boot-splash');
    if(!s)return;
    s.classList.add('ua-hide');
    setTimeout(function(){if(s&&s.parentNode)s.parentNode.removeChild(s);},600);
  }
  var started=Date.now();
  var lastMutation=started;
  var MIN_VISIBLE_MS=900;
  var SETTLE_MS=450;
  /* Past this point the splash stops waiting on the script run and lifts as
     soon as the page STRUCTURE exists, leaving Streamlit's own in-place
     spinners and skeletons to cover whatever is still loading.

     Why: isStreamlitBusy() is true for the whole first script run, and that
     run includes the provider calls -- so the full-screen cover stayed up
     through data fetching, not just through Streamlit's boot. A labelled
     "Building your command center..." spinner inside the real page is better
     progress information than a logo, and the app has 98 st.spinner sites to
     provide it.

     Fast loads are unaffected: under this budget the original
     not-busy-and-settled condition still applies, so a page that is genuinely
     ready still waits to be genuinely ready. */
  var LAYOUT_READY_MS=2200;
  var HARD_TIMEOUT_MS=45000;

  function appRoot(){
    return document.querySelector('[data-testid="stAppViewContainer"]')
      ||document.querySelector('.stApp');
  }
  function hasRenderedContent(){
    var app=appRoot();
    if(!app)return false;
    var main=app.querySelector('[data-testid="stMainBlockContainer"], .block-container, section.main');
    if(!main)return false;
    // Streamlit mounts empty layout containers before the Python script has
    // produced a page. Require an actual rendered element or meaningful text.
    return main.querySelector(
      '[data-testid="stMarkdownContainer"], [data-testid="stMetric"], '
      +'[data-testid="stDataFrame"], [data-testid="stPlotlyChart"], '
      +'[data-testid="stAlert"], [data-testid="stForm"], button, input, canvas, iframe'
    )!==null || (main.textContent||'').trim().length>24;
  }
  /* Product pages get their theme inline from the Python run, after the
     retired skin in <head> has already painted. Lifting on "content exists"
     alone showed that old look for a moment on every load. Other routes never
     get the theme, so they are not held for it. */
  var productPaths=__UA_PRODUCT_SLUGS__;
  function themeApplied(){
    var path=(location.pathname||'/').replace(/^\/+|\/+$/g,'');
    if(productPaths.indexOf(path)===-1) return true;
    var app=appRoot();
    return !!app && getComputedStyle(app).getPropertyValue('--p-ink').trim()!=='';
  }
  function isStreamlitBusy(){
    // The header running icon is Streamlit's authoritative script-run signal.
    // Page-level spinners/skeletons cover long provider calls inside that run.
    return !!document.querySelector(
      '[data-testid="stStatusWidgetRunningIcon"], [data-testid="stSpinner"], '
      +'[data-testid="stSkeleton"], [data-testid="stProgress"]'
    );
  }
  function ready(){
    var now=Date.now();
    if(now-started<MIN_VISIBLE_MS) return false;
    /* Never lift over an empty page: real rendered content is required on
       every path, including the layout-budget one below. */
    if(!hasRenderedContent()) return false;
    /* ...and never lift onto the retired skin. The product theme sets --p-ink
       on .stApp; until it is present the page underneath is the old look. */
    if(!themeApplied()) return false;
    if(now-started>=LAYOUT_READY_MS) return true;
    return !isStreamlitBusy() && now-lastMutation>=SETTLE_MS;
  }

  var observer=new MutationObserver(function(mutations){
    // Ignore the splash's own DOM. Only application DOM changes extend the
    // settling window.
    for(var j=0;j<mutations.length;j++){
      var target=mutations[j].target;
      var targetEl=target.nodeType===1?target:target.parentElement;
      if(!(targetEl && targetEl.closest && targetEl.closest('#ua-boot-splash'))){
        lastMutation=Date.now();
        break;
      }
    }
  });
  observer.observe(document.documentElement,{childList:true,subtree:true,characterData:true});

  var iv=setInterval(function(){
    if(ready()){
      clearInterval(iv);
      observer.disconnect();
      hide();
    }
  },100);
  // Safety only: never use window.load as readiness because it fires before
  // Streamlit's websocket-backed Python run has completed.
  setTimeout(function(){clearInterval(iv);observer.disconnect();hide();},HARD_TIMEOUT_MS);
})();
</script>
<!-- ua-boot-splash:end -->
""".replace("__UA_PRODUCT_SLUGS__", json.dumps(_product_slugs_or_none()))


def _product_slugs_or_none() -> list[str]:
    """product_slugs(), but never at the cost of the build: an empty list only
    means no route waits for the theme, which is how the splash behaved before."""
    try:
        return product_slugs()
    except Exception as exc:
        print(f"[boot-splash] product slugs unavailable: {exc}", flush=True)
        return []


def _inject_runtime(html: str) -> tuple[str, str]:
    """Put the runtime block immediately after <body>, replacing any prior one.

    Must land BEFORE the splash in document order: the theme bootstrap has to
    run before first paint, otherwise every load flashes the wrong palette.
    main() therefore injects the splash first and this second, since both
    insert directly after <body>.

    On a deployment built before the split, the old runtime is still inside the
    splash markers -- and _inject_or_replace has already rewritten those with
    splash-only content by the time this runs, so there is nothing to strip.
    """
    runtime = _build_runtime()

    if RUNTIME_START in html and RUNTIME_END in html:
        pattern = re.escape(RUNTIME_START) + r".*?" + re.escape(RUNTIME_END)
        updated, count = re.subn(
            pattern, lambda _m: runtime.strip(), html, count=1, flags=re.DOTALL
        )
        if count == 1:
            return updated, "runtime-updated"

    updated, count = re.subn(
        r"(<body[^>]*>)", lambda m: m.group(1) + "\n" + runtime, html, count=1
    )
    return (updated, "runtime-injected") if count == 1 else (html, "runtime-SKIPPED")


def _inject_or_replace(html: str, splash: str) -> tuple[str, int, str]:
    """Inject the splash, or replace an older injected version in-place."""
    if START_MARKER in html and END_MARKER in html:
        pattern = re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER)
        updated, count = re.subn(
            pattern, lambda _match: splash.strip(), html, count=1, flags=re.DOTALL
        )
        return updated, count, "updated"

    # Backward-compatible replacement for deployments created before explicit
    # boundary markers were added. The legacy block always begins with this
    # unique div and ends at its own script tag.
    if '<div id="ua-boot-splash"' in html:
        pattern = r'<div id="ua-boot-splash".*?</script>\s*'
        updated, count = re.subn(
            pattern, lambda _match: splash.strip() + "\n", html, count=1, flags=re.DOTALL
        )
        return updated, count, "upgraded"

    updated, count = re.subn(
        r"(<body[^>]*>)",
        lambda match: match.group(1) + splash,
        html,
        count=1,
    )
    return updated, count, "injected"


# ── Server-side social / SEO meta ────────────────────────────────────────────
# WHY: Streamlit sets the page <title> and every OG/Twitter tag via JavaScript
# (see utils.header). Social crawlers — X/Twitter, Reddit, Slack, iMessage — do
# NOT execute JS, so they see Streamlit's raw served head: <title>Streamlit</title>
# and no description. Every link preview is therefore broken (and X had cached an
# ancient "43 signals" guess). Injecting real <title> + <meta> into the served
# index.html at build time is the only thing crawlers can read. JS-capable clients
# (Googlebot) still get the richer JS-set tags; this is the crawler floor.
META_START = "<!-- ua-meta:start -->"
META_END = "<!-- ua-meta:end -->"
META_TITLE = "Unstructured Alpha — portfolio exposure to economic forces"
META_DESC = (
    "See which economic forces a portfolio is exposed to — interest rates, inflation, "
    "the dollar, oil and credit spreads — measured from three years of weekly returns, "
    "with a 90% range and an evidence label on every number. Not a forecast. "
    "Free, no account for your first report."
)
META_URL = "https://unstructuredalpha.com"
# The landing page ships this file (scripts/make_og_image.py). Without an
# image, a shared app link previews as a text-only card.
META_IMAGE = "https://unstructuredalpha.com/og-image.png"


def _build_meta() -> str:
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    t, d, u = esc(META_TITLE), esc(META_DESC), esc(META_URL)
    return (
        f"{META_START}"
        f'<meta name="description" content="{d}">'
        f'<meta property="og:site_name" content="Unstructured Alpha">'
        f'<meta property="og:type" content="website">'
        f'<meta property="og:url" content="{u}">'
        f'<meta property="og:title" content="{t}">'
        f'<meta property="og:description" content="{d}">'
        f'<meta property="og:image" content="{esc(META_IMAGE)}">'
        f'<meta name="twitter:image" content="{esc(META_IMAGE)}">'
        f'<meta name="twitter:card" content="summary">'
        f'<meta name="twitter:title" content="{t}">'
        f'<meta name="twitter:description" content="{d}">'
        f'<link rel="canonical" href="{u}">'
        f'<script type="application/ld+json">{_JSONLD}</script>'
        f"{META_END}"
    )


# JSON-LD structured data — crawlers (incl. Google rich results and LLM crawlers)
# read this regardless of JS. Describes the site + the product as a free web app.
_JSONLD = json.dumps({
    "@context": "https://schema.org",
    "@graph": [
        {
            "@type": "WebSite",
            "name": "Unstructured Alpha",
            "url": "https://unstructuredalpha.com",
            "description": META_DESC,
        },
        {
            "@type": "SoftwareApplication",
            "name": "Unstructured Alpha",
            "applicationCategory": "FinanceApplication",
            "operatingSystem": "Web",
            "url": "https://unstructuredalpha.com",
            "description": META_DESC,
            "offers": [
                {"@type": "Offer", "price": "0", "priceCurrency": "USD",
                 "description": "Free to browse"},
                {"@type": "Offer", "price": "20", "priceCurrency": "USD",
                 "description": "Pro (monthly)"},
            ],
        },
    ],
}, separators=(",", ":"))


def _inject_meta(html: str) -> tuple[str, str]:
    """Set a crawler-visible <title> and inject/replace the OG/meta block. Both
    operations are idempotent, so re-running on an already-patched file is safe."""
    action = []

    # 1) Replace the served <title> (Streamlit ships "<title>Streamlit</title>").
    new_html, n_title = re.subn(
        r"<title>.*?</title>", f"<title>{META_TITLE}</title>", html, count=1, flags=re.DOTALL
    )
    if n_title:
        action.append("title")
        html = new_html

    # 2) Inject or replace our meta block just before </head>.
    meta = _build_meta()
    if META_START in html and META_END in html:
        pattern = re.escape(META_START) + r".*?" + re.escape(META_END)
        html, n_meta = re.subn(pattern, lambda _m: meta, html, count=1, flags=re.DOTALL)
        if n_meta:
            action.append("meta-updated")
    else:
        html, n_meta = re.subn(r"(</head>)", lambda m: meta + m.group(1), html, count=1)
        if n_meta:
            action.append("meta-injected")

    return html, "+".join(action) if action else "meta-skipped"


# ── Crawlable body content ───────────────────────────────────────────────────
# WHY: Streamlit serves a JS single-page app — the raw HTML a crawler fetches has
# NO page content, just "enable JavaScript". So Google (and LLM crawlers) index an
# effectively empty site even though the sitemap lists real routes. This injects a
# <noscript> block with genuine product prose and internal links, so non-JS
# crawlers get substantive, keyword-relevant content and a link graph to the key
# pages. It's inside <noscript>, so real (JS-enabled) users never see it — the
# Streamlit app renders normally for them. This is the crawler floor; full per-URL
# prerendering would need a bot-serving proxy (Cloudflare Worker / Prerender.io),
# which is infra, not code.
SEO_START = "<!-- ua-seo:start -->"
SEO_END = "<!-- ua-seo:end -->"
_SEO_LINKS = [
    ("methodology", "Methodology — how exposure is measured, and what we tested that failed"),
    ("research", "Research record — the forward nowcast and every candidate tested"),
    ("what-changed", "What changed — how a portfolio's exposures have shifted"),
    ("pricing", "Pricing — free exposure report, early-access plans"),
    ("Model_Validation", "Model Validation — out-of-sample results, including what fails"),
    ("About", "About & methodology"),
]


def _build_seo_body() -> str:
    links = "".join(
        f'<li><a href="https://unstructuredalpha.com/{slug}">{text}</a></li>'
        for slug, text in _SEO_LINKS
    )
    return (
        f"{SEO_START}"
        '<noscript><div>'
        "<h1>Unstructured Alpha — portfolio exposure to economic forces</h1>"
        "<p>Unstructured Alpha measures which economic forces a portfolio is exposed to: "
        "interest rates, inflation expectations, the U.S. dollar, oil, credit spreads and "
        "economic growth. Enter holdings and it compares three years of weekly returns "
        "with weekly changes in each force, after accounting for the overall stock "
        "market, and reports the size of each exposure, a 90% range, the weeks of data "
        "behind it, and which holdings cause it. Data that is missing is named, never "
        "filled in. It describes the past rather than predicting returns, and the "
        "research record publishes the predictive tests that failed. Free, with no "
        "account needed for a first report.</p>"
        f"<ul>{links}</ul>"
        "</div></noscript>"
        f"{SEO_END}"
    )


def _inject_seo_body(html: str) -> str:
    seo = _build_seo_body()
    if SEO_START in html and SEO_END in html:
        pattern = re.escape(SEO_START) + r".*?" + re.escape(SEO_END)
        html, n = re.subn(pattern, lambda _m: seo, html, count=1, flags=re.DOTALL)
        return html if n else html
    html, n = re.subn(r"(</body>)", lambda m: seo + m.group(1), html, count=1)
    return html


# ── Global stylesheet, served as a cacheable file ────────────────────────────
# WHY THIS EXISTS. Every top-nav click is a FULL browser navigation (the nav is
# built from real <a href> anchors), not a Streamlit in-app transition —
# confirmed live: performance navigation type is "navigate" on every page. That
# means ~161 KB of inline <style> is re-sent and re-parsed on every single page
# change, and inline CSS can never be browser-cached. Moving it to one external
# file makes the browser fetch it once and reuse it for the rest of the session.
#
# THE PATH MATTERS AND IS THE REASON THE PREVIOUS ATTEMPT WAS REVERTED. Verified
# against production: only `/app/static/<file>` serves the real file
# (content-type text/plain for robots.txt). Both `/_stapp/static/<file>` — which
# the comment in .streamlit/config.toml claims — and `/static/<file>` return
# Streamlit's HTML shell with content-type text/html. A <link> pointing at those
# loads HTML as a stylesheet, the browser refuses it, and the whole app renders
# unstyled. Do not "simplify" this path without re-testing it against the
# deployed app.
GLOBAL_CSS_FILENAME = "ua-global.css"
GLOBAL_CSS_HREF = f"/app/static/{GLOBAL_CSS_FILENAME}"
_CSS_LINK_MARKER = "<!-- ua-global-css -->"
# The one Inter request both surfaces make; the landing page uses the same URL.
INTER_HREF = ("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800"
              "&display=swap")


def build_global_css() -> str:
    """Concatenate the always-injected stylesheets, in their runtime order.

    Covers both global entry points: render_header (_CSS, _MODERN_UI_CSS,
    CHART_CSS) and theme.inject_all_css (_SKELETON_CSS, _COUNTER_CSS,
    _MODERN_UI_CSS). _MODERN_UI_CSS is shared by both, which is why it was being
    delivered twice -- once in this file and again inline on the 8 pages that
    call inject_all_css. Order matches the runtime order so cascade wins are
    unchanged; the de-duplication below keeps the shared block appearing once.
    """
    from utils.header import _CSS
    from utils.theme import _MODERN_UI_CSS, _SKELETON_CSS, _COUNTER_CSS
    try:
        from utils.ua_charts import CHART_CSS
    except Exception:
        CHART_CSS = ""

    def _strip(block: str) -> str:
        return block.replace("<style>", "").replace("</style>", "")

    seen: set[str] = set()
    out: list[str] = []
    for block in (_CSS, _SKELETON_CSS, _COUNTER_CSS, _MODERN_UI_CSS, CHART_CSS):
        if not block:
            continue
        cleaned = _strip(block)
        key = cleaned.strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return "\n".join(out)


def write_global_css(static_dir: str) -> str | None:
    """Write the combined stylesheet into Streamlit's served static dir.

    Returns a short content digest (not the path) so the <link> can be
    cache-busted. See _inject_global_css_link for why that matters.
    """
    try:
        os.makedirs(static_dir, exist_ok=True)
        css = build_global_css()
        if not css.strip():
            return None
        path = os.path.join(static_dir, GLOBAL_CSS_FILENAME)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(css)
        return hashlib.sha256(css.encode("utf-8")).hexdigest()[:12]
    except Exception as exc:
        print(f"[boot-splash] global css not written: {exc}", flush=True)
        return None


def _inject_global_css_link(html: str, digest: str = "") -> tuple[str, str]:
    """Add one <link> to the served index.html <head>, idempotently.

    CACHE BUSTING (added 2026-08-03). This file is served by Streamlit's static
    handler, which sets NO cache-control header, and the filename is fixed. With
    no explicit header a browser applies heuristic caching, so a returning
    visitor can render a PREVIOUS deploy's stylesheet. That is not theoretical:
    verifying the Inter typography change (#112), the origin was serving the new
    CSS while a browser that had visited before still painted the old Fraunces
    hero — it looked exactly like a failed deploy.

    The filename and path are deliberately left byte-identical; only a query
    string is appended. The comment above GLOBAL_CSS_HREF explains that only
    `/app/static/<file>` serves the real file and warns against "simplifying"
    that path — this keeps that resolution untouched while still changing the
    URL whenever, and only whenever, the CSS actually changes.
    """
    # REPLACE, not add-once. Render keeps its .venv between builds, so this
    # index.html usually still holds the previous build's block; add-once left
    # it frozen -- the ?v= digest above never changed, and the Inter link added
    # on 2026-09-29 would never have reached a single visitor.
    original = html
    html = re.sub(re.escape(_CSS_LINK_MARKER) + r"\n(?:<link [^>]*>\n)*", "", html)
    href = f"{GLOBAL_CSS_HREF}?v={digest}" if digest else GLOBAL_CSS_HREF
    # Inter is requested from <head> in parallel with the stylesheet. It used
    # to arrive only through an @import inside ua-global.css -- stylesheet,
    # then import, then font, in series -- so text painted in a fallback face
    # first and then swapped: the other half of "the old font on load".
    tag = (
        f'{_CSS_LINK_MARKER}\n'
        f'<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        f'<link rel="stylesheet" href="{INTER_HREF}">\n'
        f'<link rel="stylesheet" href="{href}">\n'
    )
    if "</head>" not in html:
        return original, "css-link skipped (no </head>)"
    out = html.replace("</head>", tag + "</head>", 1)
    if out == original:
        return out, "css-link already present"
    return out, "css-link updated" if _CSS_LINK_MARKER in original else "css-link injected"


def main() -> None:
    try:
        import streamlit
        index_path = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
        if not os.path.isfile(index_path):
            print(f"[boot-splash] index.html not found at {index_path} — skipping", flush=True)
            return
        with open(index_path, "r", encoding="utf-8") as fh:
            html = fh.read()

        splash = _build_splash()
        new_html, n, action = _inject_or_replace(html, splash)
        if n != 1:
            print("[boot-splash] injection target not found — skipping (left untouched)", flush=True)
            return

        # After the splash, so the runtime lands ahead of it (both insert
        # directly after <body>) and the theme still runs before first paint.
        new_html, runtime_action = _inject_runtime(new_html)

        new_html, meta_action = _inject_meta(new_html)
        new_html = _inject_seo_body(new_html)
        # Write the stylesheet into the app's own ./static dir (what Streamlit
        # serves at /app/static/). Only link it if the write actually succeeded,
        # so a failed build step can never leave the app pointing at a 404.
        _repo_static = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
        _css_digest = write_global_css(_repo_static)
        if _css_digest:
            new_html, css_action = _inject_global_css_link(new_html, _css_digest)
        else:
            css_action = "css-link skipped (stylesheet not written)"

        with open(index_path, "w", encoding="utf-8") as fh:
            fh.write(new_html)
        print(
            f"[boot-splash] {action} splash + {runtime_action} + {meta_action} "
            f"+ seo-body + {css_action} in {index_path}",
            flush=True,
        )
    except Exception as exc:  # never fail the build
        print(f"[boot-splash] skipped due to error: {exc}", flush=True)


if __name__ == "__main__":
    main()
    sys.exit(0)
