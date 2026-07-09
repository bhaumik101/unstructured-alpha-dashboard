# pages/35_Share_Watchlist.py
# Unstructured Alpha — Public Read-Only Watchlist View
#
# Reached via: /Share_Watchlist?id=<slug>
# No account required. Shows the watchlist owner's tickers + current
# Confluence Scores + score sparklines without exposing any personal data.
#
# WHAT'S SHOWN:
#   - Current Confluence Score for each ticker (bull/bear/neutral status)
#   - 7-day delta from score_snapshots
#   - 30-day score sparkline
#   - "Open Ticker Deep Dive" button → public research page
#   - CTA to create a free account / add tickers to their own watchlist
#
# WHAT'S NOT SHOWN:
#   - Owner's email or display name (only their display_name if set, else
#     "an Unstructured Alpha user")
#   - Alert thresholds — those are per-user config, not interesting publicly
#   - Any account-specific data

import streamlit as st

st.set_page_config(
    page_title="Shared Watchlist — Unstructured Alpha",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.theme import inject_premium_css, PLOTLY_CONFIG
from utils.db import init_db
from utils.auth_ui import try_restore_session, init_cookies_for_this_run

render_header("Shared Watchlist")
render_sidebar_base()
inject_premium_css()

_cookies = init_cookies_for_this_run()
try_restore_session(_cookies)
init_db()

# ── Parse slug from query params ──────────────────────────────────────────────
_slug = st.query_params.get("id", "")

if not _slug:
    st.error("No watchlist link provided. Check the URL and try again.")
    st.stop()

# ── Resolve slug → user + tickers ─────────────────────────────────────────────
try:
    from utils.share_watchlist import get_user_by_slug, get_watchlist_for_user
    _owner = get_user_by_slug(_slug)
except Exception as exc:
    st.error(f"Could not load watchlist: {exc}")
    st.stop()

if _owner is None:
    st.error("This watchlist link is no longer active. The owner may have reset their share link.")
    st.stop()

_tickers = get_watchlist_for_user(_owner["id"])

if not _tickers:
    st.info("This watchlist is empty.")
    st.stop()

# ── Page header ───────────────────────────────────────────────────────────────
_display = _owner.get("display_name") or "An Unstructured Alpha user"
render_page_header(
    f"{_display}'s Watchlist",
    f"{len(_tickers)} ticker{'s' if len(_tickers) != 1 else ''} · "
    "Real-time Confluence Scores powered by 28 macro signals",
    icon="🔗",
)

# ── Load scores ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False, max_entries=20)
def _load_scores(tickers_tuple: tuple) -> dict:
    """
    Load Confluence Scores for the given tickers using the signals cache.
    Returns {ticker: {score, case, color}} for each ticker.
    """
    from utils.top_tickers import get_top_tickers
    try:
        result = get_top_tickers(signal_scores_hash=0)
        score_map = {}
        for row in result.get("all", []):
            if row["ticker"] in tickers_tuple:
                s   = float(row.get("score", 50))
                case = "BULL" if s >= 65 else ("BEAR" if s <= 35 else "NEUTRAL")
                color = "#00D566" if case == "BULL" else ("#FF4D6A" if case == "BEAR" else "#F59E0B")
                score_map[row["ticker"]] = {
                    "score": s,
                    "name":  row.get("name", row["ticker"]),
                    "case":  case,
                    "color": color,
                }
        return score_map
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False, max_entries=20)
def _load_history(tickers_tuple: tuple) -> dict:
    """
    Return {ticker: [{date, score}]} for each ticker, last 30 days.
    """
    from utils.score_history import get_score_history
    out = {}
    for t in tickers_tuple:
        try:
            out[t] = get_score_history(t, days=30)
        except Exception:
            out[t] = []
    return out


