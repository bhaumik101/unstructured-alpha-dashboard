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
from utils.header import render_header, render_sidebar_base, render_page_header, go_to_ticker, render_footer, disclose_unavailable_signals
from utils.quotes import get_batch_quotes
from utils.score_history import (
    record_all_signal_snapshots, get_signal_flips, get_signal_diff,
    get_signals_near_threshold,
)
from utils.signals_cache import get_all_signal_scores
from utils.narrative import generate_narrative
from utils.convergence import get_convergence_events, render_convergence_events
from utils.theme import (
    inject_all_css, empty_state, section_label,
    render_educational_callout, render_signal_legend,
)

st.set_page_config(page_title="Today's Brief — UA", layout="wide")
render_header("Today's Brief")
_brief_section = render_sidebar_base(
    page_title="Today's Brief",
    sections=("Daily Intelligence", "Weekly Research"),
    section_key="brief_section_rail",
)
inject_all_css()

render_page_header(
    "Today's Brief",
    "What the macro machine sees right now — signals, regime, and top opportunities.",
    icon="",
)

# Data-integrity disclosure: this page presents/acts on macro-signal scores. If
# any underlying signal is synthetic (no FRED/EIA key or a failed live fetch),
# that must be visible here, not only on the Signal Dashboard. Same cached call
# the page's own logic uses, so no extra network cost.
from utils.signals_cache import get_all_signal_scores as _gas_disc
disclose_unavailable_signals(_gas_disc())

init_db()

