"""
Shared header + CSS injected at the top of every page.
Call render_header() as the very first Streamlit call after st.set_page_config().
"""

from html import escape as html_escape
import re
from urllib.parse import urlencode

import streamlit as st

from utils.config import TICKERS, SIGNAL_COUNT


def _theme_switch_href(target: str, query_values: dict[str, list[str]]) -> str:
    """Build an accessible theme link without dropping functional page state."""
    pairs: list[tuple[str, str]] = []
    for key, values in (query_values or {}).items():
        if str(key) == "theme":
            continue
        pairs.extend((str(key), str(value)) for value in (values or []))
    pairs.append(("theme", "light" if target == "light" else "dark"))
    return "?" + urlencode(pairs)


def _section_slug(label: str) -> str:
    """Return a stable, URL-safe identifier for a visible section label."""
    return re.sub(r"[^a-z0-9]+", "-", str(label).strip().lower()).strip("-")


def _sync_section_query(
    *,
    widget_key: str,
    default_section: str,
    slugs_by_section: dict[str, str],
) -> None:
    """Keep the selected rail section shareable without dropping other state."""
    selected = str(st.session_state.get(widget_key) or "")
    requested_slug = (
        None
        if selected == default_section
        else slugs_by_section.get(selected)
    )
    current_slug = str(st.query_params.get("section") or "").strip().lower()

    if requested_slug and current_slug != requested_slug:
        st.query_params["section"] = requested_slug
    elif not requested_slug and current_slug:
        del st.query_params["section"]


