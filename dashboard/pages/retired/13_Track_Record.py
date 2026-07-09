"""
Page 13 — Pre-Earnings Signal Track Record
Shows how well the Confluence Score has historically anticipated earnings
outcomes for any ticker.

Data model:
  - Earnings dates + EPS actuals come from yfinance (fetch_earnings_dates).
  - Pre-earnings score snapshots come from the score_snapshots DB table.
  - Score history accumulates organically as users view the Ticker Deep Dive
    page — there is no background scheduler. Tickers not yet frequently
    visited will have sparse history. We communicate this plainly.

Methodology (transparent):
  - "Signal call" = score snapped 7–45 days before earnings
      score ≥ 60 → predicted beat
      score ≤ 40 → predicted miss
      40–60      → no directional call
  - "Actual result" = EPS Surprise % from yfinance
      > 0 → beat     < 0 → miss    = 0 → met

Honest limitation: small samples dominate. A 5/7 record sounds impressive;
it's statistically indistinguishable from a coin flip with p > 0.1. We say
this explicitly and encourage the user to treat it as exploratory context,
not an edge claim.
"""

import datetime as _dt
import streamlit as st

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.fetchers import fetch_earnings_dates
from utils.score_history import get_score_history

st.set_page_config(page_title="Earnings Track Record — UA", layout="wide")
render_header("Earnings Track Record")
render_sidebar_base()

render_page_header(
    "Earnings Track Record",
    "Historical model accuracy around earnings events across 80+ tickers.",
    icon="📊",
)

st.markdown("# Pre-Earnings Signal Track Record")
st.caption(
    "Compare what the Confluence Score said in the 7–45 days before past earnings events "
    "against actual EPS results. History grows as tickers are viewed on Ticker Deep Dive."
)

# ── Ticker input ──────────────────────────────────────────────────────────────
_tr_col1, _tr_col2 = st.columns([3, 1])
with _tr_col1:
    _tr_ticker = st.text_input(
        "Ticker",
        value=st.query_params.get("ticker", "AAPL"),
        max_chars=12,
        placeholder="e.g. AAPL, NVDA, XOM",
        key="tr_ticker_input",
        label_visibility="collapsed",
    ).upper().strip()
with _tr_col2:
    _tr_run = st.button("Analyze", use_container_width=True, type="primary", key="tr_run_btn")

if not _tr_ticker:
    st.info("Enter a ticker above.")
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────
STATUS_COLOR = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#6B7FBF"}

with st.spinner(f"Loading earnings history and score snapshots for {_tr_ticker}…"):
    _tr_earnings = fetch_earnings_dates(_tr_ticker)
    _tr_history  = get_score_history(_tr_ticker, days=730)

if not _tr_earnings:
    st.warning(f"No earnings data found for **{_tr_ticker}**. Check the ticker or try again later.")
    st.stop()

# ── Build snapshot lookup ─────────────────────────────────────────────────────
_tr_snap_map: dict[_dt.date, dict] = {}
for _row in _tr_history:
    try:
        _d = _dt.date.fromisoformat(_row["snapshot_date"])
        _tr_snap_map[_d] = _row
    except Exception:
        pass

_tr_past     = [e for e in _tr_earnings if e.get("reported") and e.get("eps_actual") is not None]
_tr_upcoming = [e for e in _tr_earnings if not e.get("reported")]

# ── Upcoming earnings callout ─────────────────────────────────────────────────
if _tr_upcoming:
    _up = _tr_upcoming[-1]
    _up_est = f"{_up['eps_estimate']:+.2f}" if _up.get("eps_estimate") is not None else "N/A"
    _days_to = (_up["date"] - _dt.date.today()).days if isinstance(_up["date"], _dt.date) else None
    _days_str = f" ({_days_to} days away)" if _days_to is not None and _days_to >= 0 else ""
    st.info(f"**Next earnings for {_tr_ticker}:** {_up['date']}{_days_str} · Consensus EPS est: **{_up_est}**")

# ── Match each past earnings to a pre-window snapshot ────────────────────────
_tr_matched: list[dict] = []
for _e in _tr_past:
    _earn_d = _e["date"]
    if isinstance(_earn_d, str):
        _earn_d = _dt.date.fromisoformat(_earn_d)
    _best_snap  = None
    _best_delta = None
    for _snap_d, _snap_row in _tr_snap_map.items():
        _delta = (_earn_d - _snap_d).days
        if 7 <= _delta <= 45:
            if _best_delta is None or _delta < _best_delta:
                _best_snap  = _snap_row
                _best_delta = _delta
    _tr_matched.append({
        "earnings":   _e,
        "snap":       _best_snap,
        "delta_days": _best_delta,
        "earn_date":  _earn_d,
    })