if _brief_section == "Daily Intelligence":

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

    # ── What Changed (compression hero) ───────────────────────────────────────────
    # Point 4: lead with the MEANINGFUL changes since yesterday, ranked, mapped to
    # the user's own holdings, with everything else explicitly bucketed as noise.
    # This sells decision compression before the full Signal Pulse below. Additive
    # and fully defensive — a hiccup here must never break the brief.
    # Engine + ranking/mapping logic: utils/what_changed.py (unit-tested).
    try:
        from utils.what_changed import build_what_changed, render_what_changed_html
        _wc_watchlist = []
        try:
            from utils import alerts_db as _wc_alerts_db
            _wc_user = st.session_state.get("user")
            if _wc_user:
                _wc_rows = _wc_alerts_db.get_watchlist(_wc_user["id"])
                _wc_watchlist = [r["ticker"] for r in (_wc_rows or [])]
        except Exception:
            _wc_watchlist = []
        _wc_diff = get_signal_diff(days_back=1)
        _wc_payload = build_what_changed(_wc_diff, watchlist=_wc_watchlist)
        st.html(section_label("What Changed", dot="#7C3AED"))
        st.html(render_what_changed_html(_wc_payload))
        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    except Exception:
        pass

    # ── Section 1: Signal Pulse ───────────────────────────────────────────────────

    st.html(section_label("Signal Pulse", dot="#00D566"))

    # Educational callout collapsed by default — returning users don't need it
    # taking up screen space every visit. New users can expand it.
    with st.expander("How to read these signals", expanded=False):
        st.markdown(
            render_educational_callout(
                title="How to read these signals",
                body=(
                    "Each signal is a 0–100 score derived from public macro data (FRED, EIA, SEC EDGAR). "
                    "A score ≥ 65 means the indicator is historically elevated in a direction that has "
                    "preceded strength in related assets. A score ≤ 35 indicates the opposite. "
                    "Scores between 36–64 are neutral — no strong tilt. "
                    "<strong>These are informational indicators, not buy/sell signals.</strong>"
                ),
                icon="",
                accent="#00C8E0",
            ),
            unsafe_allow_html=True,
        )
        st.html(render_signal_legend())

    with st.spinner("Loading signal pulse (cached 2 hours)…"):
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
        f'<div style="background:#12151E;border:1px solid rgba(255,255,255,0.07);border-radius:10px;'
        f'padding:10px 18px;margin-bottom:14px;display:flex;align-items:center;'
        f'justify-content:space-between;flex-wrap:wrap;gap:8px;font-family:Inter,sans-serif;">'
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<span class="ua-pulse-dot"></span>'
        f'<div>'
        f'<div style="font-size:0.60rem;font-weight:700;color:#8892AA;text-transform:uppercase;letter-spacing:0.12em;">'
        f'{_today_str}</div>'
        f'<div style="font-size:0.88rem;font-weight:700;color:#E8EEFF;">As of {_as_of}</div>'
        f'</div>'
        f'</div>'
        f'<div style="font-size:0.72rem;color:#6B7FBF;text-align:right;">'
        f'{len(_all_scores)} signals · 2h cache<br>'
        f'<span style="color:#4A5478;">weekly/monthly signals; 2h refresh is appropriate</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Auto Macro Narrative (above the 3-column pulse view) ─────────────────────
    try:
        _nar = generate_narrative(_all_scores)
        _nar_rc  = _nar["regime_color"]
        _nar_bg  = "rgba(0,213,102,0.08)" if ("BULL" in _nar["regime"] or "ON" in _nar["regime"]) else \
                   ("rgba(255,68,68,0.08)" if ("BEAR" in _nar["regime"] or "OFF" in _nar["regime"]) else "#12151E")
        _nar_watch_html = (
            f'<div style="margin-top:8px;padding:7px 10px;background:rgba(245,158,11,0.08);'
            f'border-left:3px solid #F59E0B;border-radius:4px;font-size:0.73rem;color:#F59E0B;">'
            f' {_nar["watch_note"]}</div>'
            if _nar.get("watch_note") else ""
        )
        st.markdown(
            f'<div class="ua-spotlight" style="--ua-spotlight-accent:{_nar_rc};margin-bottom:18px;">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">'
            f'<span class="ua-pulse-dot" style="background:{_nar_rc};flex-shrink:0;"></span>'
            f'<span style="font-size:0.62rem;font-weight:700;letter-spacing:0.14em;color:{_nar_rc};'
            f'text-transform:uppercase;">Today\'s Macro Call</span>'
            f'</div>'
            f'<div style="font-size:1.05rem;font-weight:800;color:#E8EEFF;margin-bottom:8px;'
            f'line-height:1.3;letter-spacing:-0.2px;">{_nar["headline"]}</div>'
            f'<div style="font-size:0.80rem;color:#B8C0D4;line-height:1.65;">'
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
                f'<div style="background:rgba(245,158,11,0.08);border-left:3px solid #F59E0B;padding:5px 10px;'
                f'border-radius:4px;font-size:0.76rem;color:#F59E0B;margin-bottom:8px;">'
                f' Regime shift: <b>{_d_regime}</b></div>'
                if _d_regime else ""
            )
            def _flip_pill(entry, direction):
                col = "#00D566" if direction == "bull" else "#FF4444"
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
                f'background:{"rgba(0,213,102,0.09)" if m["direction"]=="up" else "rgba(255,68,68,0.09)"};'
                f'color:{"#00D566" if m["direction"]=="up" else "#FF4444"};font-weight:600;">'
                f'{"▲" if m["direction"]=="up" else "▼"} {m["name"][:24]} ({m["delta"]:+.0f}pts)</span>'
                for m in _d_movers
            )
            _diff_lbl_style = 'style="font-size:0.72rem;color:#B8C0D4;margin-bottom:4px"'
            _diff_lbl_bear  = 'style="font-size:0.72rem;color:#B8C0D4;margin:6px 0 4px"'
            _diff_lbl_move  = 'style="font-size:0.72rem;color:#B8C0D4;margin:6px 0 4px"'
            _bull_section  = (f'<div {_diff_lbl_style}>Flipped bullish</div>' + _bull_pills) if _bull_pills else ""
            _bear_section  = (f'<div {_diff_lbl_bear}>Flipped bearish</div>' + _bear_pills) if _bear_pills else ""
            _mover_section = (f'<div {_diff_lbl_move}>Biggest score movers</div>' + _mover_pills) if _mover_pills else ""
            _flip_word     = "signals" if _d_flip_total != 1 else "signal"
            st.markdown(
                f'<div style="background:rgba(18,21,30,0.85);border-radius:12px;padding:18px 22px;'
                f'margin-bottom:18px;border:1px solid rgba(255,255,255,0.10);'
                f'border-left:4px solid #F59E0B;font-family:Inter,sans-serif;'
                f'box-shadow:0 4px 20px rgba(0,0,0,0.30);">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">'
                f'<span style="font-size:1.1rem;"></span>'
                f'<div style="font-size:0.70rem;font-weight:700;letter-spacing:0.12em;color:#F59E0B;'
                f'text-transform:uppercase;">What Changed Since Last Week</div>'
                f'<div style="margin-left:auto;font-size:0.62rem;color:#6B7FBF;">'
                f'{_d_flip_total} {_flip_word} flipped · vs 7 days ago</div>'
                f'</div>'
                f'{_regime_shift_html}'
                f'{_bull_section}{_bear_section}{_mover_section}'
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
                '<div style="font-size:0.68rem;font-weight:700;color:#8892AA;letter-spacing:0.10em;'
                'text-transform:uppercase;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:6px;margin-bottom:10px;">'
                ' SIGNAL CONVERGENCE EVENTS — 3+ signals aligned this week</div>',
                unsafe_allow_html=True,
            )
            render_convergence_events(_conv, max_bull=3, max_bear=2)
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    except Exception:
        pass

    # ── About to Flip — most actionable section on the site ──────────────────────
    try:
        _near = get_signals_near_threshold(margin=5.0)
        _n_bull_flip  = _near.get("near_bullish_flip", [])
        _n_bear_flip  = _near.get("near_bearish_flip", [])
        if _n_bull_flip or _n_bear_flip:
            st.markdown(
                '<div style="background:#12151E;border-radius:10px;padding:14px 18px;margin-bottom:18px;'
                'border:1px solid rgba(255,255,255,0.08);font-family:Inter,sans-serif;">'
                '<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.10em;color:#8892AA;'
                'text-transform:uppercase;margin-bottom:10px;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:6px;">'
                ' ABOUT TO FLIP — signals within 5 pts of a threshold crossing</div>',
                unsafe_allow_html=True,
            )
            _flip_cols = st.columns(2)
            with _flip_cols[0]:
                if _n_bull_flip:
                    st.markdown(
                        '<div style="font-size:0.72rem;font-weight:700;color:#00D566;text-transform:uppercase;'
                        'letter-spacing:0.06em;margin-bottom:6px;">▲ Approaching BULLISH (≥65)</div>',
                        unsafe_allow_html=True,
                    )
                    for _nf in _n_bull_flip[:5]:
                        _v = _nf["velocity_per_week"]
                        _eta_txt = (
                            f' · ~{_nf["eta_weeks"]}w to flip'
                            if _nf.get("eta_weeks") and _nf["eta_weeks"] < 10 else
                            (' · moving away' if _v <= 0 else '')
                        )
                        _vel_color = "#00D566" if _v > 0 else ("#FF4444" if _v < 0 else "#8892AA")
                        st.markdown(
                            f'<div style="background:rgba(0,213,102,0.08);border-radius:5px;padding:7px 12px;margin-bottom:5px;'
                            f'border-left:3px solid #00D566;">'
                            f'<div style="font-size:0.80rem;font-weight:700;color:#E8EEFF;">{_nf["name"][:32]}</div>'
                            f'<div style="font-size:0.72rem;color:#B8C0D4;margin-top:2px;">'
                            f'Score: <b>{_nf["score"]}</b> · '
                            f'<span style="color:#00D566;font-weight:700;">{_nf["pts_away"]} pts to flip</span>'
                            f' · <span style="color:{_vel_color};">'
                            f'{"▲" if _v > 0 else ("▼" if _v < 0 else "→")} {abs(_v):.1f} pts/wk</span>'
                            f'{_eta_txt}</div>'
                            f'<div style="font-size:0.67rem;color:#8892AA;margin-top:1px;">{_nf["category"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
            with _flip_cols[1]:
                if _n_bear_flip:
                    st.markdown(
                        '<div style="font-size:0.72rem;font-weight:700;color:#FF4444;text-transform:uppercase;'
                        'letter-spacing:0.06em;margin-bottom:6px;">▼ Approaching BEARISH (≤35)</div>',
                        unsafe_allow_html=True,
                    )
                    for _nf in _n_bear_flip[:5]:
                        _v = _nf["velocity_per_week"]
                        _eta_txt = (
                            f' · ~{_nf["eta_weeks"]}w to flip'
                            if _nf.get("eta_weeks") and _nf["eta_weeks"] < 10 else
                            (' · moving away' if _v >= 0 else '')
                        )
                        _vel_color = "#FF4444" if _v < 0 else ("#00D566" if _v > 0 else "#8892AA")
                        st.markdown(
                            f'<div style="background:rgba(255,68,68,0.08);border-radius:5px;padding:7px 12px;margin-bottom:5px;'
                            f'border-left:3px solid #FF4444;">'
                            f'<div style="font-size:0.80rem;font-weight:700;color:#E8EEFF;">{_nf["name"][:32]}</div>'
                            f'<div style="font-size:0.72rem;color:#B8C0D4;margin-top:2px;">'
                            f'Score: <b>{_nf["score"]}</b> · '
                            f'<span style="color:#FF4444;font-weight:700;">{_nf["pts_away"]} pts to flip</span>'
                            f' · <span style="color:{_vel_color};">'
                            f'{"▲" if _v > 0 else ("▼" if _v < 0 else "→")} {abs(_v):.1f} pts/wk</span>'
                            f'{_eta_txt}</div>'
                            f'<div style="font-size:0.67rem;color:#8892AA;margin-top:1px;">{_nf["category"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
            st.markdown('</div>', unsafe_allow_html=True)
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
        color = "#00D566" if status == "bullish" else ("#FF4444" if status == "bearish" else "#8892AA")
        bg_tint = (
            "rgba(0,213,102,0.06)" if status == "bullish" else
            "rgba(255,68,68,0.06)" if status == "bearish" else
            "rgba(18,21,30,0.8)"
        )
        label = "BULL" if status == "bullish" else ("BEAR" if status == "bearish" else "—")
        if d.get("error"):
            score_str = "—"
            label = "ERR"
            color = "#8892AA"
            bg_tint = "rgba(18,21,30,0.8)"
        else:
            score_str = f"{score:.0f}"
        return (
            f'<div style="background:{bg_tint};border-radius:7px;padding:7px 12px;margin-bottom:5px;'
            f'border-left:2px solid {color};border:1px solid rgba(255,255,255,0.06);'
            f'border-left-width:2px;font-family:Inter,sans-serif;'
            f'transition:border-color 0.15s ease;">'
            f'<div style="display:flex;align-items:center;justify-content:space-between;">'
            f'<span style="font-size:0.78rem;color:#C8D0E4;flex:1;margin-right:8px;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{d["name"]}</span>'
            f'<span style="font-size:0.82rem;font-weight:800;color:{color};'
            f'text-shadow:0 0 12px {color}40;white-space:nowrap;">'
            f'{score_str} <span style="font-size:0.62rem;letter-spacing:0.06em;'
            f'font-weight:700;">{label}</span></span>'
            f'</div>'
            f'</div>'
        )

    with _pulse_col1:
        st.markdown(
            f'<div style="font-size:0.70rem;font-weight:700;color:#00D566;letter-spacing:0.08em;'
            f'text-transform:uppercase;border-bottom:2px solid rgba(0,213,102,0.4);'
            f'padding-bottom:5px;margin-bottom:10px;display:flex;align-items:center;gap:6px;">'
            f'<span style="background:rgba(0,213,102,0.12);border:1px solid rgba(0,213,102,0.3);'
            f'border-radius:12px;padding:1px 8px;font-size:0.68rem;">▲ {len(_bull_sigs)}</span>'
            f'BULLISH</div>',
            unsafe_allow_html=True,
        )
        if _bull_sigs:
            for sid, d in _bull_sigs:
                st.html(_signal_card_html(sid, d))
        else:
            st.html(empty_state("", "No bullish signals", "All signals currently read neutral or bearish."))

    with _pulse_col2:
        st.markdown(
            f'<div style="font-size:0.70rem;font-weight:700;color:#FF4444;letter-spacing:0.08em;'
            f'text-transform:uppercase;border-bottom:2px solid rgba(255,68,68,0.4);'
            f'padding-bottom:5px;margin-bottom:10px;display:flex;align-items:center;gap:6px;">'
            f'<span style="background:rgba(255,68,68,0.12);border:1px solid rgba(255,68,68,0.3);'
            f'border-radius:12px;padding:1px 8px;font-size:0.68rem;">▼ {len(_bear_sigs)}</span>'
            f'BEARISH</div>',
            unsafe_allow_html=True,
        )
        if _bear_sigs:
            for sid, d in _bear_sigs:
                st.html(_signal_card_html(sid, d))
        else:
            st.html(empty_state("", "No bearish signals", "All signals currently read neutral or bullish."))

    with _pulse_col3:
        st.markdown(
            f'<div style="font-size:0.70rem;font-weight:700;color:#8892AA;letter-spacing:0.08em;'
            f'text-transform:uppercase;border-bottom:2px solid rgba(136,146,170,0.3);'
            f'padding-bottom:5px;margin-bottom:10px;display:flex;align-items:center;gap:6px;">'
            f'<span style="background:rgba(136,146,170,0.10);border:1px solid rgba(136,146,170,0.25);'
            f'border-radius:12px;padding:1px 8px;font-size:0.68rem;">● {len(_neut_sigs)}</span>'
            f'NEUTRAL</div>',
            unsafe_allow_html=True,
        )
        if _neut_sigs:
            for sid, d in _neut_sigs:
                st.html(_signal_card_html(sid, d))
        else:
            st.html(empty_state("", "No neutral signals", "Signals are polarized — all currently bullish or bearish."))

    # Summary bar
    _n_bull, _n_bear, _n_neut = len(_bull_sigs), len(_bear_sigs), len(_neut_sigs)
    _total = _n_bull + _n_bear + _n_neut or 1
    _bull_pct = _n_bull / _total * 100
    _bear_pct = _n_bear / _total * 100
    _neut_pct = _n_neut / _total * 100

    _overall_bias = "BULLISH LEANING" if _n_bull > _n_bear + _n_neut * 0.5 else (
        "BEARISH LEANING" if _n_bear > _n_bull + _n_neut * 0.5 else "MIXED / NEUTRAL"
    )
    _bias_color = "#00D566" if "BULL" in _overall_bias else ("#FF4444" if "BEAR" in _overall_bias else "#8892AA")

    st.markdown(
        f'<div style="background:#12151E;border:1px solid rgba(255,255,255,0.08);border-radius:10px;'
        f'padding:12px 18px;margin-top:8px;font-family:Inter,sans-serif;">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">'
        f'<b style="font-size:0.88rem;color:{_bias_color};">{_overall_bias}</b>'
        f'<span style="font-size:0.72rem;color:#8892AA;">{_n_bull}B / {_n_bear}Be / {_n_neut}N</span>'
        f'</div>'
        f'<div style="display:flex;height:6px;border-radius:4px;overflow:hidden;gap:1px;">'
        f'<div style="flex:{_bull_pct:.0f};background:#00D566;min-width:{"2px" if _bull_pct > 0 else "0"};"></div>'
        f'<div style="flex:{_bear_pct:.0f};background:#FF4444;min-width:{"2px" if _bear_pct > 0 else "0"};"></div>'
        f'<div style="flex:{_neut_pct:.0f};background:#6B7FBF;min-width:{"2px" if _neut_pct > 0 else "0"};"></div>'
        f'</div>'
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
                f'<div style="background:#12151E;border:1px solid rgba(255,255,255,0.08);border-left:5px solid #12151E;'
                f'border-radius:8px;padding:14px 20px;margin-bottom:14px;font-family:Inter,sans-serif;">'
                f'<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;'
                f'color:#12151E;font-weight:700;margin-bottom:10px;">'
                f' {len(_week_flips)} signal change{"s" if len(_week_flips) != 1 else ""} this week — what you may have missed</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:8px;">',
                unsafe_allow_html=True,
            )
            _FLIP_C  = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#8892AA", "insufficient_data": "#6B7FBF"}
            _FLIP_BG = {"bullish": "rgba(0,213,102,0.08)", "bearish": "rgba(255,68,68,0.08)", "neutral": "#12151E", "insufficient_data": "#1A1D2A"}
            _FLIP_S  = {"bullish": "▲", "bearish": "▼", "neutral": "●", "insufficient_data": "○"}
            _wflip_cells = ""
            for _wf in _week_flips[:12]:  # cap at 12 for layout
                _wf_name  = SIGNALS.get(_wf["signal_id"], {}).get("name", _wf["signal_id"])
                _wf_tc    = _FLIP_C.get(_wf["to_status"], "#8892AA")
                _wf_bg    = _FLIP_BG.get(_wf["to_status"], "#12151E")
                _wf_fc    = _FLIP_C.get(_wf["from_status"], "#8892AA")
                _wf_ts    = _FLIP_S.get(_wf["to_status"], "●")
                _wf_fs    = _FLIP_S.get(_wf["from_status"], "●")
                _wflip_cells += (
                    f'<div style="background:{_wf_bg};border:1px solid {_wf_tc}40;border-left:3px solid {_wf_tc};'
                    f'border-radius:5px;padding:6px 10px;min-width:160px;flex:1;">'
                    f'<div style="font-size:0.76rem;font-weight:700;color:#E8EEFF;line-height:1.3;margin-bottom:3px;">'
                    f'{_wf_name[:30]}</div>'
                    f'<div style="font-size:0.78rem;">'
                    f'<span style="color:{_wf_fc};">{_wf_fs}</span>'
                    f' <span style="color:#6B7FBF;">→</span> '
                    f'<span style="font-weight:700;color:{_wf_tc};">{_wf_ts} {_wf["to_status"].replace("_"," ").title()}</span>'
                    f'</div>'
                    f'<div style="font-size:0.67rem;color:#8892AA;margin-top:2px;">{_wf["to_date"]}</div>'
                    f'</div>'
                )
            st.markdown(_wflip_cells + f'</div></div>', unsafe_allow_html=True)
            if len(_week_flips) > 12:
                st.caption(f"+ {len(_week_flips) - 12} more signal changes this week.")
        else:
            st.html(empty_state("", "No signal changes this week", "The macro picture is holding steady — no direction flips in the past 7 days."))
    except Exception:
        pass  # Never crash the page if flip history unavailable

    st.divider()

    # ── Section 2: Signal Flips ───────────────────────────────────────────────────

    st.html(section_label("Signal Flips — Since Yesterday", dot="#F59E0B"))

    _flips = get_signal_flips(days_back=1)

    if not _flips:
        st.caption("No signal status changes recorded since yesterday — either nothing flipped, or today is the first visit (snapshots accumulate with each visit to this page).")
    else:
        FLIP_COLOR = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#8892AA"}
        FLIP_ARROW = {"bullish": "▲", "bearish": "▼", "neutral": "●"}
        for flip in _flips:
            sig_cfg = SIGNALS.get(flip["signal_id"], {})
            sig_name = sig_cfg.get("name", flip["signal_id"])
            fc = FLIP_COLOR.get(flip["to_status"], "#8892AA")
            fa = FLIP_ARROW.get(flip["to_status"], "●")
            fc_from = FLIP_COLOR.get(flip["from_status"], "#8892AA")
            st.markdown(
                f'<div style="background:#12151E;border-left:3px solid {fc};border-radius:4px;'
                f'padding:8px 14px;margin-bottom:6px;font-family:Inter,sans-serif;font-size:0.85rem;">'
                f'<b>{sig_name}</b> &nbsp;'
                f'<span style="color:{fc_from};">{flip["from_status"]}</span> → '
                f'<span style="color:{fc};font-weight:700;">{fa} {flip["to_status"]}</span>'
                f'<span style="color:#8892AA;font-size:0.75rem;float:right;">'
                f'{flip["from_date"]} → {flip["to_date"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Section 3: Score Movers ───────────────────────────────────────────────────

    st.html(section_label("Score Movers — Last 7 Days", dot="#7C3AED"))

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

        CASE_COLOR = {"BULL": "#00D566", "BEAR": "#FF4444", "NEUTRAL": "#8892AA"}

        # ── Watchlist-aware ordering ───────────────────────────────────────────
        # If there's a logged-in user, bubble their watched tickers to the top of
        # the list. Gracefully falls back to an empty set for anonymous visitors
        # or if the watchlist fetch fails.
        _digest_user = st.session_state.get("user")
        _watch_set: set = set()
        if _digest_user:
            try:
                from utils import alerts_db as _alerts_db_digest
                _wl_rows = _alerts_db_digest.get_watchlist(_digest_user["id"])
                _watch_set = {r["ticker"] for r in _wl_rows}
            except Exception:
                pass
        if _watch_set:
            _movers_df = _movers_df.copy()
            _movers_df["_w"] = _movers_df["ticker"].isin(_watch_set).astype(int)
            _movers_df = (
                _movers_df
                .sort_values(["_w", "abs_delta"], ascending=[False, False])
                .drop(columns=["_w"])
                .reset_index(drop=True)
            )
            _n_watching = int(_movers_df["ticker"].isin(_watch_set).sum())
            if _n_watching:
                st.caption(
                    f" {_n_watching} of your watched ticker(s) appear below — shown first."
                )

        for _, row in _movers_df.iterrows():
            ticker = row["ticker"]
            delta = row["delta"]
            to_score = row["to_score"]
            from_score = row["from_score"]
            case = str(row.get("case", "NEUTRAL") or "NEUTRAL").upper()
            from_date = row.get("from_date", "")
            to_date = row.get("to_date", "")
            case_color = CASE_COLOR.get(case, "#8892AA")
            delta_color = "#00D566" if delta > 0 else ("#FF4444" if delta < 0 else "#8892AA")
            delta_arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "●")
            company = TICKERS.get(ticker, {}).get("name", "")

            _mover_box = st.container(border=True)
            mc1, mc2, mc3 = _mover_box.columns([2.5, 2, 1])
            with mc1:
                go_to_ticker(ticker, key=f"digest_mover_{ticker}")
                if company:
                    st.caption(company)
                if ticker in _watch_set:
                    st.markdown(
                        '<span style="font-size:0.68rem;font-weight:700;color:#00C8E0;'
                        'background:rgba(0,200,224,0.12);border-radius:3px;'
                        'padding:1px 6px;letter-spacing:0.02em;"> Watching</span>',
                        unsafe_allow_html=True,
                    )
            with mc2:
                st.markdown(
                    f'<div style="font-family:Inter,sans-serif;font-size:0.85rem;padding-top:4px;">'
                    f'<span style="color:#8892AA;">{from_date}</span> → <span style="color:#E8EEFF;font-weight:700;">{to_date}</span>'
                    f'<br><span style="color:#8892AA;">{from_score:.0f}</span> → '
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

            # Explain the Move — deterministic attribution of this score change,
            # reusing the shared engine. Cheap path (genuine component snapshots
            # only, no per-ticker history scan); silent when a ticker has no
            # component breakdown recorded yet. Fully defensive.
            try:
                from utils.score_history import explain_move
                from utils.score_attribution import render_attribution_html
                _attr = explain_move(ticker, days_back=7, allow_reconstruction=False)
                if _attr.get("state") in ("ok", "insufficient_coverage") and _attr.get("summary"):
                    _mover_box.caption(_attr["summary"])
                    with _mover_box.expander(f"Explain the {abs(delta):.0f}-point move"):
                        st.html(render_attribution_html(_attr))
            except Exception:
                pass

    st.divider()

    # ── Section 3: Watchlist Activity ─────────────────────────────────────────────

    st.html(section_label("Watchlist Activity", dot="#00C8E0"))

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
                        _cc = "#00D566" if chg_pct > 0 else ("#FF4444" if chg_pct < 0 else "#8892AA")
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
                        _sc_color = "#00D566" if _snap_case == "BULL" else ("#FF4444" if _snap_case == "BEAR" else "#8892AA")
                        st.markdown(
                            f'<div style="text-align:right;font-family:Inter,sans-serif;">'
                            f'<span style="font-size:1.2rem;font-weight:700;color:{_sc_color};">{_snap_score:.0f}</span>'
                            f'<span style="font-size:0.72rem;font-weight:700;color:{_sc_color};margin-left:4px;">{_snap_case}</span>'
                            f'<br><span style="font-size:0.70rem;color:#8892AA;">as of {_snap_date}</span>'
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
    <div class="ua-pro-banner" style="margin:20px 0 14px;">
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px;">
            <div>
                <div style="font-size:0.60rem;font-weight:700;letter-spacing:0.16em;color:#A78BFA;
                            text-transform:uppercase;margin-bottom:6px;"> Want this in your inbox?</div>
                <div style="font-size:1.0rem;font-weight:800;color:#E8EEFF;margin-bottom:4px;
                            letter-spacing:-0.2px;">
                    Get Today's Brief every morning at 7 AM ET
                </div>
                <div style="font-size:0.78rem;color:#8892AA;line-height:1.55;">
                    47 signals distilled into a 2-minute read. Pro feature · 7-day free trial.
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
        _nc1, _nc2, _ = st.columns([1.4, 1.4, 2])
        with _nc1:
            _btn_label = "→ Get it in my inbox" if _cur_user else " Create free account"
            _btn_page  = "pages/29_Upgrade.py" if _cur_user else "pages/home_page.py"
            if st.button(_btn_label, use_container_width=True, type="primary", key="digest_signup_cta"):
                st.switch_page(_btn_page)
        with _nc2:
            if st.button("See what's included →", use_container_width=True, key="digest_pro_cta"):
                st.switch_page("pages/29_Upgrade.py")

    st.markdown("""
    <div class="disclaimer">
    <b>Not financial advice.</b> Signal states and scores reflect publicly available data at the cached
    time shown above. Do your own research before making any investment decision.
    </div>
    """, unsafe_allow_html=True)


if _brief_section == "Weekly Research":
    from utils.narrative_engine import get_latest_note, get_note_archive, generate_weekly_note as _gen_note

    def _wb_regime_chip(regime: str) -> str:
        colors = {
            "RISK-ON":            ("rgba(0,213,102,0.12)",  "#00D566"),
            "CAUTIOUSLY BULLISH": ("rgba(0,213,102,0.08)",  "#33691E"),
            "MIXED / TRANSITION": ("rgba(245,158,11,0.12)", "#F59E0B"),
            "CAUTIOUSLY BEARISH": ("rgba(255,68,68,0.08)",  "#BF360C"),
            "RISK-OFF":           ("rgba(255,68,68,0.12)",  "#FF4444"),
        }
        bg, fg = colors.get(regime, ("rgba(107,127,191,0.12)", "#6B7FBF"))
        return (
            f'<span style="display:inline-block;font-size:0.68rem;font-weight:700;'
            f'letter-spacing:0.10em;padding:3px 10px;border-radius:3px;'
            f'background:{bg};color:{fg};border:1px solid {fg}33;">'
            f'{regime}</span>'
        )

    with st.spinner("Loading Weekly Brief…"):
        _wb_note = get_latest_note()

    if _wb_note is None:
        st.info(
            "No Weekly Brief has been generated yet. "
            "The first note publishes automatically each Sunday, "
            "or an admin can generate one below."
        )
    else:
        _wb_regime   = _wb_note.get("regime", "MIXED / TRANSITION")
        _wb_date     = _wb_note.get("note_date", "")
        _wb_bull     = _wb_note.get("bull_count") or 0
        _wb_bear     = _wb_note.get("bear_count") or 0
        _wb_model    = _wb_note.get("model", "")
        _wb_headline = _wb_note.get("headline", "")
        _wb_body_raw = _wb_note.get("body", "")

        try:
            from datetime import datetime as _wbdt
            _wb_date_disp = _wbdt.strptime(_wb_date, "%Y-%m-%d").strftime("%B %d, %Y")
        except Exception:
            _wb_date_disp = _wb_date

        st.markdown(
            f'<div style="border-bottom:2px solid rgba(255,255,255,0.12);'
            f'padding-bottom:10px;margin-bottom:16px;display:flex;align-items:center;'
            f'justify-content:space-between;flex-wrap:wrap;gap:8px;">'
            f'<span style="font-size:1.1rem;font-weight:700;color:#E8EEFF;">'
            f' Unstructured Alpha — Weekly Brief</span>'
            f'<span style="font-size:0.70rem;color:#4A5478;">Machine intelligence · Macro synthesis</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'{_wb_regime_chip(_wb_regime)}&nbsp;&nbsp;'
            f'<span style="font-size:0.70rem;color:#8892AA;">'
            f'Published {_wb_date_disp} · {_wb_bull} bullish · {_wb_bear} bearish · {_wb_model}'
            f'</span>',
            unsafe_allow_html=True,
        )

        if _wb_headline:
            st.markdown(
                f'<div style="font-size:1.25rem;font-weight:800;color:#E8EEFF;'
                f'margin:16px 0 12px;line-height:1.35;">{_wb_headline}</div>',
                unsafe_allow_html=True,
            )

        _wb_paras = [p.strip() for p in _wb_body_raw.split("\n\n") if p.strip()]
        if _wb_paras and _wb_paras[0].strip("*#").strip() == _wb_headline.strip("*#").strip():
            _wb_paras = _wb_paras[1:]

        for _p in _wb_paras:
            st.markdown(
                f'<p style="font-size:0.90rem;color:#B8C0D4;line-height:1.75;'
                f'margin-bottom:14px;font-family:Inter,sans-serif;">{_p}</p>',
                unsafe_allow_html=True,
            )

    # Archive
    st.markdown("---")
    with st.expander(" Past issues", expanded=False):
        _wb_archive = get_note_archive(limit=20)
        if not _wb_archive:
            st.caption("No past issues yet.")
        else:
            for _an in _wb_archive:
                _a_date = _an.get("note_date","")
                _a_hl   = _an.get("headline","—")[:80]
                _a_reg  = _an.get("regime","MIXED / TRANSITION")
                st.markdown(
                    f'<div style="display:flex;align-items:baseline;gap:10px;'
                    f'padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.06);">'
                    f'<span style="font-size:0.70rem;color:#6B7FBF;min-width:90px;font-family:monospace;">{_a_date}</span>'
                    f'{_wb_regime_chip(_a_reg)}'
                    f'<span style="font-size:0.82rem;color:#E8EEFF;flex:1;line-height:1.3;">{_a_hl}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # Admin generate button
    _wb_user = st.session_state.get("user", {})
    if _wb_user.get("is_admin") or _wb_user.get("subscription_tier") == "pro":
        st.markdown("---")
        if st.button("Generate new note now", key="wb_gen_now"):
            with st.spinner("Generating via Anthropic API…"):
                try:
                    _gen_note(force=True)
                    st.success("New note generated. Refresh to see it.")
                    st.rerun()
                except Exception as _e:
                    st.error(f"Generation failed: {_e}")

# ── Footer ────────────────────────────────────────────────────────────────────
render_footer()