# ── Modern Dark Design System CSS ────────────────────────────────────────────
_CSS = """
<style>
/* preconnect hints injected via JS below for max speed */
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600;700;800&display=swap&font-display=swap');

/* ── Design tokens ───────────────────────────────────────────────────────── */
:root {
    --ua-bg:         #0B0D12;
    --ua-bg-card:    #12151E;
    --ua-bg-raised:  #1A1E2C;
    --ua-green:      #00D566;
    --ua-cyan:       #00C8E0;
    --ua-purple:     #7C3AED;
    --ua-red:        #FF4444;
    --ua-amber:      #F59E0B;
    --ua-text-hi:    #E7EAF0;
    --ua-text-mid:   #C5CBD5;
    --ua-text-lo:    #A7B0BF;
    --ua-text-cap:   #8D97A8;
    --ua-border:     rgba(255,255,255,0.07);
    --ua-border-lo:  rgba(255,255,255,0.04);
    --ua-grid:       rgba(255,255,255,0.04);
    --ua-radius:     12px;
    --ua-radius-sm:  8px;
    --ua-radius-lg:  16px;
    --ua-shadow:     0 8px 32px rgba(0,0,0,0.55);
    --ua-shadow-lg:  0 16px 64px rgba(0,0,0,0.65);
    --ua-glow-green: 0 0 28px rgba(0,213,102,0.18);
    --ua-glow-red:   0 0 28px rgba(255,68,68,0.18);
    --ua-glow-cyan:  0 0 28px rgba(0,200,224,0.14);

    /* ── Redesign 2026-07: royal palette + editorial serif + chart tokens.
       Additive — existing surfaces keep their tokens; new/migrated surfaces
       use these. See memory redesign_2026_07. */
    --ua-serif:      'Fraunces', Georgia, 'Times New Roman', serif;
    --ua-royal:      #6470F5;
    --ua-royal-2:    #8B7BF7;
    --ua-royal-deep: #3B45C9;
    --ua-royal-soft: rgba(100,112,245,0.14);
    --ua-brand-alpha-1: #7975EE;
    --ua-brand-alpha-2: #9A82E2;
    --ua-brand-alpha-3: #C19EC8;
    --ua-gold:       #D4B26A;
    --ua-text:       #ECEEF9;
    --ua-muted:      #9AA0BE;
    --ua-faint:      #646A88;
    --ua-line-2:     rgba(255,255,255,0.16);
    --ua-pos:        #48BC90;
    --ua-neg:        #E27767;
    --ua-neutral:    #7C84A8;

    /* Migration tokens (hex→var, slice 1). Dark values are EXACTLY the literals
       they replace, so dark mode is byte-identical; light values below make the
       theme flip work. See memory redesign_2026_07. */
    --ua-ink:        #E8EEFF;   /* dominant bright body text */
    --ua-ink-mut:    #8892AA;   /* dominant muted text */
    --ua-surface:    rgba(18,21,30,0.8);  /* dominant translucent card bg */

    /* Slice 2 — same exact-dark-value method. */
    --ua-ink-label:  #6B7FBF;   /* small-caps labels / captions */
    --ua-ink-soft:   #B8C0D4;   /* secondary body */
    --ua-ink-dim:    #747E94;   /* dimmest WCAG-legible text */
    --ua-ink-dim-2:  #707A91;   /* de-emphasised meta, still 4.5:1 on bg */
    --ua-hair:       rgba(255,255,255,0.08);  /* hairline borders */
    --ua-hair-2:     rgba(255,255,255,0.06);
    --ua-hair-3:     rgba(255,255,255,0.05);

    /* Slice 4 — RGB TRIPLES, not colors. Tinted fills like rgba(0,213,102,0.08)
       carry a per-use alpha, so a plain color token can't express them. CSS var
       substitution is textual, so rgba(var(--ua-green-rgb),0.08) expands to a
       valid rgba() while letting the BASE color re-theme and the alpha stay put. */
    --ua-green-rgb:  0,213,102;
    --ua-red-rgb:    255,68,68;
    --ua-purple-rgb: 124,58,237;
    --ua-cyan-rgb:   0,200,224;
    --ua-royal-rgb:  100,112,245;
    --ua-label-rgb:  107,127,191;
    --ua-card-rgb:   18,21,30;
    --ua-onbg-rgb:   255,255,255;  /* anything layered ON the background */

    /* Slice 6 — chrome surfaces found still dark in the live light beta:
       the ticker tape shell, and the panel fill/border used by page-title
       cards in utils/command_center, model_validation, portfolio_xray,
       score_explainer and what_changed. */
    --ua-shell-rgb:  12,14,20;   /* sticky tape / nav shell */
    --ua-panel:      #0F1320;    /* raised panel fill */
    --ua-panel-line: #232942;    /* raised panel border */

    /* Slice 7 — drop shadows. These need MORE than a colour swap: a 0.6-alpha
       black that reads as depth on a dark surface reads as dirt on a light one,
       so light needs a different hue AND a much lower alpha. The RGB-triple
       trick can't vary alpha, so the alpha is multiplied by a scalar token —
       calc() is valid in the alpha slot. Dark keeps k=1, so every existing
       shadow is byte-identical; light scales them all down uniformly, which
       preserves their relative weighting instead of flattening them. */
    --ua-shadow-rgb: 0,0,0;
    --ua-shadow-k:   1;
}

/* Light mode: overrides both the legacy tokens and the redesign tokens. Applied
   when <html data-ua-theme="light">. Nothing sets it yet (dark stays default);
   surfaces migrate to variables progressively so the flip stays clean. */
html[data-ua-theme="light"] {
    --ua-bg:         #F6F5FB;
    --ua-bg-card:    #FFFFFF;
    --ua-bg-raised:  #FBFAF7;
    --ua-text-hi:    #161A2E;
    --ua-text-mid:   #2C3149;
    --ua-text-lo:    #4A5069;
    --ua-text-cap:   #5E657C;
    --ua-border:     rgba(20,22,44,0.10);
    --ua-border-lo:  rgba(20,22,44,0.05);
    --ua-grid:       rgba(20,22,44,0.09);
    --ua-royal:      #4048C6;
    --ua-royal-2:    #5A46C0;
    --ua-royal-deep: #333BA8;
    --ua-royal-soft: rgba(64,72,198,0.10);
    --ua-brand-alpha-1: #5048BE;
    --ua-brand-alpha-2: #7054B8;
    --ua-brand-alpha-3: #86598D;
    --ua-gold:       #9C7A2C;
    --ua-text:       #161A2E;
    --ua-muted:      #5A6079;
    --ua-faint:      #62697E;
    --ua-line-2:     rgba(20,22,44,0.17);
    --ua-pos:        #087451;
    --ua-neg:        #A5292F;
    --ua-neutral:    #565D75;
    --ua-ink:        #161A2E;   /* light: dark ink on light bg */
    --ua-ink-mut:    #5A6079;
    --ua-surface:    #FFFFFF;
    --ua-ink-label:  #565177;
    --ua-ink-soft:   #3A4059;
    --ua-ink-dim:    #5F657A;
    --ua-ink-dim-2:  #62687D;
    /* Hairlines invert: light-on-dark becomes dark-on-light, or they vanish. */
    --ua-hair:       rgba(20,22,44,0.11);
    --ua-hair-2:     rgba(20,22,44,0.08);
    --ua-hair-3:     rgba(20,22,44,0.06);
    /* Semantic data colors need darker variants to stay legible on white. */
    --ua-green:      #087443;
    --ua-cyan:       #076879;
    --ua-purple:     #5724B3;
    --ua-red:        #B01F2A;
    --ua-amber:      #8C3C05;
    /* Triples must match the hexes above, or a tint and its solid disagree. */
    --ua-green-rgb:  8,116,67;
    --ua-red-rgb:    176,31,42;
    --ua-purple-rgb: 87,36,179;
    --ua-cyan-rgb:   7,104,121;
    --ua-royal-rgb:  64,72,198;
    --ua-label-rgb:  94,90,140;
    --ua-card-rgb:   255,255,255;
    --ua-onbg-rgb:   20,22,44;
    /* Dark-mode shadows are near-black and heavy; on a light surface that reads
       as grime, so light gets a softer, cooler shadow. */
    --ua-shadow:     0 6px 20px rgba(20,22,44,0.09);
    --ua-shadow-lg:  0 14px 44px rgba(20,22,44,0.13);
    --ua-shell-rgb:  255,255,255;
    --ua-panel:      #FFFFFF;
    --ua-panel-line: rgba(20,22,44,0.12);
    --ua-shadow-rgb: 20,22,44;   /* cool navy, not black */
    --ua-shadow-k:   0.3;        /* scale every shadow down together */
}

/* ── Light mode: app chrome ───────────────────────────────────────────────
   The token block above only recolors things that USE the tokens. Streamlit
   paints its own shell from config.toml (backgroundColor) and this file
   pins it again with !important further down, so without these overrides a
   light-mode user gets light cards floating on a black page. Selectors are
   prefixed with html[data-ua-theme="light"], which adds specificity, and they
   are declared here — before those rules — deliberately: equal-specificity
   !important ties are won by the LATER rule, so these must out-specify rather
   than out-order. Dark mode never matches any of this. */
html[data-ua-theme="light"] [data-testid="stAppViewContainer"],
html[data-ua-theme="light"] [data-testid="stAppViewContainer"] > .main,
html[data-ua-theme="light"] .stApp,
html[data-ua-theme="light"] .main,
html[data-ua-theme="light"] body {
    background: var(--ua-bg) !important;
    background-image: none !important;
    color: var(--ua-ink);
}
html[data-ua-theme="light"] section[data-testid="stSidebar"] {
    background: var(--ua-bg-card) !important;
    border-right: 1px solid var(--ua-hair) !important;
}
html[data-ua-theme="light"] header[data-testid="stHeader"] {
    background: transparent !important;
}
/* Top nav sits on the page background, so it has to follow it.
   NOTE the element is nav.ua-topnav — .ua-tnav-* are its CHILDREN. An earlier
   pass only targeted the children, which is why the bar itself stayed black in
   the live light beta. */
html[data-ua-theme="light"] .ua-topnav,
html[data-ua-theme="light"] .ua-tnav,
html[data-ua-theme="light"] .ua-tnav-menu {
    background: rgba(255,255,255,0.97) !important;
    border-color: var(--ua-hair) !important;
}
html[data-ua-theme="light"] .ua-tnav-brand-text { color: var(--ua-ink) !important; }
/* Identity chip / sign-in are Streamlit popovers, not our markup. */
html[data-ua-theme="light"] [data-testid="stPopover"] button,
html[data-ua-theme="light"] [data-testid="stPopoverButton"] {
    background: var(--ua-bg-card) !important;
    color: var(--ua-ink) !important;
    border: 1px solid var(--ua-hair) !important;
}
html[data-ua-theme="light"] [data-testid="stPopover"] button p,
html[data-ua-theme="light"] [data-testid="stPopover"] button span {
    color: var(--ua-ink) !important;
}
html[data-ua-theme="light"] [data-baseweb="popover"] [data-baseweb="menu"] {
    background: var(--ua-bg-card) !important;
}
/* Nav SUB-PAGES (the hover dropdowns) — .ua-tnav-drop, not .ua-tnav-menu.
   These stayed near-black over a light page until measured. */
html[data-ua-theme="light"] .ua-tnav-drop {
    background: #FFFFFF !important;
    border: 1px solid var(--ua-hair) !important;
    box-shadow: var(--ua-shadow-lg) !important;
}
html[data-ua-theme="light"] .ua-tnav-drop::before { background: #FFFFFF !important; }
html[data-ua-theme="light"] .ua-tnav-drop a {
    color: var(--ua-ink-mut) !important;
    background: rgba(var(--ua-royal-rgb),0.025);
    border-color: rgba(var(--ua-royal-rgb),0.12);
}
html[data-ua-theme="light"] .ua-tnav-drop a:hover {
    background: rgba(var(--ua-royal-rgb),0.08) !important;
    color: var(--ua-royal) !important;
    border-color: rgba(var(--ua-royal-rgb),0.38) !important;
}
html[data-ua-theme="light"] .ua-tnav-drop a.pro-link {
    color: #6D4FC2 !important;
    background: rgba(var(--ua-purple-rgb),0.07);
    border-color: rgba(var(--ua-purple-rgb),0.24);
}
html[data-ua-theme="light"] .ua-tnav-drop a.pro-link:hover {
    color: #5736AD !important;
    background: rgba(var(--ua-purple-rgb),0.12) !important;
    border-color: rgba(var(--ua-purple-rgb),0.44) !important;
}
html[data-ua-theme="light"] .ua-tnav-drop a.pro-link::after {
    color: #4B2A91 !important;
    background: rgba(var(--ua-purple-rgb),0.14) !important;
    border-color: rgba(var(--ua-purple-rgb),0.42) !important;
}
html[data-ua-theme="light"] .ua-tnav-drop-rule { background: var(--ua-hair) !important; }
html[data-ua-theme="light"] .ua-tnav-drop-label { color: var(--ua-ink-dim) !important; }

/* Notification panel + its hover state, in BOTH themes (hover was only ever
   defined for dark, so on light it flashed a dark row). */
html[data-ua-theme="light"] .ua-notification-item {
    background: var(--ua-bg-card) !important;
    border-color: var(--ua-hair) !important;
}
html[data-ua-theme="light"] .ua-notification-item:hover {
    background: rgba(var(--ua-royal-rgb),0.06) !important;
    border-color: rgba(var(--ua-royal-rgb),0.28) !important;
}
html[data-ua-theme="light"] .ua-notification-title,
html[data-ua-theme="light"] .ua-notification-heading { color: var(--ua-ink) !important; }
html[data-ua-theme="light"] .ua-notification-copy { color: var(--ua-ink-mut) !important; }
html[data-ua-theme="light"] .ua-notification-kicker { color: var(--ua-ink-label) !important; }

/* Streamlit tabs: the tab strip kept a dark fill, so dark-on-dark labels
   measured a 1.0 contrast ratio (invisible). */
html[data-ua-theme="light"] .stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid var(--ua-hair) !important;
}
html[data-ua-theme="light"] .stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--ua-ink-mut) !important;
}
html[data-ua-theme="light"] .stTabs [aria-selected="true"] {
    color: var(--ua-ink) !important;
    border-bottom-color: var(--ua-royal) !important;
}
html[data-ua-theme="light"] .stTabs [data-baseweb="tab-highlight"] {
    background: var(--ua-royal) !important;
}

/* ── Light mode: inline text-colour remap, part 2 ────────────────────────
   Complements the existing remap above (that block covers the bright brand
   accents). These 16 are the LIGHT GREYS used as text on a dark surface —
   invisible once the background flips. They live in quoted Python literals
   that the migration guard skips on purpose, because sibling variables get
   parsed with int(hex[1:3],16) or handed to plotly, where var() would crash.
   Matching the inline style instead touches no Python at all.
   Anchored on ^color:/;color: so background:, background-color: and
   border-color: are provably NOT matched (verified in-browser). */
html[data-ua-theme="light"] [style*=";color: #C3CBE0"],
html[data-ua-theme="light"] [style*=";color: #c3cbe0"],
html[data-ua-theme="light"] [style*=";color:#C3CBE0"],
html[data-ua-theme="light"] [style*=";color:#c3cbe0"],
html[data-ua-theme="light"] [style^="color: #C3CBE0"],
html[data-ua-theme="light"] [style^="color: #c3cbe0"],
html[data-ua-theme="light"] [style^="color:#C3CBE0"],
html[data-ua-theme="light"] [style^="color:#c3cbe0"] {
    color: #333A52 !important;
}
html[data-ua-theme="light"] [style*=";color: #E7ECF5"],
html[data-ua-theme="light"] [style*=";color: #e7ecf5"],
html[data-ua-theme="light"] [style*=";color:#E7ECF5"],
html[data-ua-theme="light"] [style*=";color:#e7ecf5"],
html[data-ua-theme="light"] [style^="color: #E7ECF5"],
html[data-ua-theme="light"] [style^="color: #e7ecf5"],
html[data-ua-theme="light"] [style^="color:#E7ECF5"],
html[data-ua-theme="light"] [style^="color:#e7ecf5"] {
    color: #1D2136 !important;
}
html[data-ua-theme="light"] [style*=";color: #EDF1F7"],
html[data-ua-theme="light"] [style*=";color: #edf1f7"],
html[data-ua-theme="light"] [style*=";color:#EDF1F7"],
html[data-ua-theme="light"] [style*=";color:#edf1f7"],
html[data-ua-theme="light"] [style^="color: #EDF1F7"],
html[data-ua-theme="light"] [style^="color: #edf1f7"],
html[data-ua-theme="light"] [style^="color:#EDF1F7"],
html[data-ua-theme="light"] [style^="color:#edf1f7"] {
    color: #1D2136 !important;
}
html[data-ua-theme="light"] [style*=";color: #E4E9F2"],
html[data-ua-theme="light"] [style*=";color: #e4e9f2"],
html[data-ua-theme="light"] [style*=";color:#E4E9F2"],
html[data-ua-theme="light"] [style*=";color:#e4e9f2"],
html[data-ua-theme="light"] [style^="color: #E4E9F2"],
html[data-ua-theme="light"] [style^="color: #e4e9f2"],
html[data-ua-theme="light"] [style^="color:#E4E9F2"],
html[data-ua-theme="light"] [style^="color:#e4e9f2"] {
    color: #161A2E !important;
}
html[data-ua-theme="light"] [style*=";color: #A7B0BF"],
html[data-ua-theme="light"] [style*=";color: #a7b0bf"],
html[data-ua-theme="light"] [style*=";color:#A7B0BF"],
html[data-ua-theme="light"] [style*=";color:#a7b0bf"],
html[data-ua-theme="light"] [style^="color: #A7B0BF"],
html[data-ua-theme="light"] [style^="color: #a7b0bf"],
html[data-ua-theme="light"] [style^="color:#A7B0BF"],
html[data-ua-theme="light"] [style^="color:#a7b0bf"] {
    color: #3A4059 !important;
}
html[data-ua-theme="light"] [style*=";color: #C8D0E4"],
html[data-ua-theme="light"] [style*=";color: #c8d0e4"],
html[data-ua-theme="light"] [style*=";color:#C8D0E4"],
html[data-ua-theme="light"] [style*=";color:#c8d0e4"],
html[data-ua-theme="light"] [style^="color: #C8D0E4"],
html[data-ua-theme="light"] [style^="color: #c8d0e4"],
html[data-ua-theme="light"] [style^="color:#C8D0E4"],
html[data-ua-theme="light"] [style^="color:#c8d0e4"] {
    color: #2C3149 !important;
}
html[data-ua-theme="light"] [style*=";color: #8892B0"],
html[data-ua-theme="light"] [style*=";color: #8892b0"],
html[data-ua-theme="light"] [style*=";color:#8892B0"],
html[data-ua-theme="light"] [style*=";color:#8892b0"],
html[data-ua-theme="light"] [style^="color: #8892B0"],
html[data-ua-theme="light"] [style^="color: #8892b0"],
html[data-ua-theme="light"] [style^="color:#8892B0"],
html[data-ua-theme="light"] [style^="color:#8892b0"] {
    color: #5A6079 !important;
}
html[data-ua-theme="light"] [style*=";color: #8F9AAD"],
html[data-ua-theme="light"] [style*=";color: #8f9aad"],
html[data-ua-theme="light"] [style*=";color:#8F9AAD"],
html[data-ua-theme="light"] [style*=";color:#8f9aad"],
html[data-ua-theme="light"] [style^="color: #8F9AAD"],
html[data-ua-theme="light"] [style^="color: #8f9aad"],
html[data-ua-theme="light"] [style^="color:#8F9AAD"],
html[data-ua-theme="light"] [style^="color:#8f9aad"] {
    color: #4A5069 !important;
}
html[data-ua-theme="light"] [style*=";color: #8D97A8"],
html[data-ua-theme="light"] [style*=";color: #8d97a8"],
html[data-ua-theme="light"] [style*=";color:#8D97A8"],
html[data-ua-theme="light"] [style*=";color:#8d97a8"],
html[data-ua-theme="light"] [style^="color: #8D97A8"],
html[data-ua-theme="light"] [style^="color: #8d97a8"],
html[data-ua-theme="light"] [style^="color:#8D97A8"],
html[data-ua-theme="light"] [style^="color:#8d97a8"] {
    color: #4A5069 !important;
}
html[data-ua-theme="light"] [style*=";color: #9AA4BC"],
html[data-ua-theme="light"] [style*=";color: #9aa4bc"],
html[data-ua-theme="light"] [style*=";color:#9AA4BC"],
html[data-ua-theme="light"] [style*=";color:#9aa4bc"],
html[data-ua-theme="light"] [style^="color: #9AA4BC"],
html[data-ua-theme="light"] [style^="color: #9aa4bc"],
html[data-ua-theme="light"] [style^="color:#9AA4BC"],
html[data-ua-theme="light"] [style^="color:#9aa4bc"] {
    color: #454B63 !important;
}
html[data-ua-theme="light"] [style*=";color: #6B7A95"],
html[data-ua-theme="light"] [style*=";color: #6b7a95"],
html[data-ua-theme="light"] [style*=";color:#6B7A95"],
html[data-ua-theme="light"] [style*=";color:#6b7a95"],
html[data-ua-theme="light"] [style^="color: #6B7A95"],
html[data-ua-theme="light"] [style^="color: #6b7a95"],
html[data-ua-theme="light"] [style^="color:#6B7A95"],
html[data-ua-theme="light"] [style^="color:#6b7a95"] {
    color: #4F5570 !important;
}
html[data-ua-theme="light"] [style*=";color: #C4B5FD"],
html[data-ua-theme="light"] [style*=";color: #c4b5fd"],
html[data-ua-theme="light"] [style*=";color:#C4B5FD"],
html[data-ua-theme="light"] [style*=";color:#c4b5fd"],
html[data-ua-theme="light"] [style^="color: #C4B5FD"],
html[data-ua-theme="light"] [style^="color: #c4b5fd"],
html[data-ua-theme="light"] [style^="color:#C4B5FD"],
html[data-ua-theme="light"] [style^="color:#c4b5fd"] {
    color: #4B2A91 !important;
}
html[data-ua-theme="light"] [style*=";color: #FF8888"],
html[data-ua-theme="light"] [style*=";color: #ff8888"],
html[data-ua-theme="light"] [style*=";color:#FF8888"],
html[data-ua-theme="light"] [style*=";color:#ff8888"],
html[data-ua-theme="light"] [style^="color: #FF8888"],
html[data-ua-theme="light"] [style^="color: #ff8888"],
html[data-ua-theme="light"] [style^="color:#FF8888"],
html[data-ua-theme="light"] [style^="color:#ff8888"] {
    color: #C0392B !important;
}
html[data-ua-theme="light"] [style*=";color: #FF8C42"],
html[data-ua-theme="light"] [style*=";color: #ff8c42"],
html[data-ua-theme="light"] [style*=";color:#FF8C42"],
html[data-ua-theme="light"] [style*=";color:#ff8c42"],
html[data-ua-theme="light"] [style^="color: #FF8C42"],
html[data-ua-theme="light"] [style^="color: #ff8c42"],
html[data-ua-theme="light"] [style^="color:#FF8C42"],
html[data-ua-theme="light"] [style^="color:#ff8c42"] {
    color: #B4530A !important;
}
html[data-ua-theme="light"] [style*=";color: #7BDE6B"],
html[data-ua-theme="light"] [style*=";color: #7bde6b"],
html[data-ua-theme="light"] [style*=";color:#7BDE6B"],
html[data-ua-theme="light"] [style*=";color:#7bde6b"],
html[data-ua-theme="light"] [style^="color: #7BDE6B"],
html[data-ua-theme="light"] [style^="color: #7bde6b"],
html[data-ua-theme="light"] [style^="color:#7BDE6B"],
html[data-ua-theme="light"] [style^="color:#7bde6b"] {
    color: #3E8E2F !important;
}

/* ── Theme toggle ─────────────────────────────────────────────────────────
   Deliberately a real <a href>, not a JS button: it works with keyboard and
   screen readers for free, survives Streamlit reruns, and needs no script
   (st.markdown does not execute one anyway). Both directions are always in the
   DOM and CSS reveals the relevant one, so the server never has to know the
   current theme — which it can't, since the theme lives in localStorage. */
.ua-theme-toggle {
    display: inline-flex; align-items: center; justify-content: center;
    gap: 5px; height: 28px; padding: 0 10px; margin-left: 8px;
    border-radius: 7px; flex-shrink: 0;
    border: 1px solid var(--ua-hair);
    background: rgba(var(--ua-onbg-rgb),0.04);
    color: var(--ua-ink-mut);
    font-family: 'Inter', sans-serif; font-size: 0.68rem; font-weight: 600;
    letter-spacing: 0.04em; text-decoration: none !important; white-space: nowrap;
    transition: color .12s ease, background .12s ease, border-color .12s ease;
}
.ua-theme-toggle:hover {
    color: var(--ua-ink);
    background: rgba(var(--ua-royal-rgb),0.10);
    border-color: rgba(var(--ua-royal-rgb),0.35);
}
.ua-theme-toggle:focus-visible {
    outline: 2px solid var(--ua-royal) !important;
    outline-offset: 2px !important;
}
.ua-theme-toggle .ua-tt-ico { font-size: 0.82rem; line-height: 1; }
/* Show the action that is available: in dark you can go light, and vice versa. */
.ua-theme-toggle[data-to="light"] { display: inline-flex; }
.ua-theme-toggle[data-to="dark"]  { display: none; }
html[data-ua-theme="light"] .ua-theme-toggle[data-to="light"] { display: none; }
html[data-ua-theme="light"] .ua-theme-toggle[data-to="dark"]  { display: inline-flex; }
html[data-ua-theme="light"] a.ua-tnav-item,
html[data-ua-theme="light"] .ua-tnav-trigger { color: var(--ua-ink-mut); }
html[data-ua-theme="light"] a.ua-tnav-item:hover,
html[data-ua-theme="light"] .ua-tnav-trigger:hover {
    color: var(--ua-ink);
    background: rgba(var(--ua-onbg-rgb),0.05);
}
/* Streamlit widgets that hardcode a dark field. */
html[data-ua-theme="light"] .stTextInput > div > div > input,
html[data-ua-theme="light"] .stSelectbox > div > div,
html[data-ua-theme="light"] .stNumberInput > div > div > input,
html[data-ua-theme="light"] .stTextArea textarea {
    background: var(--ua-bg-card) !important;
    color: var(--ua-ink) !important;
    border-color: var(--ua-hair) !important;
}
html[data-ua-theme="light"] .stButton > button {
    background: var(--ua-bg-card) !important;
    color: var(--ua-ink-soft) !important;
    border-color: var(--ua-hair) !important;
}
/* Current Streamlit quick-pick and dynamically generated buttons are not
   always nested under .stButton (tooltip wrappers can sit between them).
   Target the stable button contract as well, never generated emotion classes. */
html[data-ua-theme="light"] button[data-testid="stBaseButton-secondary"] {
    background: var(--ua-bg-card) !important;
    color: var(--ua-ink-soft) !important;
    border: 1px solid var(--ua-hair) !important;
    box-shadow: var(--ua-shadow) !important;
}
html[data-ua-theme="light"] button[data-testid="stBaseButton-secondary"]:hover {
    background: rgba(var(--ua-royal-rgb),0.06) !important;
    color: var(--ua-ink) !important;
    border-color: rgba(var(--ua-royal-rgb),0.30) !important;
}
html[data-ua-theme="light"] .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #4048C6, #3B3FA8) !important;
    color: #FFFFFF !important;
}

/* Button labels are paragraphs in current Streamlit builds. The generic
   typography rule must not recolor a button's label independently of its
   surface, especially white labels on royal form-submit actions. */
.stButton > button p,
.stDownloadButton > button p,
.stFormSubmitButton > button p,
.stLinkButton > a p,
button[data-testid^="stBaseButton"] p {
    color: inherit !important;
}

/* Plotly is rendered client-side after Python has already built the figure, so
   it cannot read the browser-only localStorage theme. Re-theme presentation
   chrome in CSS while leaving trace/data colors and figure logic untouched. */
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] .main-svg {
    background: transparent !important;
}
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] .plot-container .bg {
    fill: var(--ua-bg-card) !important;
}
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] :is(
    .xtick text, .ytick text, .gtitle, .legendtext, .annotation-text,
    .cbtitle text, .colorbar text
) {
    fill: var(--ua-ink-mut) !important;
    color: var(--ua-ink-mut) !important;
}
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] :is(
    .xgrid, .ygrid, .gridlayer path, .zerolinelayer path
) {
    stroke: var(--ua-grid) !important;
}
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] :is(
    .xlines-above, .ylines-above, .xlines-below, .ylines-below
) {
    stroke: var(--ua-hair) !important;
}
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] .modebar {
    background: rgba(var(--ua-card-rgb),0.94) !important;
    border: 1px solid var(--ua-hair) !important;
}
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] .modebar-btn path {
    fill: var(--ua-ink-mut) !important;
}
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] :is(
    .barlayer .bartext, .scatterlayer .textpoint text,
    .pielayer .slicetext, .treemaplayer .slicetext,
    .sunburstlayer .slicetext, .funnellayer .bartext
) {
    fill: var(--ua-ink) !important;
}
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] :is(
    .hoverlayer .hovertext path, .hoverlayer .axistext path
) {
    fill: var(--ua-bg-raised) !important;
    stroke: var(--ua-hair) !important;
}
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] :is(
    .hoverlayer .hovertext text, .hoverlayer .axistext text
) {
    fill: var(--ua-ink) !important;
}
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] .rangeselector .button rect {
    fill: var(--ua-bg-raised) !important;
    stroke: var(--ua-hair) !important;
}
html[data-ua-theme="light"] [data-testid="stPlotlyChart"] .rangeselector .button text {
    fill: var(--ua-ink-mut) !important;
}

/* ── Guided workflow cards ───────────────────────────────────────────────── */
.ua-guide-shell {
    position: relative;
    overflow: hidden;
    margin: 6px 0 18px;
    padding: 20px;
    border: 1px solid rgba(var(--ua-cyan-rgb),0.18);
    border-radius: 14px;
    background:
        radial-gradient(circle at 92% -10%, rgba(var(--ua-purple-rgb),0.13), transparent 34%),
        linear-gradient(145deg, rgba(15,22,31,0.98), rgba(10,15,23,0.96));
    box-shadow: 0 14px 36px rgba(var(--ua-shadow-rgb),calc(0.24*var(--ua-shadow-k))), inset 0 1px 0 rgba(var(--ua-onbg-rgb),0.025);
    font-family: Inter, sans-serif;
}
.ua-guide-shell::before {
    content: "";
    position: absolute;
    inset: 0 0 auto 0;
    height: 2px;
    background: linear-gradient(90deg, var(--ua-cyan) 0%, var(--ua-purple) 58%, transparent 100%);
    opacity: 0.9;
}
.ua-guide-kicker {
    margin-bottom: 6px;
    color: #72D6E2;
    font-size: 0.58rem;
    font-weight: 800;
    letter-spacing: 0.17em;
    text-transform: uppercase;
}
.ua-guide-title {
    color: var(--ua-text-hi);
    font-size: 1.02rem;
    font-weight: 760;
    letter-spacing: -0.015em;
    line-height: 1.3;
}
.ua-guide-intro {
    max-width: 760px;
    margin-top: 5px;
    color: var(--ua-text-lo);
    font-size: 0.76rem;
    line-height: 1.55;
}
.ua-guide-grid {
    display: grid;
    grid-template-columns: repeat(var(--ua-guide-cols, 3), minmax(0, 1fr));
    gap: 10px;
    margin-top: 16px;
}
.ua-guide-step {
    min-width: 0;
    padding: 13px 14px 14px;
    border: 1px solid rgba(var(--ua-onbg-rgb),0.065);
    border-radius: 10px;
    background: rgba(var(--ua-card-rgb),0.72);
    transition: transform 140ms ease, border-color 140ms ease, background 140ms ease;
}
.ua-guide-step:hover {
    transform: translateY(-1px);
    border-color: rgba(var(--ua-cyan-rgb),0.20);
    background: rgba(22,27,39,0.88);
}
.ua-guide-step-head {
    display: flex;
    align-items: center;
    gap: 9px;
    margin-bottom: 8px;
}
.ua-guide-step-num {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    flex: 0 0 24px;
    border: 1px solid rgba(var(--ua-cyan-rgb),0.28);
    border-radius: 7px;
    background: linear-gradient(145deg, rgba(var(--ua-cyan-rgb),0.14), rgba(var(--ua-purple-rgb),0.10));
    color: #A9EAF1;
    font-size: 0.66rem;
    font-weight: 800;
}
.ua-guide-step-title {
    color: #DDE2EB;
    font-size: 0.78rem;
    font-weight: 720;
    line-height: 1.3;
}
.ua-guide-step-body {
    color: var(--ua-text-lo);
    font-size: 0.73rem;
    line-height: 1.58;
}
@media (max-width: 900px) {
    .ua-guide-grid { grid-template-columns: 1fr; }
    .ua-guide-shell { padding: 17px; }
}

/* ── Page-local section rail ─────────────────────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] {
    gap: 3px !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 7px 9px !important;
    margin: 0 !important;
    transition: background 120ms ease, border-color 120ms ease;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: rgba(var(--ua-onbg-rgb),0.035);
    border-color: var(--ua-hair-2);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: rgba(var(--ua-purple-rgb),0.10);
    border-color: rgba(var(--ua-purple-rgb),0.28);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label p {
    font-size: 0.78rem !important;
    font-weight: 650 !important;
}

/* ── Base typography ─────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    font-variant-numeric: tabular-nums;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    line-height: 1.55;
}

/* ── Scrollbar ───────────────────────────────────────────────────────────── */
::-webkit-scrollbar              { width: 4px; height: 4px; }
::-webkit-scrollbar-track        { background: transparent; }
::-webkit-scrollbar-thumb        { background: rgba(var(--ua-green-rgb),0.22); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover  { background: rgba(var(--ua-green-rgb),0.45); }

/* ── Page background — gradient mesh ─────────────────────────────────────── */
.main {
    background-color: var(--ua-bg) !important;
    background-image:
        radial-gradient(ellipse 80% 40% at 20% -5%,  rgba(var(--ua-green-rgb),0.055) 0%, transparent 60%),
        radial-gradient(ellipse 60% 35% at 80% 5%,   rgba(var(--ua-purple-rgb),0.045) 0%, transparent 55%),
        radial-gradient(ellipse 50% 30% at 50% 100%, rgba(var(--ua-cyan-rgb),0.035) 0%, transparent 50%) !important;
}
.block-container {
    background-color: transparent !important;
    padding-top: 0.75rem !important;
}
[data-testid="stAppViewContainer"] {
    background-color: var(--ua-bg) !important;
    background-image:
        radial-gradient(ellipse 80% 40% at 20% -5%,  rgba(var(--ua-green-rgb),0.055) 0%, transparent 60%),
        radial-gradient(ellipse 60% 35% at 80% 5%,   rgba(var(--ua-purple-rgb),0.045) 0%, transparent 55%),
        radial-gradient(ellipse 50% 30% at 50% 100%, rgba(var(--ua-cyan-rgb),0.035) 0%, transparent 50%) !important;
}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0D0F1A 0%, #0A0C14 100%) !important;
    border-right: 1px solid var(--ua-border-lo) !important;
}
section[data-testid="stSidebar"] * { color: var(--ua-ink-mut) !important; }
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] a { color: var(--ua-ink-mut) !important; }
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: var(--ua-ink) !important;
    border-bottom: 1px solid var(--ua-hair-3) !important;
    padding-bottom: 4px !important;
}
[data-testid="stNavSectionHeader"] {
    background: rgba(var(--ua-green-rgb),0.07) !important;
    border-radius: 6px !important;
    padding: 3px 8px !important;
    margin-top: 12px !important;
    margin-bottom: 3px !important;
}
[data-testid="stNavSectionHeader"] p {
    font-size: 0.62rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: var(--ua-green) !important;
}
[data-testid="stSidebarNavItems"] a[aria-selected="true"],
[data-testid="stSidebarNavItems"] [aria-selected="true"] {
    background: rgba(var(--ua-green-rgb),0.09) !important;
    border-radius: 6px !important;
}
[data-testid="stSidebarNavItems"] a[aria-selected="true"] p,
[data-testid="stSidebarNavItems"] [aria-selected="true"] p { color: var(--ua-green) !important; }
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(var(--ua-green-rgb),0.09) !important;
    border: 1px solid rgba(var(--ua-green-rgb),0.22) !important;
    color: var(--ua-green) !important;
    border-radius: 8px !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(var(--ua-green-rgb),0.16) !important;
    box-shadow: 0 0 12px rgba(var(--ua-green-rgb),0.14) !important;
}
section[data-testid="stSidebar"] .stButton > button span,
section[data-testid="stSidebar"] .stButton > button p { color: var(--ua-green) !important; }

/* ── Masthead ────────────────────────────────────────────────────────────── */
.market-status-badge {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.07em;
    padding: 3px 9px; border-radius: 6px;
    font-family: 'Inter', sans-serif !important;
    transition: filter 0.15s ease;
}
.market-status-badge:hover { filter: brightness(1.15); }
.market-status-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.ua-header {
    display: flex; align-items: flex-end; justify-content: space-between;
    padding-bottom: 12px; margin-bottom: 0;
    border-bottom: 1px solid var(--ua-hair-2);
    position: relative;
}
.ua-header::after {
    content: '';
    position: absolute;
    bottom: -1px; left: 0;
    width: 200px; height: 2px;
    background: linear-gradient(90deg, var(--ua-green), var(--ua-cyan) 50%, var(--ua-purple) 100%);
    background-size: 300% 100%;
    animation: ua_gradient_x 6s ease infinite;
    border-radius: 1px;
}
.ua-wordmark {
    font-size: 1.8rem; font-weight: 800; color: var(--ua-ink);
    font-family: 'Inter', sans-serif; letter-spacing: -0.8px; line-height: 1.05;
}
.ua-wordmark span {
    background: linear-gradient(120deg,
        var(--ua-brand-alpha-1) 0%,
        var(--ua-brand-alpha-2) 58%,
        var(--ua-brand-alpha-3) 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: none;
}
.ua-tagline {
    font-size: 0.70rem; color: var(--ua-ink-label); font-family: 'Inter', sans-serif;
    margin-top: 3px; letter-spacing: 0.02em;
    display: flex; align-items: center; gap: 6px;
}
.ua-hero-title {
    font-size: 2.05rem; font-weight: 600; color: var(--ua-text, #F3F6FC);
    font-family: var(--ua-serif); letter-spacing: -0.4px; line-height: 1.08;
    max-width: 620px;
}
.ua-hero-sub {
    font-size: 0.82rem; color: var(--ua-ink-mut); font-family: 'Inter', sans-serif;
    margin-top: 6px; line-height: 1.55; max-width: 520px; font-weight: 400;
}
.ua-header-right {
    text-align: right; font-size: 0.73rem; color: var(--ua-ink-mut); font-family: 'Inter', sans-serif;
}
.ua-header-right b { color: var(--ua-text-mid); font-weight: 600; }
.gold-rule {
    height: 1px;
    background: linear-gradient(90deg, rgba(var(--ua-green-rgb),0.5), rgba(var(--ua-cyan-rgb),0.3) 40%, rgba(var(--ua-purple-rgb),0.3) 70%, transparent);
    border: none; margin: 0 0 14px 0;
}

/* ── Cards ───────────────────────────────────────────────────────────────── */
.metric-card {
    background: var(--ua-surface);
    border: 1px solid var(--ua-border);
    border-radius: 12px; padding: 16px 18px; margin-bottom: 10px;
    font-family: 'Inter', sans-serif;
    transition: all 0.22s cubic-bezier(0.4,0,0.2,1);
    position: relative; overflow: hidden;
    box-shadow: 0 2px 8px rgba(var(--ua-shadow-rgb),calc(0.3*var(--ua-shadow-k)));
}
.metric-card::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0;
    width: 3px; background: var(--ua-hair);
    border-radius: 12px 0 0 12px;
    transition: background 0.2s ease;
}
.metric-card.bull::before  { background: linear-gradient(180deg, var(--ua-green), #00A847); }
.metric-card.bear::before  { background: linear-gradient(180deg, var(--ua-red), #CC2222); }
.metric-card.neutral::before { background: linear-gradient(180deg, var(--ua-ink-label), var(--ua-ink-dim-2)); }
/* Subtle top glow when bull/bear */
.metric-card.bull { box-shadow: 0 0 0 0 transparent, inset 0 1px 0 rgba(var(--ua-green-rgb),0.06); }
.metric-card.bear { box-shadow: 0 0 0 0 transparent, inset 0 1px 0 rgba(var(--ua-red-rgb),0.06); }
.metric-card, .page-card, .stat-box { will-change: transform; }
.metric-card:hover {
    border-color: rgba(var(--ua-green-rgb),0.24);
    box-shadow: 0 0 28px rgba(var(--ua-green-rgb),0.09), 0 8px 28px rgba(var(--ua-shadow-rgb),calc(0.45*var(--ua-shadow-k)));
    transform: translate3d(0,-2px,0);
}
.metric-card.bull:hover { border-color: rgba(var(--ua-green-rgb),0.32); }
.metric-card.bear:hover { border-color: rgba(var(--ua-red-rgb),0.25); }
.metric-card b { color: var(--ua-ink); }
.metric-card span { color: var(--ua-ink-mut); }

.page-card {
    background: rgba(var(--ua-card-rgb),0.7);
    border: 1px solid var(--ua-hair-2);
    border-radius: 12px; padding: 18px 20px; margin-bottom: 10px;
    font-family: 'Inter', sans-serif;
    transition: all 0.22s cubic-bezier(0.4,0,0.2,1);
    position: relative; overflow: hidden;
}
.page-card::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0;
    width: 3px;
    background: linear-gradient(180deg, var(--ua-green), var(--ua-purple));
    border-radius: 12px 0 0 12px;
    opacity: 0; transition: opacity 0.2s ease;
}
.page-card:hover::before { opacity: 1; }
.page-card:hover {
    border-color: rgba(var(--ua-green-rgb),0.18);
    box-shadow: 0 0 24px rgba(var(--ua-green-rgb),0.07), 0 12px 32px rgba(var(--ua-shadow-rgb),calc(0.5*var(--ua-shadow-k)));
    transform: translate3d(0,-2px,0);
}
.page-card .page-title { font-size: 0.94rem; font-weight: 600; color: var(--ua-ink); margin-bottom: 4px; letter-spacing: -0.1px; }
.page-card .page-desc  { font-size: 0.79rem; color: var(--ua-ink-mut); line-height: 1.55; }

/* ── Section header ──────────────────────────────────────────────────────── */
.section-header {
    font-size: 0.63rem; font-weight: 700; color: var(--ua-ink-mut);
    font-family: 'Inter', sans-serif; letter-spacing: 0.13em;
    text-transform: uppercase;
    border-bottom: 1px solid var(--ua-hair-3);
    padding-bottom: 8px; margin-bottom: 14px;
}

/* ── Score numbers ───────────────────────────────────────────────────────── */
.score-number { font-size: 2.8rem; font-weight: 800; line-height: 1.0; font-family: 'Inter', sans-serif; letter-spacing: -1.5px; }
.score-bull {
    background: linear-gradient(135deg, var(--ua-green), var(--ua-cyan));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.score-bear {
    background: linear-gradient(135deg, var(--ua-red), #FF8888);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.score-neutral { color: var(--ua-ink-label); }

/* ── Stat boxes ──────────────────────────────────────────────────────────── */
.stat-box {
    background: var(--ua-surface); border: 1px solid var(--ua-border);
    border-radius: 10px; padding: 14px 16px; text-align: center;
    font-family: 'Inter', sans-serif;
    transition: all 0.2s cubic-bezier(0.4,0,0.2,1);
}
.stat-box:hover {
    border-color: rgba(var(--ua-green-rgb),0.2);
    box-shadow: 0 0 16px rgba(var(--ua-green-rgb),0.07);
    transform: translateY(-1px);
}
.stat-box .stat-label  { font-size: 0.60rem; text-transform: uppercase; letter-spacing: 0.11em; color: var(--ua-ink-mut); margin-bottom: 6px; font-weight: 700; }
.stat-box .stat-value  { font-size: 1.4rem; font-weight: 700; color: var(--ua-ink); letter-spacing: -0.5px; }
.stat-box .stat-change { font-size: 0.76rem; margin-top: 3px; font-weight: 500; }
.stat-box .stat-change.pos  { color: var(--ua-green); }
.stat-box .stat-change.neg  { color: var(--ua-red); }
.stat-box .stat-change.flat { color: var(--ua-ink-label); }

/* ── Info / disclaimer ───────────────────────────────────────────────────── */
.disclaimer {
    background: rgba(var(--ua-card-rgb),0.6); border: 1px solid var(--ua-hair-3);
    border-radius: 8px; padding: 10px 14px; font-size: 0.72rem;
    color: var(--ua-ink-mut); margin-top: 16px; font-family: 'Inter', sans-serif;
}
.info-box {
    background: rgba(var(--ua-green-rgb),0.05); border: 1px solid rgba(var(--ua-green-rgb),0.15);
    border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;
    font-size: 0.83rem; color: #A8E8C0; font-family: 'Inter', sans-serif;
}

/* ── Tables ──────────────────────────────────────────────────────────────── */
.comparison-table { width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 0.83rem; }
.comparison-table th {
    background: rgba(var(--ua-green-rgb),0.08); color: var(--ua-green);
    padding: 9px 12px; text-align: left; font-weight: 700;
    font-size: 0.62rem; letter-spacing: 0.08em; text-transform: uppercase;
    border-bottom: 1px solid rgba(var(--ua-green-rgb),0.18);
}
.comparison-table td { padding: 8px 12px; border-bottom: 1px solid var(--ua-border-lo); color: var(--ua-text-mid); }
.comparison-table tr:hover td { background: rgba(var(--ua-onbg-rgb),0.02); }
.comparison-table tr.highlight td { background: rgba(var(--ua-green-rgb),0.06); color: var(--ua-ink); font-weight: 600; }

.ua-data-table { width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 0.81rem; }
.ua-data-table th {
    background: rgba(var(--ua-card-rgb),0.95); color: var(--ua-ink-mut);
    padding: 9px 12px; text-align: left; font-weight: 700;
    font-size: 0.60rem; letter-spacing: 0.10em; text-transform: uppercase;
    border-bottom: 1px solid var(--ua-hair-2);
}
.ua-data-table td { padding: 9px 12px; border-bottom: 1px solid var(--ua-border-lo); color: var(--ua-ink-soft); vertical-align: middle; }
.ua-data-table tr:hover td { background: rgba(var(--ua-onbg-rgb),0.02); transition: background 0.1s ease; }
.ua-data-table .bull    { color: var(--ua-green); font-weight: 600; }
.ua-data-table .bear    { color: var(--ua-red); font-weight: 600; }
.ua-data-table .neutral { color: var(--ua-ink-label); }

/* ── Streamlit native overrides ──────────────────────────────────────────── */
/* Metrics */
.stMetric label { color: var(--ua-ink-mut) !important; font-size: 0.70rem !important; letter-spacing: 0.06em !important; font-family: 'Inter', sans-serif !important; text-transform: uppercase !important; font-weight: 600 !important; }
.stMetric [data-testid="stMetricValue"] { color: var(--ua-ink) !important; font-family: 'Inter', sans-serif !important; font-size: 1.65rem !important; font-weight: 700 !important; letter-spacing: -0.5px !important; }
.stMetric [data-testid="stMetricDelta"] { font-size: 0.78rem !important; font-weight: 500 !important; }

/* Expanders */
div[data-testid="stExpander"] { background: rgba(var(--ua-card-rgb),0.6) !important; border: 1px solid var(--ua-hair-2) !important; border-radius: 10px !important; }
.streamlit-expanderHeader { color: var(--ua-text-mid) !important; font-family: 'Inter', sans-serif !important; font-weight: 600 !important; font-size: 0.86rem !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"]  { border-bottom: 1px solid var(--ua-hair-2) !important; gap: 0 !important; background: transparent !important; }
.stTabs [data-baseweb="tab"]       { font-family: 'Inter', sans-serif !important; font-size: 0.83rem !important; font-weight: 500 !important; padding: 8px 18px !important; color: var(--ua-ink-mut) !important; background: transparent !important; border: none !important; }
.stTabs [aria-selected="true"]     { color: var(--ua-ink) !important; border-bottom: 2px solid var(--ua-green) !important; font-weight: 600 !important; }
.stTabs [data-baseweb="tab-highlight"] { background: var(--ua-green) !important; height: 2px !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 16px !important; }

/* Buttons */
.stButton > button {
    font-family: 'Inter', sans-serif !important;
    border-radius: 8px !important; font-weight: 500 !important; font-size: 0.83rem !important;
    transition: all 0.18s cubic-bezier(0.4,0,0.2,1) !important;
    border: 1px solid var(--ua-hair) !important;
    background: var(--ua-surface) !important; color: var(--ua-text-mid) !important;
}

/* Global ticker search submit: keep the action legible at every viewport.
   Streamlit's default form-button padding could leave only a few pixels for
   the label in a nested column, wrapping "Open" one character per line. */
.st-key-global_ticker_submit button,
[data-testid="stFormSubmitButton"] button[key="global_ticker_submit"] {
    min-width: 138px !important;
    min-height: 42px !important;
    padding: 0.55rem 1rem !important;
    background: #1D2634 !important;
    border: 1px solid rgba(143,154,173,0.30) !important;
    color: #DCE2EC !important;
    box-shadow: none !important;
}
.st-key-global_ticker_submit button p,
[data-testid="stFormSubmitButton"] button[key="global_ticker_submit"] p {
    white-space: nowrap !important;
    overflow-wrap: normal !important;
    word-break: keep-all !important;
}
.stButton > button:hover {
    border-color: rgba(var(--ua-royal-rgb),0.45) !important; color: #B7BEFB !important;
    box-shadow: 0 0 14px rgba(var(--ua-royal-rgb),0.14) !important;
    transform: translateY(-1px);
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6470F5, #4B54D8) !important;
    color: #FFFFFF !important; border: none !important; font-weight: 700 !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 0 22px rgba(var(--ua-royal-rgb),0.40) !important; filter: brightness(1.06);
}

/* Inputs */
.stTextInput > div > div > input {
    background: var(--ua-surface) !important; border: 1px solid var(--ua-hair) !important;
    border-radius: 8px !important; color: var(--ua-ink) !important;
    font-family: 'Inter', sans-serif !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.stTextInput > div > div > input:focus {
    border-color: rgba(var(--ua-royal-rgb),0.55) !important;
    box-shadow: 0 0 0 3px rgba(var(--ua-royal-rgb),0.10) !important; outline: none !important;
}
.stTextInput > div > div > input::placeholder { color: var(--ua-ink-mut) !important; }

/* Selectbox */
.stSelectbox > div > div {
    background: var(--ua-surface) !important; border: 1px solid var(--ua-hair) !important;
    border-radius: 8px !important; color: var(--ua-ink) !important; font-family: 'Inter', sans-serif !important;
}

/* Multiselect */
.stMultiSelect > div > div {
    background: var(--ua-surface) !important; border: 1px solid var(--ua-hair) !important;
    border-radius: 8px !important;
}
.stMultiSelect span[data-baseweb="tag"] {
    background: rgba(var(--ua-green-rgb),0.10) !important; border-color: rgba(var(--ua-green-rgb),0.25) !important;
    color: var(--ua-green) !important;
}

/* Number / Date input */
.stNumberInput > div > div > input,
.stDateInput > div > div > input {
    background: var(--ua-surface) !important; border: 1px solid var(--ua-hair) !important;
    border-radius: 8px !important; color: var(--ua-ink) !important; font-family: 'Inter', sans-serif !important;
}

/* Sliders */
.stSlider [data-baseweb="slider"] [role="progressbar"] { background: linear-gradient(90deg, var(--ua-green), var(--ua-cyan)) !important; }
.stSlider [data-baseweb="thumb"] { background: var(--ua-green) !important; border-color: var(--ua-green) !important; box-shadow: 0 0 8px rgba(var(--ua-green-rgb),0.5) !important; }

/* Toggle */
.stToggle [data-baseweb="switch"] [data-checked="true"] { background: var(--ua-green) !important; }

/* Progress bars */
.stProgress > div > div > div { background: linear-gradient(90deg, var(--ua-green), var(--ua-cyan)) !important; border-radius: 4px !important; }
.stProgress > div > div { background: var(--ua-hair-3) !important; border-radius: 4px !important; }

/* Dividers */
hr { border-color: var(--ua-hair-3) !important; opacity: 1 !important; }

/* Spinner */
.stSpinner > div { border-top-color: var(--ua-green) !important; }

/* H1/H2/H3 */
h1, h2, h3 { color: var(--ua-ink) !important; font-family: 'Inter', sans-serif !important; font-weight: 700 !important; letter-spacing: -0.3px !important; }
h1 { font-size: 1.75rem !important; }
h2 { font-size: 1.3rem !important; }
h3 { font-size: 1.05rem !important; }
p  { color: var(--ua-text-mid) !important; font-family: 'Inter', sans-serif !important; }

/* Radio / Checkbox */
.stRadio label, .stCheckbox label { color: var(--ua-text-mid) !important; font-family: 'Inter', sans-serif !important; }

/* Caption */
.stCaption, small { color: var(--ua-text-cap) !important; font-family: 'Inter', sans-serif !important; }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid var(--ua-hair-2) !important; border-radius: 10px !important; overflow: hidden !important; }

/* Alerts */
.stAlert { border-radius: 10px !important; border: none !important; }

/* Success/Info/Warning/Error alerts (dark-friendly backgrounds) */
div[data-testid="stAlertContainer"][data-baseweb="notification"][kind="success"] { background: rgba(var(--ua-green-rgb),0.08) !important; border: 1px solid rgba(var(--ua-green-rgb),0.2) !important; }
div[data-testid="stAlertContainer"][data-baseweb="notification"][kind="info"]    { background: rgba(var(--ua-cyan-rgb),0.08) !important; border: 1px solid rgba(var(--ua-cyan-rgb),0.2) !important; }
div[data-testid="stAlertContainer"][data-baseweb="notification"][kind="warning"] { background: rgba(245,158,11,0.08) !important; border: 1px solid rgba(245,158,11,0.2) !important; }
div[data-testid="stAlertContainer"][data-baseweb="notification"][kind="error"]   { background: rgba(var(--ua-red-rgb),0.08) !important; border: 1px solid rgba(var(--ua-red-rgb),0.2) !important; }

/* ── Page-entry animation ────────────────────────────────────────────────── */
@keyframes ua_page_in {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
.block-container > div:first-child {
    animation: ua_page_in 0.4s cubic-bezier(0.4,0,0.2,1) both;
}

/* ── Selectbox / dropdown dark overlay ──────────────────────────────────── */
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="select"] [data-baseweb="popover"],
ul[data-baseweb="menu"] {
    background: var(--ua-bg-card) !important;
    border: 1px solid rgba(var(--ua-onbg-rgb),0.09) !important;
    border-radius: 10px !important;
    box-shadow: 0 16px 48px rgba(var(--ua-shadow-rgb),calc(0.6*var(--ua-shadow-k))) !important;
}
[data-baseweb="menu"] li,
[data-baseweb="option"] {
    background: transparent !important;
    color: var(--ua-ink-soft) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.83rem !important;
}
[data-baseweb="option"]:hover,
[data-baseweb="option"][aria-selected="true"] {
    background: rgba(var(--ua-royal-rgb),0.12) !important;
    color: var(--ua-ink) !important;
}

/* ── Focus-visible keyboard ring ────────────────────────────────────────── */
*:focus-visible {
    outline: 2px solid rgba(var(--ua-royal-rgb),0.60) !important;
    outline-offset: 2px !important;
    border-radius: 6px;
}
.stButton > button:focus-visible {
    box-shadow: 0 0 0 3px rgba(var(--ua-royal-rgb),0.30) !important;
    outline: none !important;
}

/* ── Empty state component ──────────────────────────────────────────────── */
.ua-empty {
    text-align: center;
    padding: 48px 24px;
    background: rgba(var(--ua-card-rgb),0.5);
    border: 1px dashed var(--ua-hair);
    border-radius: 14px;
    font-family: 'Inter', sans-serif;
    margin: 12px 0;
}
.ua-empty-icon  { font-size: 2.4rem; margin-bottom: 12px; opacity: 0.5; }
.ua-empty-title { font-size: 0.94rem; font-weight: 600; color: var(--ua-ink); margin-bottom: 6px; }
.ua-empty-body  { font-size: 0.80rem; color: var(--ua-ink-mut); line-height: 1.55; max-width: 320px; margin: 0 auto; }

/* ── Tooltip dark styling ────────────────────────────────────────────────── */
[data-baseweb="tooltip"] [role="tooltip"] {
    background: var(--ua-bg-raised) !important;
    color: var(--ua-ink) !important;
    border: 1px solid rgba(var(--ua-onbg-rgb),0.1) !important;
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.78rem !important;
    box-shadow: 0 8px 24px rgba(var(--ua-shadow-rgb),calc(0.5*var(--ua-shadow-k))) !important;
}

/* ── Code blocks ─────────────────────────────────────────────────────────── */
code, pre {
    background: rgba(var(--ua-card-rgb),0.9) !important;
    color: var(--ua-cyan) !important;
    border: 1px solid var(--ua-border) !important;
    border-radius: 6px !important;
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace !important;
    font-size: 0.82rem !important;
}

/* ── Smooth section dividers ─────────────────────────────────────────────── */
.ua-divider {
    height: 1px;
    background: linear-gradient(90deg, rgba(var(--ua-green-rgb),0.18), rgba(var(--ua-cyan-rgb),0.10) 40%, rgba(var(--ua-purple-rgb),0.10) 70%, transparent);
    border: none;
    margin: 18px 0;
}

/* ── Chip / tag component ────────────────────────────────────────────────── */
.ua-chip {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em;
    padding: 3px 9px; border-radius: 20px;
    font-family: 'Inter', sans-serif;
    border: 1px solid currentColor;
    transition: all 0.15s ease;
}
.ua-chip:hover { filter: brightness(1.15); }
.ua-chip.bull  { color: var(--ua-green); background: rgba(var(--ua-green-rgb),0.08); }
.ua-chip.bear  { color: var(--ua-red); background: rgba(var(--ua-red-rgb),0.08); }
.ua-chip.neut  { color: var(--ua-ink-label); background: rgba(var(--ua-label-rgb),0.08); }
.ua-chip.pro   { color: var(--ua-purple); background: rgba(var(--ua-purple-rgb),0.10); }

/* ── Modern keyframes ────────────────────────────────────────────────────── */
@keyframes ua_pulse_ring {
    0%   { box-shadow: 0 0 0 0   rgba(var(--ua-green-rgb),0.55); }
    70%  { box-shadow: 0 0 0 8px rgba(var(--ua-green-rgb),0);    }
    100% { box-shadow: 0 0 0 0   rgba(var(--ua-green-rgb),0);    }
}
@keyframes ua_live_dot {
    0%, 100% { opacity: 1;   transform: scale(1);   }
    50%       { opacity: 0.4; transform: scale(1.35); }
}
@keyframes ua_gradient_x {
    0%, 100% { background-position: 0%   50%; }
    50%       { background-position: 100% 50%; }
}
@keyframes ua_slide_up {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0);    }
}
@keyframes ua_pop_in {
    0%   { opacity: 0; transform: scale(0.92); }
    60%  { transform: scale(1.02); }
    100% { opacity: 1; transform: scale(1);    }
}
@keyframes ua_glow_pulse_green {
    0%, 100% { box-shadow: 0 0 0 0 transparent; }
    50%       { box-shadow: var(--ua-glow-green); }
}
@keyframes ua_glow_pulse_red {
    0%, 100% { box-shadow: 0 0 0 0 transparent; }
    50%       { box-shadow: var(--ua-glow-red); }
}
@keyframes ua_border_spin {
    0%   { background-position: 0%   50%; }
    100% { background-position: 200% 50%; }
}
@keyframes ua_number_in {
    from { opacity: 0; transform: translateY(8px) scale(0.95); }
    to   { opacity: 1; transform: translateY(0)   scale(1);    }
}

/* ── Live dot — universal ────────────────────────────────────────────────── */
.ua-pulse-dot {
    display: inline-block;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--ua-green);
    animation: ua_live_dot 1.8s ease-in-out infinite;
    vertical-align: middle;
    margin-right: 5px;
}
.ua-pulse-dot.bear { background: var(--ua-red); }
.ua-pulse-dot.amber { background: var(--ua-amber); }

/* Pulsing ring variant (for score numbers etc.) */
.ua-pulse-ring {
    animation: ua_pulse_ring 2.2s cubic-bezier(0.455,0.03,0.515,0.955) infinite;
}

/* ── Glassmorphism card ───────────────────────────────────────────────────── */
.ua-glass {
    background: rgba(var(--ua-card-rgb),0.75);
    backdrop-filter: blur(18px) saturate(160%);
    -webkit-backdrop-filter: blur(18px) saturate(160%);
    border: 1px solid var(--ua-hair);
    border-radius: var(--ua-radius);
    box-shadow: var(--ua-shadow);
}
.ua-glass:hover {
    border-color: rgba(var(--ua-onbg-rgb),0.14);
    box-shadow: var(--ua-shadow-lg);
}

/* ── Animated gradient border card ──────────────────────────────────────── */
.ua-gradient-border {
    position: relative;
    background: var(--ua-bg-card);
    border-radius: var(--ua-radius);
    padding: 1px;           /* the 1px exposes the pseudo element underneath */
}
.ua-gradient-border::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    padding: 1px;
    background: linear-gradient(135deg, var(--ua-green), var(--ua-cyan), var(--ua-purple), var(--ua-green));
    background-size: 300% 300%;
    animation: ua_border_spin 4s linear infinite;
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    opacity: 0.6;
}

/* ── Bull/Bear glow cards ────────────────────────────────────────────────── */
.ua-card-bull {
    background: rgba(var(--ua-green-rgb),0.04);
    border: 1px solid rgba(var(--ua-green-rgb),0.18);
    border-radius: var(--ua-radius);
    animation: ua_glow_pulse_green 3.5s ease-in-out infinite;
}
.ua-card-bear {
    background: rgba(var(--ua-red-rgb),0.04);
    border: 1px solid rgba(var(--ua-red-rgb),0.18);
    border-radius: var(--ua-radius);
    animation: ua_glow_pulse_red 3.5s ease-in-out infinite;
}

/* ── Animated gradient text ─────────────────────────────────────────────── */
.ua-gradient-text {
    background: linear-gradient(135deg, #6470F5 0%, #8B7BF7 52%, #D4B26A 118%);
    background-size: 200% 200%;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: ua_gradient_x 5s ease infinite;
}

/* ── Slide-up stagger animations ─────────────────────────────────────────── */
.ua-slide-up         { animation: ua_slide_up 0.4s cubic-bezier(0.4,0,0.2,1) both; }
.ua-slide-up-d1      { animation: ua_slide_up 0.4s 0.05s cubic-bezier(0.4,0,0.2,1) both; }
.ua-slide-up-d2      { animation: ua_slide_up 0.4s 0.10s cubic-bezier(0.4,0,0.2,1) both; }
.ua-slide-up-d3      { animation: ua_slide_up 0.4s 0.15s cubic-bezier(0.4,0,0.2,1) both; }
.ua-slide-up-d4      { animation: ua_slide_up 0.4s 0.20s cubic-bezier(0.4,0,0.2,1) both; }

/* Pop in (numbers, scores) */
.ua-pop-in           { animation: ua_pop_in 0.45s cubic-bezier(0.4,0,0.2,1) both; }
.ua-number-in        { animation: ua_number_in 0.5s 0.1s cubic-bezier(0.4,0,0.2,1) both; }

/* ── Score badge — circular ───────────────────────────────────────────────── */
.ua-score-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 52px; height: 52px;
    border-radius: 50%;
    font-size: 1.1rem;
    font-weight: 800;
    line-height: 1;
    letter-spacing: -0.5px;
    position: relative;
    font-family: 'Inter', sans-serif;
}
.ua-score-badge.bull {
    background: rgba(var(--ua-green-rgb),0.12);
    color: var(--ua-green);
    box-shadow: 0 0 0 2px rgba(var(--ua-green-rgb),0.3), inset 0 0 12px rgba(var(--ua-green-rgb),0.08);
}
.ua-score-badge.bear {
    background: rgba(var(--ua-red-rgb),0.12);
    color: var(--ua-red);
    box-shadow: 0 0 0 2px rgba(var(--ua-red-rgb),0.3), inset 0 0 12px rgba(var(--ua-red-rgb),0.08);
}
.ua-score-badge.neut {
    background: rgba(var(--ua-label-rgb),0.10);
    color: var(--ua-ink-mut);
    box-shadow: 0 0 0 2px rgba(var(--ua-label-rgb),0.2);
}

/* ── Live section label ──────────────────────────────────────────────────── */
.ua-live-label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.60rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--ua-green);
    background: rgba(var(--ua-green-rgb),0.07);
    border: 1px solid rgba(var(--ua-green-rgb),0.20);
    border-radius: 20px;
    padding: 3px 12px;
    font-family: 'Inter', sans-serif;
}

/* ── Bento grid ──────────────────────────────────────────────────────────── */
.ua-bento {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
}
.ua-bento-wide  { grid-column: span 2; }
.ua-bento-tall  { grid-row: span 2; }

/* ── Status pill ─────────────────────────────────────────────────────────── */
.ua-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    font-family: 'Inter', sans-serif;
    white-space: nowrap;
}
.ua-pill.bull { background: rgba(var(--ua-green-rgb),0.10); color: var(--ua-green); border: 1px solid rgba(var(--ua-green-rgb),0.25); }
.ua-pill.bear { background: rgba(var(--ua-red-rgb),0.10);  color: var(--ua-red); border: 1px solid rgba(var(--ua-red-rgb),0.25); }
.ua-pill.neut { background: rgba(var(--ua-label-rgb),0.08); color: var(--ua-ink-mut); border: 1px solid rgba(var(--ua-label-rgb),0.20); }
.ua-pill.pro  { background: rgba(var(--ua-purple-rgb),0.10);  color: #A78BFA; border: 1px solid rgba(var(--ua-purple-rgb),0.25); }

/* ── Personalized decision cockpit ───────────────────────────────────────── */
.ua-cockpit-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
}
.ua-cockpit-kpi {
    background: rgba(var(--ua-onbg-rgb),0.025);
    border: 1px solid var(--ua-hair);
    border-radius: 9px;
    padding: 11px 12px;
    min-width: 0;
}
.ua-cockpit-kpi span {
    display: block;
    color: var(--ua-ink-mut);
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 4px;
}
.ua-cockpit-kpi b {
    display: block;
    color: var(--ua-ink);
    font-size: 0.85rem;
    overflow-wrap: anywhere;
}
@media (max-width: 720px) {
    .ua-cockpit-grid { grid-template-columns: 1fr; }
}

/* ── Data table — zebra striped ──────────────────────────────────────────── */
.ua-zebra tr:nth-child(even) td { background: rgba(var(--ua-onbg-rgb),0.015) !important; }

/* ── Streamlit dataframe — dark overrides ─────────────────────────────────── */
[data-testid="stDataFrame"] iframe { border-radius: 10px !important; }
/* Glide Data Grid paints its cells on an underlay canvas. The scroller sits
   above that canvas and must stay transparent; an opaque themed background
   hides every row while leaving a blank, correctly sized rectangle. */
.dvn-scroller { background: transparent !important; }
.dvn-scroller::-webkit-scrollbar       { width: 4px; height: 4px; }
.dvn-scroller::-webkit-scrollbar-thumb { background: rgba(var(--ua-green-rgb),0.22); border-radius: 2px; }

/* ── Better primary button gradient ─────────────────────────────────────── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6470F5 0%, #5A52E0 45%, #4B54D8 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    font-weight: 700 !important;
    letter-spacing: 0.01em !important;
    box-shadow: 0 2px 14px rgba(var(--ua-royal-rgb),0.30), 0 1px 3px rgba(var(--ua-shadow-rgb),calc(0.3*var(--ua-shadow-k))) !important;
    transition: all 0.18s cubic-bezier(0.4,0,0.2,1) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 22px rgba(var(--ua-royal-rgb),0.44), 0 2px 6px rgba(var(--ua-shadow-rgb),calc(0.4*var(--ua-shadow-k))) !important;
    filter: brightness(1.06) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"]:active {
    transform: translateY(0) !important;
    filter: brightness(0.97) !important;
}

/* ── Slider track — thicker, more visible ─────────────────────────────────── */
.stSlider [data-baseweb="slider"] {
    padding-top: 6px !important;
    padding-bottom: 6px !important;
}
.stSlider [data-baseweb="slider"] [role="progressbar"] {
    height: 4px !important;
    background: linear-gradient(90deg, var(--ua-green), var(--ua-cyan)) !important;
}
.stSlider [data-baseweb="thumb"] {
    width: 18px !important; height: 18px !important;
    background: var(--ua-green) !important;
    border: 2px solid var(--ua-bg) !important;
    box-shadow: 0 0 0 2px var(--ua-green), 0 0 10px rgba(var(--ua-green-rgb),0.4) !important;
}

/* ── Section divider accent ──────────────────────────────────────────────── */
.ua-section-rule {
    height: 1px;
    margin: 22px 0 18px;
    background: linear-gradient(90deg,
        rgba(var(--ua-green-rgb),0.25) 0%,
        rgba(var(--ua-cyan-rgb),0.15) 35%,
        rgba(var(--ua-purple-rgb),0.12) 65%,
        transparent 100%);
    border: none;
}

/* ── Scroll-to-top button ─────────────────────────────────────────────────── */
#ua-scroll-top {
    position: fixed;
    bottom: 28px;
    right: 28px;
    width: 40px;
    height: 40px;
    background: rgba(var(--ua-green-rgb),0.15);
    border: 1px solid rgba(var(--ua-green-rgb),0.35);
    border-radius: 50%;
    color: var(--ua-green);
    font-size: 18px;
    line-height: 40px;
    text-align: center;
    cursor: pointer;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.25s, background 0.2s;
    z-index: 9999;
    will-change: transform;
    transform: translate3d(0,0,0);
    backdrop-filter: blur(8px);
}
#ua-scroll-top.visible {
    opacity: 1;
    pointer-events: auto;
}
#ua-scroll-top:hover {
    background: rgba(var(--ua-green-rgb),0.28);
}

/* ── Mobile responsiveness ───────────────────────────────────────────────── */
@media (max-width: 768px) {
    [data-testid="stHorizontalBlock"] > [data-testid="stVerticalBlock"] {
        min-width: 45% !important;
    }
    .hero-title { font-size: 1.9rem !important; }
    .block-container { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
    .ticker-strip-outer { display: none !important; }
    .ua-bento { grid-template-columns: 1fr !important; }
    .ua-bento-wide { grid-column: span 1 !important; }
    .metric-card, .page-card { padding: 14px !important; }
    .ua-header { flex-direction: column !important; gap: 8px !important; }
    .ua-header-right { text-align: left !important; font-size: 0.72rem !important; }
    #ua-scroll-top { bottom: 16px; right: 16px; }
}

/* ── Skeleton loader ─────────────────────────────────────────────────────── */
@keyframes ua_shimmer {
    0%   { background-position: -400px 0; }
    100% { background-position: 400px 0; }
}
.ua-skeleton {
    background: linear-gradient(
        90deg,
        var(--ua-border-lo) 25%,
        rgba(var(--ua-onbg-rgb),0.09) 50%,
        var(--ua-border-lo) 75%
    );
    background-size: 800px 100%;
    animation: ua_shimmer 1.8s ease-in-out infinite;
    border-radius: 8px;
}
.ua-skeleton-line { height: 14px; margin-bottom: 10px; border-radius: 6px; }
.ua-skeleton-line.sm { width: 40%; height: 11px; }
.ua-skeleton-line.lg { width: 90%; }
.ua-skeleton-line.md { width: 70%; }
.ua-skeleton-block { height: 120px; border-radius: 12px; margin-bottom: 12px; }
.ua-skeleton-chart { height: 220px; border-radius: 12px; }

/* ── Chart container card ────────────────────────────────────────────────── */
.ua-chart-card {
    background: rgba(var(--ua-card-rgb),0.75);
    border: 1px solid var(--ua-border);
    border-radius: 14px;
    padding: 18px 20px 14px;
    margin-bottom: 16px;
    position: relative;
    overflow: hidden;
}
.ua-chart-card:hover {
    border-color: rgba(var(--ua-green-rgb),0.16);
    box-shadow: 0 0 28px rgba(var(--ua-green-rgb),0.06), 0 12px 32px rgba(var(--ua-shadow-rgb),calc(0.4*var(--ua-shadow-k)));
    transition: all 0.22s cubic-bezier(0.4,0,0.2,1);
}
.ua-chart-title {
    font-size: 0.83rem;
    font-weight: 700;
    color: var(--ua-ink);
    letter-spacing: -0.1px;
    margin-bottom: 3px;
    font-family: 'Inter', sans-serif;
}
.ua-chart-subtitle {
    font-size: 0.68rem;
    color: var(--ua-ink-mut);
    margin-bottom: 14px;
    font-family: 'Inter', sans-serif;
    line-height: 1.4;
}
.ua-chart-caption {
    font-size: 0.63rem;
    color: var(--ua-ink-dim-2);
    margin-top: 8px;
    font-family: 'Inter', sans-serif;
    font-style: italic;
    line-height: 1.45;
}
.ua-chart-source-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.60rem;
    font-weight: 700;
    color: var(--ua-ink-label);
    background: rgba(var(--ua-label-rgb),0.08);
    border: 1px solid rgba(var(--ua-label-rgb),0.15);
    border-radius: 4px;
    padding: 2px 7px;
    letter-spacing: 0.06em;
    font-family: 'Inter', sans-serif;
}

/* ── Pro upgrade CTA card ────────────────────────────────────────────────── */
.ua-pro-cta {
    background: linear-gradient(135deg, rgba(var(--ua-purple-rgb),0.12) 0%, rgba(var(--ua-purple-rgb),0.06) 100%);
    border: 1px solid rgba(var(--ua-purple-rgb),0.3);
    border-radius: 14px;
    padding: 20px 22px;
    position: relative;
    overflow: hidden;
    font-family: 'Inter', sans-serif;
}
.ua-pro-cta::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--ua-purple), var(--ua-cyan), var(--ua-purple));
    background-size: 200% 100%;
    animation: ua_gradient_x 4s ease infinite;
}
.ua-pro-cta-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 0.60rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #A78BFA;
    background: rgba(var(--ua-purple-rgb),0.12);
    border: 1px solid rgba(var(--ua-purple-rgb),0.25);
    border-radius: 20px;
    padding: 3px 10px;
    margin-bottom: 10px;
    display: inline-block;
}
.ua-pro-cta-title {
    font-size: 0.94rem;
    font-weight: 700;
    color: var(--ua-ink);
    margin-bottom: 5px;
    letter-spacing: -0.1px;
}
.ua-pro-cta-body {
    font-size: 0.80rem;
    color: var(--ua-ink-mut);
    line-height: 1.55;
    margin-bottom: 14px;
}

/* ── Better error state ──────────────────────────────────────────────────── */
.ua-error {
    text-align: center;
    padding: 36px 24px;
    background: rgba(var(--ua-red-rgb),0.04);
    border: 1px dashed rgba(var(--ua-red-rgb),0.18);
    border-radius: 14px;
    font-family: 'Inter', sans-serif;
    margin: 12px 0;
}
.ua-error-icon  { font-size: 2rem; margin-bottom: 10px; opacity: 0.6; }
.ua-error-title { font-size: 0.88rem; font-weight: 600; color: #FF8888; margin-bottom: 4px; }
.ua-error-body  { font-size: 0.76rem; color: var(--ua-ink-mut); line-height: 1.5; }

/* ── Loading pulse state ─────────────────────────────────────────────────── */
.ua-loading-card {
    background: rgba(var(--ua-card-rgb),0.7);
    border: 1px solid var(--ua-hair-2);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 10px;
    font-family: 'Inter', sans-serif;
}

/* ── Score trend indicator ───────────────────────────────────────────────── */
.ua-trend-up   { color: var(--ua-green); font-weight: 700; font-size: 0.80rem; }
.ua-trend-down { color: var(--ua-red); font-weight: 700; font-size: 0.80rem; }
.ua-trend-flat { color: var(--ua-ink-label); font-weight: 700; font-size: 0.80rem; }

/* ── Inline score bar (for signal tables) ────────────────────────────────── */
.ua-score-bar-track {
    height: 4px;
    background: var(--ua-hair-3);
    border-radius: 2px;
    overflow: hidden;
    flex-shrink: 0;
}
.ua-score-bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.6s cubic-bezier(0.4,0,0.2,1);
}
.ua-score-bar-fill.bull { background: linear-gradient(90deg, var(--ua-green), var(--ua-cyan)); }
.ua-score-bar-fill.bear { background: linear-gradient(90deg, var(--ua-red), #FF7777); }
.ua-score-bar-fill.neut { background: rgba(var(--ua-label-rgb),0.5); }

/* ── Section eyebrow label ───────────────────────────────────────────────── */
.ua-eyebrow {
    font-size: 0.60rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--ua-green);
    font-family: 'Inter', sans-serif;
    margin-bottom: 4px;
}

/* ── Premium data table with sort indication ─────────────────────────────── */
.ua-table-sortable th { cursor: pointer; user-select: none; }
.ua-table-sortable th:hover { color: var(--ua-text-hi) !important; }
.ua-table-sort-asc::after  { content: ' ▲'; font-size: 0.55rem; opacity: 0.6; }
.ua-table-sort-desc::after { content: ' ▼'; font-size: 0.55rem; opacity: 0.6; }

/* ── Category filter pills (signal dashboard, screener) ──────────────────── */
.ua-filter-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 16px;
}
.ua-filter-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    font-family: 'Inter', sans-serif;
    cursor: pointer;
    transition: all 0.15s ease;
    border: 1px solid var(--ua-hair);
    background: rgba(var(--ua-onbg-rgb),0.03);
    color: var(--ua-ink-mut);
    white-space: nowrap;
}
.ua-filter-pill:hover {
    border-color: rgba(var(--ua-green-rgb),0.3);
    color: var(--ua-ink);
    background: rgba(var(--ua-green-rgb),0.06);
}
.ua-filter-pill.active {
    border-color: rgba(var(--ua-green-rgb),0.4);
    color: var(--ua-green);
    background: rgba(var(--ua-green-rgb),0.08);
    font-weight: 700;
}

/* ── Ticker banner (at top of TDD, Watchlist rows) ───────────────────────── */
.ua-ticker-banner {
    background: rgba(var(--ua-card-rgb),0.9);
    border: 1px solid var(--ua-border);
    border-radius: 12px;
    padding: 14px 18px;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    font-family: 'Inter', sans-serif;
    margin-bottom: 16px;
}
.ua-ticker-symbol {
    font-size: 1.3rem;
    font-weight: 800;
    color: var(--ua-ink);
    letter-spacing: -0.5px;
}
.ua-ticker-name {
    font-size: 0.80rem;
    color: var(--ua-ink-mut);
}
.ua-ticker-price {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--ua-ink);
    letter-spacing: -0.3px;
}

/* ── Improved content divider with label ─────────────────────────────────── */
.ua-label-divider {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 20px 0 14px;
    font-family: 'Inter', sans-serif;
}
.ua-label-divider span {
    font-size: 0.60rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ua-ink-mut);
    white-space: nowrap;
}
.ua-label-divider::before,
.ua-label-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--ua-hair-3);
}

/* ── Watchlist row hover ─────────────────────────────────────────────────── */
.ua-watchlist-row {
    transition: background 0.15s ease;
}
.ua-watchlist-row:hover {
    background: rgba(var(--ua-green-rgb),0.04) !important;
}

/* ── De-neon (2026-07-13) ─────────────────────────────────────────────────────
   The app leaned heavily on glowing numbers — dozens of inline
   `text-shadow:0 0 …px <color>` glows that read consumer/gamer rather than
   institutional. This one !important author rule neutralises every 0-offset
   GLOW shadow app-wide (an !important author declaration overrides a
   non-important inline style), without editing ~24 scattered call sites and
   without touching legibility shadows (which use a vertical offset, not 0 0).
   Numbers keep their semantic colour; they just sit flat. Reversible: delete
   this block.
   NOTE on the selector: browsers RE-SERIALISE inline styles, so the source
   `text-shadow:0 0 20px <color>` becomes `text-shadow: <color> 0px 0px 20px` in
   the DOM. The reliable, verified match for a zero-offset GLOW is therefore the
   substring `0px 0px` (confirmed live on the Signal Dashboard). This also
   matches 0px-0px box-shadows, but setting text-shadow:none on those is a
   harmless no-op; legibility text-shadows use a vertical offset and are
   untouched. */
[style*="0px 0px"] { text-shadow: none !important; }

/* ── Institutional surface pass (2026-07-21) ──────────────────────────────
   Reduce motion, glow, glass, and decorative gradients across every page.
   Directional color remains meaningful; surfaces and typography stay quiet. */
[data-testid="stAppViewContainer"], .main {
    background: #0A0D12 !important;
    background-image: none !important;
}
section[data-testid="stSidebar"] {
    background: #0D1016 !important;
    border-right-color: var(--ua-border) !important;
}
.ua-header::after, .ua-card-shine::after { display: none !important; }
.ua-wordmark span {
    background: linear-gradient(120deg,
        var(--ua-brand-alpha-1) 0%,
        var(--ua-brand-alpha-2) 58%,
        var(--ua-brand-alpha-3) 100%) !important;
    -webkit-background-clip: text !important;
    background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    color: var(--ua-brand-alpha-2) !important;
    animation: none !important;
}
.metric-card, .page-card, .stat-box,
[data-testid="stMetric"], [data-testid="stExpander"] {
    background: var(--ua-bg-card) !important;
    backdrop-filter: none !important;
    border-color: var(--ua-hair) !important;
    border-radius: 8px !important;
    box-shadow: none !important;
    transform: none !important;
}
.metric-card p, .page-card p, .stat-box p,
[data-testid="stMetric"] [data-testid="stMetricLabel"],
[data-testid="stExpander"] p,
[data-testid="stAlert"] p,
[data-testid="stForm"] label p,
[data-testid="stVerticalBlockBorderWrapper"] p {
    color: var(--ua-text-mid) !important;
}
.metric-card .stCaption, .page-card .stCaption, .stat-box .stCaption,
[data-testid="stMetric"] [data-testid="stMetricDelta"],
[data-testid="stExpander"] .stCaption,
[data-testid="stAlert"] .stCaption,
[data-testid="stForm"] .stCaption,
[data-testid="stVerticalBlockBorderWrapper"] .stCaption {
    color: var(--ua-text-cap) !important;
}
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea,
[data-baseweb="select"] span {
    color: var(--ua-text-hi) !important;
}

/* Compact notification tray: rendered in normal document flow beneath its
   trigger, never as an auto-flipping popover that can grow upward. */
.ua-notification-panel-marker {
    display: block;
    height: 0;
    overflow: hidden;
}
.ua-notification-title {
    color: var(--ua-text-cap) !important;
    font-size: 0.60rem;
    font-weight: 750;
    letter-spacing: 0.11em;
    text-transform: uppercase;
    padding-bottom: 7px;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--ua-hair);
}
.ua-notification-item {
    background: #151A22;
    border: 1px solid var(--ua-hair);
    border-left-width: 2px;
    border-radius: 6px;
    padding: 8px 9px;
    margin-bottom: 6px;
}
.ua-notification-kicker {
    color: var(--ua-text-cap) !important;
    font-size: 0.56rem;
    font-weight: 750;
    letter-spacing: 0.09em;
    text-transform: uppercase;
}
.ua-notification-heading {
    color: var(--ua-text-hi) !important;
    font-size: 0.73rem;
    font-weight: 650;
    line-height: 1.35;
    margin-top: 2px;
}
.ua-notification-copy {
    color: var(--ua-text-lo) !important;
    font-size: 0.67rem;
    line-height: 1.42;
    margin-top: 3px;
}
.ua-notification-time {
    color: var(--ua-text-cap) !important;
    font-size: 0.57rem;
    margin-top: 4px;
}

/* Legacy page helpers still carry the former muted palette inline. Lift those
   values globally into the current restrained contrast scale without touching
   semantic bullish/bearish colors or turning body copy bright white. */
[style*="color:var(--ua-ink-mut)" i] { color: var(--ua-text-lo) !important; }
[style*="color: var(--ua-ink-mut)" i] { color: var(--ua-text-lo) !important; }
[style*="color:var(--ua-ink-label)" i] { color: var(--ua-text-cap) !important; }
[style*="color: var(--ua-ink-label)" i] { color: var(--ua-text-cap) !important; }
[style*="color:var(--ua-ink-dim-2)" i], [style*="color:var(--ua-ink-dim)" i] {
    color: #7F899A !important;
}

/* Light-mode completion: legacy render helpers still emit a bounded set of
   dark-theme text literals. Match only a real `color` declaration at the
   beginning of an inline style or immediately after a semicolon. This avoids
   the dangerous broad `style*=color` pattern, which also catches background-
   color and border-color, and leaves Python color parsing + Plotly untouched.
   Browsers serialize inline hex values to rgb(), so both forms are covered. */
html[data-ua-theme="light"] :is(
    [style^="color: #00D566" i], [style*="; color: #00D566" i],
    [style^="color:#00D566" i],  [style*=";color:#00D566" i],
    [style^="color: rgb(0, 213, 102)" i], [style*="; color: rgb(0, 213, 102)" i],
    [style^="color: #34D399" i], [style*="; color: #34D399" i],
    [style*=";color:#34D399" i],
    [style^="color:#34D399" i],  [style*=";color:#34D399" i],
    [style^="color: rgb(52, 211, 153)" i], [style*="; color: rgb(52, 211, 153)" i],
    [style^="color: #00A847" i], [style*="; color: #00A847" i],
    [style*=";color:#00A847" i],
    [style^="color: rgb(0, 168, 71)" i], [style*="; color: rgb(0, 168, 71)" i],
    [style^="color: #00C853" i], [style*="; color: #00C853" i],
    [style*=";color:#00C853" i],
    [style^="color: rgb(0, 200, 83)" i], [style*="; color: rgb(0, 200, 83)" i],
    [style^="color: #22C55E" i], [style*="; color: #22C55E" i],
    [style*=";color:#22C55E" i],
    [style^="color: rgb(34, 197, 94)" i], [style*="; color: rgb(34, 197, 94)" i],
    [style^="color: #35C98B" i], [style*="; color: #35C98B" i],
    [style*=";color:#35C98B" i],
    [style^="color: rgb(53, 201, 139)" i], [style*="; color: rgb(53, 201, 139)" i]
) { color: var(--ua-green) !important; opacity: 1 !important; }

html[data-ua-theme="light"] :is(
    [style^="color: #FF4444" i], [style*="; color: #FF4444" i],
    [style^="color:#FF4444" i],  [style*=";color:#FF4444" i],
    [style^="color: rgb(255, 68, 68)" i], [style*="; color: rgb(255, 68, 68)" i],
    [style^="color: #FF2222" i], [style*="; color: #FF2222" i],
    [style*=";color:#FF2222" i],
    [style^="color: rgb(255, 34, 34)" i], [style*="; color: rgb(255, 34, 34)" i],
    [style^="color: #CC3333" i], [style*="; color: #CC3333" i],
    [style*=";color:#CC3333" i],
    [style^="color: rgb(204, 51, 51)" i], [style*="; color: rgb(204, 51, 51)" i],
    [style^="color: #FF4D6A" i], [style*="; color: #FF4D6A" i],
    [style*=";color:#FF4D6A" i],
    [style^="color: rgb(255, 77, 106)" i], [style*="; color: rgb(255, 77, 106)" i],
    [style^="color: #FF6B6B" i], [style*="; color: #FF6B6B" i],
    [style*=";color:#FF6B6B" i],
    [style^="color: rgb(255, 107, 107)" i], [style*="; color: rgb(255, 107, 107)" i],
    [style^="color: #E06C75" i], [style*="; color: #E06C75" i],
    [style*=";color:#E06C75" i],
    [style^="color: rgb(224, 108, 117)" i], [style*="; color: rgb(224, 108, 117)" i]
) { color: var(--ua-red) !important; opacity: 1 !important; }

html[data-ua-theme="light"] :is(
    [style^="color: #00C8E0" i], [style*="; color: #00C8E0" i],
    [style^="color:#00C8E0" i],  [style*=";color:#00C8E0" i],
    [style^="color: rgb(0, 200, 224)" i], [style*="; color: rgb(0, 200, 224)" i],
    [style^="color: #0EA5E9" i], [style*="; color: #0EA5E9" i],
    [style*=";color:#0EA5E9" i],
    [style^="color: rgb(14, 165, 233)" i], [style*="; color: rgb(14, 165, 233)" i],
    [style^="color: #4A9EFF" i], [style*="; color: #4A9EFF" i],
    [style*=";color:#4A9EFF" i],
    [style^="color: rgb(74, 158, 255)" i], [style*="; color: rgb(74, 158, 255)" i],
    [style^="color: #55A7D8" i], [style*="; color: #55A7D8" i],
    [style*=";color:#55A7D8" i],
    [style^="color: rgb(85, 167, 216)" i], [style*="; color: rgb(85, 167, 216)" i],
    [style^="color: #67E8F9" i], [style*="; color: #67E8F9" i],
    [style*=";color:#67E8F9" i],
    [style^="color: rgb(103, 232, 249)" i], [style*="; color: rgb(103, 232, 249)" i],
    [style^="color: #72D6E2" i], [style*="; color: #72D6E2" i],
    [style*=";color:#72D6E2" i],
    [style^="color: rgb(114, 214, 226)" i], [style*="; color: rgb(114, 214, 226)" i]
) { color: var(--ua-cyan) !important; opacity: 1 !important; }

html[data-ua-theme="light"] :is(
    [style^="color: #F59E0B" i], [style*="; color: #F59E0B" i],
    [style^="color:#F59E0B" i],  [style*=";color:#F59E0B" i],
    [style^="color: rgb(245, 158, 11)" i], [style*="; color: rgb(245, 158, 11)" i],
    [style^="color: #FFB347" i], [style*="; color: #FFB347" i],
    [style*=";color:#FFB347" i],
    [style^="color: rgb(255, 179, 71)" i], [style*="; color: rgb(255, 179, 71)" i],
    [style^="color: #E8C766" i], [style*="; color: #E8C766" i],
    [style*=";color:#E8C766" i],
    [style^="color: rgb(232, 199, 102)" i], [style*="; color: rgb(232, 199, 102)" i],
    [style^="color: #E7C063" i], [style*="; color: #E7C063" i],
    [style*=";color:#E7C063" i],
    [style^="color: rgb(231, 192, 99)" i], [style*="; color: rgb(231, 192, 99)" i],
    [style^="color: #D8C08A" i], [style*="; color: #D8C08A" i],
    [style*=";color:#D8C08A" i],
    [style^="color: rgb(216, 192, 138)" i], [style*="; color: rgb(216, 192, 138)" i],
    [style^="color: #F97316" i], [style*="; color: #F97316" i],
    [style*=";color:#F97316" i],
    [style^="color: rgb(249, 115, 22)" i], [style*="; color: rgb(249, 115, 22)" i]
) { color: var(--ua-amber) !important; opacity: 1 !important; }

html[data-ua-theme="light"] :is(
    [style^="color: #7C3AED" i], [style*="; color: #7C3AED" i],
    [style*=";color:#7C3AED" i],
    [style^="color: rgb(124, 58, 237)" i], [style*="; color: rgb(124, 58, 237)" i],
    [style^="color: #A78BFA" i], [style*="; color: #A78BFA" i],
    [style*=";color:#A78BFA" i],
    [style^="color: rgb(167, 139, 250)" i], [style*="; color: rgb(167, 139, 250)" i],
    [style^="color: #A855F7" i], [style*="; color: #A855F7" i],
    [style*=";color:#A855F7" i],
    [style^="color: rgb(168, 85, 247)" i], [style*="; color: rgb(168, 85, 247)" i],
    [style^="color: #818CF8" i], [style*="; color: #818CF8" i],
    [style*=";color:#818CF8" i],
    [style^="color: rgb(129, 140, 248)" i], [style*="; color: rgb(129, 140, 248)" i],
    [style^="color: #B79CFF" i], [style*="; color: #B79CFF" i],
    [style*=";color:#B79CFF" i],
    [style^="color: rgb(183, 156, 255)" i], [style*="; color: rgb(183, 156, 255)" i]
) { color: var(--ua-purple) !important; opacity: 1 !important; }

html[data-ua-theme="light"] :is(
    [style^="color: #8892AA" i], [style*="; color: #8892AA" i],
    [style*=";color:#8892AA" i],
    [style^="color: rgb(136, 146, 170)" i], [style*="; color: rgb(136, 146, 170)" i],
    [style^="color: #6B7FBF" i], [style*="; color: #6B7FBF" i],
    [style*=";color:#6B7FBF" i],
    [style^="color: rgb(107, 127, 191)" i], [style*="; color: rgb(107, 127, 191)" i],
    [style^="color: #6B7280" i], [style*="; color: #6B7280" i],
    [style*=";color:#6B7280" i],
    [style^="color: rgb(107, 114, 128)" i], [style*="; color: rgb(107, 114, 128)" i]
) { color: var(--ua-neutral) !important; opacity: 1 !important; }

html[data-ua-theme="light"] :is(
    [style^="color: #B8C0D4" i], [style*="; color: #B8C0D4" i],
    [style*=";color:#B8C0D4" i],
    [style^="color: rgb(184, 192, 212)" i], [style*="; color: rgb(184, 192, 212)" i],
    [style^="color: #C5CCDE" i], [style*="; color: #C5CCDE" i],
    [style*=";color:#C5CCDE" i],
    [style^="color: rgb(197, 204, 222)" i], [style*="; color: rgb(197, 204, 222)" i],
    [style^="color: #E8EEFF" i], [style*="; color: #E8EEFF" i],
    [style*=";color:#E8EEFF" i],
    [style^="color: rgb(232, 238, 255)" i], [style*="; color: rgb(232, 238, 255)" i]
) { color: var(--ua-ink) !important; }

/* The premium theme defines these controls after the shared header and pins
   dark fills with !important. The light-prefixed rules deliberately carry
   greater specificity, so pills, ticker choices, and selected states remain
   readable without relying on generated Streamlit class names. */
html[data-ua-theme="light"] [data-testid="stButtonGroup"] button,
html[data-ua-theme="light"] [data-testid="stButtonGroup"] label {
    background: var(--ua-bg-card) !important;
    border-color: var(--ua-hair) !important;
    color: var(--ua-ink-soft) !important;
}
html[data-ua-theme="light"] [data-testid="stButtonGroup"] button p,
html[data-ua-theme="light"] [data-testid="stButtonGroup"] label p {
    color: var(--ua-ink-soft) !important;
}
html[data-ua-theme="light"] [data-testid="stButtonGroup"] button:hover,
html[data-ua-theme="light"] [data-testid="stButtonGroup"] label:hover {
    background: rgba(var(--ua-royal-rgb),0.06) !important;
    border-color: rgba(var(--ua-royal-rgb),0.28) !important;
}
html[data-ua-theme="light"] [data-testid="stButtonGroup"] button[aria-checked="true"],
html[data-ua-theme="light"] [data-testid="stButtonGroup"] button[aria-pressed="true"],
html[data-ua-theme="light"] [data-testid="stButtonGroup"] label:has(input:checked) {
    background: rgba(var(--ua-royal-rgb),0.12) !important;
    border-color: rgba(var(--ua-royal-rgb),0.42) !important;
    color: var(--ua-ink) !important;
}
html[data-ua-theme="light"] [data-testid="stButtonGroup"] button[aria-checked="true"] p,
html[data-ua-theme="light"] [data-testid="stButtonGroup"] button[aria-pressed="true"] p,
html[data-ua-theme="light"] [data-testid="stButtonGroup"] label:has(input:checked) p {
    color: var(--ua-ink) !important;
}

html[data-ua-theme="light"] .ua-guide-shell {
    background:
        radial-gradient(circle at 92% -10%, rgba(var(--ua-purple-rgb),0.08), transparent 34%),
        var(--ua-bg-card) !important;
    border-color: rgba(var(--ua-cyan-rgb),0.24) !important;
}
html[data-ua-theme="light"] .ua-guide-kicker { color: var(--ua-cyan) !important; }
html[data-ua-theme="light"] .ua-guide-title { color: var(--ua-ink) !important; }
html[data-ua-theme="light"] .ua-guide-intro,
html[data-ua-theme="light"] .ua-guide-step-body { color: var(--ua-ink-mut) !important; }
html[data-ua-theme="light"] .ua-guide-step-title { color: var(--ua-ink-soft) !important; }
html[data-ua-theme="light"] .ua-guide-step {
    background: rgba(var(--ua-card-rgb),0.82) !important;
    border-color: var(--ua-hair) !important;
}
html[data-ua-theme="light"] .ua-guide-step:hover {
    background: var(--ua-bg-card) !important;
    border-color: rgba(var(--ua-cyan-rgb),0.24) !important;
}
html[data-ua-theme="light"] .ua-guide-step-num {
    color: var(--ua-cyan) !important;
    border-color: rgba(var(--ua-cyan-rgb),0.30) !important;
}
.metric-card:hover, .page-card:hover,
[data-testid="stMetric"]:hover, [data-testid="stExpander"]:hover {
    border-color: rgba(var(--ua-onbg-rgb),0.14) !important;
    box-shadow: none !important;
    transform: none !important;
}
.stButton > button, .stDownloadButton > button,
[data-testid="stPopover"] > button {
    border-radius: 6px !important;
    box-shadow: none !important;
    font-weight: 600 !important;
}
[data-testid="stPlotlyChart"] {
    background: var(--ua-bg-card) !important;
    border: 1px solid var(--ua-hair) !important;
    border-radius: 8px !important;
    padding: 4px !important;
    box-shadow: none !important;
}
[data-testid="stPlotlyChart"]:hover { box-shadow: none !important; }
.ua-slide-up, .main .block-container,
[data-testid="stMainBlockContainer"] {
    animation: none !important;
}
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
}
</style>
"""

