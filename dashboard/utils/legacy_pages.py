# utils/legacy_pages.py
# Unstructured Alpha — pages that predate the exposure report
#
# WHY THIS EXISTS
# ---------------
# The 2026-09-20 redesign took ~25 pages out of the navigation but kept them
# routable, so existing links and bookmarks resolve. They still describe the
# old product: Confluence Scores, "the macro backdrop before you trade", signal
# lead times — claims the evidence does not support and the product no longer
# makes.
#
# That is a credibility problem the moment outreach starts. Someone who finds
# /stock-recommender through a search result or an old link reads the pitch we
# retired, with nothing telling them there is a newer, more honest product one
# click away.
#
# So every one of these pages carries a notice saying it predates the exposure
# report and is no longer maintained, and asks search engines not to index it.
# Deleting them is the eventual answer; this is the honest interim, and it
# costs one line in render_header rather than an edit per page.

from __future__ import annotations

from pathlib import Path

# Registered in app.py, deliberately not in the nav. Kept in sync with
# tests/test_nav_reaches_every_page.py by tests/test_legacy_notice.py.
LEGACY_PAGE_FILES: frozenset[str] = frozenset({
    "home_page.py",
    "1_Signal_Dashboard.py",
    "2_Today_Digest.py",
    "3_Ticker_Deep_Dive.py",
    "4_Power_Supercycle.py",
    "5_Market_Overview.py",
    "6_Stock_Screener.py",
    "8_About.py",
    "9_AI_Assistant.py",
    "10_Watchlist.py",
    "14_Stock_Chart.py",
    "27_Factor_Exposure.py",
    "28_Export.py",
    "35_Signal_Strategy.py",
    "39_How_Signals_Work.py",
    "40_Stock_Recommender.py",
    "41_Alternative_Data.py",
    "42_Sector_View.py",
    "43_Events_Forecasts.py",
    "44_Portfolio_Suite.py",
    "45_Options_Flow.py",
    "46_Thesis_Journal.py",
    "49_Decision_Queue.py",
    "50_Investor_Checkup.py",
    "51_Signal_Research.py",
})

# The evidence pages (Model Validation, Track Record, Data Trust) are NOT here:
# they are linked from the Research menu and describe testing rather than
# selling a prediction.

# The noindex half cannot live here: Streamlit sanitises <script> out of
# st.html, so a tag added this way never runs (checked in the browser). It is
# applied instead by the runtime script in scripts/inject_boot_splash.py, which
# is injected into the served index.html and does run.
NOTICE_HTML = """<style>
.ua-legacy{background:rgba(217,144,24,.10);border:1px solid rgba(217,144,24,.45);
  border-left:4px solid #d99018;border-radius:10px;padding:12px 16px;margin:0 0 14px;
  font-family:Inter,system-ui,sans-serif;font-size:.88rem;line-height:1.55;color:var(--ua-ink);}
html[data-ua-theme="light"] .ua-legacy{background:#fdf3e2;border-color:#e9c98f;color:#3a2f16;}
.ua-legacy b{font-weight:700;}
.ua-legacy a{color:inherit;text-decoration:underline;font-weight:600;}
</style>
<div class="ua-legacy" role="note">
  <b>This page predates the exposure report and is no longer maintained.</b>
  It describes an earlier version of Unstructured Alpha built around signal
  scores. Testing found no reliable way to predict markets from that data, so
  the product now measures what a portfolio is <em>exposed to</em> instead.
  <a href="/">Open the exposure report</a> ·
  <a href="/methodology">Read what changed and why</a>
</div>
"""


def is_legacy_page(caller_file: str | None) -> bool:
    """True when the calling page is one the redesign superseded."""
    if not caller_file:
        return False
    return Path(str(caller_file)).name in LEGACY_PAGE_FILES
