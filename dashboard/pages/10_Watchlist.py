"""
Page 10 — My Watchlist
Per-account watchlist management, with alerts integrated directly into this
page rather than living on a separate "Alerts" page (per explicit user
request) -- the watchlist is the primary identity of this page; the alert
feed is a sub-section of it, not the other way around.

Triggers checked for every watched ticker, via utils/alerts.py (per the
user's explicit scoping): Confluence Score threshold crossings, price moves
(52-week high/low and % moves), and differentiator-signal changes (insider
activity, short interest, 13F).

Honesty check on delivery: this page is the IN-APP notification center.
Email delivery was explicitly scoped as a fast-follow, not built yet --
that requires an actual scheduled job running outside this Streamlit
process (a cron job, a hosted scheduler, etc.) plus an email-sending
service, which is real infrastructure, not just a feature on this page.
The "Check Watchlist Now" button below runs the same evaluation logic that
job would call, but only when someone has this page open and clicks it --
it does not run on a timer in the background.
"""

import streamlit as st

from utils.config import TICKERS
from utils import alerts_db
from utils.alerts import evaluate_watchlist
from utils.header import render_header, render_sidebar_base, go_to_ticker
from utils.auth_ui import require_login

# "Quick add" presets (per explicit user request: most people adding a
# ticker don't want to hand-tune 3 threshold numbers every time). Each
# preset is a real, distinct monitoring intent built from the SAME 3
# underlying thresholds the alert engine already checks (there's no
# separate "alert type" toggle in the schema -- these are just sensible,
# named combinations of bull/bear/price thresholds, not a new mechanism):
#   - Bullish Watch: low bear bar (rarely fires bearish), moderate bull bar
#     -- for someone who mainly wants to know when upside conviction builds.
#   - Bearish Watch: the mirror image -- high bull bar (rarely fires
#     bullish), moderate bear bar.
#   - Drastic Changes Only: high bars in both directions plus a much larger
#     price-move threshold -- fewer, noisier-but-bigger alerts only.
# "Custom" (the original manual inputs) remains available for anyone who
# wants exact control instead of a preset.
QUICK_ADD_PRESETS = {
    "Bullish Watch":        {"score_bull_threshold": 60.0, "score_bear_threshold": 15.0, "price_move_pct_threshold": 5.0},
    "Bearish Watch":        {"score_bull_threshold": 90.0, "score_bear_threshold": 40.0, "price_move_pct_threshold": 5.0},
    "Drastic Changes Only": {"score_bull_threshold": 80.0, "score_bear_threshold": 20.0, "price_move_pct_threshold": 15.0},
}

st.set_page_config(page_title="My Watchlist — UA", layout="wide")
render_header("My Watchlist")
render_sidebar_base()

alerts_db.init_db()

# Unlike every other page, Watchlist DOES require an account -- it's
# inherently per-user data, so this is the one place that still calls the
# blocking gate. require_login() renders its own sign-in form and stops
# the script here if nobody's logged in; everything below this line can
# safely assume a real, verified user.
current_user = require_login()
user_id = current_user["id"]

st.markdown("# My Watchlist")
st.caption("Track the tickers you care about. Click any ticker for the full signal breakdown, "
           "or get notified when its Confluence Score, price, or a differentiator signal shifts.")

# ── Watchlist management ──────────────────────────────────────────────────────
st.markdown('<div class="section-header">WATCHLIST</div>', unsafe_allow_html=True)

new_ticker = st.text_input("Add a ticker to watch:", key="new_watch_ticker", max_chars=10).upper().strip()

st.caption("Quick add — one click, no threshold tuning required:")
qa1, qa2, qa3 = st.columns(3)
_quick_add_cols = {"Bullish Watch": qa1, "Bearish Watch": qa2, "Drastic Changes Only": qa3}
for _preset_name, _col in _quick_add_cols.items():
    with _col:
        if st.button(_preset_name, key=f"quick_add_{_preset_name.replace(' ', '_')}",
                      use_container_width=True, disabled=not new_ticker):
            alerts_db.add_to_watchlist(user_id, new_ticker, **QUICK_ADD_PRESETS[_preset_name])
            st.success(f"{new_ticker} added to watchlist with the \"{_preset_name}\" preset.")
            st.rerun()

with st.expander("Or set custom alert thresholds instead"):
    t1, t2, t3 = st.columns(3)
    with t1:
        bull_thresh = st.number_input("Bullish score ≥", min_value=50.0, max_value=99.0, value=65.0, step=1.0, key="add_bull")
    with t2:
        bear_thresh = st.number_input("Bearish score ≤", min_value=1.0, max_value=50.0, value=35.0, step=1.0, key="add_bear")
    with t3:
        price_thresh = st.number_input("Price move % ≥", min_value=0.5, max_value=50.0, value=5.0, step=0.5, key="add_price")

    if st.button("Add with Custom Thresholds", type="primary", disabled=not new_ticker):
        alerts_db.add_to_watchlist(
            user_id, new_ticker,
            score_bull_threshold=bull_thresh,
            score_bear_threshold=bear_thresh,
            price_move_pct_threshold=price_thresh,
        )
        st.success(f"{new_ticker} added to watchlist with custom thresholds.")
        st.rerun()

watchlist = alerts_db.get_watchlist(user_id)