# _DARK_CSS is kept for backward compat but no longer needed — dark IS the default.
_DARK_CSS = "<style>/* dark mode is now the default design */</style>"

_DARK_JS = ""  # No longer needed — dark is the permanent design.


def render_dark_mode_toggle() -> None:
    """No-op: dark mode is now the permanent base design, toggle removed."""
    pass


def render_data_unavailable_banner(n_unavailable: int, n_total: int) -> None:
    """Disclose that missing providers were excluded, never replaced or scored.

    The treatment is PROPORTIONATE to impact. A few signals down out of 47 is a
    minor, routine degradation (weekly/monthly series between releases, a brief
    provider hiccup) — a calm amber notice keeps the disclosure honest without
    the alarm fatigue of a full-red "everything is broken" box on every load.
    Only when a material share is unavailable does it escalate to the loud red
    treatment, because at that point coverage really is compromised. The honest
    content — exact counts, "excluded", "no synthetic" — is identical either way.
    """
    if n_unavailable <= 0:
        return

    _major = n_unavailable >= max(1, round(0.15 * max(1, n_total)))  # ~15%+ down

    if _major:
        st.markdown(f"""
    <div style="background:rgba(var(--ua-red-rgb),0.08);color:#FF8888;border-radius:10px;padding:12px 18px;
                margin-bottom:14px;font-family:Inter,sans-serif;font-size:0.83rem;
                border:1px solid rgba(var(--ua-red-rgb),0.3);border-left:3px solid var(--ua-red);">
        <b style="color:#E06C75;">REAL DATA UNAVAILABLE</b> — {n_unavailable} of {n_total} signals could not be
        loaded from their source and have been excluded from scores, rankings, and
        exports. No placeholder or synthetic observations are used. Check provider
        credentials under Setup or try again after the source recovers.
    </div>
    """, unsafe_allow_html=True)
    else:
        _live = n_total - n_unavailable
        st.markdown(f"""
    <div style="background:rgba(224,169,59,0.06);color:#D8C08A;border-radius:10px;padding:11px 16px;
                margin-bottom:14px;font-family:Inter,sans-serif;font-size:0.8rem;
                border:1px solid rgba(224,169,59,0.28);border-left:3px solid #E0A93B;">
        <b style="color:#E7C063;">PARTIAL DATA</b> — {n_unavailable} of {n_total} signals are temporarily
        unavailable from their source and have been excluded from scores and rankings;
        the other {_live} are live. No placeholder or synthetic observations are used.
    </div>
    """, unsafe_allow_html=True)


