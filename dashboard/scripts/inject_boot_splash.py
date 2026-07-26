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
import os
import re
import sys

MARKER = "ua-boot-splash"
START_MARKER = "<!-- ua-boot-splash:start -->"
END_MARKER = "<!-- ua-boot-splash:end -->"


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
<!-- ua-boot-splash:start -->
<script>
/* Theme init — runs before first paint so there is no dark-to-light flash.
   This has to live here rather than in utils/header.py: st.markdown does NOT
   execute script tags, and a Streamlit component would run inside a sandboxed
   iframe where it cannot style the parent document. This file is injected into
   the served index.html, so its script really runs and owns the html element.

   Light mode is OPT-IN while the hex->token migration finishes: pages that
   still hardcode dark colors would look broken under a flip, so normal users
   must never land in it by accident. Enter with ?theme=light, leave with
   ?theme=dark. The choice persists so in-app navigation keeps it. */
(function(){
  try{
    var q=null;
    try{ q=new URLSearchParams(window.location.search).get('theme'); }catch(e){}
    if(q==='light'||q==='dark'){ try{ localStorage.setItem('ua-theme',q); }catch(e){} }
    var t=q;
    if(!t){ try{ t=localStorage.getItem('ua-theme'); }catch(e){} }
    if(t==='light'){ document.documentElement.setAttribute('data-ua-theme','light'); }
    else { document.documentElement.removeAttribute('data-ua-theme'); }
  }catch(e){}
  /* Handle for the real toggle button once every page is migrated. */
  window.uaSetTheme=function(t){
    try{ localStorage.setItem('ua-theme',t); }catch(e){}
    if(t==='light'){ document.documentElement.setAttribute('data-ua-theme','light'); }
    else { document.documentElement.removeAttribute('data-ua-theme'); }
  };
})();
</script>
<div id="ua-boot-splash" role="status" aria-label="Loading">
  <div class="ua-boot-frame">
    <!-- Hexagon frame echoing the logo mark, so the content sits inside the
         brand shape instead of floating in empty space. Same flat-top geometry
         as the UA mark; preserveAspectRatio="none" lets it stretch to the
         content box while the stroke stays even via vector-effect. -->
    <svg class="ua-boot-hexframe" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <polygon points="50,1 99,25.5 99,74.5 50,99 1,74.5 1,25.5"
               fill="none" stroke-width="1.1" vector-effect="non-scaling-stroke"/>
    </svg>
  <div class="ua-boot-inner">
    <svg class="ua-boot-hex" viewBox="0 0 100 100" width="132" height="132" aria-hidden="true">
      <defs>
        <linearGradient id="uaBootGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#6470F5"/>
          <stop offset="55%" stop-color="#8B7BF7"/>
          <stop offset="100%" stop-color="#D4B26A"/>
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
</div>
<style>
#ua-boot-splash{position:fixed;inset:0;z-index:2147483647;background:#0B0D12;
  display:flex;align-items:center;justify-content:center;
  transition:opacity .5s ease;
  font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif;}
#ua-boot-splash.ua-hide{opacity:0;pointer-events:none;}
#ua-boot-splash .ua-boot-hex{filter:drop-shadow(0 0 30px rgba(100,112,245,0.34));
  animation:ua-boot-pulse 2.4s ease-in-out infinite;}
#ua-boot-splash .ua-boot-fact{margin:16px auto 0;max-width:440px;font-size:.78rem;
  line-height:1.5;color:#9AA6C4;border-top:1px solid rgba(255,255,255,.07);padding-top:12px;
  opacity:0;transition:opacity .5s ease;}
#ua-boot-splash .ua-boot-fact.show{opacity:1;}
#ua-boot-splash .ua-boot-fact::before{content:"DID YOU KNOW";display:block;font-size:.56rem;
  font-weight:700;letter-spacing:.14em;color:#4F5B7A;margin-bottom:5px;}
