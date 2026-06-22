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

from utils.db import init_db
from utils.auth_ui import init_cookies_for_this_run, try_restore_session

init_db()
_cookies = init_cookies_for_this_run()

pg = st.navigation(
    {
        "": [
            st.Page("pages/home_page.py",        title="Home",             default=True),
        ],
        "Signals": [
            st.Page("pages/1_Signal_Dashboard.py", title="Signal Dashboard"),
        ],
        "Research": [
            st.Page("pages/3_Ticker_Deep_Dive.py", title="Ticker Deep Dive"),
            st.Page("pages/4_Power_Supercycle.py", title="Power Supercycle"),
        ],
        "Market": [
            st.Page("pages/5_Market_Overview.py",  title="Market Overview"),
            st.Page("pages/6_Stock_Screener.py",   title="Stock Screener"),
        ],
        "Watchlist": [
            st.Page("pages/10_Watchlist.py",        title="My Watchlist"),
        ],
        "Info": [
            st.Page("pages/8_About.py",            title="About"),
            st.Page("pages/9_AI_Assistant.py",     title="AI Assistant"),
        ],
    },
    position="sidebar",
)

current_user = try_restore_session(_cookies)

pg.run()
