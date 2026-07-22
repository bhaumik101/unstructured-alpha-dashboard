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

Delivery is multi-channel: in-app alerts, hourly threshold emails, a daily
morning intelligence digest, a weekly research brief, and optional Pro
webhooks. The manual check uses the same evaluation engine as the scheduler.
"""

import streamlit as st
import yfinance as yf

from utils.config import TICKERS
from utils import alerts_db
from utils.alerts import evaluate_watchlist
from utils.header import render_header, render_sidebar_base, render_page_header, render_guided_steps, render_footer
from utils.theme import (
    inject_premium_css, inject_skeleton_css, section_label,
    style_sparkline, PLOTLY_CONFIG,
)
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
_watchlist_section = render_sidebar_base(
    page_title="My Watchlist",
    sections=("Securities", "Sharing", "Email Intelligence", "Delivery Integrations", "Alert Feed"),
    section_key="watchlist_section_rail",
)
try:
    from utils.instrumentation import record_once
    record_once("watchlist_viewed")
except Exception:
    pass
inject_premium_css()
inject_skeleton_css()

render_page_header(
    "My Watchlist",
    "A focused research command center for conviction, material changes, and alerts.",
    icon="",
)

st.markdown(
    """
    <style>
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #252B3A !important;
        box-shadow: none !important;
    }
    .ua-watchlist-summary {
        background: #12151E; border: 1px solid #252B3A; border-radius: 8px;
        padding: 14px 16px; min-height: 86px;
    }
    .ua-watchlist-summary-label {
        color: #7F8AA3; font-size: .64rem; font-weight: 700;
        letter-spacing: .09em; text-transform: uppercase;
    }
    .ua-watchlist-summary-value {
        color: #F3F4F6; font-size: 1.45rem; font-weight: 800; margin-top: 5px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

alerts_db.init_db()

# Unlike every other page, Watchlist DOES require an account -- it's
# inherently per-user data, so this is the one place that still calls the
# blocking gate. require_login() renders its own sign-in form and stops
# the script here if nobody's logged in; everything below this line can
# safely assume a real, verified user.
current_user = require_login()
user_id = current_user["id"]

if _watchlist_section == "Securities":
    # ── Watchlist management ──────────────────────────────────────────────────────
    st.html(section_label("Watchlist", color="#00C8E0", dot="#00C8E0"))
    render_guided_steps(
        "Monitor what matters without rebuilding your research each day",
        [
            ("Add a security", "Search by ticker or company and choose thresholds that match the type of move you care about."),
            ("Review material changes", "Use the security cards for live price, score movement, evidence breadth, and recent research context."),
            ("Route the alert", "Use the side menu to configure email or webhook delivery and review the resulting alert feed."),
        ],
        eyebrow="Watchlist workflow",
        intro="Each section loads independently, so market data does not block delivery settings or your alert history.",
    )

    # ── Add a ticker — fast LOCAL search across the whole universe ────────────────
    # Was a bare text_input: you had to already know the exact symbol, with no search,
    # no company names and no idea what you were adding. This builds a cached, purely
    # local index (symbol + company + sector) so typing filters instantly with zero
    # network per keystroke, and still accepts ANY symbol we don't track yet — which
    # then joins the dynamic universe on add (alerts_db.add_to_watchlist already calls
    # universe.add_to_universe).
    @st.cache_data(ttl=86400, show_spinner=False)
    def _wl_ticker_index() -> dict:
        """
        {SYMBOL: 'AAPL — Apple Inc.'} across the FULL US-listed universe (~12.6k
        symbols from utils.symbols), not just our 280 scored tickers — so you can
        search and watch almost any stock. Streamlit filters this client-side, so
        matching is instant on every keystroke with no server round-trip.
        Our scored universe is labeled "Core"; anything else still works and starts
        being tracked the moment it's added.
        """
        from utils.symbols import get_symbol_index
        from utils.config import TICKERS as _TK
        idx = dict(get_symbol_index())
        for _t in _TK:                       # mark what we actively score
            if _t in idx:
                idx[_t] = f"{idx[_t]} — Core"
        try:                                 # plus anything already in the dynamic universe
            from sqlalchemy import select as _s
            from utils.db import dynamic_universe as _du, engine as _e
            with _e.begin() as _c:
                for _r in _c.execute(_s(_du.c.ticker, _du.c.name)).fetchall():
                    if _r[0] and _r[0] not in idx:
                        idx[_r[0]] = f"{_r[0]} — {(_r[1] or _r[0])[:38]}"
        except Exception:
            pass
        return dict(sorted(idx.items()))


    @st.cache_data(ttl=900, show_spinner=False, max_entries=256)
    def _wl_latest_score(_ticker: str):
        """Latest Confluence Score from score_snapshots — an indexed read, never a
        live recompute (that's what made adding feel slow)."""
        try:
            from sqlalchemy import select as _s
            from utils.db import score_snapshots as _ss, engine as _e
            with _e.begin() as _c:
                _row = _c.execute(
                    _s(_ss.c.score, _ss.c.snapshot_date)
                    .where(_ss.c.ticker == _ticker)
                    .order_by(_ss.c.snapshot_date.desc()).limit(1)
                ).fetchone()
            return (float(_row[0]), _row[1]) if _row else (None, None)
        except Exception:
            return (None, None)


    _wl_idx = _wl_ticker_index()
    _ac1, _ac2 = st.columns([3, 2])
    with _ac1:
        # index=None + placeholder (NOT an empty-string sentinel option): with a
        # sentinel, Streamlit renders its formatted label as the box's actual VALUE,
        # so anything typed appends to it and the search matches nothing.
        _picked = st.selectbox(
            f"Search {len(_wl_idx)} stocks — symbol, company or sector",
            list(_wl_idx.keys()),
            index=None,
            placeholder="Type a symbol, company or sector…",
            format_func=lambda t: _wl_idx.get(t, t),
            key="wl_pick",
            help="Instant local search — no waiting on the network.",
        )
    with _ac2:
        _typed = st.text_input(
            "…or enter any symbol", key="new_watch_ticker", max_chars=10,
            placeholder="e.g. PLTR",
            help="Not in our list yet? Add it anyway — it joins the tracked universe.",
        ).upper().strip()

    new_ticker = (_typed or _picked or "").upper().strip()

    # ── Live preview of what you're about to add (fast, snapshot-backed) ──────────
    if new_ticker:
        _pv_score, _pv_asof = _wl_latest_score(new_ticker)
        _pv_label = _wl_idx.get(new_ticker)
        _pv_name = _pv_label.split(" — ", 1)[1] if _pv_label and " — " in _pv_label else "Not yet tracked"
        if _pv_score is not None:
            _pv_col = "#00D566" if _pv_score >= 65 else ("#FF4444" if _pv_score <= 35 else "#6B7FBF")
            _pv_right = (f'<div style="font-size:1.6rem;font-weight:900;color:{_pv_col};line-height:1;">'
                         f'{_pv_score:.0f}</div>'
                         f'<div style="font-size:0.56rem;color:#6B7FBF;">Confluence · {_pv_asof or "—"}</div>')
        else:
            _pv_right = ('<div style="font-size:0.68rem;color:#8892AA;">No score yet</div>'
                         '<div style="font-size:0.56rem;color:#6B7FBF;">Will be scored on the next run</div>')
        # "Tracked" means we actively SCORE it (the 280-ticker signal universe) —
        # not merely that it's listed. Anything else is still addable and starts
        # being tracked the moment it's added.
        try:
            from utils.symbols import is_tracked as _is_tracked
            _pv_tracked = _is_tracked(new_ticker)
        except Exception:
            _pv_tracked = bool(_pv_label)
        _pv_new = "" if _pv_tracked else (
            '<div style="margin-top:6px;font-size:0.60rem;color:#F59E0B;">'
            'Not scored yet — adding it starts tracking it.</div>')
        st.html(f"""
        <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;
                    background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);
                    border-left:3px solid #00C8E0;border-radius:9px;padding:12px 16px;margin:2px 0 12px;">
          <div>
            <div style="font-size:1.05rem;font-weight:800;color:#E8EEFF;">{new_ticker}</div>
            <div style="font-size:0.66rem;color:#8892AA;">{_pv_name}</div>{_pv_new}
          </div>
          <div style="text-align:right;flex-shrink:0;">{_pv_right}</div>
        </div>""")

    # ── Alert style presets ───────────────────────────────────────────────────────
    st.caption("**Quick add** — pick how you want to be alerted:")
    _PRESET_BLURB = {
        "Bullish Watch":        "Alerts early when the macro case turns favourable.",
        "Bearish Watch":        "Alerts early when the case deteriorates.",
        "Drastic Changes Only": "Only big moves — least noisy.",
    }
    qa1, qa2, qa3 = st.columns(3)
    for _preset_name, _col in {"Bullish Watch": qa1, "Bearish Watch": qa2, "Drastic Changes Only": qa3}.items():
        with _col:
            _p = QUICK_ADD_PRESETS[_preset_name]
            if st.button(_preset_name, key=f"quick_add_{_preset_name.replace(' ', '_')}",
                         use_container_width=True, disabled=not new_ticker,
                         help=f"{_PRESET_BLURB[_preset_name]} Alerts at score ≥{_p['score_bull_threshold']:.0f}, "
                              f"≤{_p['score_bear_threshold']:.0f}, or a {_p['price_move_pct_threshold']:.0f}% price move."):
                alerts_db.add_to_watchlist(user_id, new_ticker, **_p)
                st.success(f"{new_ticker} added with the \"{_preset_name}\" preset.")
                st.rerun()
            st.caption(f"<span style='font-size:0.60rem;color:#6B7FBF;'>{_PRESET_BLURB[_preset_name]}</span>",
                       unsafe_allow_html=True)

    with st.expander("Fine-tune alert thresholds"):
        t1, t2, t3 = st.columns(3)
        with t1:
            bull_thresh = st.slider("Alert when score rises to ≥", 50.0, 99.0, 65.0, 1.0, key="add_bull",
                                    help="Higher = only alert on a strong bullish case.")
        with t2:
            bear_thresh = st.slider("Alert when score falls to ≤", 1.0, 50.0, 35.0, 1.0, key="add_bear",
                                    help="Lower = only alert on a strongly bearish case.")
        with t3:
            price_thresh = st.slider("Alert on price move ≥ (%)", 0.5, 50.0, 5.0, 0.5, key="add_price",
                                     help="Absolute daily move that triggers an alert.")
        st.caption(
            f"You'll be alerted on **{new_ticker or 'this ticker'}** when its Confluence Score "
            f"reaches **≥{bull_thresh:.0f}** (bullish) or **≤{bear_thresh:.0f}** (bearish), "
            f"or when price moves **≥{price_thresh:.1f}%** in a day."
        )
        if st.button("Add with these thresholds", type="primary", disabled=not new_ticker,
                     use_container_width=True):
            alerts_db.add_to_watchlist(
                user_id, new_ticker,
                score_bull_threshold=bull_thresh,
                score_bear_threshold=bear_thresh,
                price_move_pct_threshold=price_thresh,
            )
            st.success(f"{new_ticker} added with custom thresholds.")
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
                                       line-height:1;">{_latest_composite:.0f}</span>
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
                        _csp_fig = style_sparkline(_csp_fig, height=70, y_range=[0, 100])
                        _csp_cols = st.columns([2, 3, 2])
                        with _csp_cols[1]:
                            st.caption("30-day composite score trend")
                            st.plotly_chart(
                                _csp_fig, use_container_width=True,
                                config=PLOTLY_CONFIG,
                                key="composite_sparkline",
                             theme=None)
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
                            f'text-transform:uppercase;margin-bottom:4px;">BEST MOVER — 7 DAYS</div>'
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
                            f'text-transform:uppercase;margin-bottom:4px;">WORST MOVER — 7 DAYS</div>'
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

        # Compact portfolio command center: prioritise material changes instead of
        # forcing users to scan every card in database order.
        _watchlist_view = []
        for _row in watchlist:
            _ticker = _row["ticker"]
            _score, _score_asof = _wl_latest_score(_ticker)
            _quote = _watch_quotes.get(_ticker, {})
            _move = _quote.get("chg_1d_pct")
            _attention = bool(
                (_score is not None and (
                    _score >= float(_row["score_bull_threshold"])
                    or _score <= float(_row["score_bear_threshold"])
                ))
                or (_move is not None and abs(_move) >= float(_row["price_move_pct_threshold"]))
            )
            _case = (
                "Bullish" if _score is not None and _score >= 55 else
                "Bearish" if _score is not None and _score <= 45 else
                "Neutral" if _score is not None else
                "No score"
            )
            _watchlist_view.append({
                **_row,
                "_score": _score,
                "_score_asof": _score_asof,
                "_move": _move,
                "_attention": _attention,
                "_case": _case,
            })

        _attention_count = sum(1 for _r in _watchlist_view if _r["_attention"])
        _priced_count = sum(1 for _r in _watchlist_view if _watch_quotes.get(_r["ticker"], {}).get("last") is not None)
        _unread_count = alerts_db.count_unread(user_id)
        _summary_cols = st.columns(4)
        _summary_values = (
            ("Securities tracked", len(_watchlist_view)),
            ("Needs review", _attention_count),
            ("Live prices", f"{_priced_count}/{len(_watchlist_view)}"),
            ("Unread alerts", _unread_count),
        )
        for _col, (_label, _value) in zip(_summary_cols, _summary_values):
            with _col:
                st.markdown(
                    f'<div class="ua-watchlist-summary"><div class="ua-watchlist-summary-label">{_label}</div>'
                    f'<div class="ua-watchlist-summary-value">{_value}</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        _filter_cols = st.columns([1.25, 1.25, 2])
        with _filter_cols[0]:
            _sort_mode = st.selectbox(
                "Sort by",
                ("Attention first", "Score: high to low", "Score: low to high", "Daily move", "Ticker"),
                key="watchlist_sort",
            )
        with _filter_cols[1]:
            _case_filter = st.selectbox(
                "View",
                ("All", "Bullish", "Neutral", "Bearish", "No score"),
                key="watchlist_case_filter",
            )
        with _filter_cols[2]:
            _ticker_filter = st.text_input(
                "Find in watchlist",
                placeholder="Ticker or company name",
                key="watchlist_ticker_filter",
            ).strip().lower()

        if _case_filter != "All":
            _watchlist_view = [_r for _r in _watchlist_view if _r["_case"] == _case_filter]
        if _ticker_filter:
            _watchlist_view = [
                _r for _r in _watchlist_view
                if _ticker_filter in _r["ticker"].lower()
                or _ticker_filter in TICKERS.get(_r["ticker"], {}).get("name", "").lower()
            ]

        _sorters = {
            "Attention first": lambda _r: (not _r["_attention"], -abs(_r["_move"] or 0), _r["ticker"]),
            "Score: high to low": lambda _r: (-(_r["_score"] if _r["_score"] is not None else -1), _r["ticker"]),
            "Score: low to high": lambda _r: ((_r["_score"] if _r["_score"] is not None else 101), _r["ticker"]),
            "Daily move": lambda _r: (-abs(_r["_move"] or 0), _r["ticker"]),
            "Ticker": lambda _r: _r["ticker"],
        }
        _watchlist_view.sort(key=_sorters[_sort_mode])

        if not _watchlist_view:
            st.info("No watched securities match these filters.")

        for row in _watchlist_view:
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
                st.caption(TICKERS.get(ticker, {}).get("name", "Tracked security"))
                st.caption(
                    f"Alerts: score ≥ {row['score_bull_threshold']:.0f} / ≤ {row['score_bear_threshold']:.0f} "
                    f"· price ±{row['price_move_pct_threshold']:.1f}%"
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
                        _sh_fig = style_sparkline(_sh_fig, height=42, y_range=[0, 100])
                        st.markdown(
                            f'<div style="font-size:0.60rem;font-weight:600;color:#8892AA;margin-top:4px;letter-spacing:0.06em;text-transform:uppercase;">'
                            f'Score 30d &nbsp;·&nbsp; <span style="color:{_sh_color};">{_sh_scores[-1]:.0f}/100</span></div>',
                            unsafe_allow_html=True,
                        )
                        st.plotly_chart(_sh_fig, use_container_width=True,
                                        config=PLOTLY_CONFIG,
                                        key=f"score_spark_{ticker}", theme=None)
                    else:
                        st.caption("Signal score: building history…")
                except Exception:
                    pass

                # Explain the Move — attribution for a material score shift on this
                # watched ticker, reusing the shared engine. Cheap path (genuine
                # snapshots only, no per-ticker history scan across the whole list);
                # silent when there's no material move or no recorded breakdown yet.
                try:
                    from utils.score_history import explain_move
                    from utils.score_attribution import render_attribution_html
                    _wl_attr = explain_move(ticker, days_back=7, allow_reconstruction=False)
                    if (_wl_attr.get("state") in ("ok", "insufficient_coverage")
                            and abs(_wl_attr.get("total_change", 0.0)) >= 3.0):
                        with st.expander(f"Why {ticker} moved {abs(_wl_attr['total_change']):.0f} pts"):
                            st.html(render_attribution_html(_wl_attr))
                except Exception:
                    pass

            with wc2:
                # Regular-session price + daily change
                if price is not None:
                    _pc = "#00D566" if (chg_pct or 0) > 0 else ("#FF4444" if (chg_pct or 0) < 0 else "#E8EEFF")
                    st.markdown(
                        f'<div class="ua-kpi-animate" style="font-size:1.35rem;font-weight:900;color:{_pc};'
                        f'line-height:1.2;margin-bottom:2px;">${price:,.2f}</div>',
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
                     theme=None)
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

if _watchlist_section == "Sharing":
    # ── Share Watchlist (public read-only link) ────────────────────────────────────
    st.html(section_label("Share Your Watchlist", color="#7C3AED", dot="#7C3AED"))
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

if _watchlist_section == "Email Intelligence":
    # ── Email Intelligence ────────────────────────────────────────────────────────
    st.html(section_label("Email Settings", color="#F59E0B", dot="#F59E0B"))
    try:
        _current_optin = get_digest_optin(user_id)
        _user_tier = get_user_tier(user_id)
        _email_cols = st.columns(3)
        _email_products = (
            (
                "MORNING INTELLIGENCE",
                "Active" if _current_optin else "Off",
                "Daily at 7 AM ET · live signal pulse, material flips, movers, and personalised watchlist research.",
            ),
            (
                "WEEKLY RESEARCH",
                "Included" if _current_optin and _user_tier == "pro" else ("Pro" if _user_tier != "pro" else "Off"),
                "A higher-context weekly review for Pro members using the same real-data watchlist and score history.",
            ),
            (
                "THRESHOLD ALERTS",
                "Monitoring",
                "Automatic alerts when tracked scores, prices, or differentiator signals cross a configured threshold.",
            ),
        )
        for _col, (_name, _status, _description) in zip(_email_cols, _email_products):
            with _col:
                st.markdown(
                    f'<div style="background:#12151E;border:1px solid #252B3A;border-radius:8px;padding:14px 16px;min-height:130px;">'
                    f'<div style="font-size:.62rem;font-weight:700;color:#9CA3AF;letter-spacing:.09em;">{_name}</div>'
                    f'<div style="font-size:.84rem;font-weight:800;color:#F3F4F6;margin:7px 0;">{_status}</div>'
                    f'<div style="font-size:.74rem;line-height:1.55;color:#8892AA;">{_description}</div></div>',
                    unsafe_allow_html=True,
                )

        _new_optin = st.toggle(
            "Daily intelligence and weekly research emails",
            value=_current_optin,
            help="Receive the 7 AM ET morning intelligence brief and the weekly Pro research note. "
                 "Threshold-crossing alerts continue automatically for monitored watchlist events.",
            key="digest_optin_toggle",
        )
        if _new_optin != _current_optin:
            set_digest_optin(user_id, _new_optin)
            if _new_optin:
                st.success("Email intelligence enabled. Your next morning brief will arrive at 7 AM ET.")
            else:
                st.info("Morning digest disabled.")
            st.rerun()
        if _current_optin:
            st.caption("Delivery is active. Every brief identifies live-source coverage and excludes unavailable data from scoring.")
        else:
            st.caption("Turn on the research cadence above. Watchlist threshold alerts remain active for monitored events.")
    except Exception as _digest_err:
        st.caption(f"Could not load email settings: {_digest_err}")

    st.divider()

if _watchlist_section == "Delivery Integrations":
    # ── Webhook Settings (Pro) ────────────────────────────────────────────────────
    st.html(section_label("Webhook Settings", color="#7C3AED", dot="#7C3AED"))

    _user_tier = get_user_tier(user_id)
    if _user_tier != "pro":
        st.markdown(
            '<div style="background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.22);'
            'border-radius:10px;padding:14px 18px;font-family:Inter,sans-serif;">'
            '<span style="font-size:0.72rem;font-weight:700;color:#8187F7;letter-spacing:0.08em;">PRO FEATURE</span>'
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
            _platform_labels = {"discord": "Discord", "slack": "Slack", "generic": "Custom webhook"}

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
                        st.success("Test alert delivered. Check your Discord or Slack channel.")
                    else:
                        st.error("Delivery failed. Double-check the URL and confirm the webhook is active.")

            st.caption(
                "Alerts fire immediately when a threshold crossing is detected on page load, "
                "and also hourly via a background job — so you'll get notified even when you're offline."
            )
        except Exception as _wh_err:
            st.caption(f"Could not load webhook settings: {_wh_err}")

    st.divider()

if _watchlist_section == "Alert Feed":
    # ── Alerts (integrated into this page, not a separate page) ─────────────────
    st.html(section_label("Alerts for Your Watchlist", color="#00D566", dot="#00D566"))

    with st.expander("How alert monitoring and delivery work"):
        st.markdown("""
        **Triggers checked for every watched ticker:**

        - **Confluence Score threshold crossing** — fires when the score moves from below your bullish
          threshold to at or above it (or the reverse for bearish), not every time it simply stays above —
          otherwise the feed would just repeat the same alert on every check.
        - **Price moves** — a single-check % move past your threshold, or a genuine new 52-week high/low.
        - **Differentiator signal changes** — insider buy/sell clustering, FINRA short interest trend, or
          curated-fund 13F positioning flipping between bullish/bearish/neutral.

        **Delivery — in-app, email, and Pro webhooks.** Threshold events are evaluated
        hourly in the background and delivered by email; the morning intelligence brief
        goes out daily at 7 AM ET to opted-in users. Pro members can also send the same
        threshold events to Slack, Discord, or another webhook. The "Check Watchlist Now"
        button runs the same evaluation logic on demand.

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