def count_unavailable_signals(all_signals: dict) -> tuple[int, int]:
    """Return unavailable and total counts from a shared signal-score mapping."""
    if not all_signals:
        return 0, 0
    total = len(all_signals)
    unavailable = sum(1 for sv in all_signals.values()
                      if isinstance(sv, dict) and (sv.get("unavailable") or sv.get("error")))
    return unavailable, total


def disclose_unavailable_signals(all_signals: dict) -> int:
    """Render the real-data availability notice and return the excluded count."""
    n_unavailable, n_total = count_unavailable_signals(all_signals)
    render_data_unavailable_banner(n_unavailable, n_total)
    return n_unavailable


def render_data_quality_strip(all_signals: dict) -> None:
    """Show compact, reusable provenance and freshness context."""
    if not all_signals:
        return
    from utils.provider_health import summarize_signal_quality

    quality = summarize_signal_quality(all_signals)
    available = quality["total"] - quality["unavailable"]
    secondary = []
    if quality["cached_live"]:
        secondary.append(f'{quality["cached_live"]} cached live')
    if quality["delayed"]:
        secondary.append(f'{quality["delayed"]} delayed')
    detail = " · ".join(secondary) or "all available observations within expected cadence"
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;
                    flex-wrap:wrap;background:#0F141C;border:1px solid rgba(var(--ua-cyan-rgb),0.20);
                    border-left:3px solid #00AFC4;border-radius:8px;padding:11px 14px;
                    margin:0 0 16px;font-family:Inter,sans-serif;">
          <div>
            <div style="font-size:0.67rem;font-weight:750;letter-spacing:0.09em;
                        text-transform:uppercase;color:#8ECAD3;">Data quality</div>
            <div style="font-size:0.78rem;color:#C6CEDD;margin-top:3px;">
              <strong style="color:#E7ECF5;">{available} of {quality['total']} signals available</strong>
              <span style="color:#7F8BA3;"> · {detail}. No synthetic observations.</span>
            </div>
          </div>
          <a href="/signal-research?section=data-quality" style="font-size:0.70rem;color:#9EDBE3;text-decoration:none;
                    font-weight:700;white-space:nowrap;border:1px solid rgba(var(--ua-cyan-rgb),0.22);
                    border-radius:6px;padding:6px 9px;">View data quality</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ticker_label(ticker: str) -> str:
    """'TICKER (Full Company Name)' when the company name is known, else just the ticker."""
    company = TICKERS.get(ticker, {}).get("name", "")
    return f"{ticker} ({company})" if company else ticker


