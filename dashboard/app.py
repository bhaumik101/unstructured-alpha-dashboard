"""
Unstructured Alpha — Signal Intelligence Dashboard
===================================================
Navigation router. Each page handles its own set_page_config.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Accounts: per explicit user request, this app does NOT require an account
to browse most of it -- only the Watchlist page (inherently per-account)
calls utils.auth_ui.require_login() itself, as that page's own concern.
Every other page is fully usable by an anonymous visitor. This file just
does a non-blocking session check (try_restore_session()) so a returning
logged-in user is recognized -- via the "remember me" cookie or an
already-active tab session -- without ever forcing anyone through a login
wall. The actual sign-in/sign-up affordance lives in the top-right of
every page (utils.header.render_account_widget(), called from each page's
own render_header()), reachable voluntarily from anywhere, not a forced
first step. Deliberately does NOT call st.set_page_config() here -- every
routed page already calls it itself as that page's first Streamlit
command, and Streamlit only allows ONE set_page_config() call per script
run.

st.navigation() is called first, drawing the grouped sidebar
(Home/Signals/Research/Market/Watchlist/Info) as a side effect -- separate
from pg.run(), which is what actually executes the selected page's
content. This ordering mattered even more under the old forced-login
design (a stale flat sidebar bug, since fixed) and remains the right order
now: the sidebar should never depend on auth state to render correctly.
"""

import streamlit as st

# ── Structured logging (pure-Python, no Streamlit call) ───────────────────────
# Installed BEFORE st.navigation so it is active for the whole run, but it
# touches no Streamlit API and cannot break the "st.navigation first" rule.
# Fixes Streamlit's default WARNING-level root logger swallowing our INFO
# [circuit]/[ratelimit] events, and gives every line a JSON shape + cid.
try:
    from utils.observability import configure_logging, log_startup_diagnostics
    configure_logging()
    log_startup_diagnostics("web")  # once-per-process; logs real cgroup CPU/RAM
except Exception:  # never let logging setup break the app
    pass

# ── Navigation registered FIRST ───────────────────────────────────────────────
# IMPORTANT: st.navigation() must be the ABSOLUTE first Streamlit call, and
# the module-level imports of utils.db / utils.auth_ui must come AFTER it.
# If those imports throw at cold-start (DB timeout, SQLAlchemy issue, etc.),
# st.navigation() would never be called and Streamlit falls back to automatic
# page discovery — a flat, ungrouped list of raw filenames. Moving imports
# below st.navigation() eliminates that race entirely.
# st.navigation() MUST be the first Streamlit call in app.py. Every run of
# app.py — including reruns triggered by the CookieManager component loading
# its data, or by any downstream st.rerun() — must establish the sidebar
# structure before anything else executes. If init_db() or the cookie manager
# were allowed to run first and threw (e.g. a cold-start DB timeout, a
# transient Neon connection error, or the CookieManager's own two-run init
# cycle), st.navigation() would never be called and Streamlit falls back to
# automatic page discovery, showing a flat unstyled list of raw filenames
# instead of the grouped navigation. Verified live: this is the exact cause
# of the "sidebar reverts to flat list after clicking anything" bug.
pg = st.navigation(
    {
        # ── Top-level ────────────────────────────────────────────────────────
        # NOTE: url_path is set EXPLICITLY on every page so it matches the
        # hardcoded hrefs in the custom horizontal top-nav (utils/header.py's
        # _render_topnav). Without this, Streamlit derives its own url_paths from
        # the filenames, the top-nav links point at slugs that don't exist, and
        # every link 404s / bounces to Home — which is exactly what happened once
        # the top-nav became clickable. These slugs are the contract between the
        # nav and the router; keep them in sync with header.py.
        # Consolidated 5-section IA (2026-07-13). Grouping mirrors the visible
        # top-nav in utils/header.py. EVERY page stays registered here (so its
        # url_path resolves) even if it's no longer a visible top-nav item —
        # Stock Chart, Signal Strategy and Alternative Data were merged out of
        # the visible nav but remain reachable by URL / cross-link.
        "": [
            st.Page("pages/home_page.py",      title="Home",             default=True),
            st.Page("pages/29_Upgrade.py",     title="Upgrade to Pro", url_path="upgrade-to-pro"),
            st.Page("pages/47_Account_Setup.py", title="Account Setup", url_path="welcome"),
        ],
        # ── Today ─────────────────────────────────────────────────────────────
        "Today": [
            st.Page("pages/2_Today_Digest.py",        title="Today's Brief",       url_path="today-s-brief"),
        ],
        # ── Portfolio ─────────────────────────────────────────────────────────
        "Portfolio": [
            st.Page("pages/10_Watchlist.py",          title="My Watchlist",        url_path="my-watchlist"),
            st.Page("pages/49_Decision_Queue.py",     title="Decision Queue",      url_path="decision-queue"),
            st.Page("pages/46_Thesis_Journal.py",     title="Thesis Journal",      url_path="thesis-journal"),
            st.Page("pages/44_Portfolio_Suite.py",    title="Portfolio Intelligence", url_path="portfolio-suite"),
        ],
        # ── Research ──────────────────────────────────────────────────────────
        "Research": [
            st.Page("pages/3_Ticker_Deep_Dive.py",    title="Ticker Deep Dive",    url_path="ticker-deep-dive"),
            st.Page("pages/6_Stock_Screener.py",      title="Stock Screener",      url_path="stock-screener"),
            st.Page("pages/40_Stock_Recommender.py",  title="Stock Recommender",   url_path="stock-recommender"),
            # merged out of visible nav (chart context now belongs on the ticker):
            st.Page("pages/14_Stock_Chart.py",        title="Stock Chart",         url_path="stock-chart"),
            # Pro-gated tools — registered for routing (reached via in-page CTAs /
            # URL), intentionally not surfaced in the visible top-nav:
            st.Page("pages/27_Factor_Exposure.py",    title="Factor Exposure",     url_path="factor-exposure"),
            st.Page("pages/45_Options_Flow.py",       title="Options Flow",        url_path="options-flow"),
            st.Page("pages/28_Export.py",             title="Export Report",       url_path="export-report"),
        ],
        # ── Signals & Methodology ─────────────────────────────────────────────
        "Signals & Methodology": [
            st.Page("pages/1_Signal_Dashboard.py",    title="Signal Dashboard",    url_path="signal-dashboard"),
            st.Page("pages/42_Sector_View.py",        title="Sector View",         url_path="sector-view"),
            st.Page("pages/5_Market_Overview.py",     title="Market Overview",     url_path="market-overview"),
            st.Page("pages/4_Power_Supercycle.py",    title="Power Supercycle",    url_path="power-supercycle"),
            st.Page("pages/11_Model_Validation.py",   title="Model Validation",    url_path="model-validation"),
            st.Page("pages/30_Track_Record_Live.py",  title="Track Record",        url_path="track-record"),
            st.Page("pages/39_How_Signals_Work.py",   title="How Signals Work",    url_path="how-signals-work"),
            st.Page("pages/48_Data_Trust.py",         title="Data Trust Center",   url_path="data-trust"),
            # merged out of visible nav (duplicate of Portfolio Suite's backtester):
            st.Page("pages/35_Signal_Strategy.py",    title="Signal Strategy",     url_path="signal-strategy"),
        ],
        # ── Monitoring ────────────────────────────────────────────────────────
        "Monitoring": [
            st.Page("pages/43_Events_Forecasts.py",   title="Catalyst Command Center", url_path="events-forecasts"),
            # merged out of visible nav (external-feed data):
            st.Page("pages/41_Alternative_Data.py",   title="Alternative Data",    url_path="alternative-data"),
        ],
        # ── Account ───────────────────────────────────────────────────────────
        "Account": [
            st.Page("pages/9_AI_Assistant.py",      title="AI Research Assistant", url_path="ai-research-assistant"),
            st.Page("pages/32_Profile.py",          title="My Profile",          url_path="my-profile"),
            st.Page("pages/8_About.py",             title="About & Methodology", url_path="about-methodology"),
            st.Page("pages/37_Legal.py",            title="Privacy & Terms",     url_path="privacy-terms"),
            st.Page("pages/38_Admin.py",            title="Admin",               url_path="admin"),
        ],
    },
    position="hidden",  # Nav UI is the custom horizontal topnav in utils/header.py
)

