"""
Unstructured Alpha — Signal Intelligence Dashboard
===================================================
Navigation router. Each page handles its own set_page_config.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Accounts: every page requires a logged-in user (see utils/auth_ui.py).
Deliberately does NOT call st.set_page_config() here -- every routed page
already calls it itself as that page's first Streamlit command, and
Streamlit only allows ONE set_page_config() call per script run. On a run
where the user isn't logged in yet, require_login() renders the login
form and calls st.stop() before pg.run() ever reaches a page, so no
conflict; on a run where they're already logged in, require_login()
returns immediately without rendering anything, leaving the routed page's
own set_page_config() call as the genuine first command.

st.navigation() is called BEFORE require_login(), deliberately. Calling it
draws the grouped sidebar (Home/Signals/Research/Market/Alerts/Info)
immediately as a side effect -- separate from pg.run(), which is what
actually executes the selected page's content. require_login() still
gates the content: if nobody's logged in, it renders the login form in
the main area and calls st.stop() before pg.run() below ever executes, so
no page content leaks pre-login. This was caught live, not assumed: with
the order reversed (require_login() first), st.navigation() never ran
on a not-logged-in script pass, so Streamlit fell back to auto-discovering
every file in pages/ and showed that flat, ungrouped list (complete with
two already-retired stub pages) instead of the intended grouped nav.
"""

import streamlit as st

from utils.db import init_db
from utils.auth_ui import require_login

init_db()

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

current_user = require_login()

pg.run()