def go_to_ticker(ticker: str, key: str) -> None:
    """
    Render a clickable ticker chip showing "TICKER (Company Name)".
    On click: set session_state.selected_ticker and switch to Ticker Deep Dive.
    `key` must be globally unique across the page.
    """
    if st.button(ticker_label(ticker), key=key, help=f"Deep dive: {ticker}", width="stretch"):
        st.session_state["selected_ticker"] = ticker
        st.switch_page("pages/3_Ticker_Deep_Dive.py")


def ticker_chips(tickers: list, key_prefix: str, per_row: int = 3) -> None:
    """
    Render clickable ticker chip buttons in a grid (default 3 per row, since
    each chip now shows the full company name and needs more width than a
    bare ticker symbol). `key_prefix` must be unique per call site.
    """
    if not tickers:
        return
    for row_start in range(0, len(tickers), per_row):
        row_tickers = tickers[row_start:row_start + per_row]
        cols = st.columns(per_row)
        for col, t in zip(cols, row_tickers):
            with col:
                go_to_ticker(t, key=f"chip_{key_prefix}_{t}")


def _normalize_global_ticker_pick(value) -> str:
    """Normalize an existing or user-entered ticker selection."""
    return str(value or "").upper().strip()


def _resolve_global_ticker_query(query, symbol_index: dict[str, str]) -> tuple[str | None, list[str]]:
    """Resolve an exact ticker first, then a unique company-name match.

    Returning ambiguous candidates instead of guessing prevents prefix collisions
    such as AMD being silently replaced by AMDC.
    """
    raw = str(query or "").strip()
    normalized = _normalize_global_ticker_pick(raw)
    if not normalized:
        return None, []
    if normalized in symbol_index:
        return normalized, []

    folded = raw.casefold()
    exact_label = [
        symbol for symbol, label in symbol_index.items()
        if str(label).casefold() == folded
    ]
    if len(exact_label) == 1:
        return exact_label[0], []

    matches = [
        symbol for symbol, label in symbol_index.items()
        if folded in str(label).casefold()
    ]
    if len(matches) == 1:
        return matches[0], []
    return None, matches[:5]


