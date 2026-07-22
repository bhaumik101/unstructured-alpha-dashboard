"""
Shared header + CSS injected at the top of every page.
Call render_header() as the very first Streamlit call after st.set_page_config().
"""

from html import escape as html_escape

import streamlit as st

from utils.config import TICKERS, SIGNAL_COUNT

# ── Modern Dark Design System CSS ────────────────────────────────────────────
_CSS = """
<style>
/* preconnect hints injected via JS below for max speed */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap&font-display=swap');

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
    background: rgba(255,255,255,0.035);
    border-color: rgba(255,255,255,0.06);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: rgba(124,58,237,0.10);
    border-color: rgba(124,58,237,0.28);
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
::-webkit-scrollbar-thumb        { background: rgba(0,213,102,0.22); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover  { background: rgba(0,213,102,0.45); }

/* ── Page background — gradient mesh ─────────────────────────────────────── */
.main {
    background-color: #0B0D12 !important;
    background-image:
        radial-gradient(ellipse 80% 40% at 20% -5%,  rgba(0,213,102,0.055) 0%, transparent 60%),
        radial-gradient(ellipse 60% 35% at 80% 5%,   rgba(124,58,237,0.045) 0%, transparent 55%),
        radial-gradient(ellipse 50% 30% at 50% 100%, rgba(0,200,224,0.035) 0%, transparent 50%) !important;
}
.block-container {
    background-color: transparent !important;
    padding-top: 0.75rem !important;
}
[data-testid="stAppViewContainer"] {
    background-color: #0B0D12 !important;
    background-image:
        radial-gradient(ellipse 80% 40% at 20% -5%,  rgba(0,213,102,0.055) 0%, transparent 60%),
        radial-gradient(ellipse 60% 35% at 80% 5%,   rgba(124,58,237,0.045) 0%, transparent 55%),
        radial-gradient(ellipse 50% 30% at 50% 100%, rgba(0,200,224,0.035) 0%, transparent 50%) !important;
}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0D0F1A 0%, #0A0C14 100%) !important;
    border-right: 1px solid rgba(255,255,255,0.04) !important;
}
section[data-testid="stSidebar"] * { color: #8892AA !important; }
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] a { color: #8892AA !important; }
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #E8EEFF !important;
    border-bottom: 1px solid rgba(255,255,255,0.05) !important;
    padding-bottom: 4px !important;
}
[data-testid="stNavSectionHeader"] {
    background: rgba(0,213,102,0.07) !important;
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
    color: #00D566 !important;
}
[data-testid="stSidebarNavItems"] a[aria-selected="true"],
[data-testid="stSidebarNavItems"] [aria-selected="true"] {
    background: rgba(0,213,102,0.09) !important;
    border-radius: 6px !important;
}
[data-testid="stSidebarNavItems"] a[aria-selected="true"] p,
[data-testid="stSidebarNavItems"] [aria-selected="true"] p { color: #00D566 !important; }
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(0,213,102,0.09) !important;
    border: 1px solid rgba(0,213,102,0.22) !important;
    color: #00D566 !important;
    border-radius: 8px !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(0,213,102,0.16) !important;
    box-shadow: 0 0 12px rgba(0,213,102,0.14) !important;
}
section[data-testid="stSidebar"] .stButton > button span,
section[data-testid="stSidebar"] .stButton > button p { color: #00D566 !important; }

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
    border-bottom: 1px solid rgba(255,255,255,0.06);
    position: relative;
}
.ua-header::after {
    content: '';
    position: absolute;
    bottom: -1px; left: 0;
    width: 200px; height: 2px;
    background: linear-gradient(90deg, #00D566, #00C8E0 50%, #7C3AED 100%);
    background-size: 300% 100%;
    animation: ua_gradient_x 6s ease infinite;
    border-radius: 1px;
}
.ua-wordmark {
    font-size: 1.8rem; font-weight: 800; color: #E8EEFF;
    font-family: 'Inter', sans-serif; letter-spacing: -0.8px; line-height: 1.05;
}
.ua-wordmark span {
    background: linear-gradient(135deg, #00D566 0%, #00C8E0 60%, #7C3AED 100%);
    background-size: 200% 200%;
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: ua_gradient_x 6s ease infinite;
}
.ua-tagline {
    font-size: 0.70rem; color: #6B7FBF; font-family: 'Inter', sans-serif;
    margin-top: 3px; letter-spacing: 0.02em;
    display: flex; align-items: center; gap: 6px;
}
.ua-header-right {
    text-align: right; font-size: 0.73rem; color: #8892AA; font-family: 'Inter', sans-serif;
}
.ua-header-right b { color: #C8D0E4; font-weight: 600; }
.gold-rule {
    height: 1px;
    background: linear-gradient(90deg, rgba(0,213,102,0.5), rgba(0,200,224,0.3) 40%, rgba(124,58,237,0.3) 70%, transparent);
    border: none; margin: 0 0 14px 0;
}

/* ── Cards ───────────────────────────────────────────────────────────────── */
.metric-card {
    background: rgba(18,21,30,0.8);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px; padding: 16px 18px; margin-bottom: 10px;
    font-family: 'Inter', sans-serif;
    transition: all 0.22s cubic-bezier(0.4,0,0.2,1);
    position: relative; overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
.metric-card::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0;
    width: 3px; background: rgba(255,255,255,0.08);
    border-radius: 12px 0 0 12px;
    transition: background 0.2s ease;
}
.metric-card.bull::before  { background: linear-gradient(180deg, #00D566, #00A847); }
.metric-card.bear::before  { background: linear-gradient(180deg, #FF4444, #CC2222); }
.metric-card.neutral::before { background: linear-gradient(180deg, #6B7FBF, #4A5280); }
/* Subtle top glow when bull/bear */
.metric-card.bull { box-shadow: 0 0 0 0 transparent, inset 0 1px 0 rgba(0,213,102,0.06); }
.metric-card.bear { box-shadow: 0 0 0 0 transparent, inset 0 1px 0 rgba(255,68,68,0.06); }
.metric-card, .page-card, .stat-box { will-change: transform; }
.metric-card:hover {
    border-color: rgba(0,213,102,0.24);
    box-shadow: 0 0 28px rgba(0,213,102,0.09), 0 8px 28px rgba(0,0,0,0.45);
    transform: translate3d(0,-2px,0);
}
.metric-card.bull:hover { border-color: rgba(0,213,102,0.32); }
.metric-card.bear:hover { border-color: rgba(255,68,68,0.25); }
.metric-card b { color: #E8EEFF; }
.metric-card span { color: #8892AA; }

.page-card {
    background: rgba(18,21,30,0.7);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px; padding: 18px 20px; margin-bottom: 10px;
    font-family: 'Inter', sans-serif;
    transition: all 0.22s cubic-bezier(0.4,0,0.2,1);
    position: relative; overflow: hidden;
}
.page-card::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0;
    width: 3px;
    background: linear-gradient(180deg, #00D566, #7C3AED);
    border-radius: 12px 0 0 12px;
    opacity: 0; transition: opacity 0.2s ease;
}
.page-card:hover::before { opacity: 1; }
.page-card:hover {
    border-color: rgba(0,213,102,0.18);
    box-shadow: 0 0 24px rgba(0,213,102,0.07), 0 12px 32px rgba(0,0,0,0.5);
    transform: translate3d(0,-2px,0);
}
.page-card .page-title { font-size: 0.94rem; font-weight: 600; color: #E8EEFF; margin-bottom: 4px; letter-spacing: -0.1px; }
.page-card .page-desc  { font-size: 0.79rem; color: #8892AA; line-height: 1.55; }

/* ── Section header ──────────────────────────────────────────────────────── */
.section-header {
    font-size: 0.63rem; font-weight: 700; color: #8892AA;
    font-family: 'Inter', sans-serif; letter-spacing: 0.13em;
    text-transform: uppercase;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    padding-bottom: 8px; margin-bottom: 14px;
}

/* ── Score numbers ───────────────────────────────────────────────────────── */
.score-number { font-size: 2.8rem; font-weight: 800; line-height: 1.0; font-family: 'Inter', sans-serif; letter-spacing: -1.5px; }
.score-bull {
    background: linear-gradient(135deg, #00D566, #00C8E0);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.score-bear {
    background: linear-gradient(135deg, #FF4444, #FF8888);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.score-neutral { color: #6B7FBF; }

/* ── Stat boxes ──────────────────────────────────────────────────────────── */
.stat-box {
    background: rgba(18,21,30,0.8); border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px; padding: 14px 16px; text-align: center;
    font-family: 'Inter', sans-serif;
    transition: all 0.2s cubic-bezier(0.4,0,0.2,1);
}
.stat-box:hover {
    border-color: rgba(0,213,102,0.2);
    box-shadow: 0 0 16px rgba(0,213,102,0.07);
    transform: translateY(-1px);
}
.stat-box .stat-label  { font-size: 0.60rem; text-transform: uppercase; letter-spacing: 0.11em; color: #8892AA; margin-bottom: 6px; font-weight: 700; }
.stat-box .stat-value  { font-size: 1.4rem; font-weight: 700; color: #E8EEFF; letter-spacing: -0.5px; }
.stat-box .stat-change { font-size: 0.76rem; margin-top: 3px; font-weight: 500; }
.stat-box .stat-change.pos  { color: #00D566; }
.stat-box .stat-change.neg  { color: #FF4444; }
.stat-box .stat-change.flat { color: #6B7FBF; }

/* ── Info / disclaimer ───────────────────────────────────────────────────── */
.disclaimer {
    background: rgba(18,21,30,0.6); border: 1px solid rgba(255,255,255,0.05);
    border-radius: 8px; padding: 10px 14px; font-size: 0.72rem;
    color: #8892AA; margin-top: 16px; font-family: 'Inter', sans-serif;
}
.info-box {
    background: rgba(0,213,102,0.05); border: 1px solid rgba(0,213,102,0.15);
    border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;
    font-size: 0.83rem; color: #A8E8C0; font-family: 'Inter', sans-serif;
}

/* ── Tables ──────────────────────────────────────────────────────────────── */
.comparison-table { width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 0.83rem; }
.comparison-table th {
    background: rgba(0,213,102,0.08); color: #00D566;
    padding: 9px 12px; text-align: left; font-weight: 700;
    font-size: 0.62rem; letter-spacing: 0.08em; text-transform: uppercase;
    border-bottom: 1px solid rgba(0,213,102,0.18);
}
.comparison-table td { padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.04); color: #C8D0E4; }
.comparison-table tr:hover td { background: rgba(255,255,255,0.02); }
.comparison-table tr.highlight td { background: rgba(0,213,102,0.06); color: #E8EEFF; font-weight: 600; }

.ua-data-table { width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 0.81rem; }
.ua-data-table th {
    background: rgba(18,21,30,0.95); color: #8892AA;
    padding: 9px 12px; text-align: left; font-weight: 700;
    font-size: 0.60rem; letter-spacing: 0.10em; text-transform: uppercase;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.ua-data-table td { padding: 9px 12px; border-bottom: 1px solid rgba(255,255,255,0.04); color: #B8C0D4; vertical-align: middle; }
.ua-data-table tr:hover td { background: rgba(255,255,255,0.02); transition: background 0.1s ease; }
.ua-data-table .bull    { color: #00D566; font-weight: 600; }
.ua-data-table .bear    { color: #FF4444; font-weight: 600; }
.ua-data-table .neutral { color: #6B7FBF; }

/* ── Streamlit native overrides ──────────────────────────────────────────── */
/* Metrics */
.stMetric label { color: #8892AA !important; font-size: 0.70rem !important; letter-spacing: 0.06em !important; font-family: 'Inter', sans-serif !important; text-transform: uppercase !important; font-weight: 600 !important; }
.stMetric [data-testid="stMetricValue"] { color: #E8EEFF !important; font-family: 'Inter', sans-serif !important; font-size: 1.65rem !important; font-weight: 700 !important; letter-spacing: -0.5px !important; }
.stMetric [data-testid="stMetricDelta"] { font-size: 0.78rem !important; font-weight: 500 !important; }

/* Expanders */
div[data-testid="stExpander"] { background: rgba(18,21,30,0.6) !important; border: 1px solid rgba(255,255,255,0.06) !important; border-radius: 10px !important; }
.streamlit-expanderHeader { color: #C8D0E4 !important; font-family: 'Inter', sans-serif !important; font-weight: 600 !important; font-size: 0.86rem !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"]  { border-bottom: 1px solid rgba(255,255,255,0.06) !important; gap: 0 !important; background: transparent !important; }
.stTabs [data-baseweb="tab"]       { font-family: 'Inter', sans-serif !important; font-size: 0.83rem !important; font-weight: 500 !important; padding: 8px 18px !important; color: #8892AA !important; background: transparent !important; border: none !important; }
.stTabs [aria-selected="true"]     { color: #E8EEFF !important; border-bottom: 2px solid #00D566 !important; font-weight: 600 !important; }
.stTabs [data-baseweb="tab-highlight"] { background: #00D566 !important; height: 2px !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 16px !important; }

/* Buttons */
.stButton > button {
    font-family: 'Inter', sans-serif !important;
    border-radius: 8px !important; font-weight: 500 !important; font-size: 0.83rem !important;
    transition: all 0.18s cubic-bezier(0.4,0,0.2,1) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    background: rgba(18,21,30,0.8) !important; color: #C8D0E4 !important;
}
.stButton > button:hover {
    border-color: rgba(0,213,102,0.4) !important; color: #00D566 !important;
    box-shadow: 0 0 14px rgba(0,213,102,0.12) !important;
    transform: translateY(-1px);
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #00D566, #00A847) !important;
    color: #001A0D !important; border: none !important; font-weight: 700 !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 0 22px rgba(0,213,102,0.35) !important; filter: brightness(1.05);
}

/* Inputs */
.stTextInput > div > div > input {
    background: rgba(18,21,30,0.8) !important; border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important; color: #E8EEFF !important;
    font-family: 'Inter', sans-serif !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.stTextInput > div > div > input:focus {
    border-color: rgba(0,213,102,0.5) !important;
    box-shadow: 0 0 0 3px rgba(0,213,102,0.08) !important; outline: none !important;
}
.stTextInput > div > div > input::placeholder { color: #8892AA !important; }

/* Selectbox */
.stSelectbox > div > div {
    background: rgba(18,21,30,0.8) !important; border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important; color: #E8EEFF !important; font-family: 'Inter', sans-serif !important;
}

/* Multiselect */
.stMultiSelect > div > div {
    background: rgba(18,21,30,0.8) !important; border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
}
.stMultiSelect span[data-baseweb="tag"] {
    background: rgba(0,213,102,0.10) !important; border-color: rgba(0,213,102,0.25) !important;
    color: #00D566 !important;
}

/* Number / Date input */
.stNumberInput > div > div > input,
.stDateInput > div > div > input {
    background: rgba(18,21,30,0.8) !important; border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important; color: #E8EEFF !important; font-family: 'Inter', sans-serif !important;
}

/* Sliders */
.stSlider [data-baseweb="slider"] [role="progressbar"] { background: linear-gradient(90deg, #00D566, #00C8E0) !important; }
.stSlider [data-baseweb="thumb"] { background: #00D566 !important; border-color: #00D566 !important; box-shadow: 0 0 8px rgba(0,213,102,0.5) !important; }

/* Toggle */
.stToggle [data-baseweb="switch"] [data-checked="true"] { background: #00D566 !important; }

/* Progress bars */
.stProgress > div > div > div { background: linear-gradient(90deg, #00D566, #00C8E0) !important; border-radius: 4px !important; }
.stProgress > div > div { background: rgba(255,255,255,0.05) !important; border-radius: 4px !important; }

/* Dividers */
hr { border-color: rgba(255,255,255,0.05) !important; opacity: 1 !important; }

/* Spinner */
.stSpinner > div { border-top-color: #00D566 !important; }

/* H1/H2/H3 */
h1, h2, h3 { color: #E8EEFF !important; font-family: 'Inter', sans-serif !important; font-weight: 700 !important; letter-spacing: -0.3px !important; }
h1 { font-size: 1.75rem !important; }
h2 { font-size: 1.3rem !important; }
h3 { font-size: 1.05rem !important; }
p  { color: var(--ua-text-mid) !important; font-family: 'Inter', sans-serif !important; }

/* Radio / Checkbox */
.stRadio label, .stCheckbox label { color: var(--ua-text-mid) !important; font-family: 'Inter', sans-serif !important; }

/* Caption */
.stCaption, small { color: var(--ua-text-cap) !important; font-family: 'Inter', sans-serif !important; }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid rgba(255,255,255,0.06) !important; border-radius: 10px !important; overflow: hidden !important; }

/* Alerts */
.stAlert { border-radius: 10px !important; border: none !important; }

/* Success/Info/Warning/Error alerts (dark-friendly backgrounds) */
div[data-testid="stAlertContainer"][data-baseweb="notification"][kind="success"] { background: rgba(0,213,102,0.08) !important; border: 1px solid rgba(0,213,102,0.2) !important; }
div[data-testid="stAlertContainer"][data-baseweb="notification"][kind="info"]    { background: rgba(0,200,224,0.08) !important; border: 1px solid rgba(0,200,224,0.2) !important; }
div[data-testid="stAlertContainer"][data-baseweb="notification"][kind="warning"] { background: rgba(245,158,11,0.08) !important; border: 1px solid rgba(245,158,11,0.2) !important; }
div[data-testid="stAlertContainer"][data-baseweb="notification"][kind="error"]   { background: rgba(255,68,68,0.08) !important; border: 1px solid rgba(255,68,68,0.2) !important; }

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
    background: #12151E !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 10px !important;
    box-shadow: 0 16px 48px rgba(0,0,0,0.6) !important;
}
[data-baseweb="menu"] li,
[data-baseweb="option"] {
    background: transparent !important;
    color: #B8C0D4 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.83rem !important;
}
[data-baseweb="option"]:hover,
[data-baseweb="option"][aria-selected="true"] {
    background: rgba(0,213,102,0.09) !important;
    color: #E8EEFF !important;
}

/* ── Focus-visible keyboard ring ────────────────────────────────────────── */
*:focus-visible {
    outline: 2px solid rgba(0,213,102,0.55) !important;
    outline-offset: 2px !important;
    border-radius: 6px;
}
.stButton > button:focus-visible {
    box-shadow: 0 0 0 3px rgba(0,213,102,0.25) !important;
    outline: none !important;
}

/* ── Empty state component ──────────────────────────────────────────────── */
.ua-empty {
    text-align: center;
    padding: 48px 24px;
    background: rgba(18,21,30,0.5);
    border: 1px dashed rgba(255,255,255,0.08);
    border-radius: 14px;
    font-family: 'Inter', sans-serif;
    margin: 12px 0;
}
.ua-empty-icon  { font-size: 2.4rem; margin-bottom: 12px; opacity: 0.5; }
.ua-empty-title { font-size: 0.94rem; font-weight: 600; color: #E8EEFF; margin-bottom: 6px; }
.ua-empty-body  { font-size: 0.80rem; color: #8892AA; line-height: 1.55; max-width: 320px; margin: 0 auto; }

/* ── Tooltip dark styling ────────────────────────────────────────────────── */
[data-baseweb="tooltip"] [role="tooltip"] {
    background: #1A1E2C !important;
    color: #E8EEFF !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.78rem !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5) !important;
}

/* ── Code blocks ─────────────────────────────────────────────────────────── */
code, pre {
    background: rgba(18,21,30,0.9) !important;
    color: #00C8E0 !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 6px !important;
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace !important;
    font-size: 0.82rem !important;
}

/* ── Smooth section dividers ─────────────────────────────────────────────── */
.ua-divider {
    height: 1px;
    background: linear-gradient(90deg, rgba(0,213,102,0.18), rgba(0,200,224,0.10) 40%, rgba(124,58,237,0.10) 70%, transparent);
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
.ua-chip.bull  { color: #00D566; background: rgba(0,213,102,0.08); }
.ua-chip.bear  { color: #FF4444; background: rgba(255,68,68,0.08); }
.ua-chip.neut  { color: #6B7FBF; background: rgba(107,127,191,0.08); }
.ua-chip.pro   { color: #7C3AED; background: rgba(124,58,237,0.10); }

/* ── Modern keyframes ────────────────────────────────────────────────────── */
@keyframes ua_pulse_ring {
    0%   { box-shadow: 0 0 0 0   rgba(0,213,102,0.55); }
    70%  { box-shadow: 0 0 0 8px rgba(0,213,102,0);    }
    100% { box-shadow: 0 0 0 0   rgba(0,213,102,0);    }
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
    background: rgba(18,21,30,0.75);
    backdrop-filter: blur(18px) saturate(160%);
    -webkit-backdrop-filter: blur(18px) saturate(160%);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: var(--ua-radius);
    box-shadow: var(--ua-shadow);
}
.ua-glass:hover {
    border-color: rgba(255,255,255,0.14);
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
    background: linear-gradient(135deg, #00D566, #00C8E0, #7C3AED, #00D566);
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
    background: rgba(0,213,102,0.04);
    border: 1px solid rgba(0,213,102,0.18);
    border-radius: var(--ua-radius);
    animation: ua_glow_pulse_green 3.5s ease-in-out infinite;
}
.ua-card-bear {
    background: rgba(255,68,68,0.04);
    border: 1px solid rgba(255,68,68,0.18);
    border-radius: var(--ua-radius);
    animation: ua_glow_pulse_red 3.5s ease-in-out infinite;
}

/* ── Animated gradient text ─────────────────────────────────────────────── */
.ua-gradient-text {
    background: linear-gradient(135deg, #00D566 0%, #00C8E0 50%, #7C3AED 100%);
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
    background: rgba(0,213,102,0.12);
    color: #00D566;
    box-shadow: 0 0 0 2px rgba(0,213,102,0.3), inset 0 0 12px rgba(0,213,102,0.08);
}
.ua-score-badge.bear {
    background: rgba(255,68,68,0.12);
    color: #FF4444;
    box-shadow: 0 0 0 2px rgba(255,68,68,0.3), inset 0 0 12px rgba(255,68,68,0.08);
}
.ua-score-badge.neut {
    background: rgba(107,127,191,0.10);
    color: #8892AA;
    box-shadow: 0 0 0 2px rgba(107,127,191,0.2);
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
    background: rgba(0,213,102,0.07);
    border: 1px solid rgba(0,213,102,0.20);
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
.ua-pill.bull { background: rgba(0,213,102,0.10); color: #00D566; border: 1px solid rgba(0,213,102,0.25); }
.ua-pill.bear { background: rgba(255,68,68,0.10);  color: #FF4444; border: 1px solid rgba(255,68,68,0.25); }
.ua-pill.neut { background: rgba(107,127,191,0.08); color: #8892AA; border: 1px solid rgba(107,127,191,0.20); }
.ua-pill.pro  { background: rgba(124,58,237,0.10);  color: #A78BFA; border: 1px solid rgba(124,58,237,0.25); }

/* ── Data table — zebra striped ──────────────────────────────────────────── */
.ua-zebra tr:nth-child(even) td { background: rgba(255,255,255,0.015) !important; }

/* ── Streamlit dataframe — dark overrides ─────────────────────────────────── */
[data-testid="stDataFrame"] iframe { border-radius: 10px !important; }
.dvn-scroller { background: var(--ua-bg-card) !important; }
.dvn-scroller::-webkit-scrollbar       { width: 4px; height: 4px; }
.dvn-scroller::-webkit-scrollbar-thumb { background: rgba(0,213,102,0.22); border-radius: 2px; }

/* ── Better primary button gradient ─────────────────────────────────────── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #00D566 0%, #00B857 40%, #00A847 100%) !important;
    color: #001A0D !important;
    border: none !important;
    font-weight: 700 !important;
    letter-spacing: 0.01em !important;
    box-shadow: 0 2px 14px rgba(0,213,102,0.28), 0 1px 3px rgba(0,0,0,0.3) !important;
    transition: all 0.18s cubic-bezier(0.4,0,0.2,1) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 22px rgba(0,213,102,0.42), 0 2px 6px rgba(0,0,0,0.4) !important;
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
    box-shadow: 0 0 0 2px var(--ua-green), 0 0 10px rgba(0,213,102,0.4) !important;
}

/* ── Section divider accent ──────────────────────────────────────────────── */
.ua-section-rule {
    height: 1px;
    margin: 22px 0 18px;
    background: linear-gradient(90deg,
        rgba(0,213,102,0.25) 0%,
        rgba(0,200,224,0.15) 35%,
        rgba(124,58,237,0.12) 65%,
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
    background: rgba(0,213,102,0.15);
    border: 1px solid rgba(0,213,102,0.35);
    border-radius: 50%;
    color: #00D566;
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
    background: rgba(0,213,102,0.28);
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
        rgba(255,255,255,0.04) 25%,
        rgba(255,255,255,0.09) 50%,
        rgba(255,255,255,0.04) 75%
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
    background: rgba(18,21,30,0.75);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 18px 20px 14px;
    margin-bottom: 16px;
    position: relative;
    overflow: hidden;
}
.ua-chart-card:hover {
    border-color: rgba(0,213,102,0.16);
    box-shadow: 0 0 28px rgba(0,213,102,0.06), 0 12px 32px rgba(0,0,0,0.4);
    transition: all 0.22s cubic-bezier(0.4,0,0.2,1);
}
.ua-chart-title {
    font-size: 0.83rem;
    font-weight: 700;
    color: #E8EEFF;
    letter-spacing: -0.1px;
    margin-bottom: 3px;
    font-family: 'Inter', sans-serif;
}
.ua-chart-subtitle {
    font-size: 0.68rem;
    color: #8892AA;
    margin-bottom: 14px;
    font-family: 'Inter', sans-serif;
    line-height: 1.4;
}
.ua-chart-caption {
    font-size: 0.63rem;
    color: #4A5280;
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
    color: #6B7FBF;
    background: rgba(107,127,191,0.08);
    border: 1px solid rgba(107,127,191,0.15);
    border-radius: 4px;
    padding: 2px 7px;
    letter-spacing: 0.06em;
    font-family: 'Inter', sans-serif;
}

/* ── Pro upgrade CTA card ────────────────────────────────────────────────── */
.ua-pro-cta {
    background: linear-gradient(135deg, rgba(124,58,237,0.12) 0%, rgba(124,58,237,0.06) 100%);
    border: 1px solid rgba(124,58,237,0.3);
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
    background: linear-gradient(90deg, #7C3AED, #00C8E0, #7C3AED);
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
    background: rgba(124,58,237,0.12);
    border: 1px solid rgba(124,58,237,0.25);
    border-radius: 20px;
    padding: 3px 10px;
    margin-bottom: 10px;
    display: inline-block;
}
.ua-pro-cta-title {
    font-size: 0.94rem;
    font-weight: 700;
    color: #E8EEFF;
    margin-bottom: 5px;
    letter-spacing: -0.1px;
}
.ua-pro-cta-body {
    font-size: 0.80rem;
    color: #8892AA;
    line-height: 1.55;
    margin-bottom: 14px;
}

/* ── Better error state ──────────────────────────────────────────────────── */
.ua-error {
    text-align: center;
    padding: 36px 24px;
    background: rgba(255,68,68,0.04);
    border: 1px dashed rgba(255,68,68,0.18);
    border-radius: 14px;
    font-family: 'Inter', sans-serif;
    margin: 12px 0;
}
.ua-error-icon  { font-size: 2rem; margin-bottom: 10px; opacity: 0.6; }
.ua-error-title { font-size: 0.88rem; font-weight: 600; color: #FF8888; margin-bottom: 4px; }
.ua-error-body  { font-size: 0.76rem; color: #8892AA; line-height: 1.5; }

/* ── Loading pulse state ─────────────────────────────────────────────────── */
.ua-loading-card {
    background: rgba(18,21,30,0.7);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 10px;
    font-family: 'Inter', sans-serif;
}

/* ── Score trend indicator ───────────────────────────────────────────────── */
.ua-trend-up   { color: #00D566; font-weight: 700; font-size: 0.80rem; }
.ua-trend-down { color: #FF4444; font-weight: 700; font-size: 0.80rem; }
.ua-trend-flat { color: #6B7FBF; font-weight: 700; font-size: 0.80rem; }

/* ── Inline score bar (for signal tables) ────────────────────────────────── */
.ua-score-bar-track {
    height: 4px;
    background: rgba(255,255,255,0.05);
    border-radius: 2px;
    overflow: hidden;
    flex-shrink: 0;
}
.ua-score-bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.6s cubic-bezier(0.4,0,0.2,1);
}
.ua-score-bar-fill.bull { background: linear-gradient(90deg, #00D566, #00C8E0); }
.ua-score-bar-fill.bear { background: linear-gradient(90deg, #FF4444, #FF7777); }
.ua-score-bar-fill.neut { background: rgba(107,127,191,0.5); }

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
    border: 1px solid rgba(255,255,255,0.08);
    background: rgba(255,255,255,0.03);
    color: #8892AA;
    white-space: nowrap;
}
.ua-filter-pill:hover {
    border-color: rgba(0,213,102,0.3);
    color: #E8EEFF;
    background: rgba(0,213,102,0.06);
}
.ua-filter-pill.active {
    border-color: rgba(0,213,102,0.4);
    color: #00D566;
    background: rgba(0,213,102,0.08);
    font-weight: 700;
}

/* ── Ticker banner (at top of TDD, Watchlist rows) ───────────────────────── */
.ua-ticker-banner {
    background: rgba(18,21,30,0.9);
    border: 1px solid rgba(255,255,255,0.07);
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
    color: #E8EEFF;
    letter-spacing: -0.5px;
}
.ua-ticker-name {
    font-size: 0.80rem;
    color: #8892AA;
}
.ua-ticker-price {
    font-size: 1.1rem;
    font-weight: 700;
    color: #E8EEFF;
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
    color: #8892AA;
    white-space: nowrap;
}
.ua-label-divider::before,
.ua-label-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: rgba(255,255,255,0.05);
}

/* ── Watchlist row hover ─────────────────────────────────────────────────── */
.ua-watchlist-row {
    transition: background 0.15s ease;
}
.ua-watchlist-row:hover {
    background: rgba(0,213,102,0.04) !important;
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
    border-right-color: rgba(255,255,255,0.07) !important;
}
.ua-header::after, .ua-card-shine::after { display: none !important; }
.ua-wordmark span {
    background: none !important;
    -webkit-text-fill-color: #DDE3EC !important;
    color: #DDE3EC !important;
    animation: none !important;
}
.metric-card, .page-card, .stat-box,
[data-testid="stMetric"], [data-testid="stExpander"] {
    background: #11151C !important;
    backdrop-filter: none !important;
    border-color: rgba(255,255,255,0.08) !important;
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
    border-bottom: 1px solid rgba(255,255,255,0.08);
}
.ua-notification-item {
    background: #151A22;
    border: 1px solid rgba(255,255,255,0.08);
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
[style*="color:#8892AA" i] { color: var(--ua-text-lo) !important; }
[style*="color: #8892AA" i] { color: var(--ua-text-lo) !important; }
[style*="color:#6B7FBF" i] { color: var(--ua-text-cap) !important; }
[style*="color: #6B7FBF" i] { color: var(--ua-text-cap) !important; }
[style*="color:#4A5280" i], [style*="color:#5A6478" i] {
    color: #7F899A !important;
}
.metric-card:hover, .page-card:hover,
[data-testid="stMetric"]:hover, [data-testid="stExpander"]:hover {
    border-color: rgba(255,255,255,0.14) !important;
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
    background: #11151C !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
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
    """Explain that missing providers were excluded, never replaced or scored."""
    if n_unavailable <= 0:
        return
    st.markdown(f"""
    <div style="background:rgba(255,68,68,0.08);color:#FF8888;border-radius:10px;padding:12px 18px;
                margin-bottom:14px;font-family:Inter,sans-serif;font-size:0.83rem;
                border:1px solid rgba(255,68,68,0.3);border-left:3px solid #FF4444;">
        <b style="color:#E06C75;">REAL DATA UNAVAILABLE</b> — {n_unavailable} of {n_total} signals could not be
        loaded from their source and have been excluded from scores, rankings, and
        exports. No placeholder or synthetic observations are used. Check provider
        credentials under Setup or try again after the source recovers.
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
    if st.button(ticker_label(ticker), key=key, help=f"Deep dive: {ticker}", use_container_width=True):
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