if not watchlist:
    st.info("Your watchlist is empty. Add a ticker above to start tracking it.")
else:
    for row in watchlist:
        ticker = row["ticker"]
        wc1, wc2, wc3, wc4, wc5 = st.columns([2, 1, 1, 1, 1])
        with wc1:
            # Clicking the ticker jumps straight to Ticker Deep Dive with
            # this ticker pre-filled (same session_state.selected_ticker +
            # switch_page mechanism used everywhere else tickers are
            # clickable on this site -- Stock Screener, ticker chips, etc.)
            go_to_ticker(ticker, key=f"watchlist_goto_{ticker}")
        with wc2:
            st.caption(f"Bull ≥ {row['score_bull_threshold']:.0f}")
        with wc3:
            st.caption(f"Bear ≤ {row['score_bear_threshold']:.0f}")
        with wc4:
            st.caption(f"Move ≥ {row['price_move_pct_threshold']:.1f}%")
        with wc5:
            if st.button("Remove", key=f"remove_{ticker}"):
                alerts_db.remove_from_watchlist(user_id, ticker)
                st.rerun()

    st.divider()
    if st.button("Check Watchlist Now", type="primary"):
        with st.spinner(f"Checking {len(watchlist)} watched ticker(s)…"):
            new_alerts = evaluate_watchlist(user_id)
        if new_alerts:
            st.success(f"{len(new_alerts)} new alert(s) generated — see the feed below.")
        else:
            st.info("No new alerts. Either nothing crossed a threshold, or this is the first check "
                    "for one or more tickers (which just establishes a baseline).")
        st.rerun()

st.divider()

# ── Alerts (integrated into this page, not a separate page) ─────────────────
st.markdown('<div class="section-header">ALERTS FOR YOUR WATCHLIST</div>', unsafe_allow_html=True)

with st.expander("How alerts work — and what's not built yet"):
    st.markdown("""
    **Triggers checked for every watched ticker:**

    - **Confluence Score threshold crossing** — fires when the score moves from below your bullish
      threshold to at or above it (or the reverse for bearish), not every time it simply stays above —
      otherwise the feed would just repeat the same alert on every check.
    - **Price moves** — a single-check % move past your threshold, or a genuine new 52-week high/low.
    - **Differentiator signal changes** — insider buy/sell clustering, FINRA short interest trend, or
      curated-fund 13F positioning flipping between bullish/bearish/neutral.

    **Delivery — in-app only right now.** This is the notification center. Email alerts were
    explicitly scoped as a fast-follow, not built yet: real email delivery needs a scheduled job that
    runs even when nobody has this page open, plus an email-sending service (e.g. SendGrid, SES) and
    its own credentials — that's infrastructure beyond what a Streamlit page can do by itself. The
    "Check Watchlist Now" button above runs the exact same evaluation logic a scheduled job would, but
    only fires when you click it while this page is open.

    **Nothing fires on the very first check** for a newly-watched ticker — there's no prior snapshot
    yet to compare against, so the first check just establishes a baseline silently.
    """)

unread_count = alerts_db.count_unread(user_id)
fc1, fc2, fc3 = st.columns([2, 1, 1])
with fc1:
    show_unread_only = st.checkbox(f"Show unread only ({unread_count} unread)", value=False)
with fc2:
    if st.button("Mark All Read", disabled=unread_count == 0):
        alerts_db.mark_all_read(user_id)
        st.rerun()
with fc3:
    if st.button("Clear Feed"):
        alerts_db.clear_all_alerts(user_id)
        st.rerun()

DIRECTION_COLOR = {"bullish": "#1B5E20", "bearish": "#7B1010"}
TYPE_LABEL = {
    "score_threshold": "Confluence Score",
    "price_move": "Price",
    "insider": "Insider Activity",
    "short_interest": "Short Interest",
    "13f": "13F Positioning",
}

alert_rows = alerts_db.get_alerts(user_id, unread_only=show_unread_only, limit=100)

if not alert_rows:
    st.info("No alerts yet. Add tickers to your watchlist and click \"Check Watchlist Now\" to evaluate them.")
else:
    for a in alert_rows:
        color = DIRECTION_COLOR.get(a["direction"], "#8B7355")
        unread_marker = "●" if not a["is_read"] else "○"
        type_label = TYPE_LABEL.get(a["alert_type"], a["alert_type"])
        company = TICKERS.get(a["ticker"], {}).get("name", "")
        ticker_disp = f"{a['ticker']} ({company})" if company else a["ticker"]
        st.markdown(f"""
        <div style="background:#F0EBE1;border-radius:6px;padding:10px 16px;margin-bottom:8px;
                    border-left:4px solid {color};font-family:Georgia,serif;">
            <span style="color:{color};font-weight:700;">{unread_marker} {ticker_disp}</span>
            <span style="color:#8B7355;font-size:0.78rem;letter-spacing:0.04em;"> · {type_label} · {a['created_at'][:16].replace('T', ' ')} UTC</span>
            <div style="color:#1A1612;margin-top:4px;">{a['message']}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("""
<div class="disclaimer">
<b>Not financial advice.</b> Alerts reflect signal and price changes in publicly available data,
not a recommendation to buy or sell. Do your own research before making any investment decision.
</div>
""", unsafe_allow_html=True)
