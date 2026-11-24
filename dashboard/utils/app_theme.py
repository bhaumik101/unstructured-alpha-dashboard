# utils/app_theme.py
# Unstructured Alpha — the landing page's look, carried into the app
#
# WHY THIS EXISTS
# ---------------
# The marketing site and the product were two different-looking things: the
# site is navy, blue and gold with cards, colour-coded factors and generous
# type; the app was the older dark purple Streamlit skin with a white bar on
# top. Clicking "Try a sample portfolio" took a visitor from a designed page to
# something rougher — the impression a prospective adviser is least forgiving
# of, and the reason the product read as assembled rather than designed.
#
# This is one stylesheet that restates the landing page's tokens (see
# unstructured-alpha-web/app/landing.css, which these values are copied from)
# and applies them to Streamlit's own furniture, plus the navy page header the
# landing hero uses.
#
# SCOPE. It is injected by render_header() for PRODUCT pages only — the ones
# built after the 2026-09-20 redesign. The ~25 superseded pages keep the old
# skin and their "this page predates the exposure report" notice; restyling
# something we are retiring is wasted work.
#
# TWO THINGS THAT SILENTLY BREAK, both learned the hard way in a browser:
#
#   1. SPECIFICITY. utils/header.py's rules are written as
#      html[data-ua-theme="light"] button[...]. A plain class selector loses to
#      them and silently does nothing. Every override here carries the same
#      html[data-ua-theme] prefix, with a :not() twin so it applies in dark too.
#
#   2. SOURCE ORDER. header.py injects ~124 KB of the old skin from the SAME
#      function. Equal-specificity ties are broken by document order, so this
#      sheet is injected LAST (see the tail of render_header). Injecting it
#      earlier looked right in production — where the old skin is a cached
#      <link> in index.html — and wrong on a laptop, which is the worst
#      possible way for a style bug to behave.
#
# FONT SIZES are declared once as --p-t-* variables and referenced with var().
# tests/test_design_tokens.py ratchets raw font-size literals downward; a new
# stylesheet full of fresh .82rem/.94rem values is exactly the accumulation it
# exists to stop, and the tokens cost nothing.

from __future__ import annotations

from pathlib import Path

# The brand system (2026-11 redesign), shared with landing.css: near-black
# canvas and nav, one teal action colour (darker on light so white text clears
# 4.5:1), gold only for the wordmark and small brand details.
_LIGHT = {
    "bg": "#f5f7fa", "surface": "#ffffff", "subtle": "#eef2f7",
    "ink": "#152033", "ink2": "#3d4a5f", "ink3": "#526176", "line": "#dce3ec",
    "accent": "#0b6f64", "accent-hover": "#095c53", "accent-ink": "#ffffff",
    "bright": "#d8b66a", "bright-ink": "#152033",
    "navy": "#0b111a", "navy2": "#101824", "sky": "#e7f5f2", "sand": "#f7f3ea",
}
_DARK = {
    "bg": "#080d14", "surface": "#101824", "subtle": "#162131",
    "ink": "#f3f6fa", "ink2": "#c3cddb", "ink3": "#a8b5c7", "line": "#263448",
    "accent": "#6ce5d2", "accent-hover": "#8debdd", "accent-ink": "#04201c",
    "bright": "#d8b66a", "bright-ink": "#152033",
    "navy": "#0b111a", "navy2": "#101824", "sky": "#11262a", "sand": "#151a22",
}

# One identity colour per economic force, used on the landing page's icons and
# hero map. Carried here so "oil" is the same amber everywhere a reader meets it.
FACTOR_HUES = {
    "rates": "#3b7ddd", "inflation": "#e0664a", "dollar": "#1a9a70",
    "oil": "#d99018", "credit": "#7c5ce0", "growth": "#1497b0",
}

# The product's type scale. Referenced with var(), never re-typed as a literal.
_TYPE = {
    "t-xs": ".75rem", "t-sm": ".82rem", "t-base": ".94rem",
    "t-md": "1.06rem", "t-lg": "1.3rem", "t-xl": "2.1rem",
}
_RADII = {"r-sm": "8px", "r-btn": "10px", "r": "12px", "r-lg": "18px", "r-pill": "999px"}



def _vars(*groups: dict) -> str:
    return "".join(f"--p-{k}:{v};" for g in groups for k, v in g.items())


_SHARED = _vars(_TYPE, _RADII) + "".join(f"--f-{k}:{v};" for k, v in FACTOR_HUES.items())

def _twin(css: str) -> str:
    """Expand each "@@ sel" into the html[data-ua-theme] pair (see SPECIFICITY above)."""
    import re

    def sel(m):
        parts = [p.strip() for p in m.group(1).split(",")]
        out = []
        for p in parts:
            if p.startswith("@@ "):
                rest = p[3:]
                out += [f'html[data-ua-theme="light"] {rest}', f'html:not([data-ua-theme="light"]) {rest}']
            else:
                out.append(p)
        return ",\n".join(out) + "{"

    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)   # comments stay in this file, not the page
    return re.sub(r"([^{}]*@@[^{}]*)\{", sel, css)