@st.cache_data(ttl=3600, show_spinner=False, max_entries=20)
def _load_deltas(tickers_tuple: tuple) -> dict:
    """
    Return {ticker: 7d_delta} using score_snapshots.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select
    from utils.db import score_snapshots, engine
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    out = {}
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(
                    score_snapshots.c.ticker,
                    score_snapshots.c.score,
                    score_snapshots.c.snapshot_date,
                )
                .where(score_snapshots.c.ticker.in_(list(tickers_tuple)))
                .where(score_snapshots.c.snapshot_date >= cutoff)
                .order_by(score_snapshots.c.ticker, score_snapshots.c.snapshot_date)
            ).fetchall()
        from collections import defaultdict
        by_t = defaultdict(list)
        for r in rows:
            by_t[r[0]].append((r[2], float(r[1])))
        for t, entries in by_t.items():
            entries.sort()
            if len(entries) >= 2:
                out[t] = round(entries[-1][1] - entries[0][1], 1)
    except Exception:
        pass
    return out


with st.spinner("Loading scores…"):
    _score_map = _load_scores(tuple(_tickers))
    _history   = _load_history(tuple(_tickers))
    _deltas    = _load_deltas(tuple(_tickers))

# ── Ticker cards ──────────────────────────────────────────────────────────────
import plotly.graph_objects as _pgo

_cols_per_row = 3
for _i in range(0, len(_tickers), _cols_per_row):
    _chunk = _tickers[_i:_i + _cols_per_row]
    _cols  = st.columns(len(_chunk))

    for _col, _tk in zip(_cols, _chunk):
        _sm    = _score_map.get(_tk, {})
        _score = _sm.get("score")
        _name  = _sm.get("name", _tk)
        _case  = _sm.get("case", "NEUTRAL")
        _color = _sm.get("color", "#F59E0B")
        _delta = _deltas.get(_tk)
        _hist  = _history.get(_tk, [])

        with _col:
            with st.container(border=True):
                # Score badge + ticker header
                _label = "Bullish" if _case == "BULL" else ("Bearish" if _case == "BEAR" else "Neutral")
                _delta_html = ""
                if _delta is not None:
                    _dc  = "#00D566" if _delta > 0 else ("#FF4D6A" if _delta < 0 else "#8892AA")
                    _da  = "▲" if _delta > 0 else ("▼" if _delta < 0 else "●")
                    _delta_html = (
                        f'<span style="font-size:0.78rem;color:{_dc};font-weight:600;">'
                        f'{_da} {_delta:+.1f} 7d</span>'
                    )

                st.markdown(
                    f'<div style="margin-bottom:8px;">'
                    f'<div style="font-size:1.05rem;font-weight:800;color:#E8EEFF;">{_tk}</div>'
                    f'<div style="font-size:0.72rem;color:#8892AA;margin-bottom:6px;">{_name}</div>'
                    + (
                        f'<div style="display:flex;align-items:baseline;gap:8px;">'
                        f'<span style="font-size:1.8rem;font-weight:900;color:{_color};">'
                        f'{_score:.0f}</span>'
                        f'<span style="font-size:0.75rem;color:#4A5280;">/100</span>'
                        f'</div>'
                        f'<div style="font-size:0.78rem;color:{_color};font-weight:600;">'
                        f'{_label}</div>'
                        f'{_delta_html}'
                        if _score is not None else
                        f'<span style="font-size:0.82rem;color:#8892AA;">Score building…</span>'
                    ) +
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # 30-day sparkline
                if len(_hist) >= 3:
                    _sh_scores = [h["score"] for h in _hist]
                    _sh_dates  = [h["snapshot_date"] for h in _hist]
                    _sh_fig    = _pgo.Figure(_pgo.Scatter(
                        x=_sh_dates, y=_sh_scores, mode="lines",
                        line=dict(color=_color, width=1.5),
                        fill="tozeroy", fillcolor=f"{_color}18",
                    ))
                    _sh_fig.update_layout(
                        margin=dict(l=0, r=0, t=0, b=0), height=50,
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(visible=False),
                        yaxis=dict(visible=False, range=[0, 100]),
                        showlegend=False,
                    )
                    st.plotly_chart(_sh_fig, use_container_width=True,
                                    config=PLOTLY_CONFIG,
                                    key=f"share_spark_{_tk}")
                else:
                    st.caption("Score history building…")

                # Deep Dive button
                if st.button(
                    "Deep Dive →",
                    key=f"share_tdd_{_tk}",
                    use_container_width=True,
                    help=f"View full signal analysis for {_tk}",
                ):
                    st.session_state["selected_ticker"] = _tk
                    st.switch_page("pages/3_Ticker_Deep_Dive.py")

# ── CTA footer ────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    '<div style="background:rgba(0,200,224,0.06);border:1px solid rgba(0,200,224,0.18);'
    'border-radius:14px;padding:24px 28px;text-align:center;max-width:620px;margin:0 auto;">'
    '<div style="font-size:1.1rem;font-weight:800;color:#E8EEFF;margin-bottom:8px;">'
    '📊 Want signals for YOUR stocks?</div>'
    '<div style="font-size:0.88rem;color:#8892AA;margin-bottom:16px;">'
    'Track any ticker with 28 real macro signals — free account, no credit card required.'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)
_cta_col1, _cta_col2, _cta_col3 = st.columns([1.5, 1, 1.5])
with _cta_col2:
    if st.button("Create Free Account →", type="primary", use_container_width=True):
        st.switch_page("pages/29_Upgrade.py")

st.caption(
    "Powered by Unstructured Alpha · 28 macro signals · Data from FRED, SEC EDGAR, FINRA, EIA"
)
