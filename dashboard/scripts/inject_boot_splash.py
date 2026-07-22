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
- Idempotent (skips if the marker is already present).
- Fully wrapped in try/except and ALWAYS exits 0 — a failure here must never fail
  the build or leave a half-written file (writes only after a successful transform).
- Trivially reversible: remove this step from render.yaml's buildCommand; the next
  deploy reinstalls a pristine Streamlit index.html.

Run from buildCommand AFTER `pip install`:  python scripts/inject_boot_splash.py
"""
import json
import os
import re
import sys

MARKER = "ua-boot-splash"


def _load_facts() -> list:
    """True macro facts from the shared module, so the splash and the in-app
    loading panel never drift. Falls back to a tiny inline set if the import
    fails — this script must never break the build."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from utils.macro_facts import FACTS
        return list(FACTS)
    except Exception:
        return [
            "An inverted yield curve has preceded every U.S. recession of the "
            "past half-century.",
            "A manufacturing PMI above 50 signals expansion; below 50, contraction.",
            "The VIX infers expected 30-day S&P 500 volatility from options prices.",
        ]


def _build_splash() -> str:
    facts_json = json.dumps(_load_facts())
    return """
<div id="ua-boot-splash" role="status" aria-label="Loading">
  <div class="ua-boot-inner">
    <svg class="ua-boot-hex" viewBox="0 0 100 100" width="132" height="132" aria-hidden="true">
      <defs>
        <linearGradient id="uaBootGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#00D566"/>
          <stop offset="55%" stop-color="#12B5A6"/>
          <stop offset="100%" stop-color="#7C3AED"/>
        </linearGradient>
      </defs>
      <polygon points="50,4 91,27 91,73 50,96 9,73 9,27" fill="url(#uaBootGrad)" opacity="0.92"/>
      <polygon points="50,4 91,27 91,73 50,96 9,73 9,27" fill="none" stroke="#0B0D12" stroke-width="2"/>
      <text x="50" y="60" text-anchor="middle" font-family="Inter,sans-serif"
            font-size="30" font-weight="900" fill="#0B0D12">UA</text>
    </svg>
    <div class="ua-boot-logo">UNSTRUCTURED <span>ALPHA</span></div>
    <div class="ua-boot-sub">Loading macro signal intelligence…</div>
    <div class="ua-boot-bar"><div class="ua-boot-bar-fill"></div></div>
    <div class="ua-boot-fact" id="ua-boot-fact"></div>
  </div>
</div>
<style>
#ua-boot-splash{position:fixed;inset:0;z-index:2147483647;background:#0B0D12;
  display:flex;align-items:center;justify-content:center;
  transition:opacity .5s ease;
  font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif;}
#ua-boot-splash.ua-hide{opacity:0;pointer-events:none;}
#ua-boot-splash .ua-boot-hex{filter:drop-shadow(0 0 30px rgba(0,213,102,0.30));
  animation:ua-boot-pulse 2.4s ease-in-out infinite;}
#ua-boot-splash .ua-boot-fact{margin:16px auto 0;max-width:440px;font-size:.78rem;
  line-height:1.5;color:#9AA6C4;border-top:1px solid rgba(255,255,255,.07);padding-top:12px;
  opacity:0;transition:opacity .5s ease;}
#ua-boot-splash .ua-boot-fact.show{opacity:1;}
#ua-boot-splash .ua-boot-fact::before{content:"DID YOU KNOW";display:block;font-size:.56rem;
  font-weight:700;letter-spacing:.14em;color:#4F5B7A;margin-bottom:5px;}
@keyframes ua-boot-pulse{0%,100%{transform:scale(1);opacity:.92;}50%{transform:scale(1.06);opacity:1;}}
@media (prefers-reduced-motion: reduce){#ua-boot-splash .ua-boot-hex{animation:none;}}
#ua-boot-splash .ua-boot-inner{text-align:center;}
#ua-boot-splash .ua-boot-logo{font-size:1.35rem;font-weight:800;letter-spacing:.04em;color:#E8EEFF;}
#ua-boot-splash .ua-boot-logo span{color:#00D566;}
#ua-boot-splash .ua-boot-sub{margin-top:8px;font-size:.72rem;color:#6B7FBF;letter-spacing:.02em;}
#ua-boot-splash .ua-boot-bar{margin:18px auto 0;width:180px;height:3px;border-radius:3px;
  background:rgba(255,255,255,.08);overflow:hidden;}
#ua-boot-splash .ua-boot-bar-fill{height:100%;width:40%;border-radius:3px;
  background:linear-gradient(90deg,#00D566,#7C3AED);
  animation:ua-boot-slide 1.1s infinite ease-in-out;}
@keyframes ua-boot-slide{0%{transform:translateX(-120%)}100%{transform:translateX(320%)}}
</style>
<script>
(function(){
  // Rotate genuinely-true macro facts while the app boots.
  var facts=__UA_FACTS_JSON__;
  var el=document.getElementById('ua-boot-fact');
  if(el&&facts&&facts.length){
    var i=Math.floor(Math.random()*facts.length);
    function showFact(){el.textContent=facts[i];el.classList.add('show');}
    function nextFact(){
      el.classList.remove('show');
      setTimeout(function(){i=(i+1)%facts.length;showFact();},500);
    }
    showFact();
    setInterval(nextFact,4200);
  }
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
    return now-started>=MIN_VISIBLE_MS
      && hasRenderedContent()
      && !isStreamlitBusy()
      && now-lastMutation>=SETTLE_MS;
  }

  var observer=new MutationObserver(function(mutations){
    // Ignore the splash's own rotating fact animation. Only application DOM
    // changes extend the settling window.
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
""".replace("__UA_FACTS_JSON__", facts_json)


def main() -> None:
    try:
        import streamlit
        index_path = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
        if not os.path.isfile(index_path):
            print(f"[boot-splash] index.html not found at {index_path} — skipping", flush=True)
            return
        with open(index_path, "r", encoding="utf-8") as fh:
            html = fh.read()
        if MARKER in html:
            print("[boot-splash] already injected — skipping", flush=True)
            return
        splash = _build_splash()
        new_html, n = re.subn(r"(<body[^>]*>)", lambda m: m.group(1) + splash, html, count=1)
        if n != 1:
            print("[boot-splash] <body> tag not found — skipping (left untouched)", flush=True)
            return
        with open(index_path, "w", encoding="utf-8") as fh:
            fh.write(new_html)
        print(f"[boot-splash] injected branded splash into {index_path}", flush=True)
    except Exception as exc:  # never fail the build
        print(f"[boot-splash] skipped due to error: {exc}", flush=True)


if __name__ == "__main__":
    main()
    sys.exit(0)