_with_data    = [r for r in _tr_matched if r["snap"] is not None]
_without_data = [r for r in _tr_matched if r["snap"] is None]

# ── Accuracy computation ──────────────────────────────────────────────────────
_n_checked     = 0
_n_correct     = 0
_n_neutral     = 0
_n_no_surprise = 0

for _r in _with_data:
    _score = _r["snap"]["score"]
    _surp  = _r["earnings"].get("surprise_pct")
    if _surp is None:
        _n_no_surprise += 1
        continue
    _n_checked += 1
    if _score >= 60:
        _pred = "bullish"
    elif _score <= 40:
        _pred = "bearish"
    else:
        _pred = "neutral"
        _n_neutral += 1
        continue
    _actual = "bullish" if _surp > 0 else "bearish"
    if _pred == _actual:
        _n_correct += 1

_n_directional = _n_checked - _n_neutral
_accuracy = (_n_correct / _n_directional * 100) if _n_directional > 0 else None

# ── Summary header ────────────────────────────────────────────────────────────
st.markdown(f"## {_tr_ticker} — Earnings Signal Track Record")

_coverage = len(_with_data)
_total_past = len(_tr_past)
_coverage_pct = _coverage / _total_past * 100 if _total_past else 0

if _total_past == 0:
    st.info("No past (reported) earnings found for this ticker.")
    st.stop()

_m1, _m2, _m3, _m4 = st.columns(4)
_m1.metric("Past Earnings Found", _total_past)
_m2.metric("Events with Score Data", f"{_coverage} ({_coverage_pct:.0f}%)")
_m3.metric("Directional Calls Made", _n_directional)
if _accuracy is not None:
    _acc_delta = "above coin-flip" if _accuracy >= 55 else "below coin-flip"
    _m4.metric("Accuracy", f"{_accuracy:.0f}%", delta=_acc_delta)
else:
    _m4.metric("Accuracy", "—")

st.caption(
    "**Methodology:** Score ≥ 60 = predicted beat · Score ≤ 40 = predicted miss · 40–60 = no call. "
    "Accuracy measured on directional calls only. **Interpret cautiously** — small samples are "
    "statistically inconclusive."
)

if _coverage == 0:
    st.warning(
        "No pre-earnings score snapshots found in the database yet for this ticker. "
        "Score history accumulates each time a user opens this ticker on Ticker Deep Dive. "
        "Visit Ticker Deep Dive regularly — especially 2–6 weeks before upcoming earnings — "
        "to start building the track record."
    )
    st.stop()

st.divider()

# ── Per-earnings event cards ──────────────────────────────────────────────────
st.markdown("### Event-by-Event Breakdown")

