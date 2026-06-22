"""
Shared header + CSS injected at the top of every page.
Call render_header() as the very first Streamlit call after st.set_page_config().
"""

import streamlit as st

from utils.config import TICKERS

# ── Shared WSJ / Bloomberg CSS ──────────────────────────────────────────────
_CSS = """
<style>
html, body, [class*="css"] {
    font-family: Georgia, "Times New Roman", serif !important;
    font-variant-numeric: tabular-nums;
}

/* Bloomberg-style tabular monospace for headline figures — keeps digits from
   "jiggling" in stacked card grids, the way terminal-style data displays do. */
.stat-value, .score-number, [data-testid="stMetricValue"], .mono-num {
    font-family: "SF Mono", "Roboto Mono", "Consolas", "Menlo", monospace !important;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
}

/* Market open/closed status badge, shown in the masthead */
.market-status-badge {
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em;
    padding: 2px 8px; border-radius: 3px;
    font-family: "SF Mono", "Roboto Mono", "Consolas", monospace !important;
}
.market-status-dot {
    width: 6px; height: 6px; border-radius: 50%; display: inline-block;
}

/* Page background */
.main { background-color: #FAF7F0 !important; }

/* Sidebar */
section[data-testid="stSidebar"] { background-color: #1C2B4A !important; }
section[data-testid="stSidebar"] * { color: #F0EBE1 !important; }
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] a,
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stTextInput label { color: #C9A84C !important; }
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #FAF7F0 !important;
    border-bottom: 1px solid rgba(201,168,76,0.35);
    padding-bottom: 4px;
}
section[data-testid="stSidebar"] .stButton > button {
    background-color: #B8860B !important;
    color: #FAF7F0 !important;
    border: none !important;
}

/* Masthead */
.ua-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    border-bottom: 3px solid #1C2B4A;
    padding-bottom: 10px;
    margin-bottom: 0;
}
.ua-header-left {}
.ua-wordmark {
    font-size: 2.0rem;
    font-weight: 700;
    color: #1C2B4A;
    font-family: Georgia, serif;
    letter-spacing: -0.5px;
    line-height: 1.15;
}
.ua-wordmark span { color: #B8860B; }
.ua-tagline {
    font-size: 0.82rem;
    color: #8B7355;
    font-family: Georgia, serif;
    font-style: italic;
    margin-top: 1px;
    letter-spacing: 0.02em;
}
.ua-header-right {
    text-align: right;
    font-size: 0.78rem;
    color: #8B7355;
    font-family: Georgia, serif;
    padding-bottom: 2px;
}
.ua-header-right b { color: #1C2B4A; }
.gold-rule {
    height: 3px;
    background: linear-gradient(90deg, #B8860B, #C9A84C, #B8860B);
    border: none;
    margin: 0 0 18px 0;
}

/* Metric cards */
.metric-card {
    background: #F0EBE1;
    border-radius: 6px;
    padding: 16px 20px;
    border-left: 4px solid #B8860B;
    border: 1px solid #D4C9B0;
    border-left: 4px solid #B8860B;
    margin-bottom: 10px;
    font-family: Georgia, serif;
}
.metric-card.bull  { border-left-color: #1B5E20; }
.metric-card.bear  { border-left-color: #7B1010; }
.metric-card.neutral { border-left-color: #8B7355; }
.metric-card b { color: #1A1612; }
.metric-card span { color: #6B6560; }

/* Page cards */
.page-card {
    background: #F0EBE1;
    border-radius: 6px;
    padding: 18px 20px;
    border: 1px solid #D4C9B0;
    border-left: 4px solid #B8860B;
    margin-bottom: 12px;
    transition: border-left-color 0.15s;
}
.page-card:hover { border-left-color: #1C2B4A; }
.page-card .page-title { font-size: 1.0rem; font-weight: 700; color: #1C2B4A; margin-bottom: 4px; }
.page-card .page-desc  { font-size: 0.83rem; color: #6B6560; line-height: 1.5; }

/* Section header */
.section-header {
    font-size: 1.0rem; font-weight: 700; color: #1C2B4A;
    font-family: Georgia, serif;
    border-bottom: 2px solid #B8860B;
    padding-bottom: 4px; margin-bottom: 14px;
    letter-spacing: 0.02em;
}

/* Score */
.score-number { font-size: 2.4rem; font-weight: 700; line-height: 1.1; font-family: Georgia, serif; }
.score-bull    { color: #1B5E20; }
.score-bear    { color: #7B1010; }
.score-neutral { color: #8B7355; }

/* Disclaimer */
.disclaimer {
    background: #F0EBE1; border: 1px solid #D4C9B0; border-radius: 6px;
    padding: 10px 14px; font-size: 0.76rem; color: #8B7355; margin-top: 16px;
    font-family: Georgia, serif;
}

/* Info box */
.info-box {
    background: #EEF3F7; border: 1px solid #A8BCD0; border-radius: 6px;
    padding: 12px 16px; margin-bottom: 12px; font-size: 0.87rem;
    color: #1C2B4A; font-family: Georgia, serif;
}

/* Comparison table */
.comparison-table { width: 100%; border-collapse: collapse; font-family: Georgia, serif; font-size: 0.87rem; }
.comparison-table th { background: #1C2B4A; color: #FAF7F0; padding: 8px 12px; text-align: left; font-weight: 600; }
.comparison-table td { padding: 7px 12px; border-bottom: 1px solid #D4C9B0; color: #1A1612; }
.comparison-table tr:nth-child(even) td { background: #F0EBE1; }
.comparison-table tr.highlight td { background: #FFF8E7; font-weight: 600; }

/* Streamlit native overrides */
.stMetric label { color: #6B6560 !important; font-size: 0.78rem !important; }
.stMetric [data-testid="stMetricValue"] { color: #1C2B4A !important; font-family: Georgia, serif !important; font-size: 1.5rem !important; }
div[data-testid="stExpander"] { background: #F0EBE1 !important; border: 1px solid #D4C9B0 !important; border-radius: 6px !important; }
.streamlit-expanderHeader { color: #1C2B4A !important; font-family: Georgia, serif !important; font-weight: 600 !important; }

/* Data tables */
.ua-data-table { width: 100%; border-collapse: collapse; font-family: Georgia, serif; font-size: 0.84rem; }
.ua-data-table th { background: #1C2B4A; color: #FAF7F0; padding: 7px 10px; text-align: left; font-weight: 600; font-size: 0.80rem; letter-spacing: 0.04em; text-transform: uppercase; }
.ua-data-table td { padding: 7px 10px; border-bottom: 1px solid #E8E0CE; color: #1A1612; vertical-align: middle; }
.ua-data-table tr:nth-child(even) td { background: #F5F1E8; }
.ua-data-table tr:hover td { background: #EDE7D4; }
.ua-data-table .bull { color: #1B5E20; font-weight: 700; }
.ua-data-table .bear { color: #7B1010; font-weight: 700; }
.ua-data-table .neutral { color: #8B7355; }

/* Stat box (used in Market Overview) */
.stat-box {
    background: #F0EBE1; border: 1px solid #D4C9B0; border-radius: 6px;
    padding: 14px 16px; text-align: center; font-family: Georgia, serif;
}
.stat-box .stat-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; color: #8B7355; margin-bottom: 4px; }
.stat-box .stat-value { font-size: 1.35rem; font-weight: 700; color: #1C2B4A; }
.stat-box .stat-change { font-size: 0.82rem; margin-top: 2px; }
.stat-box .stat-change.pos { color: #1B5E20; }
.stat-box .stat-change.neg { color: #7B1010; }
.stat-box .stat-change.flat { color: #8B7355; }
</style>
"""


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
    <div style="background:#7B1010;color:#FAF7F0;border-radius:6px;padding:12px 18px;
                margin-bottom:14px;font-family:Georgia,serif;font-size:0.88rem;
                border:2px solid #5C0A0A;">
        <b>DEMO DATA — {n_synthetic} of {n_total} signals on this page are showing
        synthetic placeholder data</b>, not real values. This happens when no FRED API
        key is configured or a live fetch fails. Add a free key in the sidebar under
        "Setup" for real data — until then, treat any bullish/bearish reading from
        these signals as illustrative only, not an actual market signal.
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