# ── Deferred imports (MUST come after st.navigation()) ────────────────────────
# These imports are placed here — never before st.navigation() — so that any
# cold-start DB timeout or SQLAlchemy error can't prevent st.navigation() from
# running and establishing the grouped sidebar. See docstring above for details.
from utils.db import init_db, run_periodic_maintenance
from utils.auth_ui import init_cookies_for_this_run, try_restore_session

# ── DB init + session restore — best-effort, never block the nav ──────────────
# Wrapped in try/except so a transient DB error or slow cold-start connection
# can't crash app.py after navigation is already established. Each individual
# page handles its own DB errors gracefully via its own try/except blocks.
try:
    init_db()
except Exception:
    pass  # page-level DB calls will surface their own errors

try:
    run_periodic_maintenance()  # low-probability hygiene pass — see utils/db.py
except Exception:
    pass  # maintenance is best-effort; never block page render

# ── Sunday auto-generate Weekly Brief (best-effort, non-blocking) ─────────────
# Session-state guard prevents a DB round-trip on every Streamlit rerun.
# should_auto_generate() only returns True on Sundays when no note exists yet,
# so the actual Anthropic API call (~2s) only fires once per Sunday per session.
if not st.session_state.get("_narrative_init_done"):
    st.session_state["_narrative_init_done"] = True
    try:
        from utils.narrative_engine import should_auto_generate, generate_weekly_note
        if should_auto_generate():
            generate_weekly_note(force=False)
    except Exception:
        pass  # never block the app for a failed note generation

_cookies = init_cookies_for_this_run()

try:
    current_user = try_restore_session(_cookies)
except Exception:
    current_user = None  # treat as anonymous; page auth checks handle the rest

# Newly verified accounts get one focused setup pass before entering the full
# product. Existing accounts are grandfathered by the schema migration. The
# session guard prevents a redirect loop while pages/47_Account_Setup.py runs.
if current_user and not st.session_state.get("_account_setup_route_attempted"):
    try:
        from utils.account_setup import needs_account_setup
        _needs_account_setup = needs_account_setup(current_user.get("id"))
    except Exception:
        _needs_account_setup = False  # never gate access on a transient DB issue
    if _needs_account_setup:
        st.session_state["_account_setup_route_attempted"] = True
        st.switch_page("pages/47_Account_Setup.py")

pg.run()
