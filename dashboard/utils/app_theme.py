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

# Landing tokens, verbatim from landing.css so the two cannot drift by eye.
_LIGHT = {
    "bg": "#fafaf8", "surface": "#ffffff", "subtle": "#f4f6fa",
    "ink": "#13213a", "ink2": "#3a4760", "ink3": "#5b6780", "line": "#dfe5ee",
    "accent": "#1f5fae", "accent-hover": "#184c8c", "accent-ink": "#ffffff",
    "bright": "#ffc24b", "bright-ink": "#13213a",
    "navy": "#0d223b", "navy2": "#15375d", "sky": "#edf4fc", "sand": "#fbf5eb",
}
_DARK = {
    "bg": "#0b1422", "surface": "#121d2f", "subtle": "#16233a",
    "ink": "#e8edf5", "ink2": "#bdc7d8", "ink3": "#8f9bb1", "line": "#243349",
    "accent": "#8cb8f2", "accent-hover": "#a9caf5", "accent-ink": "#0b1422",
    "bright": "#ffc24b", "bright-ink": "#13213a",
    "navy": "#081628", "navy2": "#10294a", "sky": "#0f1b2d", "sand": "#171b24",
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
_RADII = {"r-sm": "8px", "r": "12px", "r-lg": "18px", "r-pill": "999px"}

_STRIP = ("linear-gradient(90deg,#3b7ddd,#7c5ce0,#e0664a,#d99018,#1a9a70,#1497b0)")


def _vars(*groups: dict) -> str:
    return "".join(f"--p-{k}:{v};" for g in groups for k, v in g.items())


_SHARED = _vars(_TYPE, _RADII) + "".join(f"--f-{k}:{v};" for k, v in FACTOR_HUES.items())

PRODUCT_CSS = f"""<style>
/* ── tokens ─────────────────────────────────────────────────────────────── */
html:not([data-ua-theme="light"]) .stApp{{{_vars(_DARK)}{_SHARED}}}
html[data-ua-theme="light"] .stApp{{{_vars(_LIGHT)}{_SHARED}}}

/* ── page ground ────────────────────────────────────────────────────────── */
html[data-ua-theme="light"] .stApp,
html:not([data-ua-theme="light"]) .stApp{{
  background:var(--p-bg)!important;
  font-family:Inter,"SF Pro Text","Segoe UI",system-ui,-apple-system,sans-serif;
  font-variant-numeric:tabular-nums;
}}
.stApp [data-testid="stMain"]{{background:transparent!important;}}
.stApp .block-container{{max-width:1140px;padding-top:58px!important;}}

/* ── top nav: the landing page's navy band ──────────────────────────────── */
html[data-ua-theme="light"] .ua-topnav,
html:not([data-ua-theme="light"]) .ua-topnav{{
  background:linear-gradient(120deg,var(--p-navy),var(--p-navy2))!important;
  border-bottom:1px solid rgba(255,255,255,.10)!important;
  backdrop-filter:none!important;-webkit-backdrop-filter:none!important;
  box-shadow:0 1px 0 rgba(13,34,59,.06)!important;height:52px!important;
}}
html[data-ua-theme="light"] .ua-topnav a.ua-tnav-item,
html:not([data-ua-theme="light"]) .ua-topnav a.ua-tnav-item,
html[data-ua-theme="light"] .ua-topnav .ua-tnav-trigger,
html:not([data-ua-theme="light"]) .ua-topnav .ua-tnav-trigger{{
  color:rgba(238,243,250,.86)!important;font-size:var(--p-t-sm)!important;font-weight:500!important;
}}
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
html[data-ua-theme="light"] .ua-tnav-brand-text,
html:not([data-ua-theme="light"]) .ua-tnav-brand-text{{color:#fff!important;font-size:var(--p-t-sm)!important;}}
.ua-tnav-brand-text em{{-webkit-text-fill-color:var(--p-bright)!important;background:none!important;}}
html[data-ua-theme="light"] .ua-tnav-upgrade,
html:not([data-ua-theme="light"]) .ua-tnav-upgrade{{
  background:var(--p-bright)!important;color:var(--p-bright-ink)!important;font-weight:700!important;
  border-color:transparent!important;
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
.ua-phero{{position:relative;overflow:hidden;border-radius:var(--p-r-lg);
  margin:4px 0 26px;color:#eef3fa;
  background:
    radial-gradient(780px 420px at 88% 20%,rgba(59,125,221,.38),transparent 62%),
    radial-gradient(600px 380px at 2% 110%,rgba(124,92,224,.30),transparent 62%),
    linear-gradient(160deg,var(--p-navy) 0%,var(--p-navy2) 100%);}}
.ua-phero::before{{content:"";position:absolute;inset:0;pointer-events:none;
  background-image:radial-gradient(rgba(255,255,255,.09) 1px,transparent 1px);
  background-size:22px 22px;
  -webkit-mask-image:linear-gradient(180deg,rgba(0,0,0,.9),transparent 85%);
  mask-image:linear-gradient(180deg,rgba(0,0,0,.9),transparent 85%);}}
.ua-phero-in{{position:relative;padding:30px 34px 32px;}}
.ua-phero-eyebrow{{font-size:var(--p-t-xs)!important;font-weight:700;letter-spacing:.06em;
  text-transform:uppercase;color:var(--p-bright)!important;margin-bottom:9px;}}
.stApp .ua-phero h1{{font-size:var(--p-t-xl)!important;line-height:1.08!important;
  letter-spacing:-0.03em!important;font-weight:750!important;color:#fff!important;margin:0!important;
  padding:0!important;}}
.stApp .ua-phero .ua-phero-sub{{font-size:var(--p-t-md)!important;line-height:1.55!important;
  color:rgba(238,243,250,.86)!important;margin-top:11px!important;max-width:64ch!important;}}
.stApp .ua-phero .ua-phero-facts{{list-style:none;padding:0;margin:18px 0 0!important;
  display:flex;flex-wrap:wrap;gap:7px 20px;}}
.stApp .ua-phero .ua-phero-facts li{{display:flex;align-items:center;gap:7px;line-height:1.45!important;
  font-size:var(--p-t-sm)!important;color:rgba(238,243,250,.80)!important;max-width:none!important;}}
.ua-phero-facts li::before{{content:"";width:7px;height:7px;border-radius:50%;
  background:var(--p-bright);flex-shrink:0;}}
.ua-phero-strip{{position:relative;height:5px;background:{_STRIP};}}
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

/* ── buttons ────────────────────────────────────────────────────────────── */
html[data-ua-theme="light"] .stApp button[data-testid="stBaseButton-primary"],
html:not([data-ua-theme="light"]) .stApp button[data-testid="stBaseButton-primary"]{{
  background:var(--p-accent)!important;border:1px solid var(--p-accent)!important;
  color:var(--p-accent-ink)!important;box-shadow:none!important;border-radius:var(--p-r-sm)!important;
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
  box-shadow:none!important;border-radius:var(--p-r-sm)!important;min-height:44px!important;}}
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
  color:var(--p-ink)!important;border-radius:var(--p-r-sm)!important;min-height:44px!important;
  font-weight:600!important;font-size:var(--p-t-base)!important;box-shadow:none!important;}}
html[data-ua-theme="light"] .stApp a[data-testid="stBaseLinkButton-secondary"]:hover,
html:not([data-ua-theme="light"]) .stApp a[data-testid="stBaseLinkButton-secondary"]:hover{{
  border-color:var(--p-accent)!important;background:var(--p-sky)!important;}}
html[data-ua-theme="light"] .stApp a[data-testid="stBaseLinkButton-primary"],
html:not([data-ua-theme="light"]) .stApp a[data-testid="stBaseLinkButton-primary"]{{
  background:var(--p-accent)!important;border:1px solid var(--p-accent)!important;
  color:var(--p-accent-ink)!important;border-radius:var(--p-r-sm)!important;min-height:44px!important;
  font-weight:650!important;font-size:var(--p-t-base)!important;box-shadow:none!important;}}
.stApp :focus-visible{{outline:3px solid var(--p-bright)!important;outline-offset:2px!important;}}

/* ── inputs ─────────────────────────────────────────────────────────────── */
.stApp [data-testid="stTextArea"] textarea,.stApp [data-testid="stTextInput"] input{{
  background:var(--p-surface)!important;border:1px solid var(--p-line)!important;
  color:var(--p-ink)!important;border-radius:var(--p-r)!important;font-size:var(--p-t-base)!important;}}
.stApp [data-testid="stTextArea"] textarea:focus,.stApp [data-testid="stTextInput"] input:focus{{
  border-color:var(--p-accent)!important;box-shadow:0 0 0 3px rgba(31,95,174,.14)!important;}}
.stApp [data-testid="stFileUploaderDropzone"]{{background:var(--p-subtle)!important;
  border:1px dashed var(--p-line)!important;border-radius:var(--p-r)!important;}}
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

/* ── the account row reads as part of the nav, not a stray control ──────── */
html[data-ua-theme="light"] .st-key-ua_account_row button[data-testid="stBaseButton-secondary"],
html:not([data-ua-theme="light"]) .st-key-ua_account_row button[data-testid="stBaseButton-secondary"]{{
  min-height:34px!important;border-radius:var(--p-r-sm)!important;font-size:var(--p-t-sm)!important;}}
</style>"""


def is_product_page(caller_file: str | None) -> bool:
    """True for the pages built after the redesign, which carry this theme."""
    from utils.legacy_pages import LEGACY_PAGE_FILES

    if not caller_file:
        return False
    name = Path(str(caller_file)).name
    return (name.startswith(("60_", "61_", "62_", "63_", "64_", "65_"))
            and name not in LEGACY_PAGE_FILES)


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