GLASS_CSS = _twin(r"""/* ── the glass command bar (2026-11) ─────────────────────────────────────
   One object instead of a flat strip with two stray buttons floating above
   it: a frosted navy bar with a hairline edge, a faint blueprint grid at
   both ends, a teal-to-gold light rail along the bottom that a glint runs
   across once, and every control in it a glass chip of the same height.
   The bar is navy in both themes (the landing's band), so the chips docked
   in it are always the dark glass; chips left in the band above it follow
   the theme. Selectors are written once and doubled by _twin(). */
@@ .ua-topnav{
  background-color:var(--p-navy)!important;
  background-image:
    linear-gradient(180deg,rgba(255,255,255,.055),rgba(255,255,255,0) 55%),
    radial-gradient(520px 150px at 6% -70%,rgba(108,229,210,.20),transparent 70%),
    radial-gradient(440px 150px at 98% 170%,rgba(216,182,106,.13),transparent 70%)!important;
  border:1px solid rgba(148,180,210,.17)!important;border-radius:16px!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.08),0 26px 50px -30px rgba(0,0,0,.9),0 0 0 1px rgba(8,13,20,.55)!important;
  backdrop-filter:blur(16px) saturate(150%)!important;-webkit-backdrop-filter:blur(16px) saturate(150%)!important;
  isolation:isolate;
}
@@ .ua-topnav::before{
  content:"";position:absolute;inset:0;border-radius:inherit;z-index:-1;pointer-events:none;
  background-image:linear-gradient(rgba(108,229,210,.075) 1px,transparent 1px),
    linear-gradient(90deg,rgba(108,229,210,.075) 1px,transparent 1px);
  background-size:16px 16px;background-position:-1px -1px;
  -webkit-mask-image:linear-gradient(90deg,#000,transparent 20%,transparent 72%,#000);
  mask-image:linear-gradient(90deg,#000,transparent 20%,transparent 72%,#000);
}
@@ .ua-topnav::after{
  content:"";position:absolute;left:20px;right:20px;bottom:-1px;height:1px;pointer-events:none;
  background:linear-gradient(90deg,transparent,#fff,transparent) -140px 0/140px 1px no-repeat,
    linear-gradient(90deg,transparent,rgba(108,229,210,.85) 22%,rgba(216,182,106,.75) 78%,transparent);
  filter:drop-shadow(0 0 5px rgba(108,229,210,.55));
  animation:ua-rail-glint 2.8s cubic-bezier(.3,.6,.2,1) .5s 1 both;
}
@keyframes ua-rail-glint{from{background-position:-140px 0,0 0}to{background-position:calc(100% + 140px) 0,0 0}}

/* chips in the bar: theme toggle, Upgrade, ADMIN */
@@ .ua-topnav .ua-theme-toggle{
  height:32px!important;border-radius:10px!important;color:rgba(238,243,250,.82)!important;
  background:linear-gradient(180deg,rgba(255,255,255,.09),rgba(255,255,255,.02))!important;
  border:1px solid rgba(255,255,255,.13)!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.12)!important;
  transition:border-color .2s ease,box-shadow .2s ease,color .2s ease!important;
}
@@ .ua-topnav .ua-theme-toggle:hover{color:#fff!important;border-color:rgba(108,229,210,.6)!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.14),0 0 18px -6px rgba(108,229,210,.6)!important;}
@@ .ua-topnav .ua-tnav-upgrade,
@@ .ua-topnav .ua-tnav-admin{
  height:32px!important;border-radius:10px!important;color:#f1d896!important;
  background:linear-gradient(180deg,rgba(216,182,106,.24),rgba(216,182,106,.05))!important;
  border:1px solid rgba(216,182,106,.5)!important;
  box-shadow:inset 0 1px 0 rgba(255,236,190,.22),0 6px 18px -12px rgba(216,182,106,.6)!important;
}
@@ .ua-topnav .ua-tnav-upgrade:hover{color:#fff4d6!important;border-color:rgba(232,199,120,.85)!important;
  box-shadow:inset 0 1px 0 rgba(255,236,190,.3),0 0 22px -6px rgba(216,182,106,.75)!important;}

/* the account row: glass chips of one height */
@@ .st-key-ua_account_row button[data-testid="stBaseButton-secondary"],
@@ .st-key-ua_account_row button[data-testid="stPopoverButton"]{
  height:36px!important;min-height:36px!important;border-radius:12px!important;
  display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:7px!important;
  color:#eef3f9!important;font-size:var(--p-t-sm)!important;font-weight:650!important;
  background:linear-gradient(180deg,rgba(255,255,255,.10),rgba(255,255,255,.03))!important;
  background-color:rgba(16,24,36,.6)!important;
  border:1px solid rgba(255,255,255,.13)!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.14),inset 0 -1px 0 rgba(0,0,0,.35),0 8px 22px -12px rgba(0,0,0,.8)!important;
  backdrop-filter:blur(12px) saturate(160%)!important;-webkit-backdrop-filter:blur(12px) saturate(160%)!important;
  transition:border-color .2s ease,box-shadow .2s ease,transform .18s ease!important;
}
@@ .st-key-ua_account_row button[data-testid="stBaseButton-secondary"]:hover,
@@ .st-key-ua_account_row button[data-testid="stPopoverButton"]:hover{
  border-color:rgba(108,229,210,.6)!important;transform:translateY(-1px);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.16),0 0 0 3px rgba(108,229,210,.10),0 0 22px -6px rgba(108,229,210,.55)!important;
}
@@ .st-key-ua_account_row button:active{transform:translateY(0) scale(.97)!important;}
@@ .st-key-ua_account_row button:focus-visible{outline:2px solid #6ce5d2!important;outline-offset:2px!important;}
@@ .st-key-ua_account_row button p,
@@ .st-key-ua_account_row button svg{color:inherit!important;font-size:var(--p-t-sm)!important;font-weight:650!important;}

/* the bell: an icon, and a teal count badge on its corner only when something is unread */
@@ .st-key-ua_account_row [class*="st-key-ua_bell_"] button{padding:0 10px!important;min-width:44px!important;}
@@ .st-key-ua_account_row [class*="st-key-ua_bell_"] [data-testid="stIconMaterial"]{
  font-size:var(--p-t-lg)!important;color:rgba(238,243,250,.78)!important;transform-origin:50% 10%;}
@@ .st-key-ua_account_row .st-key-ua_bell_unread [data-testid="stIconMaterial"]{
  color:#6ce5d2!important;animation:ua-bell-ring 1.1s ease .7s 1 both;}
@@ .st-key-ua_account_row [class*="st-key-ua_bell_"] button{width:44px!important;position:relative!important;}
@@ .st-key-ua_account_row [class*="st-key-ua_bell_"] button p{font-size:0!important;margin:0!important;position:static!important;}
@@ .st-key-ua_account_row [class*="st-key-ua_bell_"] button,
@@ .st-key-ua_account_row [class*="st-key-ua_bell_"] button *{overflow:visible!important;}
@@ .st-key-ua_account_row .st-key-ua_bell_unread button p strong{
  position:absolute;top:-7px;right:-8px;margin:0!important;display:block;
  min-width:20px;padding:1px 6px!important;border-radius:999px;text-align:center;line-height:1.35!important;
  font-size:var(--p-t-xs)!important;font-weight:800!important;color:#04201c!important;
  background:linear-gradient(135deg,#6ce5d2,#a6f1e5);
  box-shadow:0 0 0 2px rgba(8,13,20,.85),0 0 14px -2px rgba(108,229,210,.85);
  animation:ua-pill-breathe 3.2s ease-in-out 1.8s infinite;
}
@keyframes ua-bell-ring{0%,100%{transform:none}20%{transform:rotate(-14deg)}40%{transform:rotate(11deg)}60%{transform:rotate(-7deg)}80%{transform:rotate(3deg)}}
@keyframes ua-pill-breathe{0%,100%{box-shadow:0 0 0 2px rgba(8,13,20,.85),0 0 10px -3px rgba(108,229,210,.6)}50%{box-shadow:0 0 0 2px rgba(8,13,20,.85),0 0 18px 0 rgba(108,229,210,.9)}}

/* the account chip: a gradient-ringed avatar with the name's initial */
@@ .st-key-ua_account_row button[data-testid="stPopoverButton"]{padding:0 10px 0 5px!important;max-width:112px!important;}
@@ .st-key-ua_account_row button[data-testid="stPopoverButton"]::before{
  content:var(--ua-initial,none) / "";flex:none;display:grid;place-items:center;width:26px;height:26px;border-radius:50%;
  font-size:var(--p-t-xs);font-weight:800;color:#04201c;
  background:conic-gradient(from 210deg,#6ce5d2,#d8b66a,#6ce5d2);
  box-shadow:0 0 0 2px rgba(8,13,20,.9),0 0 14px -3px rgba(108,229,210,.65);
}
@@ .st-key-ua_account_row button[data-testid="stPopoverButton"] p{
  max-width:52px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
@@ .stApp:not(:has(.st-key-_notification_tray_toggle)) .st-key-ua_account_row button[data-testid="stPopoverButton"]{padding:0 12px!important;}

/* In the band above the bar (where it does not fit inside), the light theme's
   chips are frosted white on the light page. */
html[data-ua-theme="light"] .st-key-ua_account_row button[data-testid="stBaseButton-secondary"],
html[data-ua-theme="light"] .st-key-ua_account_row button[data-testid="stPopoverButton"]{
  color:var(--p-ink)!important;background:linear-gradient(180deg,#fff,rgba(255,255,255,.7))!important;
  background-color:rgba(255,255,255,.8)!important;border-color:var(--p-line)!important;
  box-shadow:inset 0 1px 0 #fff,0 8px 20px -14px rgba(21,32,51,.45)!important;}
html[data-ua-theme="light"] .st-key-ua_account_row [class*="st-key-ua_bell_"] [data-testid="stIconMaterial"]{color:var(--p-ink3)!important;}
html[data-ua-theme="light"] .st-key-ua_account_row .st-key-ua_bell_unread [data-testid="stIconMaterial"]{color:var(--p-accent)!important;}
html[data-ua-theme="light"] .st-key-ua_account_row button:hover{border-color:var(--p-accent)!important;
  box-shadow:inset 0 1px 0 #fff,0 0 0 3px rgba(11,111,100,.10)!important;}

/* ── docked: inside the bar wherever it has room ─────────────────────────
   Measured: at >=1320px the links end 197px short of the bar's controls; in
   the menu layout (<=1000px) the links fold away. Between those widths, and
   on phones, the row stays in the band above. The bar keeps the room the
   row needs (padding-right), so nothing slides under it. */
@media (min-width:1320px),(min-width:680px) and (max-width:1000px){
  @@ .stApp .st-key-ua_account_row{top:8px!important;right:12px!important;}
  @@ .stApp .ua-topnav{padding-right:138px!important;}
  @@ .stApp:has(.st-key-_notification_tray_toggle) .ua-topnav{padding-right:184px!important;}
  html[data-ua-theme="light"] .st-key-ua_account_row button[data-testid="stBaseButton-secondary"],
  html[data-ua-theme="light"] .st-key-ua_account_row button[data-testid="stPopoverButton"]{
    color:#eef3f9!important;background:linear-gradient(180deg,rgba(255,255,255,.10),rgba(255,255,255,.03))!important;
    background-color:rgba(16,24,36,.6)!important;border-color:rgba(255,255,255,.13)!important;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.14),0 8px 22px -12px rgba(0,0,0,.8)!important;}
  html[data-ua-theme="light"] .st-key-ua_account_row button[data-testid="stPopoverButton"] *{color:#eef3f9!important;}
  html[data-ua-theme="light"] .st-key-ua_account_row [class*="st-key-ua_bell_"] [data-testid="stIconMaterial"]{color:rgba(238,243,250,.78)!important;}
  html[data-ua-theme="light"] .st-key-ua_account_row .st-key-ua_bell_unread [data-testid="stIconMaterial"]{color:#6ce5d2!important;}
}
/* Signed in at >=1320px the theme toggle drops its word too, so the bar's
   links keep a clear gap from its controls. */
@media (min-width:1320px){
  @@ .stApp:has(.st-key-_notification_tray_toggle) .ua-topnav .ua-theme-toggle{font-size:0!important;gap:0!important;padding:0 9px!important;}
  @@ .stApp:has(.st-key-_notification_tray_toggle) .ua-topnav .ua-theme-toggle .ua-tt-ico{font-size:var(--p-t-sm)!important;margin:0!important;}
}
@media (prefers-reduced-motion:reduce){
  @@ .ua-topnav::after{animation:none!important;}
  @@ .st-key-ua_account_row [data-testid="stIconMaterial"],
  @@ .st-key-ua_account_row button p strong{animation:none!important;}
  @@ .st-key-ua_account_row button{transition:none!important;}
}

/* ── full width on desktop ───────────────────────────────────────────────
   The page used to stop at 1200px and leave dark bands either side on any
   wide screen. It now runs edge to edge with a gutter that grows with the
   window; reading text keeps its own measure (76ch). */
@@ .stApp .block-container{max-width:none!important;
  padding-left:clamp(16px,3.2vw,64px)!important;padding-right:clamp(16px,3.2vw,64px)!important;}

/* ── the first page: one job, then the record ────────────────────────────
   Hierarchy, top to bottom: what the page does (hero), the four numbers as
   one quiet strip, the builder in a glass card (the only primary action),
   samples as the quick way into it, and the record below in tabs. */
@@ .udb-tiles{display:flex!important;flex-wrap:wrap;gap:0!important;margin:-6px 0 22px!important;
  border:1px solid rgba(148,180,210,.14);border-radius:14px;overflow:hidden;
  background:linear-gradient(180deg,rgba(255,255,255,.035),rgba(255,255,255,.01));}
@@ .udb-tiles > li{flex:1 1 200px;border-right:1px solid var(--p-line);}
@@ .udb-tiles > li:last-child{border-right:0;}
@@ .udb-tiles .udb-tile{background:transparent!important;border:0!important;border-radius:0!important;
  padding:12px 18px!important;display:grid!important;grid-template-columns:auto 1fr;column-gap:12px;align-items:baseline;}
@@ .udb-tiles .udb-v{font-size:var(--p-t-lg)!important;grid-row:span 2;}
@@ .udb-tiles .udb-l{margin:0!important;font-size:var(--p-t-sm)!important;color:var(--p-ink)!important;}
@@ .udb-tiles .udb-d{margin:0!important;}
@@ .udb-tiles a.udb-tile:hover{background:rgba(108,229,210,.06)!important;}

@@ .stApp .st-key-uar_build{position:relative;isolation:isolate;padding:26px 28px 22px;border-radius:20px;
  border:1px solid rgba(148,180,210,.18);
  background:linear-gradient(180deg,rgba(255,255,255,.055),rgba(255,255,255,.012)),var(--p-surface);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.07),0 30px 60px -36px rgba(0,0,0,.85);}
@@ .stApp .st-key-uar_build::before{content:"";position:absolute;inset:0;border-radius:inherit;z-index:-1;pointer-events:none;
  background:radial-gradient(560px 220px at 0% 0%,rgba(108,229,210,.13),transparent 70%),
    radial-gradient(420px 200px at 100% 100%,rgba(216,182,106,.08),transparent 70%);}
@@ .stApp .st-key-uar_build h2{margin-top:0!important;padding-top:0!important;}
@@ .stApp .st-key-uar_build h3,
@@ .stApp .st-key-uar_explore h3{display:flex;align-items:center;gap:12px;margin:18px 0 6px!important;padding:0!important;
  font-size:var(--p-t-xs)!important;font-weight:700!important;letter-spacing:.08em;text-transform:uppercase;color:var(--p-ink3)!important;}
@@ .stApp .st-key-uar_build h3::after{content:"";flex:1;height:1px;background:var(--p-line);}
@@ .stApp .st-key-uar_build [data-testid="stCaptionContainer"] p{font-size:var(--p-t-xs)!important;color:var(--p-ink3)!important;}
@@ .stApp .st-key-uar_build [class*="st-key-uar_sample_"] button{min-height:40px!important;border-radius:12px!important;
  background:linear-gradient(180deg,rgba(255,255,255,.07),rgba(255,255,255,.02))!important;
  border:1px solid rgba(148,180,210,.2)!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.08)!important;
  transition:border-color .2s ease,box-shadow .2s ease,transform .18s ease!important;}
@@ .stApp .st-key-uar_build [class*="st-key-uar_sample_"] button:hover{border-color:rgba(108,229,210,.6)!important;transform:translateY(-1px);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.1),0 0 22px -8px rgba(108,229,210,.6)!important;}
@@ .stApp .st-key-uar_build [class*="st-key-uar_sample_"] button p{font-weight:650!important;}

@@ .stApp .st-key-uar_explore{margin-top:14px;}
@@ .stApp .st-key-uar_explore h2{font-size:var(--p-t-md)!important;color:var(--p-ink2)!important;}
@@ .stApp .st-key-uar_explore [role="tablist"]{gap:4px!important;padding:4px;border-radius:12px;width:max-content;max-width:100%;
  border:1px solid rgba(148,180,210,.14);background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,.01));}
@@ .stApp .st-key-uar_explore [data-testid="stTab"]{border-radius:9px!important;padding:6px 14px!important;height:auto!important;border:0!important;}
@@ .stApp .st-key-uar_explore [data-testid="stTab"] > div:not([data-testid="stMarkdownContainer"]){display:none!important;}
@@ .stApp .st-key-uar_explore [role="tablist"]::after,
@@ .stApp .st-key-uar_explore [role="tablist"]::before{display:none!important;}
@@ .stApp .st-key-uar_explore [data-testid="stTab"][aria-selected="true"]{background:rgba(108,229,210,.12)!important;
  box-shadow:inset 0 0 0 1px rgba(108,229,210,.45);}
@@ .stApp .st-key-uar_explore [role="tablist"]{border-bottom:1px solid rgba(148,180,210,.14)!important;}
@@ .stApp .st-key-uar_explore [role="tablist"]{margin-bottom:6px!important;}

html[data-ua-theme="light"] .stApp .st-key-uar_build{border-color:var(--p-line);
  background:linear-gradient(180deg,#fff,rgba(255,255,255,.85));box-shadow:0 24px 50px -34px rgba(21,32,51,.4);}
html[data-ua-theme="light"] .stApp .st-key-uar_build::before{background:radial-gradient(560px 220px at 0% 0%,rgba(11,111,100,.08),transparent 70%);}
html[data-ua-theme="light"] .stApp .st-key-uar_build [class*="st-key-uar_sample_"] button{background:#fff!important;border-color:var(--p-line)!important;}
html[data-ua-theme="light"] .udb-tiles{border-color:var(--p-line);background:#fff;}
html[data-ua-theme="light"] .stApp .st-key-uar_explore [role="tablist"]{border-color:var(--p-line);background:#fff;}
html[data-ua-theme="light"] .stApp .st-key-uar_explore [data-testid="stTab"][aria-selected="true"]{background:var(--p-sky)!important;
  box-shadow:inset 0 0 0 1px var(--p-accent);}
@media (max-width:640px){
  @@ .stApp .st-key-uar_build{padding:18px 16px 16px;}
  @@ .udb-tiles > li{flex-basis:50%;border-bottom:1px solid var(--p-line);}
}

/* the hero as glass too, and one line of subtitle on a wide screen */
@@ .stApp .ua-phero{border:1px solid rgba(148,180,210,.16)!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 30px 60px -40px rgba(0,0,0,.8)!important;}
@@ .stApp .ua-phero .ua-phero-sub{max-width:78ch!important;margin-bottom:0!important;}
@@ .stApp .ua-phero h1{margin-bottom:6px!important;}

/* the dashboard row and the tour link */
@@ .stApp .st-key-uar_forces{margin:0 0 6px;}
@@ .stApp .st-key-uar_forces h3{margin:0 0 8px!important;padding:0!important;font-size:var(--p-t-xs)!important;font-weight:700!important;
  letter-spacing:.08em;text-transform:uppercase;color:var(--p-ink3)!important;}
@@ .stApp .uar-tour-link{margin:2px 0 14px!important;display:flex;justify-content:flex-end;}
@@ .stApp .uar-tour-link a{display:inline-flex;align-items:center;gap:8px;padding:7px 14px;border-radius:999px;
  font-size:var(--p-t-sm);font-weight:650;color:var(--p-ink)!important;text-decoration:none!important;
  border:1px solid rgba(108,229,210,.45);background:linear-gradient(180deg,rgba(108,229,210,.14),rgba(108,229,210,.04));
  box-shadow:inset 0 1px 0 rgba(255,255,255,.08),0 0 20px -10px rgba(108,229,210,.8);transition:box-shadow .2s ease,transform .18s ease;}
@@ .stApp .uar-tour-link a::before{content:"";width:0;height:0;border-left:8px solid var(--p-accent);
  border-top:5px solid transparent;border-bottom:5px solid transparent;}
@@ .stApp .uar-tour-link a:hover{transform:translateY(-1px);box-shadow:inset 0 1px 0 rgba(255,255,255,.1),0 0 26px -6px rgba(108,229,210,.8);}

/* ── density and glass across the report (2026-11) ───────────────────────
   Less open area: tighter section rhythm, headings that carry a thin light
   rail to the edge instead of floating in space, and every card in the same
   glass (a top highlight and a soft gradient over its surface). */
@@ .stApp [data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"]{gap:.7rem!important;}
@@ .stApp [data-testid="stMainBlockContainer"] h2{display:flex!important;align-items:center;gap:14px;
  margin:1.5rem 0 .35rem!important;padding:0!important;}
@@ .stApp [data-testid="stMainBlockContainer"] h2::after{content:"";flex:1;height:1px;min-width:40px;
  background:linear-gradient(90deg,rgba(108,229,210,.55),rgba(108,229,210,.08) 40%,transparent);}
@@ .stApp .uar-card,
@@ .stApp .uac-panel,
@@ .stApp .ult-card{background-image:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.008))!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 18px 40px -30px rgba(0,0,0,.75)!important;
  transition:border-color .2s ease;}
@@ .stApp .uar-card:hover,
@@ .stApp .uac-panel:hover,
@@ .stApp .ult-card:hover{border-color:rgba(108,229,210,.35)!important;}
html[data-ua-theme="light"] .stApp .uar-card,
html[data-ua-theme="light"] .stApp .uac-panel,
html[data-ua-theme="light"] .stApp .ult-card{background-image:linear-gradient(180deg,#fff,rgba(255,255,255,.7))!important;
  box-shadow:0 14px 34px -28px rgba(21,32,51,.45)!important;}
html[data-ua-theme="light"] .stApp [data-testid="stMainBlockContainer"] h2::after{
  background:linear-gradient(90deg,rgba(11,111,100,.5),rgba(11,111,100,.08) 40%,transparent);}
@media (prefers-reduced-motion:reduce){@@ .stApp .uar-card{transition:none!important;}}

/* the report's action bar: one glass strip, its controls in a wrapping row */
@@ .stApp .st-key-uar_actions{padding:10px 14px 14px;overflow:visible!important;height:auto!important;border-radius:14px;border:1px solid rgba(148,180,210,.16);
  background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.01));
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06);}
@@ .stApp .st-key-uar_actions > [data-testid="stVerticalBlock"],
@@ .stApp .st-key-uar_actions[data-testid="stVerticalBlock"]{flex-direction:row!important;flex-wrap:wrap;align-items:center;gap:8px 22px!important;}
@@ .stApp .st-key-uar_actions [data-testid="stElementContainer"]{width:auto!important;flex:0 1 auto;
  height:auto!important;overflow:visible!important;}
@@ .stApp .st-key-uar_actions [data-testid="stCaptionContainer"] p{margin:0!important;}
html[data-ua-theme="light"] .stApp .st-key-uar_actions{border-color:var(--p-line);background:#fff;}
""")

