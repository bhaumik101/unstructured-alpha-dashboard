"""
Shared fixtures for the Unstructured Alpha regression suite.

Run with:  pytest tests/  (from the dashboard/ directory)

These tests run fully offline-safe: pages that fetch live data (FRED, EIA,
yfinance) are expected to fall back to synthetic data or an empty Series
when network access is unavailable, and that fallback path itself is part
of what's under test — a page should never raise, even with zero network
access and zero API keys configured.

KNOWN BLIND SPOT — st.fragment bodies are NOT exercised by AppTest:
Confirmed empirically (not assumed) while wiring up live-price auto-refresh:
a real NameError inside an `@st.fragment(run_every=...)`-decorated function
(pages/5_Market_Overview.py's _render_live_index_quote, caused by a bad
import placement) did not surface during `at.run()` -- `at.exception` was
empty and none of the fragment's expected output appeared in `at.markdown`.
AppTest does not invoke fragment bodies at all; it only renders the parts of
the script that run unconditionally on a normal rerun. Every page test in
test_pages_render.py can pass cleanly while a fragment elsewhere on that same
page is silently broken. There is no test-suite-only fix for this (it is a
limitation of AppTest itself, not a gap in how these tests are written) --
any code living inside an st.fragment needs a live browser check before
trusting it, the same way it had to be caught here. Currently two fragments
exist in this codebase: Ticker Deep Dive's and Market Overview's live-price
auto-refresh. If you add another, verify it live; pytest passing is not
evidence it works.

KNOWN BLIND SPOT — the "remember me" cookie round-trip is NOT exercised by
AppTest, for the same underlying reason: streamlit-cookies-manager-v2's
CookieManager.ready() only becomes True after a real browser executes the
component's JS side and reports back. AppTest has no browser attached, so
cookies.ready() is always False there -- require_login()'s not-logged-in
path will reliably call st.stop() in tests without ever reaching the
remember-token check. tests/test_auth_and_multitenancy_unit.py unit-tests
issue_remember_token()/verify_remember_token()/revoke_remember_token()
directly (pure DB functions, no Streamlit involved), which is real
coverage -- but whether a cookie actually gets set in a browser, survives
a restart, and gets read back correctly has to be checked against a live,
deployed app in a real browser; this suite cannot confirm it.

KNOWN GAP — the "Run validated lead-time scan" button on Ticker Deep Dive
(insider activity / short interest) is NOT exercised end-to-end by any
test, for a different reason than the two blind spots above: it's not an
AppTest limitation, it's the classic "from module import name" footgun
this project has hit before. The page's own `from utils.fetchers import
fetch_insider_transactions_detail` re-resolves fresh on every AppTest
.run() (pages get fully re-executed, imports included), so mocking
utils.fetchers before a run WOULD reach the page-level call site -- but
utils/ticker_score.py imported the same function once, at first module
load, and keeps that original reference for the rest of the test session;
mocking utils.fetchers after that point does not reach it. Properly
testing the button's full handler therefore needs monkeypatching BOTH
utils.fetchers and utils.ticker_score's already-bound name, done with
real care -- not attempted yet. What IS tested directly and thoroughly:
every pure function the button's handler calls (lag_scan_with_validation,
pooled_lag_scan_across_sector, compute_signal_reliability_score, the
weekly-series adapters -- see tests/test_lead_time_research_unit.py).
What is NOT tested: that wiring those functions together behind a real
button click, with real fetcher data, doesn't raise. That needs either a
careful multi-module mock or a live check against a real ticker with
actual insider/short-interest history before trusting it in production.

KNOWN GAP — Ticker Deep Dive's Volume + RSI section (added 2026-06-22)
hits the SAME "from module import name" footgun as above, but even more
directly: utils/ticker_score.py's compute_full_ticker_score() (which
produces price_series, gating the entire price chart/stats/Volume/RSI
block behind `if not price_series.empty:`) keeps its own bound reference
to fetch_price from whenever it was first imported in the test session.
On top of that, this sandbox genuinely has no live network access at all
for yfinance (confirmed directly: every fetch attempt fails with a
blocked-outbound-proxy error, not a code bug) -- so price_series is
empty in EVERY AppTest run here, for EVERY ticker, regardless of any
monkeypatch. compute_rsi() itself is thoroughly unit-tested with
synthetic ground truth (tests/test_technical_indicators_unit.py); the
on-page rendering of real Volume/RSI charts has not been seen render
with real data in any environment yet and needs a live-browser check
before trusting it, the same as this page's price/index fragments.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Make the dashboard root importable (tests/ is one level below it).
DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_ROOT))
os.chdir(DASHBOARD_ROOT)

# Every AppTest-driven test runs the WHOLE app (app.py), which now calls
# utils.db.init_db() and gates every page behind a login -- point that at a
# throwaway file-based SQLite DB for the test session rather than the real
# local ~/.unstructured_alpha/data/app.db a developer might have data in,
# and rather than an in-memory DB (whose per-connection-pool semantics are
# less predictable across AppTest's script-execution model than a real,
# if temporary, file). Must be set before any test imports utils.db, since
# that module resolves its connection string once at import time.
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="ua_test_")
os.environ["UNSTRUCTURED_ALPHA_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"

# Every routed page, exactly as registered in app.py's st.navigation() call.
# If this list and app.py drift apart, test_app_structure.py will fail loudly
# rather than silently testing the wrong set of pages.
ROUTED_PAGES = [
    "pages/home_page.py",
    "pages/1_Signal_Dashboard.py",
    "pages/2_Today_Digest.py",
    "pages/3_Ticker_Deep_Dive.py",
    "pages/4_Power_Supercycle.py",
    "pages/5_Market_Overview.py",
    "pages/6_Stock_Screener.py",
    "pages/8_About.py",
    "pages/9_AI_Assistant.py",
    "pages/10_Watchlist.py",
    "pages/11_Model_Validation.py",
    "pages/14_Stock_Chart.py",
    "pages/27_Factor_Exposure.py",
    "pages/28_Export.py",
    "pages/29_Upgrade.py",
    "pages/30_Track_Record_Live.py",
    "pages/32_Profile.py",
    "pages/35_Signal_Strategy.py",
    "pages/37_Legal.py",
    "pages/38_Admin.py",
    "pages/39_How_Signals_Work.py",
    "pages/40_Stock_Recommender.py",
    "pages/41_Alternative_Data.py",
    "pages/42_Sector_View.py",
    "pages/43_Events_Forecasts.py",
    "pages/44_Portfolio_Suite.py",
    "pages/45_Options_Flow.py",
    "pages/46_Thesis_Journal.py",
]

# pages/2_Signal_Analysis.py and pages/7_Macro_Monitor.py used to be kept
# around as harmless "this page moved" redirect stubs (consolidated into
# Ticker Deep Dive and Market Overview respectively) because an earlier
# sandbox environment couldn't delete files. They were genuinely deleted
# once a real filesystem could do it -- RETIRED_STUB_PAGES and its test no
# longer apply and were removed along with the files.


@pytest.fixture
def app_test():
    """
    Returns a factory that gives back a *freshly run* AppTest already
    switched to the requested page.

    Every page is now gated behind a login (utils.auth_ui.require_login()),
    so before the first .run(), this injects a fake logged-in user directly
    into session_state -- bypassing the actual login form, which is tested
    on its own terms in tests/test_auth_and_multitenancy_unit.py. Without
    this, every page-render test would just be testing the login screen.

    IMPORTANT: streamlit.testing.v1.AppTest.switch_page() does NOT
    automatically rerun the app — you must call .run() again after
    switching, or you're silently asserting against whatever page ran
    last (usually the home page), not the one you think you're testing.
    This bit us once already; this fixture exists specifically so no
    test can make that mistake again.
    """
    from streamlit.testing.v1 import AppTest

    def _make(page_path: str = None, timeout: int = 120):
        at = AppTest.from_file(str(DASHBOARD_ROOT / "app.py"), default_timeout=timeout)
        at.session_state["user"] = {"id": 1, "email": "test@example.com"}
        at.run()
        if page_path:
            at.switch_page(page_path)
            at.run()
        return at

    return _make
