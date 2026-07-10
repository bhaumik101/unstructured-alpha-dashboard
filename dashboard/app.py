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
        "": [
            st.Page("pages/home_page.py",      title="Home",             default=True),
            st.Page("pages/29_Upgrade.py",     title="⚡ Upgrade to Pro"),
        ],
        # ── Watchlist ────────────────────────────────────────────────────────
        # Shared watchlist + watchlist stress test live as tabs inside My Watchlist
        "Watchlist": [
            st.Page("pages/10_Watchlist.py",   title="My Watchlist"),
            st.Page("pages/14_Stock_Chart.py", title="Stock Chart"),
        ],
        # ── Daily Intel ──────────────────────────────────────────────────────
        # Today's Brief absorbs Weekly Brief (tab).
        # Alternative Data combines Congress Tracker + Options Flow.
        # Events combines Macro Calendar + Event Forecaster.
        "Daily Intel": [
            st.Page("pages/2_Today_Digest.py",        title="Today's Brief"),
            st.Page("pages/41_Alternative_Data.py",   title="Alternative Data"),
            st.Page("pages/43_Events_Forecasts.py",   title="Events & Forecasts"),
        ],
        # ── Signals ──────────────────────────────────────────────────────────
        # Signal Dashboard absorbs Regime Playbook (tab).
        # Sector View combines Sector Map + Market Heatmap + Supply Chain.
        "Signals": [
            st.Page("pages/1_Signal_Dashboard.py",  title="Signal Dashboard"),
            st.Page("pages/42_Sector_View.py",       title="Sector View"),
        ],
        # ── Research (free) ──────────────────────────────────────────────────
        # Track Record absorbs Earnings Track Record (tab) + Signal Call Log.
        # Stock Screener absorbs Live Scoreboard + Short Squeeze Radar (tabs).
        # Signal Strategy: rules-based backtest from home page CTA.
        "Research": [
            st.Page("pages/3_Ticker_Deep_Dive.py",    title="Ticker Deep Dive"),
            st.Page("pages/4_Power_Supercycle.py",    title="Power Supercycle"),
            st.Page("pages/5_Market_Overview.py",     title="Market Overview"),
            st.Page("pages/6_Stock_Screener.py",      title="Stock Screener"),
            st.Page("pages/30_Track_Record_Live.py",  title="Track Record"),
            st.Page("pages/35_Signal_Strategy.py",    title="Signal Strategy"),
        ],
        # ── Pro Tools ────────────────────────────────────────────────────────
        # Stock Recommender: hero Pro page — ranked AI-driven stock ideas.
        # Portfolio Suite: Backtest + Stress Tester + Signal Backtester +
        #   Portfolio Analyzer + Basket Builder — all portfolio-level tools.
        "⚡ Pro Tools": [
            st.Page("pages/40_Stock_Recommender.py", title="Stock Recommender"),
            st.Page("pages/44_Portfolio_Suite.py",   title="Portfolio Suite"),
        ],
        # ── Account ──────────────────────────────────────────────────────────
        # About absorbs Model Validation (tab). Export lives inside TDD.
        "Account": [
            st.Page("pages/32_Profile.py",          title="My Profile"),
            st.Page("pages/9_AI_Assistant.py",      title="AI Research Assistant"),
            st.Page("pages/8_About.py",             title="About & Methodology"),
            st.Page("pages/39_How_Signals_Work.py", title="How Signals Work"),
            st.Page("pages/37_Legal.py",            title="Privacy & Terms"),
            st.Page("pages/38_Admin.py",            title="Admin"),
        ],
    },
    position="sidebar",
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
# Fires at most once per Sunday per server restart because should_auto_generate()
# checks whether today's note already exists before returning True.
# generate_weekly_note() is ~2s API call — acceptable on cold run startup.
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

pg.run()