def render_global_ticker_search() -> None:
    """
    Persistent ticker/company search shown in the header on every page.

    Resolution is server-side and exact-symbol-first. The previous 12,600-item
    selectbox let Streamlit's fuzzy matcher replace AMD with AMDC when Enter was
    pressed, and shipped the entire symbol directory to every browser session.
    A compact form keeps Enter-to-open behavior, resolves unique company names,
    and only scans the cached directory after submission.

    Only a submitted form can navigate, so normal Streamlit reruns never bounce
    the user back to Deep Dive. Re-submitting the same ticker remains valid.
    """
    # Search the FULL US-listed universe (~12.6k symbols via utils.symbols), not
    # just our 280 scored tickers. The cached directory stays server-side and is
    # scanned only after submission, avoiding a 12.6k-option browser payload.
    # Degrades to the tracked list if the directory is unavailable.
    try:
        from utils.symbols import get_symbol_index
        _sym_idx = dict(get_symbol_index())
        for _t in TICKERS:
            if _t in _sym_idx:
                _sym_idx[_t] = f"{_sym_idx[_t]} — Core"
    except Exception:
        _sym_idx = {}

    if not _sym_idx:
        _sym_idx = {ticker: ticker_label(ticker) for ticker in sorted(TICKERS)}

    _, search_col, _ = st.columns([2.3, 3.5, 1.0])
    with search_col:
        with st.form("global_ticker_search_form", border=False):
            query_col, submit_col = st.columns([4.5, 1.6], vertical_alignment="bottom")
            with query_col:
                query = st.text_input(
                    "Jump to a ticker",
                    placeholder="Ticker or company",
                    key="global_ticker_search",
                    label_visibility="collapsed",
                )
            with submit_col:
                submitted = st.form_submit_button(
                    "Analyze ticker",
                    key="global_ticker_submit",
                    width="stretch",
                )

    if not submitted:
        return
    picked, candidates = _resolve_global_ticker_query(query, _sym_idx)
    if not picked:
        hint = f" Try one of: {', '.join(candidates)}." if candidates else ""
        st.caption(f"Enter an exact ticker or a unique company name.{hint}")
        return
    if picked:
        st.session_state["selected_ticker"] = picked
        st.switch_page("pages/3_Ticker_Deep_Dive.py")


def _render_topnav() -> None:
    """
    Inject the sticky 46 px horizontal top-nav that replaces Streamlit's sidebar.
    Hides the native sidebar + Streamlit chrome via CSS, then renders a fixed bar
    with CSS-only hover dropdowns that mirror app.py's navigation groups.
    Called as the very first thing in render_header().

    Rendered via st.html() (NOT st.markdown) on purpose: the nav markup is
    multi-line and indented, and Streamlit's markdown parser treats blank-line-
    then-4-space-indented HTML as an indented CODE BLOCK — which was dumping the
    raw <div class="ua-tnav-group">… source as literal text in the middle of
    every page. st.html injects raw HTML with no markdown processing, so the
    indentation is harmless.
    """
    # Pro members see a small "PRO" badge in place of the "Upgrade" CTA;
    # admins see an "ADMIN" badge. Tier is read via effective_is_pro() (DB-backed,
    # session-cached) because the safe session identity intentionally does not
    # carry subscription_tier, so reading that key would always fail.
    from utils.billing import effective_is_pro, is_admin
    _hdr_user = st.session_state.get("user")
    _hdr_admin = is_admin(_hdr_user)
    if _hdr_admin:
        _upgrade_slot = '<span class="ua-tnav-pro ua-tnav-admin" title="Admin access">ADMIN</span>'
    elif effective_is_pro(_hdr_user):
        _upgrade_slot = '<span class="ua-tnav-pro" title="You\'re on Pro">PRO</span>'
    else:
        _upgrade_slot = '<a class="ua-tnav-upgrade" href="/upgrade-to-pro">Upgrade</a>'
    # Admin-only nav entry — only rendered for admins, invisible to everyone else.
    _admin_nav_slot = (
        '<div class="ua-tnav-drop-rule"></div>'
        '<a href="/admin" style="color:#E8C766;">Admin</a>'
    ) if _hdr_admin else ""

    # Keep page state when switching themes. A query-only link preserves the
    # current path, but a bare ?theme=... used to discard ticker, comparison,
    # referral, and filtered-view parameters. The link remains a real,
    # keyboard-accessible anchor; only its safely escaped query string changes.
    _query_values: dict[str, list[str]] = {}
    try:
        _query_values = {
            str(key): [str(value) for value in st.query_params.get_all(key)]
            for key in st.query_params
        }
    except Exception:
        pass
    _light_theme_href = html_escape(_theme_switch_href("light", _query_values), quote=True)
    _dark_theme_href = html_escape(_theme_switch_href("dark", _query_values), quote=True)
    st.html(("""
<style>
/* ── Hide native sidebar + Streamlit chrome ──────────────────────────────── */
section[data-testid="stSidebar"]          { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
header[data-testid="stHeader"]            { display: none !important; }
#MainMenu, footer                         { display: none !important; }
[data-testid="stMain"]                    { margin-left: 0 !important; }
[data-testid="stAppViewContainer"] > section { padding-left: 0 !important; }
/* Push page content below the 46px fixed nav bar */
.block-container { padding-top: 60px !important; }

/* ── Topnav shell ─────────────────────────────────────────────────────────── */
.ua-topnav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 99999;
  height: 46px;
  background: rgba(9,11,17,0.97);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 1px solid var(--ua-hair-2);
  display: flex; align-items: center;
  padding: 0 16px; gap: 0;
  font-family: 'Inter', -apple-system, sans-serif;
  box-shadow: 0 2px 20px rgba(var(--ua-shadow-rgb),calc(0.4*var(--ua-shadow-k)));
}

/* ── Brand ────────────────────────────────────────────────────────────────── */
.ua-tnav-brand {
  text-decoration: none !important; margin-right: 18px; flex-shrink: 0;
}
.ua-tnav-brand-text {
  font-size: 0.76rem; font-weight: 800; letter-spacing: -0.2px;
  color: var(--ua-ink); white-space: nowrap;
}
.ua-tnav-brand-text em {
  font-style: normal;
  background: linear-gradient(120deg,
      var(--ua-brand-alpha-1) 0%,
      var(--ua-brand-alpha-2) 58%,
      var(--ua-brand-alpha-3) 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* ── Links row ────────────────────────────────────────────────────────────── */
.ua-tnav-links { display: flex; align-items: center; gap: 0; flex: 1; overflow: visible; }

/* ── Direct link ──────────────────────────────────────────────────────────── */
a.ua-tnav-item {
  display: inline-flex; align-items: center;
  padding: 4px 9px; border-radius: 6px; height: 30px;
  font-size: 0.74rem; font-weight: 500; color: var(--ua-ink-mut);
  text-decoration: none !important; white-space: nowrap;
  transition: color .12s ease, background .12s ease;
}
a.ua-tnav-item:hover { color: var(--ua-ink); background: var(--ua-hair-2); }
a.ua-tnav-item.active { color: #B7BEFB !important; background: rgba(var(--ua-royal-rgb),0.12) !important; }

/* ── Dropdown group ───────────────────────────────────────────────────────── */
.ua-tnav-group { position: relative; display: inline-flex; align-items: center; }
.ua-tnav-trigger {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 4px 9px; border-radius: 6px; height: 30px;
  font-size: 0.74rem; font-weight: 500; color: var(--ua-ink-mut);
  cursor: pointer; white-space: nowrap; user-select: none;
  transition: color .12s ease, background .12s ease;
}
.ua-tnav-group:hover > .ua-tnav-trigger { color: var(--ua-ink); background: var(--ua-hair-2); }
.ua-tnav-trigger.active { color: var(--ua-green) !important; background: rgba(var(--ua-green-rgb),0.08) !important; }
.ua-tnav-caret {
  font-size: 0.45rem; opacity: .38; line-height: 1;
  display: inline-block; transition: transform .13s ease;
}
.ua-tnav-group:hover .ua-tnav-caret { transform: rotate(180deg); opacity: .72; }

/* ── Dropdown panel ───────────────────────────────────────────────────────── */
.ua-tnav-drop {
  visibility: hidden; opacity: 0; pointer-events: none;
  position: absolute; top: calc(100% + 4px); left: 0;
  min-width: 172px;
  background: rgba(12,14,22,0.98);
  border: 1px solid var(--ua-hair); border-radius: 10px;
  padding: 6px;
  box-shadow: 0 20px 60px rgba(var(--ua-shadow-rgb),calc(0.7*var(--ua-shadow-k))), 0 0 0 1px rgba(var(--ua-onbg-rgb),0.03);
  backdrop-filter: blur(24px);
  display: flex; flex-direction: column; gap: 4px;
  z-index: 100001;
  /* Close only after a short grace period, so moving the cursor from the trigger
     down into the menu doesn't snap it shut mid-transit. Opens instantly (the
     hover rule below zeroes the delay). This is the fix for "the dropdown
     disappears before I can click a sub-page." */
  transition: opacity .14s ease .28s, visibility .14s ease .28s;
}
/* Invisible bridge that fills the 4px gap between the trigger and the menu, so
   the cursor never crosses an un-hovered dead zone on its way to the items. */
.ua-tnav-drop::before {
  content: ""; position: absolute; left: 0; right: 0; top: -10px; height: 10px;
}
.ua-tnav-group:hover .ua-tnav-drop,
.ua-tnav-drop:hover {
  visibility: visible; opacity: 1; pointer-events: auto; transition-delay: 0s;
}
.ua-tnav-drop a {
  display: flex; align-items: center; justify-content: space-between; gap: 14px;
  padding: 8px 10px; border-radius: 7px;
  background: rgba(var(--ua-onbg-rgb),0.025);
  border: 1px solid rgba(var(--ua-onbg-rgb),0.075);
  font-size: 0.74rem; font-weight: 500; color: var(--ua-ink-soft);
  text-decoration: none !important; white-space: nowrap;
  transition: color .12s ease, background .12s ease, border-color .12s ease,
              transform .12s ease, box-shadow .12s ease;
}
.ua-tnav-drop a:hover {
  color: var(--ua-ink);
  background: rgba(var(--ua-royal-rgb),0.10);
  border-color: rgba(var(--ua-royal-rgb),0.42);
  box-shadow: inset 2px 0 0 rgba(var(--ua-royal-rgb),0.88);
  transform: translateX(1px);
}
.ua-tnav-drop a.active {
  color: var(--ua-green) !important;
  background: rgba(var(--ua-green-rgb),0.09) !important;
  border-color: rgba(var(--ua-green-rgb),0.34) !important;
  box-shadow: inset 2px 0 0 rgba(var(--ua-green-rgb),0.88);
}
.ua-tnav-drop a.pro-link {
  color: #C4B5FD;
  background: rgba(var(--ua-purple-rgb),0.08);
  border-color: rgba(var(--ua-purple-rgb),0.25);
}
.ua-tnav-drop a.pro-link::after {
  content: "PRO";
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 28px; padding: 2px 5px; border-radius: 999px;
  background: rgba(var(--ua-purple-rgb),0.18);
  border: 1px solid rgba(var(--ua-purple-rgb),0.38);
  color: #D8CCFF; font-size: 0.50rem; font-weight: 800;
  line-height: 1; letter-spacing: 0.08em;
}
.ua-tnav-drop a.pro-link:hover {
  color: #E2D9FF;
  background: rgba(var(--ua-purple-rgb),0.15);
  border-color: rgba(var(--ua-purple-rgb),0.52);
  box-shadow: inset 2px 0 0 rgba(var(--ua-purple-rgb),0.95);
}
.ua-tnav-drop-rule { height: 1px; background: var(--ua-hair-3); margin: 3px 2px; }

/* ── Right controls ───────────────────────────────────────────────────────── */
.ua-tnav-right { display: flex; align-items: center; gap: 7px; flex-shrink: 0; margin-left: 8px; }
.ua-tnav-upgrade {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 5px 12px; height: 30px;
  background: linear-gradient(135deg, var(--ua-purple), #6D28D9);
  color: #fff !important; font-size: 0.72rem; font-weight: 700;
  border-radius: 6px; text-decoration: none !important; letter-spacing: 0.01em;
  transition: all .14s ease; white-space: nowrap; flex-shrink: 0;
}
.ua-tnav-upgrade:hover {
  background: linear-gradient(135deg, #8B5CF6, var(--ua-purple));
  box-shadow: 0 0 18px rgba(var(--ua-purple-rgb),0.45);
}
/* Pro members: small non-clickable status pill instead of the Upgrade CTA */
.ua-tnav-pro {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 4px 10px; height: 26px;
  background: rgba(var(--ua-purple-rgb),0.12);
  color: #C4B5FD; font-size: 0.66rem; font-weight: 700;
  border: 1px solid rgba(var(--ua-purple-rgb),0.35);
  border-radius: 6px; letter-spacing: 0.05em; white-space: nowrap; flex-shrink: 0;
  cursor: default;
}
/* Admin variant — gold, to distinguish from the purple Pro pill */
.ua-tnav-admin {
  background: rgba(212,175,55,0.12);
  color: #E8C766;
  border-color: rgba(212,175,55,0.40);
}
/* Pale gold/lilac are legible on a dark bar but wash out on the white
   light-mode nav, so light uses the deep variants. */
html[data-ua-theme="light"] .ua-tnav-admin {
  background: rgba(156,122,44,0.10);
  color: #7A5E1E;
  border-color: rgba(156,122,44,0.35);
}
html[data-ua-theme="light"] .ua-tnav-pro:not(.ua-tnav-admin) {
  color: #4B2A91;
  background: rgba(var(--ua-purple-rgb),0.12);
  border-color: rgba(var(--ua-purple-rgb),0.38);
}

/* ── Mobile hamburger (JS-free checkbox toggle) ───────────────────────────── */
.ua-tnav-toggle { display: none; }            /* the open/closed state checkbox */
.ua-tnav-burger {
  display: none;                              /* hidden on desktop */
  flex-direction: column; justify-content: center; gap: 4px;
  width: 34px; height: 30px; padding: 6px; margin-left: 6px;
  border-radius: 7px; cursor: pointer; flex-shrink: 0;
}
.ua-tnav-burger span {
  display: block; height: 2px; width: 20px; border-radius: 2px;
  background: #C3CBE0; transition: background .18s ease;
}
.ua-tnav-burger:hover span { background: var(--ua-ink); }

/* Tap-to-open / keyboard-open dropdowns without needing hover (touch + a11y). */
.ua-tnav-group:focus-within > .ua-tnav-drop { visibility: visible; opacity: 1; pointer-events: auto; transition-delay: 0s; }

/* ── Responsive ───────────────────────────────────────────────────────────── */
@media (max-width: 860px) {
  /* The horizontal links become a full-width vertical menu revealed by the
     burger, with EVERY group expanded so all sub-pages are reachable by tap —
     the desktop hover dropdowns don't work on touch. This is what makes the
     whole app navigable on a phone. */
  .ua-tnav-burger { display: flex; }
  .ua-tnav-right  { order: 2; margin-left: auto; }
  .ua-tnav-burger { order: 3; }
  .ua-tnav-links {
    display: none; order: 4;
    position: absolute; top: 100%; left: 0; right: 0;
    flex-direction: column; align-items: stretch; gap: 1px;
    background: rgba(9,11,17,0.99);
    border-bottom: 1px solid var(--ua-hair);
    box-shadow: 0 24px 60px rgba(var(--ua-shadow-rgb),calc(0.75*var(--ua-shadow-k)));
    backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
    padding: 6px 10px 16px; max-height: 84vh; overflow-y: auto;
  }
  html[data-ua-theme="light"] .ua-tnav-links {
    background: rgba(255,255,255,0.99);
    border-bottom-color: var(--ua-hair);
  }
  html[data-ua-theme="light"] .ua-tnav-burger span {
    background: var(--ua-ink-soft);
  }
  html[data-ua-theme="light"] .ua-tnav-drop a.pro-link {
    color: var(--ua-purple) !important;
  }
  .ua-tnav-toggle:checked ~ .ua-tnav-links { display: flex; }
  .ua-tnav-item { width: 100%; height: auto; padding: 11px 8px; font-size: 0.86rem; }
  .ua-tnav-group { display: block; width: 100%; }
  .ua-tnav-trigger {
    width: 100%; height: auto; padding: 12px 8px 4px; font-size: 0.62rem;
    font-weight: 700; letter-spacing: 0.10em; text-transform: uppercase;
    color: var(--ua-ink-label); cursor: default;
  }
  .ua-tnav-caret { display: none; }
  .ua-tnav-drop {
    position: static; visibility: visible; opacity: 1; pointer-events: auto;
    box-shadow: none; background: transparent; border: none; min-width: 0;
    backdrop-filter: none; -webkit-backdrop-filter: none;
    padding: 0 0 6px 8px; transition: none; z-index: auto;
  }
  .ua-tnav-drop::before { display: none; }
  .ua-tnav-drop a { padding: 10px 10px; font-size: 0.84rem; }
  /* Now that the vertical menu has room, reveal the items that were hidden to
     fit the horizontal bar. */
  .ua-tnav-hide-sm { display: block !important; }
}
@media (max-width: 640px) {
  .ua-topnav { padding: 0 10px; }
  .ua-tnav-brand-text { font-size: 0.70rem; }
}
</style>

<nav class="ua-topnav" role="navigation" aria-label="Main navigation">
  <a class="ua-tnav-brand" href="/">
    <span class="ua-tnav-brand-text">UNSTRUCTURED <em>ALPHA</em></span>
  </a>

  <!-- Mobile menu toggle (JS-free): the checkbox holds open/closed state, the
       label is the hamburger button. Placed before .ua-tnav-links so the
       `.ua-tnav-toggle:checked ~ .ua-tnav-links` sibling selector reveals it. -->
  <input type="checkbox" id="ua-tnav-toggle" class="ua-tnav-toggle" aria-hidden="true" />
  <label for="ua-tnav-toggle" class="ua-tnav-burger" aria-label="Toggle navigation menu" role="button" tabindex="0">
    <span></span><span></span><span></span>
  </label>

  <!-- Consolidated 5-section IA (2026-07-13): Today · Portfolio · Research ·
       Signals & Methodology · Monitoring, + a demoted More cluster and the
       pinned Upgrade CTA. Stock Chart, Signal Strategy and Alternative Data were
       merged out of the visible nav (still URL-reachable; Signal Strategy is
       duplicated by Portfolio Suite's Signal Backtester tab). Every href here
       must have a matching url_path in app.py — keep them in sync. -->
  <div class="ua-tnav-links">
    <a class="ua-tnav-item" href="/" data-paths="/,/home">Home</a>
    <a class="ua-tnav-item" href="/today-s-brief">Today&#39;s Brief</a>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger">Portfolio <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/my-watchlist">My Watchlist</a>
        <a href="/portfolio-checkup">Portfolio Checkup</a>
        <a class="pro-link" href="/decision-queue">Decision Queue</a>
        <a class="pro-link" href="/thesis-journal">Thesis Journal</a>
        <a class="pro-link" href="/portfolio-suite">Portfolio Intelligence</a>
      </div>
    </div>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger">Research <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/ticker-deep-dive">Ticker Deep Dive</a>
        <a href="/stock-screener">Stock Screener</a>
        <a href="/power-supercycle">Power Supercycle</a>
        <a class="pro-link" href="/stock-recommender">Stock Recommender</a>
        <a class="pro-link" href="/options-flow">Options Flow</a>
      </div>
    </div>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger">Signals <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/signal-dashboard">Signal Dashboard</a>
        <a href="/market-overview">Market Overview</a>
        <a href="/sector-view">Sector View</a>
        <a href="/signal-research">Signal Research Center</a>
      </div>
    </div>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger">Monitoring <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/my-watchlist">Watchlist Alerts</a>
        <a class="pro-link" href="/events-forecasts">Catalyst Command Center</a>
      </div>
    </div>

    <div class="ua-tnav-group ua-tnav-hide-sm">
      <span class="ua-tnav-trigger">More <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/ai-research-assistant">AI Assistant</a>
        <a href="/my-profile">My Profile</a>
        <a href="/about-methodology">About &amp; Methodology</a>
        <div class="ua-tnav-drop-rule"></div>
        <a href="/privacy-terms" style="font-size:0.68rem;color:var(--ua-ink-label);">Privacy &amp; Terms</a>
        __ADMIN_NAV_SLOT__
      </div>
    </div>
  </div>

  <div class="ua-tnav-right">
    __UPGRADE_SLOT__
    <a class="ua-theme-toggle" data-to="light" href="__LIGHT_THEME_HREF__"
       role="button" aria-label="Switch to light theme" title="Switch to light theme"
       ><span class="ua-tt-ico" aria-hidden="true">&#9788;</span>LIGHT</a>
    <a class="ua-theme-toggle" data-to="dark" href="__DARK_THEME_HREF__"
       role="button" aria-label="Switch to dark theme" title="Switch to dark theme"
       ><span class="ua-tt-ico" aria-hidden="true">&#9789;</span>DARK</a>
  </div>
</nav>

<script>
(function(){
  try {
        var path = (window.location.pathname || '/').replace(/\\/+$/, '') || '/';
    document.querySelectorAll('.ua-tnav-drop a').forEach(function(a){
      var hp = (a.getAttribute('href') || '').replace(/\\/+$/, '') || '/';
      if (hp && hp === path) {
        a.classList.add('active');
        var grp = a.closest('.ua-tnav-group');
        if (grp) grp.querySelector('.ua-tnav-trigger').classList.add('active');
      }
    });
    var homeLink = document.querySelector('a.ua-tnav-item');
    if (homeLink && (path === '/' || path === '/home')) homeLink.classList.add('active');
  } catch(e){}
})();
</script>
""").replace("__UPGRADE_SLOT__", _upgrade_slot)
      .replace("__ADMIN_NAV_SLOT__", _admin_nav_slot)
      .replace("__LIGHT_THEME_HREF__", _light_theme_href)
      .replace("__DARK_THEME_HREF__", _dark_theme_href))


