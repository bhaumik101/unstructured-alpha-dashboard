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
import yfinance as yf

from utils.config import TICKERS
from utils import alerts_db
from utils.alerts import evaluate_watchlist
from utils.header import render_header, render_sidebar_base
from utils.auth_ui import require_login
from utils.quotes import get_batch_quotes, mini_sparkline
from utils.auth import set_digest_optin, get_digest_optin
from utils.score_history import get_score_history

# ── Pre/post market batch fetch ────────────────────────────────────────────────
# Separate from get_batch_quotes (which uses yf.download for speed) because
# pre/post price requires fast_info per ticker — not available in the batch
# download API. Cached 5 min; small max_entries since the result set is tiny.
@st.cache_data(ttl=300, show_spinner=False, max_entries=5)
def _get_prepost_batch(tickers_tuple: tuple) -> dict:
    """Return {ticker: {pre_price, pre_pct, post_price, post_pct}} for each."""
    result: dict = {}
    if not tickers_tuple:
        return result
    for sym in tickers_tuple:
        try:
            fi    = yf.Ticker(sym).fast_info
            last  = getattr(fi, "last_price",          None) or getattr(fi, "regular_market_price", None)
            pre   = getattr(fi, "pre_market_price",    None)
            post  = getattr(fi, "post_market_price",   None)
            entry: dict = {}
            if pre  and last and abs(pre  - last) > 0.005:
                entry["pre_price"]  = pre
                entry["pre_pct"]    = (pre  - last) / last * 100
            if post and last and abs(post - last) > 0.005:
                entry["post_price"] = post
                entry["post_pct"]   = (post - last) / last * 100
            result[sym] = entry
        except Exception:
            result[sym] = {}
    return result

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
    # Batched, cached (utils/quotes.py, 15 min) -- one fetch per watched
    # ticker, not per page render; the same module Stock Screener uses, so
    # price/% displays can't silently disagree between the two pages.
    _ticker_list = [row["ticker"] for row in watchlist]
    with st.spinner(f"Loading prices for {len(watchlist)} watched ticker(s)…"):
        _watch_quotes  = get_batch_quotes(_ticker_list)
        _prepost_quotes = _get_prepost_batch(tuple(_ticker_list))

    for row in watchlist:
        ticker  = row["ticker"]
        q       = _watch_quotes.get(ticker, {})
        pp      = _prepost_quotes.get(ticker, {})
        price   = q.get("last")
        chg_pct = q.get("chg_1d_pct")
        series  = q.get("series")

        # One bordered card per ticker.
        _row_box = st.container(border=True)
        wc1, wc2, wc3, wc4 = _row_box.columns([2.0, 1.3, 1.8, 0.9])

        with wc1:
            # Clicking the ticker name → Stock Viewer (simple chart).
            # "Research" button → Ticker Deep Dive (full signal analysis).
            if st.button(f"**{ticker}**", key=f"wl_chart_{ticker}",
                         help="Open chart viewer"):
                st.session_state["chart_ticker"] = ticker
                st.switch_page("pages/14_Stock_Chart.py")
            st.caption(
                f"Bull ≥ {row['score_bull_threshold']:.0f} · "
                f"Bear ≤ {row['score_bear_threshold']:.0f} · "
                f"Move ≥ {row['price_move_pct_threshold']:.1f}%"
            )
            # Score history sparkline — shows 30-day confluence score trend.
            # Rising score while price is flat = early warning that macro
            # conditions are improving before the stock reacts.
            try:
                _score_hist = get_score_history(ticker, days=30)
                if len(_score_hist) >= 3:
                    import plotly.graph_objects as go
                    _sh_scores = [h["score"] for h in _score_hist]
                    _sh_dates  = [h["snapshot_date"] for h in _score_hist]
                    _sh_color  = "#1B5E20" if _sh_scores[-1] >= _sh_scores[0] else "#7B1010"
                    _sh_fig = go.Figure(go.Scatter(
                        x=_sh_dates, y=_sh_scores, mode="lines",
                        line=dict(color=_sh_color, width=1.5),
                        fill="tozeroy", fillcolor=f"{_sh_color}18",
                    ))
                    _sh_fig.update_layout(
                        margin=dict(l=0, r=0, t=0, b=0), height=38,
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(visible=False), yaxis=dict(visible=False, range=[0, 100]),
                        showlegend=False,
                    )
                    st.markdown(
                        f'<div style="font-size:0.60rem;color:#9E9E8E;margin-top:2px;">'
                        f'Signal score 30d · latest: <b style="color:{_sh_color}">{_sh_scores[-1]:.0f}/100</b></div>',
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(_sh_fig, use_container_width=True,
                                    config={"displayModeBar": False},
                                    key=f"score_spark_{ticker}")
                else:
                    st.caption("Signal score: building history…")
            except Exception:
                pass

        with wc2:
            # Regular-session price + daily change
            if price is not None:
                st.markdown(f"**${price:,.2f}**")
            else:
                st.caption("Price unavailable")
            if chg_pct is not None:
                _cc = "#1B5E20" if chg_pct > 0 else ("#7B1010" if chg_pct < 0 else "#8B7355")
                _ca = "▲" if chg_pct > 0 else ("▼" if chg_pct < 0 else "●")
                st.markdown(
                    f'<span style="color:{_cc};font-size:0.85rem;">{_ca} {chg_pct:+.2f}%</span>',
                    unsafe_allow_html=True,
                )
            # Pre/post market prices (only shown when the market is closed
            # and the extended-hours price differs from the last close)
            _pre_p  = pp.get("pre_price")
            _pre_c  = pp.get("pre_pct")
            _post_p = pp.get("post_price")
            _post_c = pp.get("post_pct")
            _ext_lines = []
            if _pre_p is not None:
                _ec = "#1B5E20" if (_pre_c or 0) >= 0 else "#7B1010"
                _ext_lines.append(
                    f'<span style="color:{_ec};font-size:0.72rem;">'
                    f'Pre ${_pre_p:,.2f} ({_pre_c:+.2f}%)</span>'
                )
            if _post_p is not None:
                _ec = "#1B5E20" if (_post_c or 0) >= 0 else "#7B1010"
                _ext_lines.append(
                    f'<span style="color:{_ec};font-size:0.72rem;">'
                    f'Post ${_post_p:,.2f} ({_post_c:+.2f}%)</span>'
                )
            if _ext_lines:
                st.markdown("<br>".join(_ext_lines), unsafe_allow_html=True)

        with wc3:
            # 3-month mini sparkline with axes — long enough to show trend,
            # short enough not to flatten a recent move against multi-year history.
            if series is not None and not series.empty:
                _spark_color = "#1B5E20" if (chg_pct or 0) >= 0 else "#7B1010"
                st.plotly_chart(
                    mini_sparkline(series, _spark_color, "3M", show_axes=True),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"watch_spark_{ticker}",
                )
            else:
                st.caption("Chart unavailable")

        with wc4:
            if st.button("Research →", key=f"wl_tdd_{ticker}",
                         help="Ticker Deep Dive: signals, earnings, insider data"):
                st.session_state["selected_ticker"] = ticker
                st.switch_page("pages/3_Ticker_Deep_Dive.py")
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

# ── Morning Digest Opt-In ─────────────────────────────────────────────────────
st.markdown('<div class="section-header">EMAIL SETTINGS</div>', unsafe_allow_html=True)
try:
    _current_optin = get_digest_optin(user_id)
    _new_optin = st.toggle(
        "📬 Morning digest email (7 AM ET daily)",
        value=_current_optin,
        help="Receive a daily email with signal flips since yesterday and biggest score movers. "
             "Sent via Resend to your account email. Unsubscribe any time by turning this off.",
        key="digest_optin_toggle",
    )
    if _new_optin != _current_optin:
        set_digest_optin(user_id, _new_optin)
        if _new_optin:
            st.success("Morning digest enabled — you'll receive your first email tomorrow at 7 AM ET.")
        else:
            st.info("Morning digest disabled.")
        st.rerun()
    if _current_optin:
        st.caption("✓ You'll receive a morning brief at 7 AM ET with signal flips and score movers.")
    else:
        st.caption("Turn on to receive a daily morning brief with the day's signal changes and top movers.")
except Exception as _digest_err:
    st.caption(f"Could not load email settings: {_digest_err}")

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

    **Delivery — in-app + morning email.** This is the in-app notification center.
    A morning digest email (signal flips + score movers) goes out daily at 7 AM ET
    to opted-in users — toggle that below. The "Check Watchlist Now" button above
    runs the same evaluation logic on demand whenever you want a fresh read.

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
