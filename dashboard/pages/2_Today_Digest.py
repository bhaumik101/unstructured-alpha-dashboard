"""
Page 2 — Today's Intelligence Brief
Cross-cutting daily digest: current state of every signal in the library,
score movers from the snapshot history, and a watchlist summary for
logged-in users. The "morning brief" for the platform — one page that
answers "what changed and what should I look at today?"

Data freshness is deliberately tiered:
- Signal Pulse: fetched live, cached 2 hours (40 HTTP calls is real cost,
  not something to redo on every page refresh; 2h is honest for
  monthly/weekly signals whose values don't change intraday anyway).
- Score Movers: pulled from score_snapshots (the DB built organically by
  Ticker Deep Dive views) -- only tickers someone has recently viewed
  appear here. Stated plainly in the UI, not hidden.
- Watchlist / prices: 15-min cache via utils/quotes.py (same as Watchlist
  and Stock Screener, for consistency).
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import select

from utils.config import SIGNALS, TICKERS
from utils.db import engine, score_snapshots, init_db
from utils.header import render_header, render_sidebar_base, go_to_ticker
from utils.quotes import get_batch_quotes
from utils.score_history import record_all_signal_snapshots, get_signal_flips, get_signal_diff
from utils.signals_cache import get_all_signal_scores
from utils.narrative import generate_narrative
from utils.convergence import get_convergence_events, render_convergence_events

st.set_page_config(page_title="Today's Brief — UA", layout="wide")
render_header("Today's Brief")
render_sidebar_base()

init_db()

# ── Helpers ───────────────────────────────────────────────────────────────────

# Scores are loaded from the shared cross-page cache (utils/signals_cache.py).
# compute_all_signal_scores() has been removed — use get_all_signal_scores()
# directly. This eliminates a duplicate 40-signal FRED sweep and aligns TTL
# with home page and Sector Map (all now 2h from the same cache entry).


def get_score_movers(days_back: int = 7) -> pd.DataFrame:
    """
    From score_snapshots, find tickers with the biggest score delta between
    their earliest and latest snapshot within the last `days_back` days.
    Only tickers with at least 2 recorded snapshots in the window appear —
    a single snapshot has no delta to compare against.
    Returns empty DataFrame if no data (common for a fresh/low-traffic DB).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(score_snapshots)
                .where(score_snapshots.c.snapshot_date >= cutoff)
                .order_by(score_snapshots.c.ticker, score_snapshots.c.snapshot_date)
            ).mappings().all()
    except Exception:
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])
    results = []
    for ticker, grp in df.groupby("ticker"):
        grp = grp.sort_values("snapshot_date")
        if len(grp) < 2:
            continue
        earliest = grp.iloc[0]
        latest = grp.iloc[-1]
        delta = latest["score"] - earliest["score"]
        results.append({
            "ticker": ticker,
            "from_score": round(earliest["score"], 1),
            "from_date": earliest["snapshot_date"],
            "to_score": round(latest["score"], 1),
            "to_date": latest["snapshot_date"],
            "delta": round(delta, 1),
            "case": latest.get("case", "NEUTRAL") or "NEUTRAL",
        })

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(results)
    result_df["abs_delta"] = result_df["delta"].abs()
    return result_df.sort_values("abs_delta", ascending=False).reset_index(drop=True)


def get_watchlist_snapshots(user_id: int) -> pd.DataFrame:
    """
    Most recent recorded score for each of a user's watchlist tickers.
    Returns empty DataFrame if none have been viewed yet.
    """
    from utils import alerts_db
    watchlist = alerts_db.get_watchlist(user_id)
    if not watchlist:
        return pd.DataFrame()

    tickers = [row["ticker"] for row in watchlist]
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(score_snapshots)
                .where(score_snapshots.c.ticker.in_(tickers))
                .order_by(score_snapshots.c.snapshot_date.desc())
            ).mappings().all()
    except Exception:
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])
    # Keep only the most recent snapshot per ticker
    return df.sort_values("snapshot_date", ascending=False).drop_duplicates("ticker").reset_index(drop=True)


# ── Page header ───────────────────────────────────────────────────────────────