def render_global_ticker_search() -> None:
    """
    Persistent, type-to-filter ticker search shown in the header on every
    page — jumps straight to Ticker Deep Dive on selection. Plain
    st.selectbox over every tracked ticker; Streamlit's selectbox already
    supports typing to filter a long option list, so this needed no
    custom component or JS.

    NAVIGATION-LOOP GUARD, verified live (not assumed) before shipping:
    a naive "if picked: switch_page()" would redirect every single time
    the header re-renders afterward, forever -- the selectbox's own
    session_state value persists across reruns, so `picked` stays truthy
    on every subsequent page load too. The fix is NOT to del the widget's
    session_state key after navigating -- that was tried first and
    crashes Streamlit's own widget-state bookkeeping on the next rerun
    (confirmed against a real AppTest run, not a guess). Instead, this
    compares the picked value against the last value actually acted on
    and only navigates when it's genuinely new.
    """
    # Search the FULL US-listed universe (~12.6k symbols via utils.symbols), not
    # just our 280 scored tickers — matching on symbol AND company name, filtered
    # client-side so it's instant per keystroke. Scored tickers are labeled Core.
    # The option list is static, so Streamlit ships it once per session rather
    # than on every rerun. Degrades to the tracked list if the directory is
    # unavailable, so search never breaks.
    try:
        from utils.symbols import get_symbol_index
        _sym_idx = dict(get_symbol_index())
        for _t in TICKERS:
            if _t in _sym_idx:
                _sym_idx[_t] = f"{_sym_idx[_t]} — Core"
    except Exception:
        _sym_idx = {}

    if _sym_idx:
        options = list(_sym_idx.keys())
        _fmt = lambda t: _sym_idx.get(t, t)          # noqa: E731
    else:
        options = sorted(TICKERS.keys())
        _fmt = ticker_label

    _, search_col, _ = st.columns([3, 2.2, 1.4])
    with search_col:
        picked = st.selectbox(
            "Jump to a ticker",
            options,
            index=None,
            placeholder="Search ticker or company",
            key="global_ticker_search",
            label_visibility="collapsed",
            format_func=_fmt,
        )
    if picked and picked != st.session_state.get("_last_global_ticker_search"):
        st.session_state["_last_global_ticker_search"] = picked
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
    # session-cached) because the session user dict only holds {id, email} —
    # it does NOT carry subscription_tier, so reading that key always failed.
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
  border-bottom: 1px solid rgba(255,255,255,0.06);
  display: flex; align-items: center;
  padding: 0 16px; gap: 0;
  font-family: 'Inter', -apple-system, sans-serif;
  box-shadow: 0 2px 20px rgba(0,0,0,0.4);
}

