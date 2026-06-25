"""
pages/19_Signal_Backtester.py
=============================
Custom Signal Combination Backtester

Build your own signal rule (e.g. "when ATA Trucking > 70 AND HY Spread < 35")
and see every historical instance since we started tracking, with forward returns
at 4 / 8 / 12 weeks for any ticker you choose.

Data source: signal_snapshots table (populated daily as users visit TDD) +
             yfinance for historical prices at each instance date.

Minimum data requirement: 5 instances to show results; otherwise shows the
current data window and an honest "not enough history yet" note.
"""

import streamlit as st

st.set_page_config(
    page_title="Signal Backtester — Unstructured Alpha",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from utils.header import render_header

render_header()

# ── Imports ───────────────────────────────────────────────────────────────────
import html as _html_mod
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import utils.db as db
from utils.config import SIGNALS

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
.block-container { padding-top: 0.5rem !important; }
.bt-card {
    background: #FAF6F0;
    border: 1px solid #DDD5C5;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 12px;
    font-family: Georgia, serif;
}
.bt-stat {
    text-align: center;
    background: #FAFAF7;
    border: 1px solid #D4C9B0;
    border-radius: 8px;
    padding: 14px 10px;
}
.bt-stat-n  { font-size: 1.8rem; font-weight: 800; color: #1A1612; font-family: Georgia, serif; }
.bt-stat-l  { font-size: 0.68rem; color: #8B7355; letter-spacing: 0.10em; font-weight: 600; margin-top: 2px; }
.bt-win-pos { color: #1B5E20; }
.bt-win-neg { color: #7B1010; }
.bt-section-hdr {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: #8B7355;
    text-transform: uppercase;
    margin-bottom: 8px;
    border-bottom: 1px solid #E0D5C5;
    padding-bottom: 4px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="font-family:Georgia,serif;margin-bottom:6px;">
    <div style="font-size:1.55rem;font-weight:800;color:#1A1612;">🔬 Custom Signal Backtester</div>
    <div style="font-size:0.85rem;color:#6B5E52;line-height:1.5;margin-top:4px;max-width:760px;">
    Build a multi-signal rule and test it against every historical instance
    in our signal database. Forward returns computed via yfinance.
    Data grows richer every day as signals are snapshotted.
    </div>
</div>
<hr style="border:none;border-top:1px solid #DDD5C5;margin:10px 0 18px;">
""", unsafe_allow_html=True)

# ── Signal metadata ───────────────────────────────────────────────────────────
_CAT_ORDER = [
    "macro", "energy", "ai_infrastructure", "nuclear",
    "financials", "healthcare", "consumer", "industrials",
]
_CAT_LABELS = {
    "macro":            "Macro / Credit / Rates",
    "energy":           "Energy Markets",
    "ai_infrastructure":"AI & Technology",
    "nuclear":          "Nuclear & Power",
    "financials":       "Financial Conditions",
    "healthcare":       "Healthcare",
    "consumer":         "Consumer",
    "industrials":      "Industrials",
}

# Build display name → signal_id mapping for the multiselect
_SIG_DISPLAY: dict[str, str] = {}  # "Signal Name (Category)" → signal_id
_SIG_BY_CAT: dict[str, list[str]] = {}
for _sid, _cfg in SIGNALS.items():
    _cat = _cfg.get("category", "macro")
    _label = f'{_cfg["name"]} [{_CAT_LABELS.get(_cat, _cat)}]'
    _SIG_DISPLAY[_label] = _sid
    _SIG_BY_CAT.setdefault(_cat, []).append(_label)

_ALL_DISPLAY_NAMES = []
for _c in _CAT_ORDER:
    _ALL_DISPLAY_NAMES.extend(sorted(_SIG_BY_CAT.get(_c, [])))
# Add any category not in order
for _lbl, _sid in _SIG_DISPLAY.items():
    if _lbl not in _ALL_DISPLAY_NAMES:
        _ALL_DISPLAY_NAMES.append(_lbl)


# ── Helper: query signal_snapshots for dates where score meets condition ───────

def _get_signal_dates(signal_id: str, condition: str, threshold: float) -> set[str]:
    """
    Return set of snapshot_date strings where the signal meets the condition.
    condition: "above" or "below"
    """
    try:
        from sqlalchemy import select, text
        snap = db.signal_snapshots
        with db.engine.connect() as conn:
            rows = conn.execute(
                select(snap.c.snapshot_date, snap.c.score)
                .where(snap.c.signal_id == signal_id)
            ).fetchall()
        result: set[str] = set()
        for snap_date, score in rows:
            if score is None:
                continue
            if condition == "above" and float(score) >= threshold:
                result.add(str(snap_date))
            elif condition == "below" and float(score) <= threshold:
                result.add(str(snap_date))
        return result
    except Exception:
        return set()


def _get_data_window() -> tuple[str | None, str | None, int]:
    """
    Return (earliest_date, latest_date, total_snapshot_rows) from signal_snapshots.
    """
    try:
        from sqlalchemy import select, func, text
        snap = db.signal_snapshots
        with db.engine.connect() as conn:
            row = conn.execute(
                select(
                    func.min(snap.c.snapshot_date),
                    func.max(snap.c.snapshot_date),
                    func.count(snap.c.id),
                )
            ).fetchone()
        if row:
            return str(row[0]) if row[0] else None, str(row[1]) if row[1] else None, int(row[2] or 0)
        return None, None, 0
    except Exception:
        return None, None, 0


def _run_backtest(
    instance_dates: list[str],
    ticker: str,
    direction: str,  # "bull" or "bear"
) -> pd.DataFrame | None:
    """
    For each instance date, fetch price and forward prices at +4w/+8w/+12w.
    Returns DataFrame with columns: date, price_entry, price_4w, price_8w,
    price_12w, ret_4w, ret_8w, ret_12w, correct_4w, correct_8w, correct_12w.
    Returns None if data unavailable.
    """
    if not instance_dates:
        return None

    try:
        import yfinance as yf

        # Determine price fetch range: earliest instance - 5 days to latest + 90 days
        sorted_dates = sorted(instance_dates)
        start_dt = (datetime.strptime(sorted_dates[0], "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
        end_dt   = (datetime.strptime(sorted_dates[-1], "%Y-%m-%d") + timedelta(days=100)).strftime("%Y-%m-%d")

        hist = yf.download(ticker.upper(), start=start_dt, end=end_dt, progress=False, auto_adjust=True)
        if hist.empty:
            return None

        # Flatten MultiIndex if present (yfinance returns (OHLCV, ticker) MultiIndex sometimes)
        if isinstance(hist.columns, pd.MultiIndex):
            hist = hist.xs(ticker.upper(), axis=1, level=1) if ticker.upper() in hist.columns.get_level_values(1) else hist
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.droplevel(1)

        close = hist["Close"] if "Close" in hist.columns else hist.iloc[:, 0]
        close.index = pd.to_datetime(close.index).tz_localize(None)

        rows = []
        for date_str in sorted_dates:
            try:
                entry_dt   = pd.Timestamp(date_str)
                entry_px   = float(close.asof(entry_dt))
                px_4w      = float(close.asof(entry_dt + timedelta(weeks=4)))
                px_8w      = float(close.asof(entry_dt + timedelta(weeks=8)))
                px_12w     = float(close.asof(entry_dt + timedelta(weeks=12)))

                if any(np.isnan(v) for v in [entry_px, px_4w, px_8w, px_12w]):
                    continue
                if entry_px <= 0:
                    continue

                ret_4w  = (px_4w  - entry_px) / entry_px
                ret_8w  = (px_8w  - entry_px) / entry_px
                ret_12w = (px_12w - entry_px) / entry_px

                if direction == "bull":
                    c4, c8, c12 = int(ret_4w > 0), int(ret_8w > 0), int(ret_12w > 0)
                else:  # bear → correct if down
                    c4, c8, c12 = int(ret_4w < 0), int(ret_8w < 0), int(ret_12w < 0)

                rows.append({
                    "date":        date_str,
                    "price_entry": round(entry_px, 2),
                    "price_4w":    round(px_4w,    2),
                    "price_8w":    round(px_8w,    2),
                    "price_12w":   round(px_12w,   2),
                    "ret_4w":      ret_4w,
                    "ret_8w":      ret_8w,
                    "ret_12w":     ret_12w,
                    "correct_4w":  c4,
                    "correct_8w":  c8,
                    "correct_12w": c12,
                })
            except Exception:
                continue

        if not rows:
            return None
        return pd.DataFrame(rows)

    except Exception:
        return None


# ── Layout: left config | right results ──────────────────────────────────────
_left, _right = st.columns([1, 1.65])

with _left:
    # ── Data window info ──────────────────────────────────────────────────────
    _early, _late, _n_rows = _get_data_window()
    if _early and _late:
        st.markdown(
            f'<div class="bt-card" style="border-left:3px solid #B8860B;">'
            f'<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.10em;'
            f'color:#B8860B;margin-bottom:4px;">SIGNAL HISTORY WINDOW</div>'
            f'<div style="font-size:0.82rem;color:#2A2420;">'
            f'{_early} → {_late}</div>'
            f'<div style="font-size:0.72rem;color:#8B7355;margin-top:2px;">'
            f'{_n_rows:,} snapshots across all signals · grows daily</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("No signal history yet — visit Ticker Deep Dive pages to start accumulating snapshots.")

    # ── Ticker input ──────────────────────────────────────────────────────────
    st.markdown('<div class="bt-section-hdr">TARGET TICKER</div>', unsafe_allow_html=True)
    ticker_input = st.text_input(
        "Ticker",
        value="NVDA",
        label_visibility="collapsed",
        placeholder="e.g. NVDA, SPY, XOM",
        max_chars=10,
    ).strip().upper()

    # ── Direction ─────────────────────────────────────────────────────────────
    st.markdown('<div class="bt-section-hdr" style="margin-top:10px;">RULE DIRECTION</div>', unsafe_allow_html=True)
    direction = st.radio(
        "direction",
        ["Bullish setup (expect price up)", "Bearish setup (expect price down)"],
        label_visibility="collapsed",
        horizontal=True,
    )
    direction_key = "bull" if "Bullish" in direction else "bear"

    # ── Signal picker ─────────────────────────────────────────────────────────
    st.markdown('<div class="bt-section-hdr" style="margin-top:10px;">SIGNAL CONDITIONS</div>', unsafe_allow_html=True)
    st.caption("Pick 1–6 signals. All conditions must be true simultaneously.")

    selected_labels = st.multiselect(
        "signals",
        options=_ALL_DISPLAY_NAMES,
        default=[
            next((lbl for lbl in _ALL_DISPLAY_NAMES if "ATA Trucking" in lbl), _ALL_DISPLAY_NAMES[0]),
            next((lbl for lbl in _ALL_DISPLAY_NAMES if "High-Yield Credit" in lbl), _ALL_DISPLAY_NAMES[1]),
        ],
        max_selections=6,
        label_visibility="collapsed",
    )

    # ── Per-signal threshold controls ────────────────────────────────────────
    signal_rules: list[dict] = []
    if selected_labels:
        st.markdown(
            '<div style="font-size:0.72rem;color:#8B7355;margin:6px 0 4px;">'
            'Set threshold for each signal (score 0–100):</div>',
            unsafe_allow_html=True,
        )
        for lbl in selected_labels:
            sid = _SIG_DISPLAY.get(lbl, "")
            if not sid:
                continue
            sig_name = SIGNALS[sid]["name"][:32]
            _cond_col, _thresh_col = st.columns([1, 2])
            with _cond_col:
                cond = st.selectbox(
                    f"cond_{sid}",
                    ["above", "below"],
                    label_visibility="collapsed",
                    key=f"cond_{sid}",
                )
            with _thresh_col:
                default_thresh = 65.0 if (cond == "above") else 35.0
                thresh = st.slider(
                    sig_name,
                    min_value=0,
                    max_value=100,
                    value=65 if cond == "above" else 35,
                    step=5,
                    key=f"thresh_{sid}",
                )
            signal_rules.append({"signal_id": sid, "condition": cond, "threshold": float(thresh)})

    # ── Run button ────────────────────────────────────────────────────────────
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    run_pressed = st.button(
        "▶ Run Backtest",
        type="primary",
        use_container_width=True,
        disabled=(not signal_rules or not ticker_input),
    )

# ── Results panel ─────────────────────────────────────────────────────────────
with _right:
    if not run_pressed:
        st.markdown("""
        <div style="text-align:center;padding:60px 20px;font-family:Georgia,serif;color:#8B7355;">
            <div style="font-size:2.5rem;margin-bottom:12px;">🔬</div>
            <div style="font-size:1.1rem;font-weight:700;color:#2A2420;margin-bottom:8px;">
                Configure your signal rule and click Run
            </div>
            <div style="font-size:0.85rem;line-height:1.65;max-width:480px;margin:0 auto;">
                Pick any combination of signals, set thresholds, choose a ticker,
                and see every historical date those conditions held — with forward
                returns to show whether the setup actually worked.
            </div>
        </div>
        """, unsafe_allow_html=True)

    else:
        if not ticker_input:
            st.warning("Enter a ticker symbol.")
        elif not signal_rules:
            st.warning("Select at least one signal.")
        else:
            with st.spinner(f"Querying signal history and fetching {ticker_input} prices…"):
                # ── Find intersection of all rule dates ───────────────────────
                date_sets: list[set[str]] = []
                for rule in signal_rules:
                    ds = _get_signal_dates(rule["signal_id"], rule["condition"], rule["threshold"])
                    date_sets.append(ds)

                if date_sets:
                    matching_dates = list(set.intersection(*date_sets))
                else:
                    matching_dates = []

                matching_dates.sort()
                n_instances = len(matching_dates)

            # ── Show rule summary ─────────────────────────────────────────────
            rule_parts = []
            for rule in signal_rules:
                sig_name = SIGNALS[rule["signal_id"]]["name"][:30]
                rule_parts.append(
                    f'<span style="font-weight:700;">{sig_name}</span> '
                    f'{rule["condition"]} <span style="font-weight:700;">{rule["threshold"]:.0f}</span>'
                )
            st.markdown(
                f'<div class="bt-card">'
                f'<div class="bt-section-hdr">RULE</div>'
                f'<div style="font-size:0.82rem;color:#2A2420;line-height:1.65;">'
                + " &nbsp;AND&nbsp; ".join(rule_parts) +
                f'</div>'
                f'<div style="font-size:0.72rem;color:#8B7355;margin-top:6px;">'
                f'Ticker: <b>{ticker_input}</b> · Direction: <b>{"BULLISH" if direction_key == "bull" else "BEARISH"}</b>'
                f' · Instances found: <b>{n_instances}</b>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if n_instances == 0:
                st.warning(
                    "No historical dates found where all conditions held simultaneously. "
                    "Try relaxing thresholds or using fewer signals."
                )
            elif n_instances < 5:
                st.info(
                    f"Only {n_instances} instance{'s' if n_instances != 1 else ''} found — "
                    "not enough for statistically meaningful results. "
                    "The signal history is still growing; check back as more data accumulates. "
                    f"Dates found: {', '.join(matching_dates)}"
                )
            else:
                # ── Run the price backtest ────────────────────────────────────
                with st.spinner(f"Fetching {ticker_input} price history…"):
                    bt_df = _run_backtest(matching_dates, ticker_input, direction_key)

                if bt_df is None or bt_df.empty:
                    st.error(
                        f"Could not fetch price history for {ticker_input}. "
                        "Check the ticker symbol and try again."
                    )
                else:
                    n_res = len(bt_df)

                    # ── Summary stat tiles ────────────────────────────────────
                    win4  = bt_df["correct_4w"].mean()  * 100
                    win8  = bt_df["correct_8w"].mean()  * 100
                    win12 = bt_df["correct_12w"].mean() * 100
                    med4  = bt_df["ret_4w"].median()  * 100
                    med8  = bt_df["ret_8w"].median()  * 100
                    med12 = bt_df["ret_12w"].median() * 100

                    def _win_cls(v: float) -> str:
                        return "bt-win-pos" if v >= 55 else ("bt-win-neg" if v <= 45 else "")

                    _s1, _s2, _s3, _s4, _s5 = st.columns(5)
                    for _col, _lbl, _val, _suffix, _cls in [
                        (_s1, "INSTANCES",  n_res,   "",   ""),
                        (_s2, "WIN RATE 4W", win4,   "%",  _win_cls(win4)),
                        (_s3, "WIN RATE 8W", win8,   "%",  _win_cls(win8)),
                        (_s4, "WIN RATE 12W",win12,  "%",  _win_cls(win12)),
                        (_s5, "MEDIAN 8W",   med8,   "%",  "bt-win-pos" if med8 > 0 else "bt-win-neg"),
                    ]:
                        with _col:
                            _fmt = f"{_val:.0f}{_suffix}" if isinstance(_val, float) else str(_val)
                            st.markdown(
                                f'<div class="bt-stat">'
                                f'<div class="bt-stat-n {_cls}">{_fmt}</div>'
                                f'<div class="bt-stat-l">{_lbl}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

                    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

                    # ── Box plots ─────────────────────────────────────────────
                    _GREEN = "#2E7D32"
                    _RED   = "#C62828"
                    _box_color = _GREEN if direction_key == "bull" else _RED

                    fig = go.Figure()
                    for _horizon, _col_name, _lbl in [
                        ("4 Weeks",  "ret_4w",  "4W"),
                        ("8 Weeks",  "ret_8w",  "8W"),
                        ("12 Weeks", "ret_12w", "12W"),
                    ]:
                        _vals = bt_df[_col_name].dropna() * 100
                        fig.add_trace(go.Box(
                            y=_vals,
                            name=_horizon,
                            boxpoints="all",
                            jitter=0.4,
                            pointpos=-1.6,
                            marker=dict(size=5, opacity=0.6, color=_box_color),
                            line=dict(color=_box_color, width=1.5),
                            fillcolor=f"{_box_color}22",
                            hovertemplate=f"<b>{_lbl}</b><br>Return: %{{y:.1f}}%<extra></extra>",
                        ))

                    fig.add_hline(
                        y=0,
                        line_dash="solid",
                        line_color="#888",
                        line_width=1,
                        annotation_text="Breakeven",
                        annotation_position="right",
                    )
                    fig.update_layout(
                        height=340,
                        margin=dict(l=0, r=0, t=28, b=0),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="#FAFAF7",
                        font=dict(family="Georgia, serif", size=12, color="#2A2420"),
                        title=dict(
                            text=f"{ticker_input} forward returns across {n_res} instances",
                            font=dict(size=13, color="#1A1612"),
                            x=0,
                        ),
                        yaxis=dict(
                            title="Return (%)",
                            gridcolor="#EDE8E0",
                            zerolinecolor="#888",
                        ),
                        showlegend=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # ── Return distribution summary ────────────────────────────
                    def _sign_html(v: float) -> str:
                        col = "#1B5E20" if v > 0 else ("#7B1010" if v < 0 else "#888")
                        sgn = "+" if v > 0 else ""
                        return f'<span style="color:{col};font-weight:700;">{sgn}{v:.1f}%</span>'

                    st.markdown(
                        f'<div class="bt-card">'
                        f'<div class="bt-section-hdr">RETURN DISTRIBUTION SUMMARY</div>'
                        f'<table style="width:100%;font-size:0.80rem;border-collapse:collapse;">'
                        f'<tr style="color:#8B7355;">'
                        f'<th style="text-align:left;padding:3px 0;">Horizon</th>'
                        f'<th style="text-align:center;">Median</th>'
                        f'<th style="text-align:center;">Mean</th>'
                        f'<th style="text-align:center;">Best</th>'
                        f'<th style="text-align:center;">Worst</th>'
                        f'<th style="text-align:center;">Win %</th>'
                        f'</tr>'
                        + "".join(
                            f'<tr style="border-top:1px solid #E8E0D4;">'
                            f'<td style="padding:4px 0;font-weight:600;">{hz}</td>'
                            f'<td style="text-align:center;">{_sign_html(bt_df[col].median()*100)}</td>'
                            f'<td style="text-align:center;">{_sign_html(bt_df[col].mean()*100)}</td>'
                            f'<td style="text-align:center;">{_sign_html(bt_df[col].max()*100)}</td>'
                            f'<td style="text-align:center;">{_sign_html(bt_df[col].min()*100)}</td>'
                            f'<td style="text-align:center;font-weight:700;color:{"#1B5E20" if bt_df[c_col].mean()*100>=55 else "#7B1010"}">'
                            f'{bt_df[c_col].mean()*100:.0f}%</td>'
                            f'</tr>'
                            for hz, col, c_col in [
                                ("4W",  "ret_4w",  "correct_4w"),
                                ("8W",  "ret_8w",  "correct_8w"),
                                ("12W", "ret_12w", "correct_12w"),
                            ]
                        ) +
                        f'</table>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # ── Instance data table ───────────────────────────────────
                    with st.expander(f"📋 All {n_res} instances (date + prices + returns)", expanded=False):
                        _disp = bt_df.copy()
                        _disp["ret_4w"]  = (_disp["ret_4w"]  * 100).round(1).astype(str) + "%"
                        _disp["ret_8w"]  = (_disp["ret_8w"]  * 100).round(1).astype(str) + "%"
                        _disp["ret_12w"] = (_disp["ret_12w"] * 100).round(1).astype(str) + "%"
                        _disp = _disp.rename(columns={
                            "date":        "Date",
                            "price_entry": "Entry $",
                            "price_4w":    "4W Price",
                            "price_8w":    "8W Price",
                            "price_12w":   "12W Price",
                            "ret_4w":      "4W Ret",
                            "ret_8w":      "8W Ret",
                            "ret_12w":     "12W Ret",
                            "correct_4w":  "✓ 4W",
                            "correct_8w":  "✓ 8W",
                            "correct_12w": "✓ 12W",
                        })
                        st.dataframe(_disp, use_container_width=True, hide_index=True)

                    # ── Honest caveats ────────────────────────────────────────
                    st.markdown(
                        f'<div style="font-size:0.70rem;color:#8B7355;font-family:\'Georgia\',serif;'
                        f'margin-top:6px;line-height:1.6;">'
                        f'⚠ Past results do not guarantee future performance. '
                        f'Signal history is based on {_early or "N/A"} → {_late or "N/A"} snapshots. '
                        f'Insufficient sample size (&lt;30 instances) reduces statistical reliability. '
                        f'These are observations, not trading recommendations.'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