PRODUCT_CSS = f"""<style>
/* ── tokens ─────────────────────────────────────────────────────────────── */
html:not([data-ua-theme="light"]) .stApp,
html:not([data-ua-theme="light"]) #stFloatingOverlayPortal{{{_vars(_DARK)}{_SHARED}}}
html[data-ua-theme="light"] .stApp,
html[data-ua-theme="light"] #stFloatingOverlayPortal{{{_vars(_LIGHT)}{_SHARED}}}
/* Popovers (Sign In), select menus and tooltips render in a portal OUTSIDE
   .stApp, so every .stApp rule missed them: the sign-in form had no focus
   ring, a 2.5:1 caption, and the retired violet on its checkbox and tabs.
   The tokens are defined there too, and the control rules below name it. */

/* ── page ground ────────────────────────────────────────────────────────── */
html[data-ua-theme="light"] .stApp,
html:not([data-ua-theme="light"]) .stApp{{
  background:var(--p-bg)!important;
  font-family:Inter,"SF Pro Text","Segoe UI",system-ui,-apple-system,sans-serif;
  font-variant-numeric:tabular-nums;
}}
/* The full-screen container sits above .stApp and the retired skin painted it
   (#0a0d12 dark, #f6f5fb light) with !important, so the token ground above
   never showed: the app and the landing page were two different navies. */
html[data-ua-theme="light"] .stApp [data-testid="stAppViewContainer"],
html:not([data-ua-theme="light"]) .stApp [data-testid="stAppViewContainer"]{{
  background:var(--p-bg)!important;}}
.stApp [data-testid="stMain"]{{background:transparent!important;}}
.stApp .block-container{{max-width:1200px;padding-top:58px!important;}}

/* ── top nav: the landing page's navy band ──────────────────────────────── */
html[data-ua-theme="light"] .ua-topnav,
html:not([data-ua-theme="light"]) .ua-topnav{{
  background:var(--p-navy)!important;
  /* A solid colour under the gradient: what shows if the gradient cannot, and
     what contrast checkers measure the bar's text against. */
  background-color:var(--p-navy)!important;
  border-bottom:1px solid #1c2738!important;
  backdrop-filter:none!important;-webkit-backdrop-filter:none!important;
  box-shadow:0 1px 0 rgba(13,34,59,.06)!important;height:52px!important;
}}
html[data-ua-theme="light"] .ua-topnav a.ua-tnav-item,
html:not([data-ua-theme="light"]) .ua-topnav a.ua-tnav-item,
html[data-ua-theme="light"] .ua-topnav .ua-tnav-trigger,
html:not([data-ua-theme="light"]) .ua-topnav .ua-tnav-trigger{{
  color:rgba(238,243,250,.86)!important;font-size:var(--p-t-sm)!important;font-weight:500!important;
}}
/* WCAG 2.2 target size: the links had collapsed to their 15px line box, and
   with the menu triggers now real buttons beside them, neighbouring targets
   sat closer than 24px. The bar is 52px; every item takes 32 of it. */
html[data-ua-theme="light"] .ua-topnav .ua-tnav-links > a.ua-tnav-item,
html:not([data-ua-theme="light"]) .ua-topnav .ua-tnav-links > a.ua-tnav-item,
html[data-ua-theme="light"] .ua-topnav .ua-tnav-trigger,
html:not([data-ua-theme="light"]) .ua-topnav .ua-tnav-trigger{{
  display:inline-flex!important;align-items:center!important;min-height:32px!important;box-sizing:border-box;}}
/* The triggers became buttons (keyboard access) and picked up a grey button
   face (#6b6b6b, 4.0:1) from an older rule; they wear the bar like the links. */
html[data-ua-theme="light"] .ua-topnav button.ua-tnav-trigger,
html:not([data-ua-theme="light"]) .ua-topnav button.ua-tnav-trigger,
html[data-ua-theme="light"] .ua-topnav button.ua-tnav-burger,
html:not([data-ua-theme="light"]) .ua-topnav button.ua-tnav-burger{{
  background:transparent!important;border:0!important;box-shadow:none!important;font-family:inherit!important;}}
html[data-ua-theme="light"] .ua-topnav .ua-tnav-group:focus-within>.ua-tnav-trigger,
html:not([data-ua-theme="light"]) .ua-topnav .ua-tnav-group:focus-within>.ua-tnav-trigger{{
  color:#fff!important;background:rgba(255,255,255,.10)!important;}}
html[data-ua-theme="light"] .ua-topnav a.ua-tnav-item:hover,
html:not([data-ua-theme="light"]) .ua-topnav a.ua-tnav-item:hover,
html[data-ua-theme="light"] .ua-topnav .ua-tnav-group:hover>.ua-tnav-trigger,
html:not([data-ua-theme="light"]) .ua-topnav .ua-tnav-group:hover>.ua-tnav-trigger{{
  color:#fff!important;background:rgba(255,255,255,.10)!important;
}}
html[data-ua-theme="light"] .ua-topnav a.ua-tnav-item.active,
html:not([data-ua-theme="light"]) .ua-topnav a.ua-tnav-item.active,
html[data-ua-theme="light"] .ua-topnav .ua-tnav-trigger.active,
html:not([data-ua-theme="light"]) .ua-topnav .ua-tnav-trigger.active{{
  color:#fff!important;background:rgba(255,255,255,.14)!important;
}}
/* Below the nav's breakpoint the links stop being a row on the navy bar and
   become a drop-down panel that is WHITE in light mode -- but they are still
   inside .ua-topnav, so the rule above painted them near-white on white and
   the whole menu vanished. Found by opening it at 900px: "Report", "What
   changed", "Alerts" and "Methodology" were all rgba(238,243,250,.86) on
   rgba(255,255,255,.99). Only the sub-links were readable, because the old
   skin still themes those. */
@media (max-width: 1000px) {{
  html[data-ua-theme="light"] .ua-topnav .ua-tnav-links a.ua-tnav-item,
  html[data-ua-theme="light"] .ua-topnav .ua-tnav-links .ua-tnav-trigger{{
    color:var(--p-ink)!important;}}
  html[data-ua-theme="light"] .ua-topnav .ua-tnav-links a.ua-tnav-item:hover{{
    background:var(--p-sky)!important;color:var(--p-accent)!important;}}
  html[data-ua-theme="light"] .ua-topnav .ua-tnav-links a.ua-tnav-item.active{{
    background:var(--p-sky)!important;color:var(--p-accent)!important;}}
  html[data-ua-theme="light"] .ua-topnav .ua-tnav-links .ua-tnav-trigger{{
    color:var(--p-ink3)!important;}}
}}
html[data-ua-theme="light"] .ua-tnav-brand-text,
html:not([data-ua-theme="light"]) .ua-tnav-brand-text{{color:#fff!important;font-size:var(--p-t-sm)!important;}}
.ua-tnav-brand-text em{{-webkit-text-fill-color:var(--p-bright)!important;background:none!important;}}
html[data-ua-theme="light"] .ua-tnav-upgrade,
html:not([data-ua-theme="light"]) .ua-tnav-upgrade{{
  background:transparent!important;color:var(--p-bright)!important;font-weight:650!important;
  border:1px solid rgba(216,182,106,.45)!important;
  /* "transition: all" animated the focus ring in from 0px; focus shows at once. */
  transition:background-color .14s ease,color .14s ease!important;
}}
html[data-ua-theme="light"] .ua-theme-toggle,
html:not([data-ua-theme="light"]) .ua-theme-toggle{{
  color:rgba(238,243,250,.72)!important;border-color:rgba(255,255,255,.22)!important;
  background:transparent!important;
}}
/* The hover menus are children of a now-navy bar; keep them on the page's
   surface colour rather than the old skin's near-black. */
html[data-ua-theme="light"] .ua-tnav-drop{{background:var(--p-surface)!important;
  border-color:var(--p-line)!important;}}
html[data-ua-theme="light"] .ua-tnav-drop a{{color:var(--p-ink2)!important;}}
html[data-ua-theme="light"] .ua-tnav-drop a:hover{{background:var(--p-sky)!important;color:var(--p-ink)!important;}}

/* ── the page header, as the landing hero ───────────────────────────────── */
.ua-phero{{position:relative;overflow:hidden;border-radius:var(--p-r);
  margin:4px 0 24px;color:#f3f6fa;border:1px solid #1c2738;
  background:
    radial-gradient(640px 300px at 92% 0%,rgba(108,229,210,.10),transparent 65%),
    var(--p-navy);}}
.ua-phero::before{{content:"";position:absolute;inset:0;pointer-events:none;
  background-image:linear-gradient(rgba(168,181,199,.06) 1px,transparent 1px),
    linear-gradient(90deg,rgba(168,181,199,.06) 1px,transparent 1px);
  background-size:40px 40px;
  -webkit-mask-image:radial-gradient(ellipse 60% 90% at 85% 0%,#000 10%,transparent 70%);
  mask-image:radial-gradient(ellipse 60% 90% at 85% 0%,#000 10%,transparent 70%);}}
.ua-phero-in{{position:relative;padding:24px 28px 24px;}}
.ua-phero-eyebrow{{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:var(--p-t-xs)!important;
  font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:#6ce5d2!important;margin-bottom:8px;}}
.stApp .ua-phero h1{{font-size:var(--p-t-xl)!important;line-height:1.08!important;
  letter-spacing:-0.03em!important;font-weight:700!important;color:#fff!important;margin:0!important;
  padding:0!important;}}
.stApp .ua-phero .ua-phero-sub{{font-size:var(--p-t-md)!important;line-height:1.55!important;
  color:#a8b5c7!important;margin-top:8px!important;max-width:64ch!important;}}
.stApp .ua-phero .ua-phero-facts{{list-style:none;padding:0;margin:14px 0 0!important;
  display:flex;flex-wrap:wrap;gap:6px 18px;}}
.stApp .ua-phero .ua-phero-facts li{{display:flex;align-items:center;gap:8px;line-height:1.45!important;
  font-size:var(--p-t-sm)!important;color:#a8b5c7!important;max-width:none!important;}}
.ua-phero-facts li::before{{content:"";width:5px;height:5px;border-radius:50%;
  background:#6ce5d2;flex-shrink:0;}}
.ua-phero-strip{{display:none;}}
@media (max-width:760px){{.ua-phero-in{{padding:22px 20px 24px;}}}}

/* ── type ───────────────────────────────────────────────────────────────── */
.stApp h2{{font-size:var(--p-t-lg)!important;font-weight:700!important;
  letter-spacing:-0.02em!important;color:var(--p-ink)!important;}}
.stApp h3{{font-size:var(--p-t-md)!important;font-weight:650!important;color:var(--p-ink)!important;}}
.stApp [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stMarkdownContainer"] li{{color:var(--p-ink2)!important;
  font-size:var(--p-t-base)!important;line-height:1.65!important;max-width:76ch;}}
.stApp [data-testid="stMarkdownContainer"] strong{{color:var(--p-ink)!important;}}
.stApp [data-testid="stCaptionContainer"],.stApp [data-testid="stCaptionContainer"] p{{
  color:var(--p-ink3)!important;}}
/* Streamlit gives captions opacity:.6 on top of their colour, which took
   --p-ink3 (#5b6780, 5.6:1) to #9ba2b0 on the light ground: 2.45:1, a WCAG
   failure on every caption of every product page. The colour already carries
   the de-emphasis. */
.stApp [data-testid="stCaptionContainer"]{{opacity:1!important;}}
#stFloatingOverlayPortal [data-testid="stCaptionContainer"],
#stFloatingOverlayPortal [data-testid="stCaptionContainer"] p{{color:var(--p-ink3)!important;opacity:1!important;}}

/* "Stocks" made seven top-level items, 33px too wide for a 1024px screen
   (the width #251 had to fix once already). Below 1100px the items tighten
   from 9px to 6px a side instead of any of them being dropped. */
@media (max-width:1099px){{
  html[data-ua-theme="light"] .ua-topnav .ua-tnav-links > a.ua-tnav-item,
  html:not([data-ua-theme="light"]) .ua-topnav .ua-tnav-links > a.ua-tnav-item,
  html[data-ua-theme="light"] .ua-topnav .ua-tnav-links .ua-tnav-trigger,
  html:not([data-ua-theme="light"]) .ua-topnav .ua-tnav-links .ua-tnav-trigger{{
    padding-left:6px!important;padding-right:6px!important;}}
}}

/* ── buttons ────────────────────────────────────────────────────────────── */
html[data-ua-theme="light"] .stApp button[data-testid="stBaseButton-primary"],
html:not([data-ua-theme="light"]) .stApp button[data-testid="stBaseButton-primary"]{{
  background:var(--p-accent)!important;border:1px solid var(--p-accent)!important;
  color:var(--p-accent-ink)!important;box-shadow:none!important;border-radius:var(--p-r-btn)!important;
  font-weight:650!important;min-height:44px!important;}}
html[data-ua-theme="light"] .stApp button[data-testid="stBaseButton-primary"]:hover,
html:not([data-ua-theme="light"]) .stApp button[data-testid="stBaseButton-primary"]:hover{{
  background:var(--p-accent-hover)!important;border-color:var(--p-accent-hover)!important;}}
html[data-ua-theme="light"] .stApp button[data-testid="stBaseButton-primary"] p,
html:not([data-ua-theme="light"]) .stApp button[data-testid="stBaseButton-primary"] p{{
  color:var(--p-accent-ink)!important;font-weight:650!important;font-size:var(--p-t-base)!important;}}
html[data-ua-theme="light"] .stApp button[data-testid="stBaseButton-secondary"],
html:not([data-ua-theme="light"]) .stApp button[data-testid="stBaseButton-secondary"]{{
  background:var(--p-surface)!important;border:1px solid var(--p-line)!important;
  box-shadow:none!important;border-radius:var(--p-r-btn)!important;min-height:44px!important;}}
html[data-ua-theme="light"] .stApp button[data-testid="stBaseButton-secondary"] p,
html:not([data-ua-theme="light"]) .stApp button[data-testid="stBaseButton-secondary"] p{{
  color:var(--p-ink)!important;font-weight:600!important;font-size:var(--p-t-base)!important;}}
html[data-ua-theme="light"] .stApp button[data-testid="stBaseButton-secondary"]:hover,
html:not([data-ua-theme="light"]) .stApp button[data-testid="stBaseButton-secondary"]:hover{{
  border-color:var(--p-accent)!important;background:var(--p-sky)!important;}}
/* st.link_button renders its own testid and inherits none of the above, so
   "Ask about the pilot" came out near-black on navy. */
html[data-ua-theme="light"] .stApp a[data-testid="stBaseLinkButton-secondary"],
html:not([data-ua-theme="light"]) .stApp a[data-testid="stBaseLinkButton-secondary"]{{
  background:var(--p-surface)!important;border:1px solid var(--p-line)!important;
  color:var(--p-ink)!important;border-radius:var(--p-r-btn)!important;min-height:44px!important;
  font-weight:600!important;font-size:var(--p-t-base)!important;box-shadow:none!important;}}
html[data-ua-theme="light"] .stApp a[data-testid="stBaseLinkButton-secondary"]:hover,
html:not([data-ua-theme="light"]) .stApp a[data-testid="stBaseLinkButton-secondary"]:hover{{
  border-color:var(--p-accent)!important;background:var(--p-sky)!important;}}
html[data-ua-theme="light"] .stApp a[data-testid="stBaseLinkButton-primary"],
html:not([data-ua-theme="light"]) .stApp a[data-testid="stBaseLinkButton-primary"]{{
  background:var(--p-accent)!important;border:1px solid var(--p-accent)!important;
  color:var(--p-accent-ink)!important;border-radius:var(--p-r-btn)!important;min-height:44px!important;
  font-weight:650!important;font-size:var(--p-t-base)!important;box-shadow:none!important;}}
/* ── keyboard focus ─────────────────────────────────────────────────────────
   Measured 2026-09-29: no Streamlit button, input or radio showed focus. The
   retired skin drew button focus as a box-shadow with outline:none, and the
   buttons above set box-shadow:none, removing the only indicator; its old
   .stButton > button:focus-visible{{outline:none!important}} also out-ranked
   the amber ring that used to be here -- which was 1.6:1 on the light ground
   anyway. Now: the accent (6.4:1 light, 9:1 dark) in content, amber on the
   navy nav band, and the html[data-ua-theme] prefix so it always wins. */
html[data-ua-theme="light"] .stApp *:focus-visible,
html:not([data-ua-theme="light"]) .stApp *:focus-visible,
html #stFloatingOverlayPortal *:focus-visible{{
  outline:2px solid var(--p-accent)!important;outline-offset:2px!important;}}
html[data-ua-theme="light"] .stApp .ua-topnav *:focus-visible,
html:not([data-ua-theme="light"]) .stApp .ua-topnav *:focus-visible{{
  outline:2px solid var(--p-bright)!important;outline-offset:2px!important;}}
/* ...and white on the gold-outlined Upgrade link, to tell the ring from its border. */
html[data-ua-theme="light"] .stApp .ua-topnav a.ua-tnav-upgrade:focus-visible,
html:not([data-ua-theme="light"]) .stApp .ua-topnav a.ua-tnav-upgrade:focus-visible{{
  outline:2px solid #ffffff!important;outline-offset:2px!important;}}
/* Streamlit's text inputs and selects clip an outline on the input itself,
   and its radios hide the real input, so the ring goes on what is visible. */
html[data-ua-theme="light"] .stApp [data-baseweb="input"]:focus-within,
html:not([data-ua-theme="light"]) .stApp [data-baseweb="input"]:focus-within,
html #stFloatingOverlayPortal [data-baseweb="input"]:focus-within,
html #stFloatingOverlayPortal [data-testid="stCheckbox"] label:has(input:focus-visible),
html[data-ua-theme="light"] .stApp [data-baseweb="textarea"]:focus-within,
html:not([data-ua-theme="light"]) .stApp [data-baseweb="textarea"]:focus-within,
html[data-ua-theme="light"] .stApp [data-baseweb="select"] > div:focus-within,
html:not([data-ua-theme="light"]) .stApp [data-baseweb="select"] > div:focus-within,
html[data-ua-theme="light"] .stApp [data-testid="stRadio"] label:has(input:focus-visible),
html:not([data-ua-theme="light"]) .stApp [data-testid="stRadio"] label:has(input:focus-visible),
html[data-ua-theme="light"] .stApp [data-testid="stCheckbox"] label:has(input:focus-visible),
html:not([data-ua-theme="light"]) .stApp [data-testid="stCheckbox"] label:has(input:focus-visible){{
  outline:2px solid var(--p-accent)!important;outline-offset:2px!important;}}
html[data-ua-theme="light"] .stApp [data-baseweb="input"] input:focus-visible,
html:not([data-ua-theme="light"]) .stApp [data-baseweb="input"] input:focus-visible,
html #stFloatingOverlayPortal [data-baseweb="input"] input:focus-visible,
html[data-ua-theme="light"] .stApp [data-baseweb="select"] input:focus-visible,
html:not([data-ua-theme="light"]) .stApp [data-baseweb="select"] input:focus-visible{{
  outline:none!important;}}
/* Text and password fields clip an outline drawn on the input (only a sliver
   showed at the right edge), and in Streamlit 1.64 the input is not under
   [data-baseweb="input"]. The ring goes on the input's own frame instead. */
html[data-ua-theme="light"] .stApp [data-testid="stTextInput"] div:has(> input:focus-visible),
html:not([data-ua-theme="light"]) .stApp [data-testid="stTextInput"] div:has(> input:focus-visible),
html #stFloatingOverlayPortal [data-testid="stTextInput"] div:has(> input:focus-visible),
html[data-ua-theme="light"] .stApp [data-testid="stTextArea"] div:has(> textarea:focus-visible),
html:not([data-ua-theme="light"]) .stApp [data-testid="stTextArea"] div:has(> textarea:focus-visible){{
  outline:2px solid var(--p-accent)!important;outline-offset:2px!important;border-radius:8px;}}
html[data-ua-theme="light"] .stApp [data-testid="stTextInput"] input:focus-visible,
html:not([data-ua-theme="light"]) .stApp [data-testid="stTextInput"] input:focus-visible,
html #stFloatingOverlayPortal [data-testid="stTextInput"] input:focus-visible,
html[data-ua-theme="light"] .stApp [data-testid="stTextArea"] textarea:focus-visible,
html:not([data-ua-theme="light"]) .stApp [data-testid="stTextArea"] textarea:focus-visible{{outline:none!important;}}
/* Streamlit's "Press Enter to submit form" hint, in the retired faint grey. */
.stApp [data-testid="InputInstructions"],#stFloatingOverlayPortal [data-testid="InputInstructions"]{{
  color:var(--p-ink3)!important;opacity:1!important;}}

/* ── radio buttons ─────────────────────────────────────────────────────────
   Streamlit paints the radio circle from its base theme, which is still the
   retired dark skin: an UNselected option drew a 14px #0b0d12 dot filling its
   circle -- it looked more selected than the selected one, which was the
   retired violet #6470f5. Now the standard reading: a hollow ring when off
   (ink3, 5.6:1 against the surface), the accent with a centre dot when on. */
html[data-ua-theme="light"] .stApp [data-testid="stRadio"] label > div:first-of-type > div:first-of-type,
html:not([data-ua-theme="light"]) .stApp [data-testid="stRadio"] label > div:first-of-type > div:first-of-type{{
  background:var(--p-surface)!important;border:1.5px solid var(--p-ink3)!important;
  box-sizing:border-box!important;width:16px!important;height:16px!important;
  display:flex!important;align-items:center!important;justify-content:center!important;}}
html[data-ua-theme="light"] .stApp [data-testid="stRadio"] label > div:first-of-type > div:first-of-type > div,
html:not([data-ua-theme="light"]) .stApp [data-testid="stRadio"] label > div:first-of-type > div:first-of-type > div{{
  background:transparent!important;width:6px!important;height:6px!important;}}
html[data-ua-theme="light"] .stApp [data-testid="stRadio"] label:has(input:checked) > div:first-of-type > div:first-of-type,
html:not([data-ua-theme="light"]) .stApp [data-testid="stRadio"] label:has(input:checked) > div:first-of-type > div:first-of-type{{
  background:var(--p-accent)!important;border-color:var(--p-accent)!important;}}
html[data-ua-theme="light"] .stApp [data-testid="stRadio"] label:has(input:checked) > div:first-of-type > div:first-of-type > div,
html:not([data-ua-theme="light"]) .stApp [data-testid="stRadio"] label:has(input:checked) > div:first-of-type > div:first-of-type > div{{
  background:var(--p-accent-ink)!important;}}

/* ── checkboxes and tabs: the same base-theme leak as the radios ─────────────
   Checked boxes and the selected tab's underline were the retired violet. */
html[data-ua-theme="light"] .stApp [data-testid="stCheckbox"] label > div:first-of-type,
html:not([data-ua-theme="light"]) .stApp [data-testid="stCheckbox"] label > div:first-of-type,
html #stFloatingOverlayPortal [data-testid="stCheckbox"] label > div:first-of-type{{
  background:var(--p-surface)!important;border:1.5px solid var(--p-ink3)!important;}}
html[data-ua-theme="light"] .stApp [data-testid="stCheckbox"] label:has(input:checked) > div:first-of-type,
html:not([data-ua-theme="light"]) .stApp [data-testid="stCheckbox"] label:has(input:checked) > div:first-of-type,
html #stFloatingOverlayPortal [data-testid="stCheckbox"] label:has(input:checked) > div:first-of-type{{
  background:var(--p-accent)!important;border-color:var(--p-accent)!important;}}
html[data-ua-theme="light"] .stApp [data-testid="stCheckbox"] label:has(input:checked) > div:first-of-type svg,
html:not([data-ua-theme="light"]) .stApp [data-testid="stCheckbox"] label:has(input:checked) > div:first-of-type svg,
html #stFloatingOverlayPortal [data-testid="stCheckbox"] label:has(input:checked) > div:first-of-type svg{{
  color:var(--p-accent-ink)!important;stroke:var(--p-accent-ink)!important;}}
html[data-ua-theme="light"] .stApp [role="tab"][aria-selected="true"] > div:last-child,
html:not([data-ua-theme="light"]) .stApp [role="tab"][aria-selected="true"] > div:last-child,
html #stFloatingOverlayPortal [role="tab"][aria-selected="true"] > div:last-child{{
  background:var(--p-accent)!important;}}

/* Placeholders carried the retired skin's faint grey (axe: 2.3:1 on /compare). */
.stApp input::placeholder,.stApp textarea::placeholder{{color:var(--p-ink3)!important;opacity:1!important;}}
/* A select's type-to-search text was #e8eeff -- the retired dark ink -- on a
   white field: anything typed into it was invisible (1.15:1). */
html[data-ua-theme="light"] .stApp [data-baseweb="select"] input,
html:not([data-ua-theme="light"]) .stApp [data-baseweb="select"] input,
html[data-ua-theme="light"] .stApp [data-testid="stSelectbox"] input,
html:not([data-ua-theme="light"]) .stApp [data-testid="stSelectbox"] input{{
  color:var(--p-ink)!important;-webkit-text-fill-color:var(--p-ink)!important;}}

/* ── every control surface, not just the visible face of one ────────────────
   Found by sweeping the rendered page for the retired skin's own colours
   (#0b0d12, #12151e, #6470f5) rather than by looking at screenshots. Styling
   an <input> while leaving BaseWeb's wrapper alone leaves a dark ring around a
   white field, and the radio and checkbox markers kept the old purple
   throughout. These are the wrappers and the markers. */
html[data-ua-theme="light"] .stApp [data-testid="stTextInputRootElement"],
html:not([data-ua-theme="light"]) .stApp [data-testid="stTextInputRootElement"],
html[data-ua-theme="light"] .stApp [data-baseweb="input"],
html:not([data-ua-theme="light"]) .stApp [data-baseweb="input"],
html[data-ua-theme="light"] .stApp [data-baseweb="base-input"],
html:not([data-ua-theme="light"]) .stApp [data-baseweb="base-input"],
html[data-ua-theme="light"] .stApp [data-baseweb="textarea"],
html:not([data-ua-theme="light"]) .stApp [data-baseweb="textarea"]{{
  background:var(--p-surface)!important;border-color:var(--p-line)!important;
  color:var(--p-ink)!important;}}
html[data-ua-theme="light"] .stApp [data-testid="stRadio"] [role="radiogroup"] label > div:first-child,
html:not([data-ua-theme="light"]) .stApp [data-testid="stRadio"] [role="radiogroup"] label > div:first-child{{
  background:var(--p-surface)!important;border-color:var(--p-line)!important;}}
html[data-ua-theme="light"] .stApp [data-testid="stRadio"] label:has(input:checked) > div:first-child,
html:not([data-ua-theme="light"]) .stApp [data-testid="stRadio"] label:has(input:checked) > div:first-child{{
  background:var(--p-accent)!important;border-color:var(--p-accent)!important;}}
html[data-ua-theme="light"] .stApp [data-testid="stCheckbox"] label span[aria-hidden="true"],
html:not([data-ua-theme="light"]) .stApp [data-testid="stCheckbox"] label span[aria-hidden="true"]{{
  background-color:var(--p-accent)!important;border-color:var(--p-accent)!important;}}
/* The label element carries the old ink even when the <p> inside is themed;
   one nested override away from being visible, so it is set too. */
html[data-ua-theme="light"] .stApp [data-testid="stWidgetLabel"],
html[data-ua-theme="light"] .stApp [data-testid="stRadio"] [role="radiogroup"] label,
html[data-ua-theme="light"] .stApp [data-testid="stRadio"] [role="radiogroup"] label div{{
  color:var(--p-ink2)!important;}}
html[data-ua-theme="light"] .stApp [data-testid="stRadio"] label:has(input:checked) div{{
  color:var(--p-accent)!important;}}

/* ── select boxes, closed and open ──────────────────────────────────────
   No product page used st.selectbox until Compare, so nothing themed it: the
   closed control rendered as a near-black bar (rgba(15,17,24,.92)) on the light
   page, and the open list was #0b0d12 with #e8eeff text.

   The open list is a BaseWeb PORTAL outside .stApp — the same trap as the
   sign-in panel — so its rules are deliberately not .stApp-scoped, and they use
   literal colours because the --p-* tokens are declared on .stApp and do not
   exist out there. :has() narrows them to the select's own popover so the
   sign-in panel, which is also a BaseWeb popover, is left alone. */
html[data-ua-theme="light"] .stApp [data-baseweb="select"] > div,
html:not([data-ua-theme="light"]) .stApp [data-baseweb="select"] > div{{
  background:var(--p-surface)!important;border:1px solid var(--p-line)!important;
  border-radius:var(--p-r)!important;color:var(--p-ink)!important;}}
html[data-ua-theme="light"] .stApp [data-baseweb="select"] > div:focus-within,
html:not([data-ua-theme="light"]) .stApp [data-baseweb="select"] > div:focus-within{{
  border-color:var(--p-accent)!important;box-shadow:0 0 0 3px rgba(31,95,174,.14)!important;}}
html[data-ua-theme="light"] .stApp [data-baseweb="select"] *,
html:not([data-ua-theme="light"]) .stApp [data-baseweb="select"] *{{color:var(--p-ink)!important;}}
html[data-ua-theme="light"] .stApp [data-baseweb="select"] svg{{fill:var(--p-ink3)!important;}}
/* The select's type-ahead <input> kept #d8dde5 on white (1.36:1, measured by
   axe) despite the rule above, because the old skin paints input text with
   -webkit-text-fill-color, which beats `color` in WebKit and Blink. */
html[data-ua-theme="light"] .stApp [data-baseweb="select"] input,
html:not([data-ua-theme="light"]) .stApp [data-baseweb="select"] input{{
  color:var(--p-ink)!important;-webkit-text-fill-color:var(--p-ink)!important;}}
html[data-ua-theme="light"] [data-baseweb="popover"]:has([data-testid="stSelectboxVirtualDropdown"]),
html[data-ua-theme="light"] [data-testid="stSelectboxVirtualDropdown"]{{
  background:#ffffff!important;border:1px solid #dfe5ee!important;border-radius:12px!important;
  box-shadow:0 24px 50px -30px rgba(13,34,59,.35)!important;}}
html[data-ua-theme="light"] [data-testid="stSelectboxVirtualDropdown"] *{{color:#13213a!important;}}
html[data-ua-theme="light"] [data-testid="stSelectboxVirtualDropdown"] li:hover,
html[data-ua-theme="light"] [data-testid="stSelectboxVirtualDropdown"] [aria-selected="true"]{{
  background:#edf4fc!important;}}
html[data-ua-theme="light"] [data-testid="stSelectboxVirtualDropdown"] [aria-selected="true"] *{{
  color:#1f5fae!important;font-weight:600!important;}}
html:not([data-ua-theme="light"]) [data-baseweb="popover"]:has([data-testid="stSelectboxVirtualDropdown"]),
html:not([data-ua-theme="light"]) [data-testid="stSelectboxVirtualDropdown"]{{
  background:#121d2f!important;border:1px solid #243349!important;border-radius:12px!important;}}
html:not([data-ua-theme="light"]) [data-testid="stSelectboxVirtualDropdown"] *{{color:#e8edf5!important;}}
html:not([data-ua-theme="light"]) [data-testid="stSelectboxVirtualDropdown"] li:hover,
html:not([data-ua-theme="light"]) [data-testid="stSelectboxVirtualDropdown"] [aria-selected="true"]{{
  background:#16233a!important;}}

/* ── inputs ─────────────────────────────────────────────────────────────── */
.stApp [data-testid="stTextArea"] textarea,.stApp [data-testid="stTextInput"] input,
.stApp [data-testid="stNumberInput"] input{{
  background:var(--p-surface)!important;border:1px solid var(--p-line)!important;
  color:var(--p-ink)!important;border-radius:var(--p-r)!important;font-size:var(--p-t-base)!important;}}
.stApp [data-testid="stTextArea"] textarea:focus,.stApp [data-testid="stTextInput"] input:focus,
.stApp [data-testid="stNumberInput"] input:focus{{
  border-color:var(--p-accent)!important;box-shadow:0 0 0 3px rgba(31,95,174,.14)!important;}}
/* The number input wraps its field and the -/+ steppers in a container that
   carries its own background; left alone it rendered as a black slab on the
   light page. */
.stApp [data-testid="stNumberInputContainer"]{{background:var(--p-surface)!important;
  border:1px solid var(--p-line)!important;border-radius:var(--p-r)!important;
  box-shadow:none!important;}}
/* BaseWeb nests two unlabelled divs between that container and the field, and
   both carry the old skin's near-black. Measured: the container was white and
   the control still rendered as a black slab. */
.stApp [data-testid="stNumberInputContainer"] div{{background:transparent!important;}}
.stApp [data-testid="stNumberInput"] input{{border:0!important;background:transparent!important;}}
/* The -/+ steppers carry no accessible name, which axe reports as a real
   button-name failure, and Streamlit gives no way to label them from Python.
   They are tabindex="-1" decoration next to a field whose actual interaction
   is typing a percentage, so display:none removes both the clutter and the
   violation — aria-hidden would need an attribute this stylesheet cannot set. */
.stApp [data-testid="stNumberInputStepDown"],
.stApp [data-testid="stNumberInputStepUp"]{{display:none!important;}}
.stApp [data-testid="stFileUploaderDropzone"]{{background:var(--p-subtle)!important;
  border:1px dashed var(--p-line)!important;border-radius:var(--p-r)!important;}}
/* The uploader's own labels and the accepted-file row kept the dark skin's ink.
   Measured on the light page: "Drag and drop file here" rendered #e8eeff on
   #f4f6fa, about 1.1:1 — legible only if you already knew what it said. */
html[data-ua-theme="light"] .stApp [data-testid="stFileUploaderDropzone"] span,
html[data-ua-theme="light"] .stApp [data-testid="stFileUploaderDropzone"] div,
html[data-ua-theme="light"] .stApp [data-testid="stFileUploaderFile"] div,
html[data-ua-theme="light"] .stApp [data-testid="stFileUploaderFile"] span{{
  color:var(--p-ink)!important;}}
html[data-ua-theme="light"] .stApp [data-testid="stFileUploaderDropzone"] small,
html[data-ua-theme="light"] .stApp [data-testid="stFileUploaderFile"] small{{
  color:var(--p-ink3)!important;}}
html:not([data-ua-theme="light"]) .stApp [data-testid="stFileUploaderDropzone"] span,
html:not([data-ua-theme="light"]) .stApp [data-testid="stFileUploaderFile"] div{{
  color:var(--p-ink)!important;}}
.stApp [data-testid="stWidgetLabel"] p{{color:var(--p-ink3)!important;font-size:var(--p-t-sm)!important;}}

/* ── radio as a segmented control ───────────────────────────────────────── */
.stApp [data-testid="stRadio"] [role="radiogroup"]{{gap:8px!important;}}
.stApp [data-testid="stRadio"] label{{background:var(--p-surface)!important;
  border:1px solid var(--p-line)!important;border-radius:var(--p-r-pill)!important;
  padding:6px 14px!important;margin:0!important;}}
.stApp [data-testid="stRadio"] label p{{color:var(--p-ink2)!important;font-size:var(--p-t-sm)!important;}}
.stApp [data-testid="stRadio"] label:has(input:checked){{border-color:var(--p-accent)!important;
  background:var(--p-sky)!important;}}
.stApp [data-testid="stRadio"] label:has(input:checked) p{{color:var(--p-accent)!important;
  font-weight:650!important;}}
.stApp [data-testid="stRadio"] [data-testid="stWidgetLabel"]{{margin-bottom:6px!important;}}

/* ── expanders, code, alerts, checkbox ──────────────────────────────────── */
.stApp [data-testid="stExpander"] details{{background:var(--p-surface)!important;
  border:1px solid var(--p-line)!important;border-radius:var(--p-r)!important;}}
.stApp [data-testid="stExpander"] summary{{color:var(--p-ink)!important;font-weight:600!important;}}
.stApp [data-testid="stCode"],.stApp pre{{background:var(--p-subtle)!important;
  border:1px solid var(--p-line)!important;border-radius:var(--p-r)!important;}}
.stApp [data-testid="stAlertContainer"]{{border-radius:var(--p-r)!important;
  border:1px solid var(--p-line)!important;}}
.stApp [data-testid="stCheckbox"] label p{{color:var(--p-ink2)!important;font-size:var(--p-t-base)!important;}}

/* Below 1180px the theme toggle keeps its icon and drops its word, so the
   bar's last control no longer runs past its edge at 1024px. Its accessible
   name is the aria-label, so nothing is lost to a screen reader. */
@media (max-width:1179px){{
  html[data-ua-theme="light"] .ua-topnav .ua-theme-toggle,
  html:not([data-ua-theme="light"]) .ua-topnav .ua-theme-toggle{{font-size:0!important;gap:0!important;padding:0 9px!important;}}
  html[data-ua-theme="light"] .ua-topnav .ua-theme-toggle .ua-tt-ico,
  html:not([data-ua-theme="light"]) .ua-topnav .ua-theme-toggle .ua-tt-ico{{font-size:var(--p-t-sm)!important;margin:0!important;}}
}}
{GLASS_CSS}
</style>"""