for _r in sorted(_with_data, key=lambda x: x["earn_date"], reverse=True):
    _e     = _r["earnings"]
    _snap  = _r["snap"]
    _delta = _r["delta_days"]
    _score = _snap["score"]
    _case  = _snap.get("case", "mixed")
    _surp  = _e.get("surprise_pct")
    _act   = _e.get("eps_actual")
    _est   = _e.get("eps_estimate")

    if _score >= 60:
        _pred_dir   = "bullish"
        _pred_label = f"▲ Bullish signal ({_score:.0f}/100)"
        _pred_color = "#00D566"
        _pred_bg    = "rgba(0,213,102,0.08)"
    elif _score <= 40:
        _pred_dir   = "bearish"
        _pred_label = f"▼ Bearish signal ({_score:.0f}/100)"
        _pred_color = "#FF4444"
        _pred_bg    = "rgba(255,68,68,0.08)"
    else:
        _pred_dir   = "neutral"
        _pred_label = f"● Mixed signals ({_score:.0f}/100)"
        _pred_color = "#6B7FBF"
        _pred_bg    = "#12151E"

    if _surp is not None:
        _surp_dir = "bullish" if _surp > 0 else ("bearish" if _surp < 0 else "neutral")
        if _surp > 0:
            _out_label = f"✅ Beat — EPS {_act:+.2f} vs est {_est:+.2f} (Surprise: +{_surp:.1f}%)"
            _out_color = "#00D566"
        elif _surp < 0:
            _out_label = f"❌ Miss — EPS {_act:+.2f} vs est {_est:+.2f} (Surprise: {_surp:.1f}%)"
            _out_color = "#FF4444"
        else:
            _out_label = f"● Met estimate — EPS {_act:+.2f}"
            _out_color = "#6B7FBF"

        if _pred_dir != "neutral":
            _matched = _pred_dir == _surp_dir
            _call_label = "✅ Correct call" if _matched else "❌ Wrong call"
            _call_color = "#00D566" if _matched else "#FF4444"
        else:
            _call_label = "— No directional call"
            _call_color = "#6B7FBF"
    else:
        _out_label = "No EPS surprise data"
        _out_color = "#9E9E8E"
        _call_label = "—"
        _call_color = "#9E9E8E"

    st.markdown(f"""
<div style="background:{_pred_bg};border:1px solid rgba(255,255,255,0.08);border-left:5px solid {_pred_color};
            border-radius:8px;padding:16px 20px;margin-bottom:12px;font-family:Inter,sans-serif;">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
        <div>
            <div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.08em;color:#6B7FBF;">
                Earnings · {_r['earn_date']}
            </div>
            <div style="font-size:1.05rem;font-weight:700;color:{_out_color};margin-top:4px;">
                {_out_label}
            </div>
        </div>
        <div style="text-align:right;">
            <div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.06em;color:#6B7FBF;">
                Signal {_delta} days before
            </div>
            <div style="font-size:0.95rem;font-weight:700;color:{_pred_color};margin-top:2px;">
                {_pred_label}
            </div>
            <div style="font-size:0.82rem;font-weight:700;color:{_call_color};margin-top:2px;">
                {_call_label}
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Events without snapshot data ─────────────────────────────────────────────
if _without_data:
    with st.expander(
        f"⚪ {len(_without_data)} past earnings event(s) with no score snapshot in the 7–45 day window"
    ):
        st.caption(
            "These events occurred before this ticker was viewed on Ticker Deep Dive, "
            "or snapshots weren't recorded in the pre-window. No call can be assessed."
        )
        for _r in sorted(_without_data, key=lambda x: x["earn_date"], reverse=True):
            _e = _r["earnings"]
            _surp = _e.get("surprise_pct")
            _act  = _e.get("eps_actual")
            _surp_str = f"+{_surp:.1f}% beat" if (_surp or 0) > 0 else (
                f"{_surp:.1f}% miss" if _surp else "no surprise data")
            _act_str = f"{_act:+.2f}" if _act is not None else "?"
            st.markdown(f"- **{_r['earn_date']}** — EPS: {_act_str} ({_surp_str}) — *no score snapshot*")

st.divider()

# ── Interpretation guidance ───────────────────────────────────────────────────
with st.expander("How to interpret this track record"):
    st.markdown("""
    **What this shows:** In the 7–45 days before each past earnings date, what was the
    Confluence Score saying? If it was ≥ 60 (bullish), it "predicted" a beat. If ≤ 40
    (bearish), it "predicted" a miss. If 40–60, no directional call was made.

    **How to use it:**
    - A consistent track record across 8+ events starts becoming meaningful
    - 4 events or fewer: indistinguishable from a coin flip, statistically speaking
    - Even with a good record: the Confluence Score is a macro signal tool, not an
      earnings-surprise predictor. Use this as one data point, not the sole signal

    **Why is coverage sometimes low?**
    Score snapshots are recorded each time a user opens Ticker Deep Dive for that ticker.
    Tickers not frequently visited may have very few past snapshots. The more often this
    ticker is opened (especially in the weeks before earnings), the better the coverage.

    **The honest caveat:**
    The Confluence Score measures macro alternative data alignment — trucking freight,
    energy prices, insider activity, credit spreads, etc. It is *not* specifically trained
    to predict EPS surprises. Some correlation may exist (macro tailwinds tend to lift
    fundamentals) but it is incidental, not causal. Don't overfit to a small sample.

    *All data from public sources. Not financial advice.*
    """)

# ── CTA back to Ticker Deep Dive ─────────────────────────────────────────────
st.markdown("")
_tdd_col, _ = st.columns([1, 3])
with _tdd_col:
    if st.button(f"Open {_tr_ticker} in Ticker Deep Dive →", use_container_width=True):
        st.query_params["ticker"] = _tr_ticker
        st.switch_page("pages/3_Ticker_Deep_Dive.py")

st.markdown("""
<div style="text-align:center;padding:16px;font-size:0.75rem;color:#9E9E8E;font-family:Inter,sans-serif;">
    Unstructured Alpha · Track record data is observational, not validated. Not financial advice.
</div>
""", unsafe_allow_html=True)