def render_header(page_subtitle: str = "") -> None:
    """
    Inject global CSS and render the Unstructured Alpha masthead.
    Call this immediately after st.set_page_config() on every page.

    Args:
        page_subtitle: Short section name shown on the right side of the header bar
                       (e.g. "Signal Dashboard", "Market Overview").
    """
    from datetime import datetime

    st.markdown(_CSS, unsafe_allow_html=True)

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
    _status_bg    = "rgba(27,94,32,0.15)" if _market_open else "rgba(123,16,16,0.12)"
    _status_fg    = "#1B5E20" if _market_open else "#7B1010"
    _status_dot   = "#1B5E20" if _market_open else "#7B1010"
    _time_str     = _now_et.strftime("%-I:%M %p ET")
    _date_str     = _now_et.strftime("%A, %B %-d, %Y")

    status_badge_html = (
        f'<span class="market-status-badge" style="background:{_status_bg};color:{_status_fg};">'
        f'<span class="market-status-dot" style="background:{_status_dot};"></span>{_status_label} · {_time_str}'
        f'</span>'
    )
    right_html = (
        f"<b>{page_subtitle}</b><br>{_date_str}<br>{status_badge_html}"
        if page_subtitle else f"{_date_str}<br>{status_badge_html}"
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

    # Top-right Sign In / account widget -- a real Streamlit popover, not
    # raw HTML, so it can't live inside the markdown block above (Streamlit
    # widgets don't render inside injected HTML). Rendered here so every
    # page gets it automatically just by calling render_header(), which
    # they all already do -- no per-page wiring needed, and no risk of a
    # page forgetting to add it.
    from utils.auth_ui import render_account_widget
    render_account_widget()


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
                f'<div style="font-size:0.78rem;color:#C9A84C;margin-bottom:4px;">'
                f'Logged in as<br><b style="color:#F0EBE1;">{user["email"]}</b></div>',
                unsafe_allow_html=True,
            )
            if st.button("Log Out", key="sidebar_logout", use_container_width=True):
                from utils.auth_ui import logout
                logout()
                st.rerun()
            st.divider()

        # AI Assistant quick-access
        st.markdown(
            '<div style="background:rgba(184,134,11,0.15);border-radius:6px;padding:10px 12px;'
            'border:1px solid rgba(184,134,11,0.4);margin-bottom:12px;">'
            '<div style="font-size:0.75rem;color:#C9A84C;font-weight:700;letter-spacing:0.05em;">AI RESEARCH ASSISTANT</div>'
            '<div style="font-size:0.80rem;color:#F0EBE1;margin-top:3px;">'
            'Questions about signals, tickers, or methodology?</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.page_link("pages/9_AI_Assistant.py", label="Open AI Assistant")

        st.divider()
        st.markdown("### Setup")
        with st.expander("Configure API Keys"):
            st.markdown("All signals work in **demo mode** without keys. Add keys for real-time data.")
            fred_key = st.text_input(
                "FRED API Key", type="password",
                value=st.session_state.get("FRED_API_KEY", ""),
                help="Free key at fred.stlouisfed.org",
            )
            if fred_key:
                st.session_state["FRED_API_KEY"] = fred_key
                st.success("FRED key saved")
            st.caption("[Get free FRED key](https://fred.stlouisfed.org/docs/api/api_key.html)")

            eia_key = st.text_input(
                "EIA API Key", type="password",
                value=st.session_state.get("EIA_API_KEY", ""),
                help="Free key at eia.gov/opendata — powers crude oil inventories and natural gas storage",
            )
            if eia_key:
                st.session_state["EIA_API_KEY"] = eia_key
                st.success("EIA key saved")
            st.caption("[Get free EIA key](https://www.eia.gov/opendata/register.php)")

        st.divider()
        st.markdown("""
        <div class="disclaimer">
        <b>Not financial advice.</b> All signals are interpretations of publicly available data.
        Do your own research before making any investment decision.
        </div>
        """, unsafe_allow_html=True)
