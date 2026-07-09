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
from utils.header import render_header, render_sidebar_base, render_page_header, render_footer
from utils.theme import inject_premium_css, inject_skeleton_css, section_label, PLOTLY_CONFIG
from utils.auth_ui import require_login
from utils.quotes import get_batch_quotes, mini_sparkline
from utils.auth import set_digest_optin, get_digest_optin
from utils.score_history import get_score_history
from utils.billing import get_user_tier
from utils import webhook as _webhook

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
inject_premium_css()
inject_skeleton_css()

render_page_header(
    "My Watchlist",
    "Track confluence scores and alerts for your saved tickers.",
    icon="⭐",
)

alerts_db.init_db()

# Unlike every other page, Watchlist DOES require an account -- it's
# inherently per-user data, so this is the one place that still calls the
# blocking gate. require_login() renders its own sign-in form and stops
# the script here if nobody's logged in; everything below this line can
# safely assume a real, verified user.
current_user = require_login()
user_id = current_user["id"]

# ── Watchlist management ──────────────────────────────────────────────────────
st.markdown(section_label("Watchlist", color="#00C8E0", dot="#00C8E0"), unsafe_allow_html=True)

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
    # ── Portfolio Composite Score ─────────────────────────────────────────────
    # Weighted-average confluence score across all watchlist tickers, derived
    # from score_snapshots (already in DB, no live recompute needed). Gives
    # users a single macro exposure number for their entire portfolio, with
    # a 30-day sparkline so they can see how their aggregate positioning has
    # shifted over time.
    try:
        import pandas as pd
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select as _sel
        from utils.db import score_snapshots as _snaps, engine as _eng

        _wl_tickers = [r["ticker"] for r in watchlist]
        _cutoff = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y-%m-%d")

        with _eng.begin() as _conn:
            _snap_rows = _conn.execute(
                _sel(
                    _snaps.c.ticker,
                    _snaps.c.score,
                    _snaps.c.snapshot_date,
                )
                .where(_snaps.c.ticker.in_(_wl_tickers))
                .where(_snaps.c.snapshot_date >= _cutoff)
                .order_by(_snaps.c.snapshot_date)
            ).fetchall()

        if _snap_rows:
            _snap_df = pd.DataFrame(_snap_rows, columns=["ticker", "score", "date"])
            _snap_df["score"] = _snap_df["score"].astype(float)

            # Daily composite = mean score across all tickers with data that day
            _daily = (
                _snap_df.groupby("date")["score"]
                .mean()
                .reset_index()
                .sort_values("date")
            )

            # Latest composite score
            _latest_composite = float(_daily["score"].iloc[-1]) if not _daily.empty else None

            # 7-day delta for the composite
            _7d_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
            _week_rows = _daily[_daily["date"] >= _7d_ago]
            _composite_delta = (
                float(_daily["score"].iloc[-1] - _week_rows["score"].iloc[0])
                if len(_week_rows) >= 2 else None
            )

            if _latest_composite is not None:
                _comp_case = "BULL" if _latest_composite >= 65 else ("BEAR" if _latest_composite <= 35 else "NEUTRAL")
                _comp_color = "#00D566" if _comp_case == "BULL" else ("#FF4D6A" if _comp_case == "BEAR" else "#F59E0B")
                _comp_label = "Bullish" if _comp_case == "BULL" else ("Bearish" if _comp_case == "BEAR" else "Neutral")

                _delta_str = ""
                if _composite_delta is not None:
                    _dc = "#00D566" if _composite_delta >= 0 else "#FF4D6A"
                    _da = "▲" if _composite_delta >= 0 else "▼"
                    _delta_str = f'<span style="font-size:0.88rem;color:{_dc};font-weight:700;"> {_da} {abs(_composite_delta):.1f} <span style="font-size:0.72rem;color:#6B7A95;">7d</span></span>'

                st.markdown(f"""
                <div style="background:rgba(18,21,30,0.8);border:1px solid #1E2535;border-radius:12px;
                            padding:16px 24px;margin-bottom:20px;display:flex;align-items:center;
                            gap:24px;flex-wrap:wrap;">
                  <div>
                    <div style="font-size:0.60rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;
                                text-transform:uppercase;margin-bottom:4px;">Portfolio Macro Score</div>
                    <div style="display:flex;align-items:baseline;gap:6px;">
                      <span style="font-size:2.4rem;font-weight:900;color:{_comp_color};
                                   text-shadow:0 0 32px {_comp_color}40;line-height:1;">{_latest_composite:.0f}</span>
                      <span style="font-size:1rem;color:#4A5280;">/100</span>
                      {_delta_str}
                    </div>
                    <div style="font-size:0.78rem;color:{_comp_color};margin-top:2px;font-weight:600;">{_comp_label} · {len(_wl_tickers)} ticker avg</div>
                  </div>
                  <div style="width:1px;height:56px;background:rgba(255,255,255,0.07);flex-shrink:0;"></div>
                  <div style="flex:1;min-width:180px;" id="composite-spark"></div>
                </div>
                """, unsafe_allow_html=True)

                # Render the sparkline in its own row right below
                if len(_daily) >= 3:
                    import plotly.graph_objects as _pgo
                    _csp_fig = _pgo.Figure(_pgo.Scatter(
                        x=_daily["date"].tolist(),
                        y=_daily["score"].tolist(),
                        mode="lines",
                        line=dict(color=_comp_color, width=2),
                        fill="tozeroy",
                        fillcolor=f"{_comp_color}18",
                    ))
                    _csp_fig.update_layout(
                        margin=dict(l=0, r=0, t=0, b=0), height=70,
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(visible=False),
                        yaxis=dict(visible=False, range=[0, 100]),
                        showlegend=False,
                    )
                    _csp_cols = st.columns([2, 3, 2])
                    with _csp_cols[1]:
                        st.caption("30-day composite score trend")
                        st.plotly_chart(
                            _csp_fig, use_container_width=True,
                            config=PLOTLY_CONFIG,
                            key="composite_sparkline",
                        )
    except Exception:
        pass  # composite score is best-effort; never block the watchlist render

    # ── Weekly Score Report Card ──────────────────────────────────────────────
    # Grades each watched ticker on its 7-day score performance. Uses
    # score_snapshots (already in DB) — no live recompute. Displayed as a
    # compact heat-mapped table so users can see their whole week at a glance.
    # Placed here, just below the composite score, so users get the
    # macro-level view → week-level detail → then individual ticker rows below.
    try:
        from datetime import datetime as _dt_rc, timedelta as _td_rc, timezone as _tz_rc
        from sqlalchemy import select as _sel_rc
        from utils.db import score_snapshots as _snaps_rc, engine as _eng_rc

        _rc_tickers = [r["ticker"] for r in watchlist]
        _rc_cutoff  = (_dt_rc.now(_tz_rc.utc) - _td_rc(days=8)).strftime("%Y-%m-%d")

        with _eng_rc.begin() as _conn:
            _rc_rows = _conn.execute(
                _sel_rc(
                    _snaps_rc.c.ticker,
                    _snaps_rc.c.score,
                    _snaps_rc.c.snapshot_date,
                )
                .where(_snaps_rc.c.ticker.in_(_rc_tickers))
                .where(_snaps_rc.c.snapshot_date >= _rc_cutoff)
                .order_by(_snaps_rc.c.ticker, _snaps_rc.c.snapshot_date)
            ).fetchall()

        if _rc_rows:
            import pandas as _pd_rc
            _rc_df = _pd_rc.DataFrame(_rc_rows, columns=["ticker", "score", "date"])
            _rc_df["score"] = _rc_df["score"].astype(float)

            # Build per-ticker stats: current score, 7d-ago score, delta, grade
            _rc_stats = []
            for _rc_tk in _rc_tickers:
                _tk_rows = _rc_df[_rc_df["ticker"] == _rc_tk].sort_values("date")
                if len(_tk_rows) < 2:
                    continue
                _cur  = float(_tk_rows["score"].iloc[-1])
                _old  = float(_tk_rows["score"].iloc[0])
                _delta = round(_cur - _old, 1)
                # Grade: weighted toward current level + direction of change
                if   _cur >= 70 or (_cur >= 55 and _delta >= 5):  _grade = "A"
                elif _cur >= 55 or (_cur >= 40 and _delta >= 2):  _grade = "B"
                elif _cur >= 40 or abs(_delta) < 2:               _grade = "C"
                elif _cur >= 25 or _delta >= -4:                   _grade = "D"
                else:                                               _grade = "F"
                _grade_colors = {"A": "#00D566", "B": "#7BDE6B",
                                 "C": "#F59E0B", "D": "#FF8C42", "F": "#FF4D6A"}
                _score_color  = "#00D566" if _cur >= 65 else ("#FF4D6A" if _cur <= 35 else "#F59E0B")
                _delta_color  = "#00D566" if _delta > 0 else ("#FF4D6A" if _delta < 0 else "#8892AA")
                _rc_stats.append({
                    "ticker":      _rc_tk,
                    "cur":         _cur,
                    "delta":       _delta,
                    "grade":       _grade,
                    "grade_color": _grade_colors[_grade],
                    "score_color": _score_color,
                    "delta_color": _delta_color,
                })

            if _rc_stats:
                # Best + worst mover for the week header blurb
                _best  = max(_rc_stats, key=lambda x: x["delta"])
                _worst = min(_rc_stats, key=lambda x: x["delta"])

                st.markdown(
                    section_label("Weekly Score Report Card", color="#00C8E0", dot="#00C8E0"),
                    unsafe_allow_html=True,
                )

                # Best/worst mover callout row
                _bw_col1, _bw_col2 = st.columns(2)
                with _bw_col1:
                    _bc = _best["delta_color"]
                    st.markdown(
                        f'<div style="background:rgba(0,213,102,0.07);border:1px solid rgba(0,213,102,0.18);'
                        f'border-radius:10px;padding:12px 16px;">'
                        f'<div style="font-size:0.60rem;font-weight:700;color:#8892AA;letter-spacing:0.10em;'
                        f'text-transform:uppercase;margin-bottom:4px;">📈 Best Mover — 7 Days</div>'
                        f'<span style="font-size:1.15rem;font-weight:900;color:{_bc};">{_best["ticker"]}</span>'
                        f'<span style="font-size:0.85rem;color:{_bc};font-weight:700;margin-left:8px;">'
                        f'▲ +{_best["delta"]:.1f} pts</span>'
                        f'<div style="font-size:0.75rem;color:#8892AA;margin-top:2px;">'
                        f'Score now: {_best["cur"]:.0f}/100 &nbsp;·&nbsp; Grade: '
                        f'<span style="color:{_best["grade_color"]};font-weight:700;">{_best["grade"]}</span></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with _bw_col2:
                    _wc = _worst["delta_color"]
                    st.markdown(
                        f'<div style="background:rgba(255,77,106,0.07);border:1px solid rgba(255,77,106,0.18);'
                        f'border-radius:10px;padding:12px 16px;">'
                        f'<div style="font-size:0.60rem;font-weight:700;color:#8892AA;letter-spacing:0.10em;'
                        f'text-transform:uppercase;margin-bottom:4px;">📉 Worst Mover — 7 Days</div>'
                        f'<span style="font-size:1.15rem;font-weight:900;color:{_wc};">{_worst["ticker"]}</span>'
                        f'<span style="font-size:0.85rem;color:{_wc};font-weight:700;margin-left:8px;">'
                        f'▼ {_worst["delta"]:.1f} pts</span>'
                        f'<div style="font-size:0.75rem;color:#8892AA;margin-top:2px;">'
                        f'Score now: {_worst["cur"]:.0f}/100 &nbsp;·&nbsp; Grade: '
                        f'<span style="color:{_worst["grade_color"]};font-weight:700;">{_worst["grade"]}</span></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

                # Report card grid — one card per ticker
                _rc_cols_per_row = 4
                for _i in range(0, len(_rc_stats), _rc_cols_per_row):
                    _chunk = _rc_stats[_i:_i + _rc_cols_per_row]
                    _grid_cols = st.columns(len(_chunk))
                    for _col, _s in zip(_grid_cols, _chunk):
                        with _col:
                            _arrow = "▲" if _s["delta"] > 0 else ("▼" if _s["delta"] < 0 else "●")
                            st.markdown(
                                f'<div style="background:rgba(18,21,30,0.8);border:1px solid #1E2535;'
                                f'border-radius:10px;padding:14px 16px;text-align:center;">'
                                f'<div style="font-size:0.72rem;font-weight:700;color:#C5CCDE;'
                                f'letter-spacing:0.06em;">{_s["ticker"]}</div>'
                                f'<div style="font-size:2.0rem;font-weight:900;color:{_s["grade_color"]};'
                                f'line-height:1.1;margin:4px 0;">{_s["grade"]}</div>'
                                f'<div style="font-size:1.05rem;font-weight:800;color:{_s["score_color"]};">'
                                f'{_s["cur"]:.0f}<span style="font-size:0.65rem;color:#4A5280;">/100</span></div>'
                                f'<div style="font-size:0.78rem;color:{_s["delta_color"]};font-weight:600;margin-top:2px;">'
                                f'{_arrow} {_s["delta"]:+.1f} <span style="font-size:0.65rem;color:#6B7A95;">7d</span></div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

                st.caption(
                    "Grades based on current score level and 7-day direction. "
                    "A = high conviction, F = very weak. Coverage limited to tickers with recent Confluence Score history."
                )
                st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)

    except Exception:
        pass  # report card is best-effort; never block the watchlist render

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
                    _sh_color  = "#00D566" if _sh_scores[-1] >= _sh_scores[0] else "#FF4444"
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
                        f'<div style="font-size:0.60rem;font-weight:600;color:#8892AA;margin-top:4px;letter-spacing:0.06em;text-transform:uppercase;">'
                        f'Score 30d &nbsp;·&nbsp; <span style="color:{_sh_color};text-shadow:0 0 10px {_sh_color}50;">{_sh_scores[-1]:.0f}/100</span></div>',
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(_sh_fig, use_container_width=True,
                                    config=PLOTLY_CONFIG,
                                    key=f"score_spark_{ticker}")
                else:
                    st.caption("Signal score: building history…")
            except Exception:
                pass

        with wc2:
            # Regular-session price + daily change
            if price is not None:
                _pc = "#00D566" if (chg_pct or 0) > 0 else ("#FF4444" if (chg_pct or 0) < 0 else "#E8EEFF")
                st.markdown(
                    f'<div class="ua-kpi-animate" style="font-size:1.35rem;font-weight:900;color:{_pc};'
                    f'text-shadow:0 0 18px {_pc}35;line-height:1.2;margin-bottom:2px;">${price:,.2f}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption("Price unavailable")
            if chg_pct is not None:
                _cc = "#00D566" if chg_pct > 0 else ("#FF4444" if chg_pct < 0 else "#6B7FBF")
                _ca = "▲" if chg_pct > 0 else ("▼" if chg_pct < 0 else "●")
                st.markdown(
                    f'<span style="color:{_cc};font-size:0.85rem;font-weight:700;">{_ca} {chg_pct:+.2f}%</span>',
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
                _ec = "#00D566" if (_pre_c or 0) >= 0 else "#FF4444"
                _ext_lines.append(
                    f'<span style="color:{_ec};font-size:0.72rem;">'
                    f'Pre ${_pre_p:,.2f} ({_pre_c:+.2f}%)</span>'
                )
            if _post_p is not None:
                _ec = "#00D566" if (_post_c or 0) >= 0 else "#FF4444"
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
                _spark_color = "#00D566" if (chg_pct or 0) >= 0 else "#FF4444"
                st.plotly_chart(
                    mini_sparkline(series, _spark_color, "3M", show_axes=True),
                    use_container_width=True,
                    config=PLOTLY_CONFIG,
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

# ── Share Watchlist (public read-only link) ────────────────────────────────────
st.markdown(section_label("Share Your Watchlist", color="#7C3AED", dot="#7C3AED"), unsafe_allow_html=True)
try:
    from utils.share_watchlist import get_or_create_slug, revoke_slug, build_share_url

    _slug_state_key = f"share_slug_{user_id}"
    if _slug_state_key not in st.session_state:
        st.session_state[_slug_state_key] = None  # lazy — don't hit DB until user asks

    _sw_col1, _sw_col2 = st.columns([3, 1])
    with _sw_col1:
        if st.session_state[_slug_state_key] is None:
            st.markdown(
                '<div style="font-size:0.84rem;color:#8892AA;">'
                'Generate a read-only public link to your watchlist — '
                'share it anywhere to show your macro positioning. '
                'No personal data is exposed (email, alert thresholds, etc.).'
                '</div>',
                unsafe_allow_html=True,
            )
            if st.button("Generate Share Link", key="gen_share_link", type="primary"):
                try:
                    _new_slug = get_or_create_slug(user_id)
                    st.session_state[_slug_state_key] = _new_slug
                    st.rerun()
                except Exception as _se:
                    st.error(f"Could not generate link: {_se}")
        else:
            _share_url = build_share_url(st.session_state[_slug_state_key])
            st.markdown(
                f'<div style="background:rgba(124,58,237,0.07);border:1px solid rgba(124,58,237,0.20);'
                f'border-radius:10px;padding:14px 18px;">'
                f'<div style="font-size:0.60rem;font-weight:700;color:#8892AA;letter-spacing:0.10em;'
                f'text-transform:uppercase;margin-bottom:6px;">Your share link</div>'
                f'<code style="font-size:0.80rem;color:#00C8E0;word-break:break-all;">{_share_url}</code>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.caption("Anyone with this link can view your watchlist scores (read-only). Copy and share freely.")

    with _sw_col2:
        if st.session_state[_slug_state_key] is not None:
            st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
            if st.button("Reset Link", key="revoke_share_link",
                          help="Invalidates the current link and creates a new one"):
                try:
                    _new_slug = revoke_slug(user_id)
                    st.session_state[_slug_state_key] = _new_slug
                    st.success("Share link reset. Old link is now invalid.")
                    st.rerun()
                except Exception as _re:
                    st.error(f"Could not reset: {_re}")

except Exception as _share_err:
    st.caption(f"Share feature unavailable: {_share_err}")

st.divider()

# ── Morning Digest Opt-In ─────────────────────────────────────────────────────
st.markdown(section_label("Email Settings", color="#F59E0B", dot="#F59E0B"), unsafe_allow_html=True)
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

# ── Webhook Settings (Pro) ────────────────────────────────────────────────────
st.markdown(section_label("Webhook Settings", color="#7C3AED", dot="#7C3AED"), unsafe_allow_html=True)

_user_tier = get_user_tier(user_id)
if _user_tier != "pro":
    st.markdown(
        '<div style="background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.22);'
        'border-radius:10px;padding:14px 18px;font-family:Inter,sans-serif;">'
        '<span style="font-size:0.88rem;font-weight:700;color:#7C3AED;">⚡ Pro feature</span>'
        '<div style="font-size:0.82rem;color:#8892AA;margin-top:4px;">'
        'Get push alerts to Discord, Slack, or any webhook endpoint the moment a watched ticker '
        'crosses a threshold — no need to have the site open.'
        '</div></div>',
        unsafe_allow_html=True,
    )
    if st.button("Upgrade to Pro →", key="wl_webhook_upgrade"):
        st.switch_page("pages/29_Upgrade.py")
else:
    try:
        _current_url = _webhook.get_webhook_url(user_id) or ""
        _platform = _webhook.detect_platform(_current_url) if _current_url else None
        _platform_labels = {"discord": "Discord ✓", "slack": "Slack ✓", "generic": "Custom webhook ✓"}

        if _current_url:
            _badge = _platform_labels.get(_platform, "")
            st.markdown(
                f'<div style="font-size:0.80rem;color:#00D566;font-family:Inter,sans-serif;margin-bottom:6px;">'
                f'● Webhook active — {_badge}</div>',
                unsafe_allow_html=True,
            )

        _new_url = st.text_input(
            "Webhook URL (Discord, Slack, or any HTTP endpoint):",
            value=_current_url,
            placeholder="https://discord.com/api/webhooks/...",
            key="webhook_url_input",
            help="Discord: Server Settings → Integrations → Webhooks. "
                 "Slack: api.slack.com/apps → Incoming Webhooks. "
                 "Generic: any POST endpoint that accepts JSON.",
        )
        _wh_col1, _wh_col2 = st.columns([1, 1])
        with _wh_col1:
            if st.button("Save Webhook URL", key="save_webhook", type="primary"):
                _webhook.set_webhook_url(user_id, _new_url.strip() or None)
                if _new_url.strip():
                    st.success("Webhook URL saved.")
                else:
                    st.info("Webhook cleared.")
                st.rerun()
        with _wh_col2:
            if _current_url and st.button("Send Test Alert", key="test_webhook"):
                with st.spinner("Sending test alert…"):
                    _ok = _webhook.fire_test_alert(_current_url)
                if _ok:
                    st.success("✅ Test alert delivered! Check your Discord/Slack channel.")
                else:
                    st.error("❌ Delivery failed. Double-check the URL and that the webhook is still active.")

        st.caption(
            "Alerts fire immediately when a threshold crossing is detected on page load, "
            "and also hourly via a background job — so you'll get notified even when you're offline."
        )
    except Exception as _wh_err:
        st.caption(f"Could not load webhook settings: {_wh_err}")

st.divider()

# ── Alerts (integrated into this page, not a separate page) ─────────────────
st.markdown(section_label("Alerts for Your Watchlist", color="#00D566", dot="#00D566"), unsafe_allow_html=True)

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

DIRECTION_COLOR = {"bullish": "#00D566", "bearish": "#FF4444"}
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
        color = DIRECTION_COLOR.get(a["direction"], "#6B7FBF")
        unread_marker = "●" if not a["is_read"] else "○"
        type_label = TYPE_LABEL.get(a["alert_type"], a["alert_type"])
        company = TICKERS.get(a["ticker"], {}).get("name", "")
        ticker_disp = f"{a['ticker']} ({company})" if company else a["ticker"]
        st.markdown(f"""
        <div style="background:rgba(18,21,30,0.7);border-radius:6px;padding:10px 16px;margin-bottom:8px;
                    border-left:4px solid {color};font-family:Inter,sans-serif;">
            <span style="color:{color};font-weight:700;">{unread_marker} {ticker_disp}</span>
            <span style="color:#6B7FBF;font-size:0.78rem;letter-spacing:0.04em;"> · {type_label} · {a['created_at'][:16].replace('T', ' ')} UTC</span>
            <div style="color:#E8EEFF;margin-top:4px;">{a['message']}</div>
        </div>
        """, unsafe_allow_html=True)

render_footer()