@keyframes ua-boot-pulse{0%,100%{transform:scale(1);opacity:.92;}50%{transform:scale(1.06);opacity:1;}}
@media (prefers-reduced-motion: reduce){#ua-boot-splash .ua-boot-hex{animation:none;}}
/* Hexagon frame around the whole splash block. The padding is asymmetric on
   purpose: a hexagon pinches at top and bottom, so square padding would let the
   wordmark and the fact text collide with the sloped edges. */
#ua-boot-splash .ua-boot-frame{
  position:relative;
  padding:74px 96px;
  max-width:min(92vw,700px);
}
#ua-boot-splash .ua-boot-hexframe{
  position:absolute;inset:0;width:100%;height:100%;
  pointer-events:none;overflow:visible;
}
#ua-boot-splash .ua-boot-hexframe polygon{
  stroke:rgba(139,123,247,0.55);   /* dark mode: purple */
}
html[data-ua-theme="light"] #ua-boot-splash .ua-boot-hexframe polygon{
  stroke:rgba(16,18,32,0.72);      /* light mode: near-black, inverted */
}
@media (max-width:640px){
  #ua-boot-splash .ua-boot-frame{padding:56px 34px;}
}
#ua-boot-splash .ua-boot-inner{text-align:center;position:relative;z-index:1;}
#ua-boot-splash .ua-boot-logo{font-size:1.35rem;font-weight:800;letter-spacing:.04em;color:#E8EEFF;}
#ua-boot-splash .ua-boot-logo span{background:linear-gradient(135deg,#6470F5,#8B7BF7 60%,#D4B26A 120%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
#ua-boot-splash .ua-boot-sub{margin-top:8px;font-size:.72rem;color:#6B7FBF;letter-spacing:.02em;}
#ua-boot-splash .ua-boot-bar{margin:18px auto 0;width:180px;height:3px;border-radius:3px;
  background:rgba(255,255,255,.08);overflow:hidden;}
#ua-boot-splash .ua-boot-bar-fill{height:100%;width:40%;border-radius:3px;
  background:linear-gradient(90deg,#6470F5,#8B7BF7 55%,#D4B26A);
  animation:ua-boot-slide 1.1s infinite ease-in-out;}
@keyframes ua-boot-slide{0%{transform:translateX(-120%)}100%{transform:translateX(320%)}}
/* Light theme: the splash is the very first thing painted, so if it stayed dark
   a light-mode user would get a full-screen dark flash before the app appears. */
html[data-ua-theme="light"] #ua-boot-splash{background:#F6F5FB;}
html[data-ua-theme="light"] #ua-boot-splash .ua-boot-logo{color:#161A2E;}
html[data-ua-theme="light"] #ua-boot-splash .ua-boot-sub{color:#5E5A8C;}
html[data-ua-theme="light"] #ua-boot-splash .ua-boot-fact{color:#3A4059;border-top-color:rgba(20,22,44,0.10);}
html[data-ua-theme="light"] #ua-boot-splash .ua-boot-fact::before{color:#8A90A6;}
html[data-ua-theme="light"] #ua-boot-splash .ua-boot-bar{background:rgba(20,22,44,0.10);}
html[data-ua-theme="light"] #ua-boot-splash .ua-boot-hex polygon[stroke]{stroke:#F6F5FB;}
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
<!-- ua-boot-splash:end -->
""".replace("__UA_FACTS_JSON__", facts_json)


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
META_TITLE = "Unstructured Alpha — 47-signal macro intelligence"
META_DESC = (
    "47 macro and alt-data signals scored daily on first-print data — no hindsight, "
    "no synthetic values. Public out-of-sample validation and a live revision audit. "
    "Free to browse."
)
META_URL = "https://unstructuredalpha.com"


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
    ("Signal_Dashboard", "Signal Dashboard — all 47 signals scored live"),
    ("Model_Validation", "Model Validation — out-of-sample results, including the signals that fail"),
    ("Ticker_Deep_Dive", "Ticker Deep Dive — score any stock against the macro backdrop"),
    ("Stock_Screener", "Stock Screener — rank stocks by macro tailwind"),
    ("Today_Digest", "Today's Brief — the day's macro read in plain English"),
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
        "<h1>Unstructured Alpha — 47-signal macro intelligence</h1>"
        "<p>Unstructured Alpha scores 47 macro and alternative-data signals daily — "
        "Fed liquidity, credit spreads, the yield-curve slope, energy inventories, "
        "insider buying, short interest, put/call sentiment, the copper/gold ratio and "
        "more — into a single 0–100 Confluence Score for each stock. Backtests run on "
        "first-print (point-in-time) data, so a signal only earns credit for what was "
        "knowable at the time: no revised hindsight and no synthetic values. "
        "Out-of-sample validation and a per-signal revision audit are published in the "
        "open. Free to browse.</p>"
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

        new_html, meta_action = _inject_meta(new_html)
        new_html = _inject_seo_body(new_html)

        with open(index_path, "w", encoding="utf-8") as fh:
            fh.write(new_html)
        print(f"[boot-splash] {action} splash + {meta_action} + seo-body in {index_path}", flush=True)
    except Exception as exc:  # never fail the build
        print(f"[boot-splash] skipped due to error: {exc}", flush=True)


if __name__ == "__main__":
    main()
    sys.exit(0)