def _track_page_view(page_label: str) -> None:
    """
    Log one page_view analytics event per navigation (deduped per session so
    Streamlit reruns don't inflate traffic). Best-effort — never raises, never
    blocks (track() fires on a daemon thread). Powers the Admin traffic metrics.
    """
    try:
        label = (page_label or "Home").strip() or "Home"
        if st.session_state.get("_pv_tracked") == label:
            return  # already logged this page for the current navigation
        st.session_state["_pv_tracked"] = label

        sid = None
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            _ctx = get_script_run_ctx()
            sid = getattr(_ctx, "session_id", None) if _ctx else None
        except Exception:
            sid = None

        _u = st.session_state.get("user") or {}
        from utils.analytics import track, Event
        track(Event.PAGE_VIEW, user_id=_u.get("id"),
              properties={"page": label}, session_id=sid)
    except Exception:
        pass


def render_header(page_subtitle: str = "", hero_title: str = "", hero_sub: str = "") -> None:
    """
    Inject global CSS and render the Unstructured Alpha masthead.
    Call this immediately after st.set_page_config() on every page.

    Args:
        page_subtitle: Short section name shown on the right side of the header bar
                       (e.g. "Signal Dashboard", "Market Overview").
    """
    from datetime import datetime
    from utils.theme import _MODERN_UI_CSS, static_global_css_available

    # ── Correlation id for this session's log lines ────────────────────────────
    # Seed a stable per-session id once, then bind it to the current rerun's
    # log context so every [circuit]/[ratelimit]/event line during this run is
    # attributable to one browser session. Best-effort; never blocks a render.
    try:
        from utils.observability import set_correlation_id, new_correlation_id
        _cid = st.session_state.get("_cid")
        if not _cid:
            _cid = st.session_state["_cid"] = new_correlation_id()
        set_correlation_id(_cid)
    except Exception:
        pass

    # ── Horizontal topnav (replaces sidebar, hides Streamlit chrome) ───────────
    _render_topnav()

    # Traffic tracking (deduped per session+page) — feeds the Admin dashboard.
    _track_page_view(page_subtitle)

    # Session heartbeat. Duration is derived as (last event - first event) per
    # session, and with one page_view per session that difference was always
    # zero — which is why every duration percentile in the usage report read 0s.
    # Firing on each navigation gives multi-page sessions a real span.
    try:
        from utils.instrumentation import heartbeat
        heartbeat()
    except Exception:
        pass

    # Render/production generates one cacheable stylesheet in
    # scripts/inject_boot_splash.py. Keep this runtime path as a fail-safe for
    # local development or a failed optional build step; never leave the app
    # unstyled merely because the static asset is absent.
    if not static_global_css_available():
        st.markdown(_CSS, unsafe_allow_html=True)
        st.markdown(_MODERN_UI_CSS, unsafe_allow_html=True)
        try:
            from utils.ua_charts import CHART_CSS as _UA_CHART_CSS
            st.markdown(_UA_CHART_CSS, unsafe_allow_html=True)
        except Exception:
            pass

    # ── OpenGraph / social meta tags (JS injection) ────────────────────────────
    # Reddit's link scraper is server-side and won't execute this JS, but
    # Googlebot (which does execute JS) and Twitter's card validator will.
    # The title tag set by st.set_page_config IS visible to all scrapers.
    st.markdown("""
<script>
(function() {
    var metas = [
        {property: 'og:site_name',    content: 'Unstructured Alpha'},
        {property: 'og:type',         content: 'website'},
        {property: 'og:url',          content: 'https://unstructuredalpha.com'},
        {property: 'og:title',        content: 'Unstructured Alpha — 47-Signal Market Intelligence'},
        {property: 'og:description',  content: 'Research 47 registered signals across 13 real-data source families. Public validation and track record; deeper testing and research workflows in Pro.'},
        {name:     'description',     content: 'Research 47 registered signals across macro, market, filings, energy, contracts and alternative data. No synthetic placeholder observations.'},
        {name:     'twitter:card',    content: 'summary'},
        {name:     'twitter:title',   content: 'Unstructured Alpha — Alternative Data Intelligence'},
        {name:     'twitter:description', content: '47 macro signals scored daily. Free to browse. Insider trades, credit spreads, VIX term structure, copper/gold ratio and more.'},
    ];
    metas.forEach(function(m) {
        var el = document.createElement('meta');
        Object.keys(m).forEach(function(k) { el.setAttribute(k, m[k]); });
        document.head.appendChild(el);
    });
})();
</script>
""", unsafe_allow_html=True)

    # ── Scroll-to-top button ───────────────────────────────────────────────────
    st.markdown("""
<div id="ua-scroll-top" title="Back to top">↑</div>
<script>
(function() {
    var btn = document.getElementById('ua-scroll-top');
    if (!btn) return;
    var root = document.querySelector('[data-testid="stAppViewContainer"]') || window;
    function onScroll() {
        var y = (root === window) ? window.scrollY : root.scrollTop;
        btn.classList.toggle('visible', y > 300);
    }
    (root === window ? window : root).addEventListener('scroll', onScroll, {passive: true});
    btn.addEventListener('click', function() {
        if (root === window) window.scrollTo({top: 0, behavior: 'smooth'});
        else root.scrollTo({top: 0, behavior: 'smooth'});
    });
})();
</script>
""", unsafe_allow_html=True)

    # ── Live ticker strip ──────────────────────────────────────────────────────
    _render_live_ticker_strip()

    # Market open/closed status — NYSE regular hours, Mon-Fri 9:30-16:00 ET.
    # Best-effort only (no holiday calendar) — falls back to local time if
    # zoneinfo's tz database isn't available in the runtime environment.
    try:
        from zoneinfo import ZoneInfo
        _now_et = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        _now_et = datetime.now()
    _mins_et = _now_et.hour * 60 + _now_et.minute
    _market_open = (_now_et.weekday() < 5) and (9 * 60 + 30) <= _mins_et < 16 * 60
    _status_label = "MARKET OPEN" if _market_open else "MARKET CLOSED"
    _status_bg    = "rgba(var(--ua-green-rgb),0.10)" if _market_open else "rgba(var(--ua-red-rgb),0.08)"
    _status_fg    = "var(--ua-green)" if _market_open else "var(--ua-red)"
    _status_dot   = "var(--ua-green)" if _market_open else "var(--ua-red)"
    _time_str     = _now_et.strftime("%-I:%M %p ET")
    _date_str     = _now_et.strftime("%A, %B %-d, %Y")

    status_badge_html = (
        f'<span class="market-status-badge" style="background:{_status_bg};color:{_status_fg};">'
        f'<span class="market-status-dot" style="background:{_status_dot};"></span>{_status_label} · {_time_str}'
        f'</span>'
    )
    # User pill — shown inline in the header bar whenever someone is signed in
    _user = st.session_state.get("user")
    _user_email = (_user or {}).get("email", "")
    from utils.billing import effective_is_pro as _eip2, is_admin as _isadmin2
    _is_pro = _eip2(_user)
    _is_admin = _isadmin2(_user)
    _user_pill = ""
    if _user_email:
        if _is_admin:
            _tier_badge = (
                '<span style="background:#D4AF37;color:#1a1a1a;font-size:0.55rem;font-weight:700;'
                'padding:1px 5px;border-radius:4px;margin-left:4px;letter-spacing:0.04em;">ADMIN</span>'
            )
        elif _is_pro:
            _tier_badge = (
                '<span style="background:var(--ua-purple);color:#fff;font-size:0.55rem;font-weight:700;'
                'padding:1px 5px;border-radius:4px;margin-left:4px;letter-spacing:0.04em;">PRO</span>'
            )
        else:
            _tier_badge = ""
        _user_pill = (
            f'<span style="display:inline-flex;align-items:center;gap:4px;'
            f'background:rgba(var(--ua-green-rgb),0.08);border:1px solid rgba(var(--ua-green-rgb),0.2);'
            f'border-radius:6px;padding:2px 8px;font-size:0.68rem;color:var(--ua-green);'
            f'font-weight:600;font-family:Inter,sans-serif;white-space:nowrap;">'
            f'{_user_email}{_tier_badge}</span>'
        )

    right_html = (
        f"<b>{page_subtitle}</b><br>{_date_str}<br>{status_badge_html}"
        + (f"<br><div style='margin-top:5px;'>{_user_pill}</div>" if _user_pill else "")
        if page_subtitle else
        f"{_date_str}<br>{status_badge_html}"
        + (f"<br><div style='margin-top:5px;'>{_user_pill}</div>" if _user_pill else "")
    )

    # The left side is the brand wordmark on every page EXCEPT where a caller
    # passes a hero_title. The top nav already carries the wordmark, so on the
    # landing page repeating it here is pure duplication; leading with the value
    # proposition instead is both less redundant and a stronger first read.
    if hero_title:
        _left_html = (
            f'<div class="ua-hero-title">{hero_title}</div>'
            + (f'<div class="ua-hero-sub">{hero_sub}</div>' if hero_sub else "")
        )
    else:
        _left_html = (
            '<div class="ua-wordmark">UNSTRUCTURED <span>ALPHA</span></div>'
            '<div class="ua-tagline">Alternative Data Intelligence &mdash; what&rsquo;s coming, not what happened</div>'
        )

    st.markdown(f"""
    <div class="ua-header">
        <div class="ua-header-left">
            {_left_html}
        </div>
        <div class="ua-header-right">{right_html}</div>
    </div>
    <div class="gold-rule"></div>
    """, unsafe_allow_html=True)

    # ── Sticky Macro Regime Bar ────────────────────────────────────────────────
    # One slim line visible on every page so users never lose macro context.
    # Reads persisted signal snapshots only. A previous version called the full
    # 47-signal engine from global chrome, turning every cold page load into a
    # hidden provider sweep even when the page itself needed no macro data.
    try:
        from utils.score_history import get_latest_signal_states as _glss
        from utils.regime import compute_macro_regime
        _rs = _glss()
        # SSOT: the header bar and the home hero now classify the regime through
        # ONE function fed the SAME source (persisted snapshots). Previously each
        # rolled its own count off a different source, so the landing page showed
        # two contradictory reads. See utils/regime.py.
        _reg = compute_macro_regime(_rs, total=SIGNAL_COUNT)
        _rb, _rr, _rn = _reg.bullish, _reg.bearish, _reg.neutral
        _runavail = _reg.excluded
        _rs_date = max((str(v.get("snapshot_date") or "") for v in _rs.values()), default="")
        _regime_lbl, _regime_col, _regime_bg = _reg.label, _reg.color, _reg.bg
        st.markdown(
            f'<div style="background:{_regime_bg};border:1px solid var(--ua-hair-2);'
            f'border-left:3px solid {_regime_col};'
            f'border-radius:8px;padding:6px 14px;margin-bottom:12px;'
            f'display:flex;align-items:center;gap:16px;font-family:Inter,sans-serif;">'
            f'<span style="font-size:0.60rem;color:var(--ua-ink-mut);text-transform:uppercase;letter-spacing:0.11em;font-weight:700;">MACRO REGIME</span>'
            f'<span style="font-size:0.75rem;font-weight:700;color:{_regime_col};">● {_regime_lbl}</span>'
            f'<span style="font-size:0.68rem;color:var(--ua-ink-mut);">'
            f'<span style="color:var(--ua-green);">▲ {_rb}</span>'
            f' · <span style="color:var(--ua-red);">▼ {_rr}</span>'
            f' · <span style="color:var(--ua-ink-label);">→ {_rn}</span>'
            + (f' · <span style="color:var(--ua-ink-dim);" title="Signals with insufficient recent data this cycle">⊘ {_runavail}</span>' if _runavail else "")
            + f'</span>'
            f'<span style="font-size:0.60rem;color:var(--ua-ink-label);margin-left:auto;">'
            f'{SIGNAL_COUNT} signals · {"snapshot " + _rs_date if _rs_date else "no snapshot yet"}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    except Exception:
        pass  # never crash the header for a cosmetic bar

    # Global ticker search -- same reasoning as the account widget below:
    # a real Streamlit widget can't live inside the markdown block above,
    # so it's rendered here in its own row, automatically on every page
    # that calls render_header() (all of them).
    render_global_ticker_search()

    # ── Top-right widget row: notifications (logged-in only) + account ────────
    # Single st.columns() call so both widgets share one horizontal row.
    # Bell is only rendered for logged-in users (no point showing notifications
    # to a guest who has no account-linked data).
    from utils.auth_ui import get_cookies, try_restore_session, render_auth_forms, logout
    _cookies = get_cookies()
    _hdr_user = try_restore_session(_cookies)
    _uid = (_hdr_user or {}).get("id")

    _space, _bell_col, _acct_col = st.columns([3.9, 1.15, 1.35])

    _notification_api = None
    _unread = 0

    # Bell — logged-in users only
    if _uid:
        try:
            from utils.prediction_log import (
                clear_notifications, get_unread_notification_count,
                get_recent_notifications, mark_all_read,
            )
            _unread = get_unread_notification_count(_uid)
            _badge_text = f" {_unread if _unread < 100 else '99+'}" if _unread > 0 else ""
            _notification_api = (get_recent_notifications, mark_all_read, clear_notifications)
            with _bell_col:
                if st.button(
                    f"Notifications{_badge_text}",
                    key="_notification_tray_toggle",
                    width="stretch",
                ):
                    st.session_state["_notification_tray_open"] = not st.session_state.get(
                        "_notification_tray_open", False
                    )
        except Exception:
            pass  # Never crash the header for a notification badge

    # Account widget — all users
    with _acct_col:
        if _hdr_user:
            _identity_name = (_hdr_user.get("display_name") or "Account").strip()
            _identity_button = _identity_name if len(_identity_name) <= 20 else f"{_identity_name[:19]}…"
            with st.popover(_identity_button, width="stretch"):
                if _hdr_user.get("display_name"):
                    st.text(_hdr_user["display_name"])
                    st.caption(_hdr_user.get("email", ""))
                if st.button("My Profile", key="topright_profile", width="stretch"):
                    st.switch_page("pages/32_Profile.py")
                if st.button("Log Out", key="topright_logout", width="stretch"):
                    logout()
                    st.rerun()
        else:
            with st.popover("Sign In", width="stretch"):
                render_auth_forms(_cookies, key_prefix="widget_")

    # A compact, fixed-height tray in normal page flow. Keeping it outside a
    # popover prevents BaseWeb from flipping the panel upward when it estimates
    # that the viewport is constrained. Recent rows are fetched only while open.
    if _uid and _notification_api and st.session_state.get("_notification_tray_open", False):
        _notif_space, _notif_panel_col = st.columns([3.65, 1.35])
        with _notif_panel_col:
            with st.container(height=340, border=True):
                st.markdown(
                    '<span class="ua-notification-panel-marker"></span>'
                    '<div class="ua-notification-title">System Notifications</div>',
                    unsafe_allow_html=True,
                )
                _get_recent_notifications, _mark_all_read, _clear_notifications = _notification_api
                _notifs = _get_recent_notifications(limit=10, user_id=_uid)
                if not _notifs:
                    st.caption(
                        "No notifications yet. Convergence events and prediction resolutions will appear here."
                    )
                else:
                    _NOTIF_LABELS = {
                        "convergence":         "CONVERGENCE",
                        "regime_change":       "REGIME",
                        "near_flip":           "WATCH",
                        "prediction_resolved": "RESOLVED",
                    }
                    for _n in _notifs:
                        _type_label = _NOTIF_LABELS.get(_n.get("notif_type", ""), "UPDATE")
                        _n_border = "#35C98B" if _n.get("direction") == "bull" else (
                            "#E06C75" if _n.get("direction") == "bear" else "#6F7888"
                        )
                        _n_ts = html_escape(str(_n.get("created_at", ""))[:10])
                        _n_title = html_escape(str(_n.get("title", "")))
                        _n_body = html_escape(str(_n.get("body", "")))
                        st.markdown(
                            f'<div class="ua-notification-item" style="border-left-color:{_n_border};">'
                            f'<div class="ua-notification-kicker">{_type_label}</div>'
                            f'<div class="ua-notification-heading">{_n_title}</div>'
                            f'<div class="ua-notification-copy">{_n_body}</div>'
                            f'<div class="ua-notification-time">{_n_ts}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                if _notifs:
                    _read_col, _clear_col = st.columns(2)
                    if _unread > 0 and _read_col.button(
                        "Mark read",
                        key="_notif_mark_read",
                        width="stretch",
                    ):
                        _mark_all_read(_uid)
                        st.rerun()
                    if _clear_col.button(
                        "Clear",
                        key="_notif_clear",
                        width="stretch",
                        help="Remove all current notifications from your feed",
                    ):
                        if _clear_notifications(_uid):
                            st.rerun()
                        else:
                            st.error("Could not clear notifications. Try again.")


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def _fetch_ticker_strip():
    """Fetch live prices for the header ticker strip. 60s TTL, one set of symbols."""
    import yfinance as yf
    # Well-known large-cap stocks everyone recognizes — a market anchor (SPY)
    # plus the mega-cap names, rather than commodity/crypto futures symbols.
    _SYMBOLS = [
        ("SPY",  "S&P 500"),
        ("AAPL", "Apple"),
        ("MSFT", "Microsoft"),
        ("NVDA", "Nvidia"),
        ("AMZN", "Amazon"),
        ("GOOGL","Alphabet"),
        ("META", "Meta"),
        ("TSLA", "Tesla"),
        ("AMD",  "AMD"),
    ]
    results = []
    try:
        tickers = yf.Tickers(" ".join(s for s, _ in _SYMBOLS))
        for sym, label in _SYMBOLS:
            try:
                info = tickers.tickers[sym].fast_info
                price = getattr(info, "last_price", None)
                prev  = getattr(info, "previous_close", None)
                if price and prev and prev > 0:
                    chg_pct = (price - prev) / prev * 100
                    results.append((sym, label, price, chg_pct))
            except Exception:
                pass
    except Exception:
        pass
    return results


def _render_live_ticker_strip() -> None:
    """
    Render a horizontal live price ticker strip above the UA masthead.
    Bloomberg/CNBC-style: symbol · price · ▲/▼ ±x.xx%, green=up red=down.
    Updates every 60 seconds via TTL cache.
    """
    items = _fetch_ticker_strip()
    if not items:
        return

    chips = []
    for sym, label, price, chg in items:
        arrow = "▲" if chg >= 0 else "▼"
        color = "var(--ua-green)" if chg >= 0 else "var(--ua-red)"
        # Always show two decimal places for every price (e.g. $225.34, $1,234.56).
        p_fmt = f"${price:,.2f}"
        chips.append(
            f'<span style="display:inline-flex;align-items:center;gap:6px;'
            f'padding:0 14px;border-right:1px solid var(--ua-hair-2);">'
            f'<span style="color:var(--ua-ink-mut);font-weight:600;font-size:0.68rem;">{sym}</span>'
            f'<span style="color:var(--ua-ink);font-weight:700;font-size:0.70rem;">{p_fmt}</span>'
            f'<span style="color:{color};font-size:0.68rem;font-weight:600;">{arrow} {abs(chg):.2f}%</span>'
            f'</span>'
        )

    inner = "".join(chips)
    # Duplicate for seamless marquee loop
    ticker_html = f"""
<div style="background:rgba(var(--ua-shell-rgb),0.95);border-bottom:1px solid var(--ua-hair-3);
             overflow:hidden;white-space:nowrap;padding:5px 0;margin-bottom:0;
             font-family:Inter,sans-serif;">
  <div style="display:inline-flex;animation:tickerScroll 28s linear infinite;">
    {inner}{inner}
  </div>
</div>
<style>
@keyframes tickerScroll {{
  0%   {{ transform: translate3d(0,0,0); }}
  100% {{ transform: translate3d(-50%,0,0); }}
}}
</style>
"""
    st.markdown(ticker_html, unsafe_allow_html=True)


def render_page_header(title: str, subtitle: str = "",
                       icon: str = "", live_stat: str = "") -> None:
    """
    Restrained page title with a quiet divider and
    optional live right-side stat chip.

    Args:
        title:     Page title.
        subtitle:  One-line description of what the page does.
        icon:      Deprecated visual-prefix argument; intentionally ignored.
        live_stat: Optional right-aligned stat string (e.g. "47 signals active").
    """
    # De-emoji (2026-07-13): every page title now renders WITHOUT its emoji icon
    # for a cleaner, institutional look. The `icon` argument is kept for
    # backwards-compat (call sites still pass it) but is intentionally ignored
    # here — this single line de-emojis every page header at once. To restore,
    # put the {icon} span back.
    icon_html = ""

    stat_html = (
        f'<div style="display:inline-flex;align-items:center;gap:6px;'
        f'background:var(--ua-bg-card);border:1px solid rgba(var(--ua-onbg-rgb),0.09);'
        f'border-radius:6px;padding:5px 10px;font-size:0.66rem;font-weight:650;'
        f'color:var(--ua-ink-mut);letter-spacing:0.04em;white-space:nowrap;font-family:Inter,sans-serif;">'
        f'{live_stat}</div>'
    ) if live_stat else ""

    sub_html = (
        f'<div style="font-size:0.86rem;color:var(--ua-ink-mut);margin-top:5px;line-height:1.5;'
        f'font-weight:400;font-family:Inter,sans-serif;max-width:640px;">{subtitle}</div>'
    ) if subtitle else ""

    st.markdown(f"""
<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px;
            margin:8px 0 20px;padding-bottom:16px;position:relative;
            border-bottom:1px solid var(--ua-hair-3);"
     class="ua-slide-up">
    <div>
        <div style="font-size:1.8rem;font-weight:720;letter-spacing:-0.55px;line-height:1.15;
                    font-family:Inter,sans-serif;display:flex;align-items:center;flex-wrap:wrap;">
            {icon_html}<span style="color:var(--ua-ink);">{title}</span>
        </div>
        {sub_html}
    </div>
    <div style="padding-top:4px;flex-shrink:0;">{stat_html}</div>
</div>
""", unsafe_allow_html=True)


def render_guided_steps(
    title: str,
    steps: list[tuple[str, str]],
    *,
    eyebrow: str = "Guided workflow",
    intro: str = "",
) -> None:
    """Render a concise, themed workflow explainer for product features.

    This deliberately accepts plain text only. Escaping every field keeps the
    shared component safe if a future caller includes a ticker or provider name.
    Ordinary status, warning, and empty-state messages should continue using
    Streamlit alerts; this component is reserved for multi-step guidance.
    """
    if not steps:
        return

    _step_html = []
    for _index, (_heading, _body) in enumerate(steps, start=1):
        _step_html.append(
            '<div class="ua-guide-step">'
            '<div class="ua-guide-step-head">'
            f'<span class="ua-guide-step-num">{_index:02d}</span>'
            f'<span class="ua-guide-step-title">{html_escape(str(_heading))}</span>'
            '</div>'
            f'<div class="ua-guide-step-body">{html_escape(str(_body))}</div>'
            '</div>'
        )

    _intro_html = (
        f'<div class="ua-guide-intro">{html_escape(str(intro))}</div>'
        if intro else ""
    )
    _columns = min(max(len(steps), 1), 4)
    st.markdown(
        '<div class="ua-guide-shell">'
        f'<div class="ua-guide-kicker">{html_escape(str(eyebrow))}</div>'
        f'<div class="ua-guide-title">{html_escape(str(title))}</div>'
        f'{_intro_html}'
        f'<div class="ua-guide-grid" style="--ua-guide-cols:{_columns};">'
        f'{"".join(_step_html)}'
        '</div></div>',
        unsafe_allow_html=True,
    )


def render_footer(page: str = "") -> None:
    """
    Render a professional full-width disclaimer footer.
    Call once at the bottom of any page that surfaces signal data or analysis.
    The `page` argument is optional — used to add a page-specific methodology note.
    """
    _year = __import__("datetime").datetime.now().year
    _page_note_html = ""
    if page == "signals":
        _page_note_html = (
            '<div style="font-size:0.70rem;color:var(--ua-ink-label);margin-top:4px;">'
            'Signal scores are 0–100 percentile ranks within a trailing 2-year '
            'distribution. A score of 65+ is "bullish" (top percentile); 35− is '
            '"bearish." Scores are informational — they do not predict specific price '
            'targets or returns for any security.'
            '</div>'
        )
    elif page == "ticker":
        _page_note_html = (
            '<div style="font-size:0.70rem;color:var(--ua-ink-label);margin-top:4px;">'
            'The Confluence Score is a correlation-weighted average of macro signals. '
            'It reflects the current macro environment, not a price target. '
            'Historical lead times are back-tested on available data and may not hold '
            'in future market regimes.'
            '</div>'
        )

    # Pro members: footer shows a quiet "Pro member" tag instead of the Upgrade CTA.
    from utils.billing import effective_is_pro as _eip
    _foot_is_pro = _eip(st.session_state.get("user"))
    _foot_cta = (
        '<span style="font-size:0.68rem;color:#C4B5FD;font-weight:700;'
        'background:rgba(var(--ua-purple-rgb),0.12);border:1px solid rgba(var(--ua-purple-rgb),0.35);'
        'padding:5px 12px;border-radius:6px;white-space:nowrap;">Pro member</span>'
        if _foot_is_pro else
        '<a href="/upgrade-to-pro" style="font-size:0.68rem;color:#fff;text-decoration:none;'
        'font-weight:700;background:linear-gradient(135deg,var(--ua-purple),#6D28D9);'
        'padding:5px 12px;border-radius:6px;white-space:nowrap;" '
        'onmouseover="this.style.opacity=\'0.88\'" '
        'onmouseout="this.style.opacity=\'1\'">Upgrade to Pro</a>'
    )

    # st.html (not st.markdown) — this footer is multi-line indented HTML, which
    # the markdown parser would turn into a code block and dump as raw text at the
    # bottom of the page (same bug that hit the top-nav). st.html skips markdown.
    st.html(f"""
<div style="margin-top:48px;padding:28px 0 20px;border-top:1px solid var(--ua-hair-3);
            font-family:Inter,sans-serif;">
    <div style="max-width:900px;margin:0 auto;padding:0 16px;">

        <!-- Primary disclaimer -->
        <div style="background:rgba(var(--ua-card-rgb),0.6);border:1px solid var(--ua-hair-2);
                    border-radius:10px;padding:16px 20px;margin-bottom:16px;">
            <div style="font-size:0.65rem;font-weight:700;color:var(--ua-ink-mut);letter-spacing:0.10em;
                        text-transform:uppercase;margin-bottom:6px;">
                Important Disclaimer
            </div>
            <div style="font-size:0.73rem;color:var(--ua-ink-label);line-height:1.65;">
                Unstructured Alpha is for <strong style="color:var(--ua-ink-mut);">educational and informational
                purposes only</strong> and does not constitute personalized financial, investment, tax,
                or legal advice. Nothing on this platform should be interpreted as a recommendation to
                buy, sell, or hold any security. Macro signals reflect statistical patterns in historical
                publicly available data — they are not guarantees of future performance. Past patterns
                do not reliably predict future returns. Always consult a licensed financial adviser
                before making investment decisions.
            </div>
            {_page_note_html}
        </div>

        <!-- Source + links row -->
        <div style="display:flex;justify-content:space-between;align-items:center;
                    flex-wrap:wrap;gap:12px;">
            <div>
                <div style="font-size:0.63rem;color:var(--ua-ink-dim-2);line-height:1.6;">
                    Data sourced from public APIs:&nbsp;
                    <span style="color:var(--ua-ink-mut);font-weight:600;">FRED</span> (Federal Reserve) ·
                    <span style="color:var(--ua-ink-mut);font-weight:600;">SEC EDGAR</span> (insider filings) ·
                    <span style="color:var(--ua-ink-mut);font-weight:600;">FINRA</span> (short interest) ·
                    <span style="color:var(--ua-ink-mut);font-weight:600;">EIA</span> (energy data) ·
                    <span style="color:var(--ua-ink-mut);font-weight:600;">yfinance</span> (price data)
                </div>
                <div style="font-size:0.63rem;color:var(--ua-ink-dim-2);margin-top:3px;">
                    Signal data cached every ~6 hours. Scores are not real-time.
                    © {_year} Unstructured Alpha. All rights reserved.
                </div>
            </div>
            <div style="display:flex;gap:14px;align-items:center;flex-shrink:0;">
                <a href="/about-methodology" style="font-size:0.68rem;color:var(--ua-ink-label);text-decoration:none;
                                           font-weight:500;" onmouseover="this.style.color='var(--ua-cyan)'"
                   onmouseout="this.style.color='var(--ua-ink-label)'">About</a>
                <a href="/privacy-terms" style="font-size:0.68rem;color:var(--ua-ink-label);text-decoration:none;
                                                     font-weight:500;" onmouseover="this.style.color='var(--ua-cyan)'"
                   onmouseout="this.style.color='var(--ua-ink-label)'">Privacy</a>
                <a href="/privacy-terms" style="font-size:0.68rem;color:var(--ua-ink-label);text-decoration:none;
                                                       font-weight:500;" onmouseover="this.style.color='var(--ua-cyan)'"
                   onmouseout="this.style.color='var(--ua-ink-label)'">Terms</a>
                <!-- Pro members see a quiet status tag; everyone else sees the Upgrade CTA. -->
                {_foot_cta}
            </div>
        </div>
    </div>
</div>
""")


def render_sidebar_base(
    *,
    page_title: str | None = None,
    sections: list[str] | tuple[str, ...] | None = None,
    section_key: str | None = None,
    default_section: str | None = None,
    section_aliases: dict[str, str] | None = None,
) -> str | None:
    """
    Render a visible, lazy-loading page-local section rail.

    The section rail intentionally uses a radio + normal Python branching
    instead of st.tabs(). Streamlit eagerly executes every tab body, while this
    pattern executes only the selected section — reducing load time and keeping
    long research pages focused. Its selected value is mirrored to a stable
    ``?section=`` deep link so a refresh, bookmark, or browser history action
    returns to the same view without dropping other query-string state.

    The global top navigation intentionally hides Streamlit's native sidebar,
    so the section control must live in the main canvas. On desktop it becomes
    a persistent left rail and reserves canvas space; on smaller screens it
    becomes a compact sticky horizontal switcher.

    Do not rebuild account, theme, assistant, or disclaimer widgets here: those
    actions already live in the visible header/footer. Rendering duplicates in
    a display:none sidebar adds elements and rerun work without giving the user
    any reachable control.
    """
    selected_section: str | None = None
    if sections:
        _options = list(sections)
        _default = default_section if default_section in _options else _options[0]
        _widget_key = (
            section_key
            or f"section_rail_{(page_title or 'page').lower().replace(' ', '_')}"
        )
        _slugs_by_section = {option: _section_slug(option) for option in _options}
        _sections_by_slug = {
            slug: option for option, slug in _slugs_by_section.items()
        }
        for alias, option in (section_aliases or {}).items():
            if option in _options:
                _sections_by_slug[_section_slug(alias)] = option

        _requested_slug = str(
            st.query_params.get("section") or ""
        ).strip().lower()
        _requested_option = _sections_by_slug.get(_requested_slug)
        if _requested_option:
            # This runs before the widget is instantiated, so direct links and
            # browser back/forward can safely override stale session state.
            st.session_state[_widget_key] = _requested_option
        _active_option = st.session_state.get(_widget_key, _default)
        if _active_option not in _options:
            _active_option = _default
        st.markdown(
            """
<style>
/* The native Streamlit sidebar is hidden by the global top-nav. Keep the
   section selector in the visible main canvas and reserve room for it. */
.st-key-ua_page_section_rail {
    position: absolute;
    /* Offset from Streamlit's padded inner canvas to land at viewport x=18px. */
    left: min(-220px, calc((1500px - 100vw) / 2 - 220px));
    top: -164px;
    width: 202px;
    max-height: calc(100vh - 92px);
    overflow-y: auto;
    z-index: 910;
    padding: 13px 12px 11px;
    background: rgba(var(--ua-shell-rgb),0.97);
    border: 1px solid rgba(var(--ua-label-rgb),0.20);
    border-radius: 12px;
    box-shadow: 0 12px 34px rgba(var(--ua-shadow-rgb),calc(0.24*var(--ua-shadow-k)));
    backdrop-filter: blur(12px);
}
body:has(.st-key-ua_page_section_rail) [data-testid="stMainBlockContainer"] {
    padding-left: max(238px, calc((100vw - 1500px) / 2 + 238px)) !important;
}
/* Streamlit's inner canvas establishes a containing block, so position:fixed
   scrolls with the page. A zero-height sticky parent keeps the rail anchored
   without adding a blank row above the selected section's content. */
body:has(.st-key-ua_page_section_rail)
  [data-testid="stMainBlockContainer"] div:has(> .st-key-ua_page_section_rail) {
    position: sticky;
    top: 236px;
    height: 0;
    overflow: visible;
    z-index: 910;
}
body:has(.st-key-ua_page_section_rail) .ua-topnav {
    left: min(-238px, calc((1500px - 100vw) / 2 - 238px));
    right: auto;
    width: 100vw;
}
.st-key-ua_page_section_rail [data-testid="stVerticalBlock"] {
    gap: 0.35rem !important;
}
.st-key-ua_page_section_rail [data-testid="stRadio"] [role="radiogroup"] {
    gap: 3px !important;
}
.st-key-ua_page_section_rail [data-testid="stRadio"] label {
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 7px 8px !important;
    margin: 0 !important;
    transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
}
.st-key-ua_page_section_rail [data-testid="stRadio"] label:hover {
    background: rgba(var(--ua-onbg-rgb),0.045);
    border-color: var(--ua-hair-2);
}
.st-key-ua_page_section_rail [data-testid="stRadio"] label:has(input:checked) {
    background: rgba(var(--ua-purple-rgb),0.11);
    border-color: rgba(var(--ua-purple-rgb),0.32);
}
.st-key-ua_page_section_rail [data-testid="stRadio"] label p {
    color: var(--ua-ink-mut) !important;
    font-size: 0.76rem !important;
    font-weight: 650 !important;
    line-height: 1.25 !important;
}
.st-key-ua_page_section_rail [data-testid="stRadio"] label:has(input:checked) p {
    color: var(--ua-ink) !important;
}
.ua-page-rail-kicker {
    color: var(--ua-ink-label);
    font-size: 0.59rem;
    font-weight: 800;
    letter-spacing: 0.13em;
    line-height: 1.35;
    text-transform: uppercase;
}
.ua-page-rail-note {
    color: var(--ua-ink-dim);
    font-size: 0.61rem;
    line-height: 1.45;
    margin-top: 3px;
}
@media (max-width: 1150px) {
    body:has(.st-key-ua_page_section_rail) [data-testid="stMainBlockContainer"] {
        padding-left: 1rem !important;
    }
    .st-key-ua_page_section_rail {
        position: sticky;
        top: 54px;
        left: auto;
        width: auto;
        max-height: none;
        overflow: visible;
        z-index: 900;
        margin: 0 0 14px;
        padding: 10px 11px 9px;
    }
    body:has(.st-key-ua_page_section_rail)
      [data-testid="stMainBlockContainer"] div:has(> .st-key-ua_page_section_rail) {
        position: static;
        top: auto;
        height: auto;
    }
    body:has(.st-key-ua_page_section_rail) .ua-topnav {
        left: -1rem;
    }
    .st-key-ua_page_section_rail [data-testid="stRadio"] [role="radiogroup"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: wrap !important;
        gap: 5px !important;
    }
    .st-key-ua_page_section_rail [data-testid="stRadio"] label {
        flex: 0 1 auto !important;
        padding: 6px 8px !important;
    }
    .ua-page-rail-note { display: none; }
}
@media (max-width: 640px) {
    body:has(.st-key-ua_page_section_rail) [data-testid="stMainBlockContainer"] {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    .st-key-ua_page_section_rail {
        top: 48px;
        border-radius: 9px;
        margin-bottom: 10px;
    }
    body:has(.st-key-ua_page_section_rail) .ua-topnav {
        left: -0.5rem;
    }
    .st-key-ua_page_section_rail [data-testid="stRadio"] label p {
        font-size: 0.70rem !important;
    }
}
</style>
""",
            unsafe_allow_html=True,
        )
        with st.container(key="ua_page_section_rail"):
            st.markdown(
                f'<div class="ua-page-rail-kicker">'
                f'{html_escape(page_title or "On this page")}</div>',
                unsafe_allow_html=True,
            )
            selected_section = st.radio(
                "Page section",
                _options,
                # Match the widget's declared default to restored/deep-linked
                # state. A mismatched index can make the browser briefly report
                # the first option during hydration and fire a false change.
                index=_options.index(_active_option),
                key=_widget_key,
                label_visibility="collapsed",
                on_change=_sync_section_query,
                kwargs={
                    "widget_key": _widget_key,
                    "default_section": _default,
                    "slugs_by_section": _slugs_by_section,
                },
            )
            # Streamlit can rebuild widget state in a second browser pass after
            # a hard refresh. Reconcile once more from the value actually on
            # screen so that pass cannot leave a selected subsection behind a
            # URL whose ``section`` parameter was transiently cleared.
            _sync_section_query(
                widget_key=_widget_key,
                default_section=_default,
                slugs_by_section=_slugs_by_section,
            )
            st.markdown(
                '<div class="ua-page-rail-note">Only this section loads. '
                'The menu stays visible while you scroll.</div>',
                unsafe_allow_html=True,
            )

    return selected_section
