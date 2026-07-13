"""
Shared header + CSS injected at the top of every page.
Call render_header() as the very first Streamlit call after st.set_page_config().
"""

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
    --ua-text-hi:    #E8EEFF;
    --ua-text-mid:   #B8C0D4;
    --ua-text-lo:    #8892AA;
    --ua-text-cap:   #6B7FBF;
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
p  { color: #B8C0D4 !important; font-family: 'Inter', sans-serif !important; }

/* Radio / Checkbox */
.stRadio label, .stCheckbox label { color: #B8C0D4 !important; font-family: 'Inter', sans-serif !important; }

/* Caption */
.stCaption, small { color: #8892AA !important; font-family: 'Inter', sans-serif !important; }

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
</style>
"""

# _DARK_CSS is kept for backward compat but no longer needed — dark IS the default.
_DARK_CSS = "<style>/* dark mode is now the default design */</style>"

_DARK_JS = ""  # No longer needed — dark is the permanent design.


def render_dark_mode_toggle() -> None:
    """No-op: dark mode is now the permanent base design, toggle removed."""
    pass


def render_synthetic_data_banner(n_synthetic: int, n_total: int) -> None:
    """
    Render an unmissable banner when any FRED-sourced data on the page is
    synthetic placeholder data (shown whenever no FRED API key is configured,
    or a live fetch failed). Intentionally loud — a quiet caption is how a
    user mistakes a fabricated chart for a real one.
    """
    if n_synthetic <= 0:
        return
    st.markdown(f"""
    <div style="background:rgba(255,68,68,0.08);color:#FF8888;border-radius:10px;padding:12px 18px;
                margin-bottom:14px;font-family:Inter,sans-serif;font-size:0.83rem;
                border:1px solid rgba(255,68,68,0.3);border-left:3px solid #FF4444;">
        <b style="color:#FF4444;">⚠ DEMO DATA</b> — {n_synthetic} of {n_total} signals on this page are showing
        synthetic placeholder data, not real values. This happens when no FRED API
        key is configured or a live fetch fails. Add a free key in the sidebar under
        "Setup" for real data — until then, treat any bullish/bearish reading from
        these signals as illustrative only.
    </div>
    """, unsafe_allow_html=True)


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
    options = sorted(TICKERS.keys())
    _, search_col, _ = st.columns([3, 2.2, 1.4])
    with search_col:
        picked = st.selectbox(
            "Jump to a ticker",
            options,
            index=None,
            placeholder="🔍 Search any ticker…",
            key="global_ticker_search",
            label_visibility="collapsed",
            format_func=ticker_label,
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
    """
    st.markdown("""
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
  cursor: default; white-space: nowrap; user-select: none;
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
  transition: opacity .12s ease, visibility .12s ease;
}
.ua-tnav-group:hover .ua-tnav-drop { visibility: visible; opacity: 1; pointer-events: auto; }
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

/* ── Responsive ───────────────────────────────────────────────────────────── */
@media (max-width: 860px) { .ua-tnav-hide-sm { display: none !important; } }
@media (max-width: 640px) {
  .ua-topnav { padding: 0 10px; }
  .ua-tnav-brand-text { font-size: 0.70rem; }
}
</style>

<nav class="ua-topnav" role="navigation" aria-label="Main navigation">
  <a class="ua-tnav-brand" href="/">
    <span class="ua-tnav-brand-text">UNSTRUCTURED <em>ALPHA</em></span>
  </a>

  <div class="ua-tnav-links">
    <a class="ua-tnav-item" href="/" data-paths="/,/home">Home</a>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger">Daily Intel <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/today-s-brief">Today&#39;s Brief</a>
        <a href="/alternative-data">Alternative Data</a>
        <a href="/events-forecasts">Events &amp; Forecasts</a>
      </div>
    </div>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger">Signals <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/signal-dashboard">Signal Dashboard</a>
        <a href="/sector-view">Sector View</a>
      </div>
    </div>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger">Research <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/ticker-deep-dive">Ticker Deep Dive</a>
        <a href="/market-overview">Market Overview</a>
        <a href="/stock-screener">Stock Screener</a>
        <a href="/power-supercycle">Power Supercycle</a>
        <a href="/track-record">Track Record</a>
        <a href="/signal-strategy" class="ua-tnav-hide-sm">Signal Strategy</a>
      </div>
    </div>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger">Watchlist <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/my-watchlist">My Watchlist</a>
        <a href="/stock-chart">Stock Chart</a>
      </div>
    </div>

    <div class="ua-tnav-group">
      <span class="ua-tnav-trigger" style="color:#A78BFA;">&#9889; Pro <span class="ua-tnav-caret" style="color:#A78BFA;">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a class="pro-link" href="/stock-recommender">Stock Recommender</a>
        <a class="pro-link" href="/portfolio-suite">Portfolio Suite</a>
      </div>
    </div>

    <div class="ua-tnav-group ua-tnav-hide-sm">
      <span class="ua-tnav-trigger">More <span class="ua-tnav-caret">&#9660;</span></span>
      <div class="ua-tnav-drop">
        <a href="/my-profile">My Profile</a>
        <a href="/ai-research-assistant">AI Assistant</a>
        <a href="/about-methodology">About &amp; Methodology</a>
        <a href="/how-signals-work">How Signals Work</a>
        <div class="ua-tnav-drop-rule"></div>
        <a href="/privacy-terms" style="font-size:0.68rem;color:#6B7FBF;">Privacy &amp; Terms</a>
      </div>
    </div>
  </div>

  <div class="ua-tnav-right">
    <a class="ua-tnav-upgrade" href="/upgrade-to-pro">&#9889; Upgrade</a>
  </div>
</nav>

<script>
(function(){
  try {
    var path = (window.location.pathname || '/').replace(/\/+$/, '') || '/';
    document.querySelectorAll('.ua-tnav-drop a').forEach(function(a){
      var hp = (a.getAttribute('href') || '').replace(/\/+$/, '') || '/';
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
""", unsafe_allow_html=True)


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

    # ── Horizontal topnav (replaces sidebar, hides Streamlit chrome) ───────────
    _render_topnav()

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
        {property: 'og:title',        content: 'Unstructured Alpha — 43-Signal Macro Intelligence'},
        {property: 'og:description',  content: 'Score insider trades, credit spreads, energy inventories and 44 other signals daily. Free to browse. Pro $20/mo.'},
        {name:     'description',     content: 'Score insider trades, credit spreads, energy inventories and 44 other macro signals daily. Confluence Score for any stock. Free to browse.'},
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
    _is_pro = (_user or {}).get("subscription_tier", "") == "pro"
    _user_pill = ""
    if _user_email:
        _tier_badge = (
            '<span style="background:#7C3AED;color:#fff;font-size:0.55rem;font-weight:700;'
            'padding:1px 5px;border-radius:4px;margin-left:4px;letter-spacing:0.04em;">PRO</span>'
        ) if _is_pro else ""
        _user_pill = (
            f'<span style="display:inline-flex;align-items:center;gap:4px;'
            f'background:rgba(0,213,102,0.08);border:1px solid rgba(0,213,102,0.2);'
            f'border-radius:6px;padding:2px 8px;font-size:0.68rem;color:#00D566;'
            f'font-weight:600;font-family:Inter,sans-serif;white-space:nowrap;">'
            f'👤 {_user_email}{_tier_badge}</span>'
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
        _rto = max(1, _rb + _rr + _rn)
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
            f'</span>'
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

    # ── Top-right widget row: bell (logged-in only) + account ─────────────────
    # Single st.columns() call so both widgets share one horizontal row.
    # Bell is only rendered for logged-in users (no point showing notifications
    # to a guest who has no account-linked data).
    from utils.auth_ui import get_cookies, try_restore_session, render_auth_forms, logout
    _cookies = get_cookies()
    _hdr_user = try_restore_session(_cookies)
    _uid = (_hdr_user or {}).get("id")

    _space, _bell_col, _acct_col = st.columns([4.2, 0.45, 1.55])

    # Bell — logged-in users only
    if _uid:
        try:
            from utils.prediction_log import (
                get_unread_notification_count, get_recent_notifications, mark_all_read
            )
            _unread = get_unread_notification_count(_uid)
            _badge_text = f" ({min(_unread, 99)})" if _unread > 0 else ""
            with _bell_col:
                with st.popover(f"🔔{_badge_text}", use_container_width=True):
                    st.markdown(
                        '<div style="font-size:0.62rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;'
                        'text-transform:uppercase;margin-bottom:10px;border-bottom:1px solid rgba(255,255,255,0.06);'
                        'padding-bottom:6px;font-family:Inter,sans-serif;">System Notifications</div>',
                        unsafe_allow_html=True,
                    )
                    _notifs = get_recent_notifications(limit=15)
                    if not _notifs:
                        st.caption("No notifications yet. Convergence events and prediction resolutions will appear here.")
                    else:
                        _NOTIF_ICONS = {
                            "convergence":          "⚡",
                            "regime_change":        "📈",
                            "near_flip":            "⏳",
                            "prediction_resolved":  "📊",
                        }
                        for _n in _notifs:
                            _icon = _NOTIF_ICONS.get(_n.get("notif_type", ""), "●")
                            _n_bg = "rgba(0,213,102,0.06)" if _n.get("direction") == "bull" else (
                                    "rgba(255,68,68,0.06)" if _n.get("direction") == "bear" else "rgba(18,21,30,0.6)"
                            )
                            _n_border = "#00D566" if _n.get("direction") == "bull" else (
                                        "#FF4444" if _n.get("direction") == "bear" else "rgba(255,255,255,0.07)"
                            )
                            _n_ts = _n.get("created_at", "")[:10]
                            st.markdown(
                                f'<div style="background:{_n_bg};border-radius:8px;padding:8px 10px;'
                                f'margin-bottom:6px;border-left:3px solid {_n_border};font-family:Inter,sans-serif;">'
                                f'<div style="font-size:0.76rem;font-weight:600;color:#E8EEFF;">'
                                f'{_icon} {_n.get("title","")}</div>'
                                f'<div style="font-size:0.70rem;color:#8892AA;margin-top:3px;line-height:1.4;">'
                                f'{_n.get("body","")}</div>'
                                f'<div style="font-size:0.60rem;color:#8892AA;margin-top:4px;">{_n_ts}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                    if _unread > 0:
                        if st.button("Mark all read", key="_notif_mark_read", use_container_width=True):
                            mark_all_read(_uid)
                            st.rerun()
        except Exception:
            pass  # Never crash the header for a notification badge

    # Account widget — all users
    with _acct_col:
        if _hdr_user:
            with st.popover("⚙ Account", use_container_width=True):
                if st.button("Log Out", key="topright_logout", use_container_width=True):
                    logout()
                    st.rerun()
        else:
            with st.popover("Sign In", use_container_width=True):
                render_auth_forms(_cookies, key_prefix="widget_")


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def _fetch_ticker_strip():
    """Fetch live prices for the header ticker strip. 60s TTL, one set of symbols."""
    import yfinance as yf
    _SYMBOLS = [
        ("SPY",    "S&P 500"),
        ("QQQ",    "Nasdaq"),
        ("BTC-USD","Bitcoin"),
        ("GC=F",   "Gold"),
        ("CL=F",   "WTI Oil"),
        ("^VIX",   "VIX"),
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
        # Format price (crypto needs more decimals)
        p_fmt = f"${price:,.0f}" if price >= 100 else f"${price:,.2f}"
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
    Modern page title with gradient text, animated underline accent, and
    optional live right-side stat chip.

    Args:
        title:     Page title — displayed with gradient text + animated accent.
        subtitle:  One-line description of what the page does.
        icon:      Optional emoji/icon prefix for the title (e.g. "📊").
        live_stat: Optional right-aligned stat string (e.g. "47 signals active").
    """
    icon_html = (
        f'<span style="margin-right:9px;font-size:1.55rem;vertical-align:middle;'
        f'line-height:1;">{icon}</span>'
    ) if icon else ""

    stat_html = (
        f'<div style="display:inline-flex;align-items:center;gap:6px;'
        f'background:rgba(0,213,102,0.07);border:1px solid rgba(0,213,102,0.18);'
        f'border-radius:20px;padding:4px 12px;font-size:0.68rem;font-weight:700;'
        f'color:#00D566;letter-spacing:0.06em;white-space:nowrap;font-family:Inter,sans-serif;">'
        f'<span class="ua-pulse-dot" style="margin-right:2px;"></span>{live_stat}</div>'
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
    <!-- Animated gradient accent line -->
    <div style="position:absolute;bottom:-1px;left:0;width:200px;height:2px;
                background:linear-gradient(90deg,#00D566,#00C8E0,#7C3AED);
                background-size:300% 100%;
                animation:ua_gradient_x 5s ease infinite;
                border-radius:1px;"></div>
    <div>
        <div style="font-size:1.9rem;font-weight:800;letter-spacing:-0.7px;line-height:1.1;
                    font-family:Inter,sans-serif;display:flex;align-items:center;flex-wrap:wrap;">
            {icon_html}<span style="background:linear-gradient(135deg,#E8EEFF 0%,#C8D0E4 100%);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
            background-clip:text;">{title}</span>
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

    st.markdown(f"""
<div style="margin-top:48px;padding:28px 0 20px;border-top:1px solid rgba(255,255,255,0.05);
            font-family:Inter,sans-serif;">
    <div style="max-width:900px;margin:0 auto;padding:0 16px;">

        <!-- Primary disclaimer -->
        <div style="background:rgba(18,21,30,0.6);border:1px solid rgba(255,255,255,0.06);
                    border-radius:10px;padding:16px 20px;margin-bottom:16px;">
            <div style="font-size:0.65rem;font-weight:700;color:#8892AA;letter-spacing:0.10em;
                        text-transform:uppercase;margin-bottom:6px;">
                ⚠ Important Disclaimer
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
            <div style="display:flex;gap:14px;flex-shrink:0;">
                <a href="/8_About" style="font-size:0.68rem;color:#6B7FBF;text-decoration:none;
                                           font-weight:500;" onmouseover="this.style.color='#00C8E0'"
                   onmouseout="this.style.color='#6B7FBF'">About</a>
                <a href="/36_Privacy_Policy" style="font-size:0.68rem;color:#6B7FBF;text-decoration:none;
                                                     font-weight:500;" onmouseover="this.style.color='#00C8E0'"
                   onmouseout="this.style.color='#6B7FBF'">Privacy Policy</a>
                <a href="/37_Terms_of_Service" style="font-size:0.68rem;color:#6B7FBF;text-decoration:none;
                                                       font-weight:500;" onmouseover="this.style.color='#00C8E0'"
                   onmouseout="this.style.color='#6B7FBF'">Terms of Service</a>
                <a href="/Upgrade" style="font-size:0.68rem;color:#7C3AED;text-decoration:none;
                                          font-weight:600;" onmouseover="this.style.color='#A78BFA'"
                   onmouseout="this.style.color='#7C3AED'">Pro ⚡</a>
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


def render_sidebar_base() -> None:
    """
    Render the standard sidebar content (account info, FRED key input, AI
    assistant link, disclaimer). Call inside a `with st.sidebar:` block or
    standalone.
    """
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