# Pages outside the 60-65 block that are nonetheless part of the current
# product. 29_Upgrade.py is here because Stripe's success_url, the Pro gates,
# referral links and several emails all point at /upgrade-to-pro; the route
# cannot move, so the page comes to the theme instead.
EXTRA_PRODUCT_PAGES = frozenset({"29_Upgrade.py"})


def is_product_page(caller_file: str | None) -> bool:
    """True for the pages built after the redesign, which carry this theme."""
    from utils.legacy_pages import LEGACY_PAGE_FILES

    if not caller_file:
        return False
    name = Path(str(caller_file)).name
    if name in LEGACY_PAGE_FILES:
        return False
    return name.startswith(("60_", "61_", "62_", "63_", "64_", "65_", "66_", "67_", "68_", "69_", "70_", "71_")) or name in EXTRA_PRODUCT_PAGES


def product_page_header(title: str, subtitle: str = "", *, eyebrow: str = "",
                        facts: "tuple[str, ...] | list[str]" = ()) -> None:
    """The landing page's hero, as a page header.

    render_page_header() puts a plain h1 and a hairline on a grey field. That
    is what made the product read as a different, rougher thing than the site a
    visitor had just come from. This is the same navy band, dot texture and
    gold accents the landing hero uses, so the two are recognisably one product.

    `facts` are short claims shown as a bulleted row — the hero's job is to say
    what the page measures, so they must be statements of method, never of
    performance.
    """
    import streamlit as st
    from html import escape

    eyebrow_html = (f'<div class="ua-phero-eyebrow">{escape(eyebrow)}</div>'
                    if eyebrow else "")
    sub_html = f'<p class="ua-phero-sub">{escape(subtitle)}</p>' if subtitle else ""
    facts_html = ("<ul class=\"ua-phero-facts\">"
                  + "".join(f"<li>{escape(str(f))}</li>" for f in facts)
                  + "</ul>") if facts else ""
    st.html(
        '<div class="ua-phero"><div class="ua-phero-in">'
        f'{eyebrow_html}<h1 class="ua-page-title">{escape(title)}</h1>'
        f'{sub_html}{facts_html}'
        '</div><div class="ua-phero-strip"></div></div>'
    )