try:
    from zoneinfo import ZoneInfo
    _today_str = datetime.now(ZoneInfo("America/New_York")).strftime("%A, %B %-d, %Y")
except Exception:
    _today_str = datetime.now().strftime("%A, %B %-d, %Y")

st.markdown(f"# Today's Intelligence Brief")
st.caption(f"{_today_str} — signal state, score movers, and watchlist activity at a glance.")

# ── Section 1: Signal Pulse ───────────────────────────────────────────────────

st.markdown('<div class="section-header">SIGNAL PULSE</div>', unsafe_allow_html=True)

with st.spinner("Loading signal pulse (38 signals — cached 2 hours)…"):
    _all_scores = get_all_signal_scores()

# "as of" reflects when this page rendered, which is close enough — the data
# was fetched within the last 2h (the shared cache TTL). Exact fetch time is
# not stored because the shared cache serves all pages.
_as_of = datetime.now().strftime("%-I:%M %p ET, %b %-d")

# Batch-upsert today's snapshot for every signal in ONE DB transaction.
# Replaces the old per-signal loop (40 connections → 1).
try:
    record_all_signal_snapshots(_all_scores)
except Exception:
    pass

st.markdown(
    f'<div style="background:#1C2B4A;border-radius:8px;padding:10px 18px;margin-bottom:14px;'
    f'display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;'
    f'font-family:Georgia,serif;">'
    f'<div style="color:#EEF3FA;font-size:0.82rem;">'
    f'<span style="color:#8FB3D4;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;">'
    f'DATA AS OF</span><br>'
    f'<b style="font-size:1.0rem;">{_as_of}</b>'
    f'</div>'
    f'<div style="color:#8FB3D4;font-size:0.75rem;text-align:right;">'
    f'{len(_all_scores)} signals · cached 2h<br>'
    f'<span style="color:#6B8FA8;">signals are weekly/monthly; 2h cache is appropriate</span>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Auto Macro Narrative (above the 3-column pulse view) ─────────────────────
try:
    _nar = generate_narrative(_all_scores)
    _nar_rc  = _nar["regime_color"]
    _nar_bg  = "#EDF7ED" if ("BULL" in _nar["regime"] or "ON" in _nar["regime"]) else \
               ("#FDF0F0" if ("BEAR" in _nar["regime"] or "OFF" in _nar["regime"]) else "#FAF7F0")
    _nar_watch_html = (
        f'<div style="margin-top:8px;padding:7px 10px;background:#FFF8E7;'
        f'border-left:3px solid #B8860B;border-radius:4px;font-size:0.73rem;color:#5C4A1A;">'
        f'👁 {_nar["watch_note"]}</div>'
        if _nar.get("watch_note") else ""
    )
    st.markdown(
        f'<div style="background:{_nar_bg};border-radius:10px;padding:16px 20px;'
        f'border-left:5px solid {_nar_rc};font-family:Georgia,serif;margin-bottom:18px;">'
        f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:8px;">'
        f'<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.12em;color:{_nar_rc};'
        f'text-transform:uppercase;">TODAY\'S MACRO CALL</div>'
        f'<div style="font-size:1.1rem;font-weight:800;color:#1C2B4A;">{_nar["headline"]}</div>'
        f'</div>'
        f'<div style="font-size:0.80rem;color:#4A4440;line-height:1.65;">'
        f'{_nar["summary"]}</div>'
        f'{_nar_watch_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
except Exception:
    pass

# ── What Changed Since Last Week ──────────────────────────────────────────────
try:
    _diff = get_signal_diff(days_back=7)
    _d_bull = _diff.get("flipped_bullish", [])
    _d_bear = _diff.get("flipped_bearish", [])
    _d_movers = _diff.get("biggest_movers", [])
    _d_flip_total = _diff.get("total_flips", 0)
    _d_regime = _diff.get("regime_shift")

    if _d_flip_total > 0 or _d_movers or _d_regime:
        _regime_shift_html = (
            f'<div style="background:#FFF8E7;border-left:3px solid #B8860B;padding:5px 10px;'
            f'border-radius:4px;font-size:0.76rem;color:#5C4A1A;margin-bottom:8px;">'
            f'⚡ Regime shift: <b>{_d_regime}</b></div>'
            if _d_regime else ""
        )
        def _flip_pill(entry, direction):
            col = "#1B5E20" if direction == "bull" else "#7B1010"
            arrow = "▲" if direction == "bull" else "▼"
            return (
                f'<span style="display:inline-block;margin:2px 3px;padding:2px 8px;'
                f'border-radius:10px;font-size:0.70rem;background:{col}18;color:{col};font-weight:600;">'
                f'{arrow} {entry["name"][:28]}</span>'
            )
        _bull_pills = "".join(_flip_pill(e, "bull") for e in _d_bull)
        _bear_pills = "".join(_flip_pill(e, "bear") for e in _d_bear)
        _mover_pills = "".join(
            f'<span style="display:inline-block;margin:2px 3px;padding:2px 8px;'
            f'border-radius:10px;font-size:0.70rem;'
            f'background:{"#1B5E2018" if m["direction"]=="up" else "#7B101018"};'
            f'color:{"#1B5E20" if m["direction"]=="up" else "#7B1010"};font-weight:600;">'
            f'{"▲" if m["direction"]=="up" else "▼"} {m["name"][:24]} ({m["delta"]:+.0f}pts)</span>'
            for m in _d_movers
        )
        st.markdown(
            f'<div style="background:#F5F1E8;border-radius:8px;padding:14px 18px;'
            f'margin-bottom:18px;border:1px solid #D4C9B0;font-family:Georgia,serif;">'
            f'<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.10em;color:#8B7355;'
            f'text-transform:uppercase;margin-bottom:8px;">WHAT CHANGED SINCE LAST WEEK</div>'
            f'{_regime_shift_html}'
            f'{"<div style=\\"font-size:0.72rem;color:#4A4440;margin-bottom:4px\\">Flipped bullish</div>" + _bull_pills if _bull_pills else ""}'
            f'{"<div style=\\"font-size:0.72rem;color:#4A4440;margin:6px 0 4px\\">Flipped bearish</div>" + _bear_pills if _bear_pills else ""}'
            f'{"<div style=\\"font-size:0.72rem;color:#4A4440;margin:6px 0 4px\\">Biggest score movers</div>" + _mover_pills if _mover_pills else ""}'
            f'<div style="font-size:0.65rem;color:#9E9E8E;margin-top:8px;">'
            f'vs 7 days ago · {_d_flip_total} signal{"s" if _d_flip_total != 1 else ""} flipped direction</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
except Exception:
    pass

# ── Signal Convergence Events ─────────────────────────────────────────────────
try:
    _conv = get_convergence_events(days_back=7, min_signals=3)
    if _conv:
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#8B7355;letter-spacing:0.10em;'
            'text-transform:uppercase;border-bottom:1px solid #D4C9B0;padding-bottom:6px;margin-bottom:10px;">'
            '⚡ SIGNAL CONVERGENCE EVENTS — 3+ signals aligned this week</div>',
            unsafe_allow_html=True,
        )
        render_convergence_events(_conv, max_bull=3, max_bear=2)
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
except Exception:
    pass

_bull_sigs = sorted(
    [(sid, d) for sid, d in _all_scores.items() if d["status"] == "bullish" and not d.get("error")],
    key=lambda x: -x[1]["score"],
)
_bear_sigs = sorted(
    [(sid, d) for sid, d in _all_scores.items() if d["status"] == "bearish" and not d.get("error")],
    key=lambda x: x[1]["score"],
)
_neut_sigs = sorted(
    [(sid, d) for sid, d in _all_scores.items() if d["status"] == "neutral" or d.get("error")],
    key=lambda x: -x[1]["score"],
)

_pulse_col1, _pulse_col2, _pulse_col3 = st.columns(3)

def _signal_card_html(sid: str, d: dict) -> str:
    score = d["score"]
    status = d["status"]
    color = "#1B5E20" if status == "bullish" else ("#7B1010" if status == "bearish" else "#8B7355")
    border = "#1B5E20" if status == "bullish" else ("#7B1010" if status == "bearish" else "#D4C9B0")
    label = "BULL" if status == "bullish" else ("BEAR" if status == "bearish" else "—")
    if d.get("error"):
        score_str = "—"
        label = "ERR"
        color = "#8B7355"
        border = "#D4C9B0"
    else:
        score_str = f"{score:.0f}"
    return (
        f'<div style="background:#F5F1E8;border-radius:5px;padding:8px 12px;margin-bottom:6px;'
        f'border-left:3px solid {border};font-family:Georgia,serif;">'
        f'<span style="font-size:0.82rem;color:#1A1612;">{d["name"]}</span>'
        f'<span style="float:right;font-size:0.80rem;font-weight:700;color:{color};">'
        f'{score_str} <span style="font-size:0.68rem;letter-spacing:0.05em;">{label}</span></span>'
        f'</div>'
    )

with _pulse_col1:
    st.markdown(
        f'<div style="font-size:0.78rem;font-weight:700;color:#1B5E20;letter-spacing:0.06em;'
        f'text-transform:uppercase;border-bottom:2px solid #1B5E20;padding-bottom:4px;margin-bottom:10px;">'
        f'▲ BULLISH ({len(_bull_sigs)})</div>',
        unsafe_allow_html=True,
    )
    if _bull_sigs:
        for sid, d in _bull_sigs:
            st.markdown(_signal_card_html(sid, d), unsafe_allow_html=True)
    else:
        st.caption("No bullish signals right now.")

with _pulse_col2:
    st.markdown(
        f'<div style="font-size:0.78rem;font-weight:700;color:#7B1010;letter-spacing:0.06em;'
        f'text-transform:uppercase;border-bottom:2px solid #7B1010;padding-bottom:4px;margin-bottom:10px;">'
        f'▼ BEARISH ({len(_bear_sigs)})</div>',
        unsafe_allow_html=True,
    )
    if _bear_sigs:
        for sid, d in _bear_sigs:
            st.markdown(_signal_card_html(sid, d), unsafe_allow_html=True)
    else:
        st.caption("No bearish signals right now.")

with _pulse_col3:
    st.markdown(
        f'<div style="font-size:0.78rem;font-weight:700;color:#8B7355;letter-spacing:0.06em;'
        f'text-transform:uppercase;border-bottom:2px solid #8B7355;padding-bottom:4px;margin-bottom:10px;">'
        f'● NEUTRAL ({len(_neut_sigs)})</div>',
        unsafe_allow_html=True,
    )
    if _neut_sigs:
        for sid, d in _neut_sigs:
            st.markdown(_signal_card_html(sid, d), unsafe_allow_html=True)
    else:
        st.caption("No neutral signals right now.")

# Summary bar
_n_bull, _n_bear, _n_neut = len(_bull_sigs), len(_bear_sigs), len(_neut_sigs)
_total = _n_bull + _n_bear + _n_neut or 1
_bull_pct = _n_bull / _total * 100
_bear_pct = _n_bear / _total * 100
_neut_pct = _n_neut / _total * 100

_overall_bias = "BULLISH LEANING" if _n_bull > _n_bear + _n_neut * 0.5 else (
    "BEARISH LEANING" if _n_bear > _n_bull + _n_neut * 0.5 else "MIXED / NEUTRAL"
)
_bias_color = "#1B5E20" if "BULL" in _overall_bias else ("#7B1010" if "BEAR" in _overall_bias else "#8B7355")

st.markdown(
    f'<div style="background:#F0EBE1;border:1px solid #D4C9B0;border-radius:6px;padding:10px 16px;'
    f'margin-top:8px;font-family:Georgia,serif;font-size:0.85rem;">'
    f'<b style="color:{_bias_color};">{_overall_bias}</b> — '
    f'{_n_bull} bullish · {_n_bear} bearish · {_n_neut} neutral '
    f'<span style="color:#8B7355;font-size:0.78rem;">({_bull_pct:.0f}% / {_bear_pct:.0f}% / {_neut_pct:.0f}%)</span>'
    f'</div>',
    unsafe_allow_html=True,
)

st.divider()

# ── "What Changed This Week" — highest-retention section ─────────────────────
# Shows signal direction changes over the past 7 days in a clean summary.
# This answers "do I need to act on anything since I last checked?" — the core
# reason a user returns to the Brief each morning. 7-day window is deliberately
# wider than the "since yesterday" banner below, catching users who check weekly.
try:
    _week_flips = get_signal_flips(days_back=7)
    if _week_flips:
        st.markdown(
            f'<div style="background:#FAF7F0;border:1px solid #D4C9B0;border-left:5px solid #1C2B4A;'
            f'border-radius:8px;padding:14px 20px;margin-bottom:14px;font-family:Georgia,serif;">'
            f'<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;'
            f'color:#1C2B4A;font-weight:700;margin-bottom:10px;">'
            f'⚡ {len(_week_flips)} signal change{"s" if len(_week_flips) != 1 else ""} this week — what you may have missed</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:8px;">',
            unsafe_allow_html=True,
        )
        _FLIP_C  = {"bullish": "#1B5E20", "bearish": "#7B1010", "neutral": "#8B7355", "insufficient_data": "#9E9E8E"}
        _FLIP_BG = {"bullish": "#EDF7ED", "bearish": "#FDF0F0", "neutral": "#FAF7F0", "insufficient_data": "#F5F5F5"}
        _FLIP_S  = {"bullish": "▲", "bearish": "▼", "neutral": "●", "insufficient_data": "○"}
        _wflip_cells = ""
        for _wf in _week_flips[:12]:  # cap at 12 for layout
            _wf_name  = SIGNALS.get(_wf["signal_id"], {}).get("name", _wf["signal_id"])
            _wf_tc    = _FLIP_C.get(_wf["to_status"], "#8B7355")
            _wf_bg    = _FLIP_BG.get(_wf["to_status"], "#FAF7F0")
            _wf_fc    = _FLIP_C.get(_wf["from_status"], "#8B7355")
            _wf_ts    = _FLIP_S.get(_wf["to_status"], "●")
            _wf_fs    = _FLIP_S.get(_wf["from_status"], "●")
            _wflip_cells += (
                f'<div style="background:{_wf_bg};border:1px solid {_wf_tc}40;border-left:3px solid {_wf_tc};'
                f'border-radius:5px;padding:6px 10px;min-width:160px;flex:1;">'
                f'<div style="font-size:0.76rem;font-weight:700;color:#1A1612;line-height:1.3;margin-bottom:3px;">'
                f'{_wf_name[:30]}</div>'
                f'<div style="font-size:0.78rem;">'
                f'<span style="color:{_wf_fc};">{_wf_fs}</span>'
                f' <span style="color:#9E9E8E;">→</span> '
                f'<span style="font-weight:700;color:{_wf_tc};">{_wf_ts} {_wf["to_status"].replace("_"," ").title()}</span>'
                f'</div>'
                f'<div style="font-size:0.67rem;color:#8B7355;margin-top:2px;">{_wf["to_date"]}</div>'
                f'</div>'
            )
        st.markdown(_wflip_cells + f'</div></div>', unsafe_allow_html=True)
        if len(_week_flips) > 12:
            st.caption(f"+ {len(_week_flips) - 12} more signal changes this week.")
    else:
        st.info("No signal direction changes in the past 7 days — the macro picture is holding steady.", icon="✅")
except Exception:
    pass  # Never crash the page if flip history unavailable

st.divider()

# ── Section 2: Signal Flips ───────────────────────────────────────────────────

st.markdown('<div class="section-header">SIGNAL FLIPS (SINCE YESTERDAY)</div>', unsafe_allow_html=True)

_flips = get_signal_flips(days_back=1)

if not _flips:
    st.caption("No signal status changes recorded since yesterday — either nothing flipped, or today is the first visit (snapshots accumulate with each visit to this page).")
else:
    FLIP_COLOR = {"bullish": "#1B5E20", "bearish": "#7B1010", "neutral": "#8B7355"}
    FLIP_ARROW = {"bullish": "▲", "bearish": "▼", "neutral": "●"}
    for flip in _flips:
        sig_cfg = SIGNALS.get(flip["signal_id"], {})
        sig_name = sig_cfg.get("name", flip["signal_id"])
        fc = FLIP_COLOR.get(flip["to_status"], "#8B7355")
        fa = FLIP_ARROW.get(flip["to_status"], "●")
        fc_from = FLIP_COLOR.get(flip["from_status"], "#8B7355")
        st.markdown(
            f'<div style="background:#F5F1E8;border-left:3px solid {fc};border-radius:4px;'
            f'padding:8px 14px;margin-bottom:6px;font-family:Georgia,serif;font-size:0.85rem;">'
            f'<b>{sig_name}</b> &nbsp;'
            f'<span style="color:{fc_from};">{flip["from_status"]}</span> → '
            f'<span style="color:{fc};font-weight:700;">{fa} {flip["to_status"]}</span>'
            f'<span style="color:#8B7355;font-size:0.75rem;float:right;">'
            f'{flip["from_date"]} → {flip["to_date"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.divider()

# ── Section 3: Score Movers ───────────────────────────────────────────────────

st.markdown('<div class="section-header">SCORE MOVERS (LAST 7 DAYS)</div>', unsafe_allow_html=True)

_movers_df = get_score_movers(days_back=7)

if _movers_df.empty:
    st.info(
        "No score movement data yet — this feed populates organically as tickers are viewed on Ticker Deep Dive. "
        "Open any ticker there to start building the history."
    )
else:
    st.caption(
        "Score changes across tickers with at least 2 recorded snapshots in the last 7 days. "
        "History accumulates as tickers are viewed on Ticker Deep Dive — not a complete universe."
    )

    CASE_COLOR = {"BULL": "#1B5E20", "BEAR": "#7B1010", "NEUTRAL": "#8B7355"}

    for _, row in _movers_df.iterrows():
        ticker = row["ticker"]
        delta = row["delta"]
        to_score = row["to_score"]
        from_score = row["from_score"]
        case = str(row.get("case", "NEUTRAL") or "NEUTRAL").upper()
        from_date = row.get("from_date", "")
        to_date = row.get("to_date", "")
        case_color = CASE_COLOR.get(case, "#8B7355")
        delta_color = "#1B5E20" if delta > 0 else ("#7B1010" if delta < 0 else "#8B7355")
        delta_arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "●")
        company = TICKERS.get(ticker, {}).get("name", "")

        _mover_box = st.container(border=True)
        mc1, mc2, mc3 = _mover_box.columns([2.5, 2, 1])
        with mc1:
            go_to_ticker(ticker, key=f"digest_mover_{ticker}")
            if company:
                st.caption(company)
        with mc2:
            st.markdown(
                f'<div style="font-family:Georgia,serif;font-size:0.85rem;padding-top:4px;">'
                f'<span style="color:#8B7355;">{from_date}</span> → <span style="color:#1A1612;font-weight:700;">{to_date}</span>'
                f'<br><span style="color:#8B7355;">{from_score:.0f}</span> → '
                f'<b style="color:{case_color};">{to_score:.0f}</b>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with mc3:
            st.markdown(
                f'<div style="text-align:right;padding-top:4px;">'
                f'<span style="font-size:1.3rem;font-weight:700;color:{delta_color};">'
                f'{delta_arrow} {abs(delta):.0f}</span>'
                f'<br><span style="font-size:0.72rem;font-weight:700;color:{case_color};">{case}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

st.divider()

# ── Section 3: Watchlist Activity ─────────────────────────────────────────────

st.markdown('<div class="section-header">WATCHLIST ACTIVITY</div>', unsafe_allow_html=True)

_user = st.session_state.get("user")
if not _user:
    st.info("Sign in to see your watchlist tickers' latest recorded scores and live prices here.")
else:
    _user_id = _user["id"]
    from utils import alerts_db
    _watchlist = alerts_db.get_watchlist(_user_id)

    if not _watchlist:
        st.info("Your watchlist is empty. Add tickers on the Watchlist page to track them here.")
    else:
        _watch_tickers = [r["ticker"] for r in _watchlist]

        with st.spinner(f"Loading live prices for {len(_watch_tickers)} watched ticker(s)…"):
            _watch_quotes = get_batch_quotes(_watch_tickers)

        _watch_snaps = get_watchlist_snapshots(_user_id)
        _snap_by_ticker = {}
        if not _watch_snaps.empty:
            for _, srow in _watch_snaps.iterrows():
                _snap_by_ticker[srow["ticker"]] = srow

        for row in _watchlist:
            ticker = row["ticker"]
            q = _watch_quotes.get(ticker, {})
            price = q.get("last")
            chg_pct = q.get("chg_1d_pct")
            snap = _snap_by_ticker.get(ticker)

            _wbox = st.container(border=True)
            wa1, wa2, wa3 = _wbox.columns([2.5, 1.5, 1.5])

            with wa1:
                go_to_ticker(ticker, key=f"digest_watch_{ticker}")
                company = TICKERS.get(ticker, {}).get("name", "")
                if company:
                    st.caption(company)

            with wa2:
                if price is not None:
                    st.markdown(f"**${price:,.2f}**")
                else:
                    st.caption("Price unavailable")
                if chg_pct is not None:
                    _cc = "#1B5E20" if chg_pct > 0 else ("#7B1010" if chg_pct < 0 else "#8B7355")
                    _ca = "▲" if chg_pct > 0 else ("▼" if chg_pct < 0 else "●")
                    st.markdown(
                        f'<span style="color:{_cc};font-size:0.85rem;">{_ca} {chg_pct:+.2f}% today</span>',
                        unsafe_allow_html=True,
                    )

            with wa3:
                if snap is not None:
                    _snap_score = snap["score"]
                    _snap_case = str(snap.get("case", "NEUTRAL") or "NEUTRAL").upper()
                    _snap_date = snap.get("snapshot_date", "")
                    _sc_color = "#1B5E20" if _snap_case == "BULL" else ("#7B1010" if _snap_case == "BEAR" else "#8B7355")
                    st.markdown(
                        f'<div style="text-align:right;font-family:Georgia,serif;">'
                        f'<span style="font-size:1.2rem;font-weight:700;color:{_sc_color};">{_snap_score:.0f}</span>'
                        f'<span style="font-size:0.72rem;font-weight:700;color:{_sc_color};margin-left:4px;">{_snap_case}</span>'
                        f'<br><span style="font-size:0.70rem;color:#8B7355;">as of {_snap_date}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("No score recorded yet — open on Ticker Deep Dive to generate one.")

# ── Email Digest Nudge ────────────────────────────────────────────────────────
# Psychology: show after user has seen value (full page) — reciprocity principle.
# Only show if not already opted-in.
_cur_user = st.session_state.get("user")
_already_opted_in = False
if _cur_user:
    try:
        from utils.auth import get_digest_optin
        _already_opted_in = get_digest_optin(_cur_user["id"])
    except Exception:
        pass

if not _already_opted_in:
    st.markdown("""
<div style="background:#1C2B4A;border-radius:10px;padding:20px 24px;margin:20px 0 14px;
            font-family:Georgia,serif;display:flex;align-items:center;
            justify-content:space-between;flex-wrap:wrap;gap:14px;">
    <div>
        <div style="font-size:0.68rem;letter-spacing:0.12em;color:#C9A84C;font-weight:600;
                    text-transform:uppercase;margin-bottom:4px;">WANT THIS IN YOUR INBOX?</div>
        <div style="font-size:0.95rem;font-weight:700;color:#FAF7F0;">
            Get Today's Brief every morning at 7 AM ET
        </div>
        <div style="font-size:0.80rem;color:#A0A8B8;margin-top:4px;line-height:1.5;">
            Free. No spam. 38 signals distilled into a 2-minute read. Unsubscribe any time.
        </div>
    </div>
</div>
""", unsafe_allow_html=True)
    _nc1, _nc2, _ = st.columns([1.4, 1.4, 2])
    with _nc1:
        if st.button("📬 Create free account", use_container_width=True, type="primary", key="digest_signup_cta"):
            st.switch_page("pages/home_page.py")
    with _nc2:
        if _cur_user:
            if st.button("Enable in Watchlist →", use_container_width=True, key="digest_enable_cta"):
                st.switch_page("pages/10_Watchlist.py")

st.markdown("""
<div class="disclaimer">
<b>Not financial advice.</b> Signal states and scores reflect publicly available data at the cached
time shown above. Do your own research before making any investment decision.
</div>
""", unsafe_allow_html=True)