/* ── Brand ────────────────────────────────────────────────────────────────── */
.ua-tnav-brand {
  text-decoration: none !important; margin-right: 18px; flex-shrink: 0;
}
.ua-tnav-brand-text {
  font-size: 0.76rem; font-weight: 800; letter-spacing: -0.2px;
  color: #E8EEFF; white-space: nowrap;
}
.ua-tnav-brand-text em {
  font-style: normal;
  background: linear-gradient(135deg, #00D566, #00C8E0);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* ── Links row ────────────────────────────────────────────────────────────── */
.ua-tnav-links { display: flex; align-items: center; gap: 0; flex: 1; overflow: visible; }

/* ── Direct link ──────────────────────────────────────────────────────────── */
a.ua-tnav-item {
  display: inline-flex; align-items: center;
  padding: 4px 9px; border-radius: 6px; height: 30px;
  font-size: 0.74rem; font-weight: 500; color: #8892AA;
  text-decoration: none !important; white-space: nowrap;
  transition: color .12s ease, background .12s ease;
}
a.ua-tnav-item:hover { color: #E8EEFF; background: rgba(255,255,255,0.06); }
a.ua-tnav-item.active { color: #00D566 !important; background: rgba(0,213,102,0.08) !important; }

/* ── Dropdown group ───────────────────────────────────────────────────────── */
.ua-tnav-group { position: relative; display: inline-flex; align-items: center; }
.ua-tnav-trigger {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 4px 9px; border-radius: 6px; height: 30px;
  font-size: 0.74rem; font-weight: 500; color: #8892AA;
  cursor: pointer; white-space: nowrap; user-select: none;
  transition: color .12s ease, background .12s ease;
}
.ua-tnav-group:hover > .ua-tnav-trigger { color: #E8EEFF; background: rgba(255,255,255,0.06); }
.ua-tnav-trigger.active { color: #00D566 !important; background: rgba(0,213,102,0.08) !important; }
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
  border: 1px solid rgba(255,255,255,0.08); border-radius: 10px;
  padding: 5px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.03);
  backdrop-filter: blur(24px);
  display: flex; flex-direction: column; gap: 1px;
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
  display: block; padding: 7px 10px; border-radius: 6px;
  font-size: 0.74rem; font-weight: 500; color: #B8C0D4;
  text-decoration: none !important; white-space: nowrap;
  transition: color .1s ease, background .1s ease;
}
.ua-tnav-drop a:hover { color: #E8EEFF; background: rgba(255,255,255,0.07); }
.ua-tnav-drop a.active { color: #00D566 !important; background: rgba(0,213,102,0.09) !important; }
.ua-tnav-drop a.pro-link { color: #A78BFA; }
.ua-tnav-drop a.pro-link:hover { color: #C4B5FD; background: rgba(124,58,237,0.10); }
.ua-tnav-drop-rule { height: 1px; background: rgba(255,255,255,0.05); margin: 3px 2px; }

/* ── Right controls ───────────────────────────────────────────────────────── */
.ua-tnav-right { display: flex; align-items: center; gap: 7px; flex-shrink: 0; margin-left: 8px; }
.ua-tnav-upgrade {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 5px 12px; height: 30px;
  background: linear-gradient(135deg, #7C3AED, #6D28D9);
  color: #fff !important; font-size: 0.72rem; font-weight: 700;
  border-radius: 6px; text-decoration: none !important; letter-spacing: 0.01em;
  transition: all .14s ease; white-space: nowrap; flex-shrink: 0;
}
.ua-tnav-upgrade:hover {
  background: linear-gradient(135deg, #8B5CF6, #7C3AED);
  box-shadow: 0 0 18px rgba(124,58,237,0.45);
}
/* Pro members: small non-clickable status pill instead of the Upgrade CTA */
.ua-tnav-pro {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 4px 10px; height: 26px;
  background: rgba(124,58,237,0.12);
  color: #C4B5FD; font-size: 0.66rem; font-weight: 700;
  border: 1px solid rgba(124,58,237,0.35);
  border-radius: 6px; letter-spacing: 0.05em; white-space: nowrap; flex-shrink: 0;
  cursor: default;
}
/* Admin variant — gold, to distinguish from the purple Pro pill */
.ua-tnav-admin {
  background: rgba(212,175,55,0.12);
  color: #E8C766;
  border-color: rgba(212,175,55,0.40);
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
.ua-tnav-burger:hover span { background: #E8EEFF; }

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
    border-bottom: 1px solid rgba(255,255,255,0.08);
    box-shadow: 0 24px 60px rgba(0,0,0,0.75);
    backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
    padding: 6px 10px 16px; max-height: 84vh; overflow-y: auto;
  }
  .ua-tnav-toggle:checked ~ .ua-tnav-links { display: flex; }
  .ua-tnav-item { width: 100%; height: auto; padding: 11px 8px; font-size: 0.86rem; }
  .ua-tnav-group { display: block; width: 100%; }
  .ua-tnav-trigger {
    width: 100%; height: auto; padding: 12px 8px 4px; font-size: 0.62rem;
    font-weight: 700; letter-spacing: 0.10em; text-transform: uppercase;
    color: #6B7FBF; cursor: default;
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
        <a class="pro-link" href="/thesis-journal">Thesis Journal</a>
        <a class="pro-link" href="/portfolio-suite">Portfolio Suite</a>
      </div>
    </div>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger">Research <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/ticker-deep-dive">Ticker Deep Dive</a>
        <a href="/stock-screener">Stock Screener</a>
        <a class="pro-link" href="/stock-recommender">Stock Recommender</a>
        <a class="pro-link" href="/options-flow">Options Flow</a>
      </div>
    </div>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger">Signals <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/signal-dashboard">Signal Dashboard</a>
        <a href="/sector-view">Sector View</a>
        <a href="/market-overview">Market Overview</a>
        <a href="/power-supercycle">Power Supercycle</a>
        <a href="/model-validation">Model Validation</a>
        <a href="/track-record">Track Record</a>
        <a href="/how-signals-work">How Signals Work</a>
      </div>
    </div>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger">Monitoring <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/my-watchlist">Watchlist Alerts</a>
        <a href="/events-forecasts">Events &amp; Forecasts</a>
      </div>
    </div>

    <div class="ua-tnav-group ua-tnav-hide-sm">
      <span class="ua-tnav-trigger">More <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/ai-research-assistant">AI Assistant</a>
        <a href="/my-profile">My Profile</a>
        <a href="/about-methodology">About &amp; Methodology</a>
        <div class="ua-tnav-drop-rule"></div>
        <a href="/privacy-terms" style="font-size:0.68rem;color:#6B7FBF;">Privacy &amp; Terms</a>
        __ADMIN_NAV_SLOT__
      </div>
    </div>
  </div>

  <div class="ua-tnav-right">
    __UPGRADE_SLOT__
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
      .replace("__ADMIN_NAV_SLOT__", _admin_nav_slot))


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


def render_header(page_subtitle: str = "") -> None:
    """
    Inject global CSS and render the Unstructured Alpha masthead.
    Call this immediately after st.set_page_config() on every page.

    Args:
        page_subtitle: Short section name shown on the right side of the header bar
                       (e.g. "Signal Dashboard", "Market Overview").
    """
    from datetime import datetime
    from utils.theme import _MODERN_UI_CSS  # deferred to avoid circular import at module level

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

    st.markdown(_CSS, unsafe_allow_html=True)
    # Inject modern UI system (pill tabs, glass buttons, metrics, etc.) globally
    # so every page that calls render_header() gets it automatically.
    st.markdown(_MODERN_UI_CSS, unsafe_allow_html=True)

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
    _status_bg    = "rgba(0,213,102,0.10)" if _market_open else "rgba(255,68,68,0.08)"
    _status_fg    = "#00D566" if _market_open else "#FF4444"
    _status_dot   = "#00D566" if _market_open else "#FF4444"
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
                '<span style="background:#7C3AED;color:#fff;font-size:0.55rem;font-weight:700;'
                'padding:1px 5px;border-radius:4px;margin-left:4px;letter-spacing:0.04em;">PRO</span>'
            )
        else:
            _tier_badge = ""
        _user_pill = (
            f'<span style="display:inline-flex;align-items:center;gap:4px;'
            f'background:rgba(0,213,102,0.08);border:1px solid rgba(0,213,102,0.2);'
            f'border-radius:6px;padding:2px 8px;font-size:0.68rem;color:#00D566;'
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

    st.markdown(f"""
    <div class="ua-header">
        <div class="ua-header-left">
            <div class="ua-wordmark">UNSTRUCTURED <span>ALPHA</span></div>
            <div class="ua-tagline">Alternative Data Intelligence &mdash; what&rsquo;s coming, not what happened</div>
        </div>
        <div class="ua-header-right">{right_html}</div>
    </div>
    <div class="gold-rule"></div>
    """, unsafe_allow_html=True)

    # ── Sticky Macro Regime Bar ────────────────────────────────────────────────
    # One slim line visible on every page so users never lose macro context.
    # Uses the shared 2h cache — zero extra API cost.
    try:
        from utils.signals_cache import get_all_signal_scores as _gss
        _rs = _gss()
        _rb  = sum(1 for v in _rs.values() if not v.get("error") and v.get("status") == "bullish")
        _rr  = sum(1 for v in _rs.values() if not v.get("error") and v.get("status") == "bearish")
        _rn  = sum(1 for v in _rs.values() if not v.get("error") and v.get("status") == "neutral")
        _rscored = _rb + _rr + _rn
        _rto = max(1, _rscored)
        # Signals in the registry that couldn't be scored this cycle (error /
        # insufficient recent data). Surfaced so the bar's numbers reconcile to
        # the advertised SIGNAL_COUNT instead of silently dropping ~6 signals.
        _runavail = max(0, SIGNAL_COUNT - _rscored)
        _rbp = _rb / _rto
        _rrp = _rr / _rto
        if _rbp >= 0.58:
            _regime_lbl, _regime_col, _regime_bg = "RISK-ON", "#00D566", "rgba(0,213,102,0.06)"
        elif _rrp >= 0.52:
            _regime_lbl, _regime_col, _regime_bg = "RISK-OFF", "#FF4444", "rgba(255,68,68,0.06)"
        elif _rbp >= 0.48:
            _regime_lbl, _regime_col, _regime_bg = "LEANING BULLISH", "#00A847", "rgba(0,168,71,0.05)"
        elif _rrp >= 0.44:
            _regime_lbl, _regime_col, _regime_bg = "LEANING BEARISH", "#CC3333", "rgba(204,51,51,0.05)"
        else:
            _regime_lbl, _regime_col, _regime_bg = "MIXED SIGNALS", "#6B7FBF", "rgba(107,127,191,0.05)"
        st.markdown(
            f'<div style="background:{_regime_bg};border:1px solid rgba(255,255,255,0.06);'
            f'border-left:3px solid {_regime_col};'
            f'border-radius:8px;padding:6px 14px;margin-bottom:12px;'
            f'display:flex;align-items:center;gap:16px;font-family:Inter,sans-serif;">'
            f'<span style="font-size:0.60rem;color:#8892AA;text-transform:uppercase;letter-spacing:0.11em;font-weight:700;">MACRO REGIME</span>'
            f'<span style="font-size:0.75rem;font-weight:700;color:{_regime_col};">● {_regime_lbl}</span>'
            f'<span style="font-size:0.68rem;color:#8892AA;">'
            f'<span style="color:#00D566;">▲ {_rb}</span>'
            f' · <span style="color:#FF4444;">▼ {_rr}</span>'
            f' · <span style="color:#6B7FBF;">→ {_rn}</span>'
            + (f' · <span style="color:#5A6478;" title="Signals with insufficient recent data this cycle">⊘ {_runavail}</span>' if _runavail else "")
            + f'</span>'
            f'<span style="font-size:0.60rem;color:#6B7FBF;margin-left:auto;">{SIGNAL_COUNT} signals · 2h cache</span>'
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
                get_unread_notification_count, get_recent_notifications, mark_all_read
            )
            _unread = get_unread_notification_count(_uid)
            _badge_text = f" {_unread if _unread < 100 else '99+'}" if _unread > 0 else ""
            _notification_api = (get_recent_notifications, mark_all_read)
            with _bell_col:
                if st.button(
                    f"Notifications{_badge_text}",
                    key="_notification_tray_toggle",
                    use_container_width=True,
                ):
                    st.session_state["_notification_tray_open"] = not st.session_state.get(
                        "_notification_tray_open", False
                    )
        except Exception:
            pass  # Never crash the header for a notification badge

    # Account widget — all users
    with _acct_col:
        if _hdr_user:
            with st.popover("Account", use_container_width=True):
                if st.button("Log Out", key="topright_logout", use_container_width=True):
                    logout()
                    st.rerun()
        else:
            with st.popover("Sign In", use_container_width=True):
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
                _get_recent_notifications, _mark_all_read = _notification_api
                _notifs = _get_recent_notifications(limit=10)
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
                if _unread > 0 and st.button(
                    "Mark all read",
                    key="_notif_mark_read",
                    use_container_width=True,
                ):
                    _mark_all_read(_uid)
                    st.rerun()


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
        color = "#00D566" if chg >= 0 else "#FF4444"
        # Always show two decimal places for every price (e.g. $225.34, $1,234.56).
        p_fmt = f"${price:,.2f}"
        chips.append(
            f'<span style="display:inline-flex;align-items:center;gap:6px;'
            f'padding:0 14px;border-right:1px solid rgba(255,255,255,0.06);">'
            f'<span style="color:#8892AA;font-weight:600;font-size:0.68rem;">{sym}</span>'
            f'<span style="color:#E8EEFF;font-weight:700;font-size:0.70rem;">{p_fmt}</span>'
            f'<span style="color:{color};font-size:0.68rem;font-weight:600;">{arrow} {abs(chg):.2f}%</span>'
            f'</span>'
        )

    inner = "".join(chips)
    # Duplicate for seamless marquee loop
    ticker_html = f"""
<div style="background:rgba(12,14,20,0.95);border-bottom:1px solid rgba(255,255,255,0.05);
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
        f'background:#11151C;border:1px solid rgba(255,255,255,0.09);'
        f'border-radius:6px;padding:5px 10px;font-size:0.66rem;font-weight:650;'
        f'color:#AAB3C5;letter-spacing:0.04em;white-space:nowrap;font-family:Inter,sans-serif;">'
        f'{live_stat}</div>'
    ) if live_stat else ""

    sub_html = (
        f'<div style="font-size:0.86rem;color:#8892AA;margin-top:5px;line-height:1.5;'
        f'font-weight:400;font-family:Inter,sans-serif;max-width:640px;">{subtitle}</div>'
    ) if subtitle else ""

    st.markdown(f"""
<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px;
            margin:8px 0 20px;padding-bottom:16px;position:relative;
            border-bottom:1px solid rgba(255,255,255,0.05);"
     class="ua-slide-up">
    <div>
        <div style="font-size:1.8rem;font-weight:720;letter-spacing:-0.55px;line-height:1.15;
                    font-family:Inter,sans-serif;display:flex;align-items:center;flex-wrap:wrap;">
            {icon_html}<span style="color:#E4E9F2;">{title}</span>
        </div>
        {sub_html}
    </div>
    <div style="padding-top:4px;flex-shrink:0;">{stat_html}</div>
</div>
""", unsafe_allow_html=True)


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
            '<div style="font-size:0.70rem;color:#6B7FBF;margin-top:4px;">'
            'Signal scores are 0–100 percentile ranks within a trailing 2-year '
            'distribution. A score of 65+ is "bullish" (top percentile); 35− is '
            '"bearish." Scores are informational — they do not predict specific price '
            'targets or returns for any security.'
            '</div>'
        )
    elif page == "ticker":
        _page_note_html = (
            '<div style="font-size:0.70rem;color:#6B7FBF;margin-top:4px;">'
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
        'background:rgba(124,58,237,0.12);border:1px solid rgba(124,58,237,0.35);'
        'padding:5px 12px;border-radius:6px;white-space:nowrap;">Pro member</span>'
        if _foot_is_pro else
        '<a href="/upgrade-to-pro" style="font-size:0.68rem;color:#fff;text-decoration:none;'
        'font-weight:700;background:linear-gradient(135deg,#7C3AED,#6D28D9);'
        'padding:5px 12px;border-radius:6px;white-space:nowrap;" '
        'onmouseover="this.style.opacity=\'0.88\'" '
        'onmouseout="this.style.opacity=\'1\'">Upgrade to Pro</a>'
    )

    # st.html (not st.markdown) — this footer is multi-line indented HTML, which
    # the markdown parser would turn into a code block and dump as raw text at the
    # bottom of the page (same bug that hit the top-nav). st.html skips markdown.
    st.html(f"""
<div style="margin-top:48px;padding:28px 0 20px;border-top:1px solid rgba(255,255,255,0.05);
            font-family:Inter,sans-serif;">
    <div style="max-width:900px;margin:0 auto;padding:0 16px;">

        <!-- Primary disclaimer -->
        <div style="background:rgba(18,21,30,0.6);border:1px solid rgba(255,255,255,0.06);
                    border-radius:10px;padding:16px 20px;margin-bottom:16px;">
            <div style="font-size:0.65rem;font-weight:700;color:#8892AA;letter-spacing:0.10em;
                        text-transform:uppercase;margin-bottom:6px;">
                Important Disclaimer
            </div>
            <div style="font-size:0.73rem;color:#6B7FBF;line-height:1.65;">
                Unstructured Alpha is for <strong style="color:#8892AA;">educational and informational
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
                <div style="font-size:0.63rem;color:#4A5280;line-height:1.6;">
                    Data sourced from public APIs:&nbsp;
                    <span style="color:#8892AA;font-weight:600;">FRED</span> (Federal Reserve) ·
                    <span style="color:#8892AA;font-weight:600;">SEC EDGAR</span> (insider filings) ·
                    <span style="color:#8892AA;font-weight:600;">FINRA</span> (short interest) ·
                    <span style="color:#8892AA;font-weight:600;">EIA</span> (energy data) ·
                    <span style="color:#8892AA;font-weight:600;">yfinance</span> (price data)
                </div>
                <div style="font-size:0.63rem;color:#4A5280;margin-top:3px;">
                    Signal data cached every ~2 hours. Scores are not real-time.
                    © {_year} Unstructured Alpha. All rights reserved.
                </div>
            </div>
            <div style="display:flex;gap:14px;align-items:center;flex-shrink:0;">
                <a href="/about-methodology" style="font-size:0.68rem;color:#6B7FBF;text-decoration:none;
                                           font-weight:500;" onmouseover="this.style.color='#00C8E0'"
                   onmouseout="this.style.color='#6B7FBF'">About</a>
                <a href="/privacy-terms" style="font-size:0.68rem;color:#6B7FBF;text-decoration:none;
                                                     font-weight:500;" onmouseover="this.style.color='#00C8E0'"
                   onmouseout="this.style.color='#6B7FBF'">Privacy</a>
                <a href="/privacy-terms" style="font-size:0.68rem;color:#6B7FBF;text-decoration:none;
                                                       font-weight:500;" onmouseover="this.style.color='#00C8E0'"
                   onmouseout="this.style.color='#6B7FBF'">Terms</a>
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
) -> str | None:
    """
    Render the standard sidebar content (account info, FRED key input, AI
    assistant link, disclaimer) and, when supplied, a page-local section rail.

    The section rail intentionally uses a radio + normal Python branching
    instead of st.tabs(). Streamlit eagerly executes every tab body, while this
    pattern executes only the selected section — reducing load time and keeping
    long research pages focused. Existing call sites remain backward compatible.
    """
    selected_section: str | None = None
    with st.sidebar:
        # Account info — most pages no longer require login (per explicit
        # user request), so an anonymous visitor is a completely normal,
        # expected case here, not an edge case. This sidebar block is just
        # a secondary "you're logged in" indicator + quick Log Out; the
        # actual sign-in entry point is the top-right widget rendered by
        # render_header() (utils.auth_ui.render_account_widget()).
        user = st.session_state.get("user")
        if user:
            st.markdown(
                f'<div style="font-size:0.78rem;color:#8892AA;margin-bottom:4px;">'
                f'Logged in as<br><b style="color:#E8EEFF;">{user["email"]}</b></div>',
                unsafe_allow_html=True,
            )
            if st.button("Log Out", key="sidebar_logout", use_container_width=True):
                from utils.auth_ui import logout
                logout()
                st.rerun()
            st.divider()

        # Dark mode toggle — persists preference in localStorage
        render_dark_mode_toggle()
        st.divider()

        if sections:
            _options = list(sections)
            _default = default_section if default_section in _options else _options[0]
            st.markdown(
                f'<div style="font-size:0.60rem;font-weight:800;color:#6B7FBF;'
                f'letter-spacing:0.13em;text-transform:uppercase;margin:2px 0 5px;">'
                f'{page_title or "On this page"}</div>',
                unsafe_allow_html=True,
            )
            selected_section = st.radio(
                "Page section",
                _options,
                index=_options.index(_default),
                key=section_key or f"section_rail_{(page_title or 'page').lower().replace(' ', '_')}",
                label_visibility="collapsed",
            )
            st.caption("Only this section is loaded.")
            st.divider()

        # AI Assistant quick-access
        st.markdown(
            '<div style="background:rgba(184,134,11,0.13);border-radius:6px;padding:10px 12px;'
            'border:1px solid rgba(184,134,11,0.35);margin-bottom:6px;">'
            '<div style="font-size:0.68rem;color:#C9A84C;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">AI Research Assistant</div>'
            '<div style="font-size:0.79rem;color:rgba(255,255,255,0.75);margin-top:3px;line-height:1.4;">'
            'Questions about signals, tickers, or methodology?</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.page_link("pages/9_AI_Assistant.py", label="Open AI Assistant")

        st.divider()
        st.markdown(
            '<div style="font-size:0.72rem;color:rgba(201,168,76,0.55);line-height:1.5;padding:0 2px;">'
            '<b style="color:rgba(201,168,76,0.70);">Not financial advice.</b> '
            'All signals are interpretations of publicly available data. '
            'Do your own research before making any investment decision.'
            '</div>',
            unsafe_allow_html=True,
        )
    return selected_section
