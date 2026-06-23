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

from utils.db import init_db, run_periodic_maintenance
from utils.auth_ui import init_cookies_for_this_run, try_restore_session

# ── Navigation registered FIRST ───────────────────────────────────────────────
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
        "": [
            st.Page("pages/home_page.py",           title="Home",              default=True),
        ],
        "Watchlist": [
            st.Page("pages/10_Watchlist.py",        title="My Watchlist"),
        ],
        "Daily Intel": [
            st.Page("pages/2_Today_Digest.py",      title="Today's Brief"),
            st.Page("pages/12_Sector_Map.py",       title="Sector Map"),
        ],
        "Signals": [
            st.Page("pages/1_Signal_Dashboard.py",  title="Signal Dashboard"),
        ],
        "Research": [
            st.Page("pages/3_Ticker_Deep_Dive.py",  title="Ticker Deep Dive"),
            st.Page("pages/13_Track_Record.py",     title="Earnings Track Record"),
            st.Page("pages/4_Power_Supercycle.py",  title="Power Supercycle"),
        ],
        "Market": [
            st.Page("pages/5_Market_Overview.py",   title="Market Overview"),
            st.Page("pages/6_Stock_Screener.py",    title="Stock Screener"),
        ],
        "Info": [
            st.Page("pages/11_Model_Validation.py", title="Model Validation"),
            st.Page("pages/8_About.py",             title="About"),
            st.Page("pages/9_AI_Assistant.py",      title="AI Assistant"),
        ],
    },
    position="sidebar",
)

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

_cookies = init_cookies_for_this_run()

try:
    current_user = try_restore_session(_cookies)
except Exception:
    current_user = None  # treat as anonymous; page auth checks handle the rest

pg.run()
