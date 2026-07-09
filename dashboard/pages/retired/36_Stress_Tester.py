# pages/36_Stress_Tester.py
# Unstructured Alpha — Macro Scenario Stress Tester  (Pro)
#
# Lets a Pro user adjust 4 macro variables (Fed Rate, VIX, 10Y Yield, DXY)
# from their current levels and see the ESTIMATED directional impact on every
# ticker in their watchlist.
#
# METHODOLOGY (honest):
#   Each macro lever corresponds to a set of signals in the SIGNALS library.
#   When the user shifts a lever, the affected signals' z-scores shift by
#   Δvalue / std_52w. Signal scores are recomputed via the linear approximation
#   score ≈ 50 + clamp(z × 20, -50, 50). The delta from the live score is
#   the estimated signal impact. Per-ticker exposure = fraction of a ticker's
#   relevant signals that are in the affected set.
#
#   THIS IS DIRECTIONAL, NOT EXACT. The real scoring engine uses the full
#   multi-period z-score; this approximation uses only the 52w std from the
#   signals cache. Use it to understand sensitivity, not to predict precise
#   numbers.
#
# Pro-gated. Free users see the gate.

import streamlit as st

st.set_page_config(
    page_title="Stress Tester — UA",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.header import render_header, render_page_header, render_sidebar_base
from utils.theme import inject_premium_css
from utils.auth_ui import require_login
from utils.billing import get_user_tier

render_header("Stress Tester")
render_sidebar_base()
inject_premium_css()

render_page_header(
    "Macro Scenario Stress Tester",
    "Adjust macro variables from current levels and see estimated impact on your watchlist.",
    icon="🧪",
)

current_user = require_login()
user_id = current_user["id"]

# ── Pro gate ──────────────────────────────────────────────────────────────────
if get_user_tier(user_id) != "pro":
    st.markdown(
        '<div style="background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.22);'
        'border-radius:14px;padding:28px 32px;text-align:center;max-width:540px;margin:40px auto;">'
        '<div style="font-size:1.25rem;font-weight:800;color:#E8EEFF;margin-bottom:8px;">⚡ Pro Feature</div>'
        '<div style="font-size:0.88rem;color:#8892AA;margin-bottom:20px;">'
        'Stress-test your watchlist against custom macro scenarios. '
        'Adjust Fed rate, VIX, 10Y yield, and DXY to see directional score impacts '
        'across all your tickers in real time.'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if st.button("Upgrade to Pro →", type="primary"):
        st.switch_page("pages/29_Upgrade.py")
    st.stop()

# ── Load signals cache ────────────────────────────────────────────────────────
from utils.signals_cache import get_all_signal_scores
from utils.config import SIGNALS

all_sv = get_all_signal_scores()

# ── Macro driver → signal mappings ────────────────────────────────────────────
# Maps each lever to signal IDs. Signals are marked with their DIRECTION
# relative to the lever: "same" means rising lever → higher signal value,
# "inverse" means rising lever → lower signal value.
#
# Note: the signal's own `inverse` flag in config is a SEPARATE concern
# (it maps signal value to bull/bear). The driver_direction here describes
# the MECHANICAL relationship between the slider value and the raw signal data.
DRIVER_SIGNALS = {
    "fed": {
        "label": "Fed Funds Rate",
        "unit":  "%",
        "min":   0.0,
        "max":   10.0,
        "step":  0.25,
        "signals": {
            # Rising fed rate → tighter credit spreads environment (bearish for spreads)
            "hy_spread":           "inverse",  # higher rates = wider HY spreads = bearish
            "ig_credit":           "inverse",  # higher rates = IG credit headwind
            "bank_lending_standards": "same",  # higher rates → tighter standards = bearish
            "fedspeaks_hawkishness":  "same",  # hawkish fed = rising rates
        },
    },
    "vix": {
        "label": "CBOE VIX",
        "unit":  "pts",
        "min":   10.0,
        "max":   80.0,
        "step":  1.0,
        "signals": {
            "vix":                "same",       # directly tracking VIX level
            "vix_term_structure": "same",       # VIX up → term structure stressed
            "put_call_ratio":     "same",       # VIX up → fear = more puts
        },
    },
    "ten_yr": {
        "label": "10Y Treasury Yield",
        "unit":  "%",
        "min":   0.5,
        "max":   8.0,
        "step":  0.10,
        "signals": {
            "ten_year_yield":  "same",          # directly tracking 10Y
            "yield_curve":     "inverse",       # higher 10Y vs 2Y = steeper = less inverted
            "tips_breakeven":  "same",          # higher nominal yield often = higher breakeven
        },
    },
    "dxy": {
        "label": "US Dollar Index (DXY)",
        "unit":  "pts",
        "min":   85.0,
        "max":   120.0,
        "step":  0.5,
        "signals": {
            "dollar_index":    "same",          # directly tracking DXY
            "copper_gold_ratio": "inverse",     # strong dollar = bearish copper/gold ratio
        },
    },
}


def _get_current_level(driver_key: str) -> float | None:
    """
    Return the current live value for a macro lever from signals_cache.
    Uses the `current` field from the most relevant signal for that driver.
    """
    primary = {
        "fed":    "fedspeaks_hawkishness",   # no direct FEDFUNDS signal; use hawkishness proxy
        "vix":    "vix",
        "ten_yr": "ten_year_yield",
        "dxy":    "dollar_index",
    }
    sig_id = primary.get(driver_key)
    if sig_id and sig_id in all_sv:
        v = all_sv[sig_id].get("current")
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def _estimate_signal_impact(sig_id: str, delta_raw: float, direction: str) -> float:
    """
    Given a raw value shift in the macro lever and the mechanical direction,
    estimate the change in signal SCORE (0-100 scale).

    Strategy: use the signal's std_52w to convert Δvalue → Δz, then
    Δscore ≈ 20 × Δz (the slope of score ≈ 50 + 20z around z=0), bounded ±30.
    If direction == "inverse", the signal value moves opposite the lever.
    """
    sv = all_sv.get(sig_id, {})
    if sv.get("error", True):
        return 0.0

    std = sv.get("std_52w")
    if not std or std <= 0:
        return 0.0

    # Directional mapping: does lever rise → signal value rise or fall?
    signed_delta = delta_raw if direction == "same" else -delta_raw

    delta_z = signed_delta / std
    # Signal score = f(z), roughly linear near origin
    # The config's `inverse` flag means high signal value → bearish score
    cfg     = SIGNALS.get(sig_id, {})
    is_inv  = cfg.get("inverse", False)

    if is_inv:
        delta_score = -delta_z * 20  # rising value → falling score
    else:
        delta_score = delta_z * 20   # rising value → rising score

    return max(-30.0, min(30.0, delta_score))


# ── Load user's watchlist ─────────────────────────────────────────────────────
from utils import alerts_db as _wl_db
_watchlist = _wl_db.get_watchlist(user_id)
_wl_tickers = [r["ticker"] for r in _watchlist]

# Optionally allow adding extra tickers (not in watchlist) for ad hoc testing
from utils.config import TICKERS as _ALL_TICKERS

# ── Current live signal scores ────────────────────────────────────────────────
# Build a reverse map: ticker → list of signal IDs it's in relevant_tickers for
from collections import defaultdict
_ticker_signals: dict[str, list[str]] = defaultdict(list)
for sig_id, cfg in SIGNALS.items():
    for t in cfg.get("relevant_tickers", []):
        _ticker_signals[t.upper()].append(sig_id)

# For each ticker, also get its current score from top_tickers
@st.cache_data(ttl=3600, show_spinner=False, max_entries=1)
def _load_current_scores() -> dict:
    try:
        from utils.top_tickers import get_top_tickers
        result = get_top_tickers(signal_scores_hash=0)
        return {r["ticker"]: float(r.get("score", 50)) for r in result.get("all", [])}
    except Exception:
        return {}


_current_scores = _load_current_scores()

# ── UI ────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="background:rgba(124,58,237,0.06);border:1px solid rgba(124,58,237,0.15);'
    'border-radius:12px;padding:14px 20px;margin-bottom:20px;font-size:0.82rem;color:#8892AA;">'
    '⚠️ <strong style="color:#C5CCDE;">Directional estimates only</strong> — '
    'adjusting a slider shows how much the affected signals would move the Confluence Score '
    'if the macro variable were at that level. The real score recomputes from live data; '
    'this shows sensitivity, not exact predictions.'
    '</div>',
    unsafe_allow_html=True,
)

# Ticker selector
_all_tickers_sorted = sorted(set(list(_ticker_signals.keys()) + _wl_tickers))
_default_tickers    = _wl_tickers if _wl_tickers else _all_tickers_sorted[:5]

_selected_tickers = st.multiselect(
    "Tickers to stress-test:",
    options=_all_tickers_sorted,
    default=_default_tickers,
    help="Pre-populated from your watchlist. Add or remove any ticker.",
    key="stress_tickers",
)

if not _selected_tickers:
    st.info("Add at least one ticker above to run the stress test.")
    st.stop()

st.divider()

# ── Macro sliders ─────────────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.60rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;'
    'text-transform:uppercase;margin-bottom:12px;">Adjust Macro Levels</div>',
    unsafe_allow_html=True,
)

_slider_col_fed, _slider_col_vix, _slider_col_10y, _slider_col_dxy = st.columns(4)

# Sensible defaults derived from current levels (or fallback)
_defaults = {
    "fed":    _get_current_level("fed")    or 5.25,
    "vix":    _get_current_level("vix")    or 20.0,
    "ten_yr": _get_current_level("ten_yr") or 4.30,
    "dxy":    _get_current_level("dxy")    or 103.0,
}
# Clamp defaults to slider bounds
for _dk, _dv in _defaults.items():
    _cfg = DRIVER_SIGNALS[_dk]
    _defaults[_dk] = max(_cfg["min"], min(_cfg["max"], round(_dv, 2)))

with _slider_col_fed:
    st.markdown(
        '<div style="font-size:0.72rem;font-weight:600;color:#C5CCDE;">🏦 Fed Rate (%)</div>',
        unsafe_allow_html=True,
    )
    _v_fed = st.slider(
        "fed_rate_slider",
        min_value=DRIVER_SIGNALS["fed"]["min"],
        max_value=DRIVER_SIGNALS["fed"]["max"],
        value=_defaults["fed"],
        step=DRIVER_SIGNALS["fed"]["step"],
        label_visibility="collapsed",
        key="slider_fed",
    )
    _delta_fed = _v_fed - _defaults["fed"]
    if abs(_delta_fed) > 0.01:
        _dfc = "#00D566" if _delta_fed < 0 else "#FF4D6A"
        st.markdown(
            f'<span style="font-size:0.75rem;color:{_dfc};">{"▲" if _delta_fed>0 else "▼"} '
            f'{_delta_fed:+.2f}% from current</span>',
            unsafe_allow_html=True,
        )

with _slider_col_vix:
    st.markdown(
        '<div style="font-size:0.72rem;font-weight:600;color:#C5CCDE;">😱 VIX (pts)</div>',
        unsafe_allow_html=True,
    )
    _v_vix = st.slider(
        "vix_slider",
        min_value=DRIVER_SIGNALS["vix"]["min"],
        max_value=DRIVER_SIGNALS["vix"]["max"],
        value=_defaults["vix"],
        step=DRIVER_SIGNALS["vix"]["step"],
        label_visibility="collapsed",
        key="slider_vix",
    )
    _delta_vix = _v_vix - _defaults["vix"]
    if abs(_delta_vix) > 0.5:
        _dvc = "#00D566" if _delta_vix < 0 else "#FF4D6A"
        st.markdown(
            f'<span style="font-size:0.75rem;color:{_dvc};">{"▲" if _delta_vix>0 else "▼"} '
            f'{_delta_vix:+.1f} pts from current</span>',
            unsafe_allow_html=True,
        )

with _slider_col_10y:
    st.markdown(
        '<div style="font-size:0.72rem;font-weight:600;color:#C5CCDE;">📈 10Y Yield (%)</div>',
        unsafe_allow_html=True,
    )
    _v_10y = st.slider(
        "ten_yr_slider",
        min_value=DRIVER_SIGNALS["ten_yr"]["min"],
        max_value=DRIVER_SIGNALS["ten_yr"]["max"],
        value=_defaults["ten_yr"],
        step=DRIVER_SIGNALS["ten_yr"]["step"],
        label_visibility="collapsed",
        key="slider_10y",
    )
    _delta_10y = _v_10y - _defaults["ten_yr"]
    if abs(_delta_10y) > 0.05:
        _d10c = "#00D566" if _delta_10y < 0 else "#FF4D6A"
        st.markdown(
            f'<span style="font-size:0.75rem;color:{_d10c};">{"▲" if _delta_10y>0 else "▼"} '
            f'{_delta_10y:+.2f}% from current</span>',
            unsafe_allow_html=True,
        )

with _slider_col_dxy:
    st.markdown(
        '<div style="font-size:0.72rem;font-weight:600;color:#C5CCDE;">💵 DXY (pts)</div>',
        unsafe_allow_html=True,
    )
    _v_dxy = st.slider(
        "dxy_slider",
        min_value=DRIVER_SIGNALS["dxy"]["min"],
        max_value=DRIVER_SIGNALS["dxy"]["max"],
        value=_defaults["dxy"],
        step=DRIVER_SIGNALS["dxy"]["step"],
        label_visibility="collapsed",
        key="slider_dxy",
    )
    _delta_dxy = _v_dxy - _defaults["dxy"]
    if abs(_delta_dxy) > 0.3:
        _ddxc = "#00D566" if _delta_dxy < 0 else "#FF4D6A"
        st.markdown(
            f'<span style="font-size:0.75rem;color:{_ddxc};">{"▲" if _delta_dxy>0 else "▼"} '
            f'{_delta_dxy:+.1f} pts from current</span>',
            unsafe_allow_html=True,
        )

# Map slider → raw lever delta
_lever_deltas = {
    "fed":    _v_fed    - _defaults["fed"],
    "vix":    _v_vix    - _defaults["vix"],
    "ten_yr": _v_10y    - _defaults["ten_yr"],
    "dxy":    _v_dxy    - _defaults["dxy"],
}

# ── Compute signal impacts ─────────────────────────────────────────────────────
# For each (lever, signal, direction) tuple, compute estimated score change
_signal_impacts: dict[str, float] = {}
for _lever_key, _lever_delta in _lever_deltas.items():
    if abs(_lever_delta) < 1e-6:
        continue
    for _sig_id, _dir in DRIVER_SIGNALS[_lever_key]["signals"].items():
        _impact = _estimate_signal_impact(_sig_id, _lever_delta, _dir)
        _signal_impacts[_sig_id] = _signal_impacts.get(_sig_id, 0.0) + _impact


# ── Compute per-ticker estimated impact ───────────────────────────────────────
def _ticker_stress_delta(ticker: str) -> tuple[float, list[str]]:
    """
    Return (estimated_score_delta, list_of_affected_signal_names) for a ticker.
    delta = weighted average of impacted signals that appear in ticker's relevant_tickers.
    """
    t_sigs = _ticker_signals.get(ticker.upper(), [])
    if not t_sigs:
        return 0.0, []

    total_impact  = 0.0
    affected_names = []
    n_affected = 0

    for sig_id in t_sigs:
        if sig_id in _signal_impacts and abs(_signal_impacts[sig_id]) > 0.2:
            total_impact += _signal_impacts[sig_id]
            n_affected   += 1
            name = SIGNALS.get(sig_id, {}).get("name", sig_id)
            affected_names.append(name)

    if n_affected == 0:
        return 0.0, []

    # Normalize: each signal has roughly 1/n_signals weight in the overall score
    # Using a modest damping factor since signal weights are correlation-based
    n_total = max(len(t_sigs), 1)
    # Scale by fraction of ticker's signals that are affected, dampened by 0.6
    estimated_delta = total_impact * (n_affected / n_total) * 0.6

    return round(estimated_delta, 1), affected_names[:4]


st.divider()
st.markdown(
    '<div style="font-size:0.60rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;'
    'text-transform:uppercase;margin-bottom:12px;">Estimated Score Impact Under Scenario</div>',
    unsafe_allow_html=True,
)

# Show results in a grid of cards
_any_nonzero = any(
    abs(_ticker_stress_delta(t)[0]) > 0.05 for t in _selected_tickers
)

if not _any_nonzero and all(abs(d) < 1e-6 for d in _lever_deltas.values()):
    st.info("Move the sliders above to see estimated impacts.")
else:
    _cols_per_row = 4
    for _i in range(0, len(_selected_tickers), _cols_per_row):
        _chunk = _selected_tickers[_i:_i + _cols_per_row]
        _result_cols = st.columns(len(_chunk))

        for _rcol, _t in zip(_result_cols, _chunk):
            _cur_score = _current_scores.get(_t, 50.0)
            _delta, _affected = _ticker_stress_delta(_t)
            _stressed = max(0.0, min(100.0, _cur_score + _delta))
            _case_cur   = "BULL" if _cur_score >= 65 else ("BEAR" if _cur_score <= 35 else "NEUT")
            _case_str   = "BULL" if _stressed >= 65 else ("BEAR" if _stressed <= 35 else "NEUT")
            _color_cur  = "#00D566" if _case_cur == "BULL" else ("#FF4D6A" if _case_cur == "BEAR" else "#F59E0B")
            _color_str  = "#00D566" if _case_str == "BULL" else ("#FF4D6A" if _case_str == "BEAR" else "#F59E0B")

            _arrow = "▲" if _delta > 0.5 else ("▼" if _delta < -0.5 else "●")
            _dc    = "#00D566" if _delta > 0 else ("#FF4D6A" if _delta < 0 else "#8892AA")

            # Regime flip indicator
            _flip_html = ""
            if _case_str != _case_cur:
                _fclr = "#00D566" if _case_str == "BULL" else "#FF4D6A"
                _flip_html = (
                    f'<div style="font-size:0.70rem;color:{_fclr};font-weight:700;margin-top:4px;">'
                    f'⚡ Regime flip: {_case_cur} → {_case_str}</div>'
                )

            _affected_html = ""
            if _affected:
                _affected_html = (
                    f'<div style="font-size:0.60rem;color:#6B7A95;margin-top:4px;line-height:1.4;">'
                    f'Via: {", ".join(_affected[:2])}'
                    + ("…" if len(_affected) > 2 else "") +
                    f'</div>'
                )

            with _rcol:
                st.markdown(
                    f'<div style="background:rgba(18,21,30,0.8);border:1px solid #1E2535;'
                    f'border-radius:12px;padding:16px 18px;">'
                    f'<div style="font-size:0.75rem;font-weight:700;color:#C5CCDE;">{_t}</div>'
                    f'<div style="display:flex;align-items:center;gap:10px;margin:8px 0;">'
                    f'<div style="text-align:center;">'
                    f'<div style="font-size:0.55rem;color:#6B7A95;text-transform:uppercase;">Now</div>'
                    f'<div style="font-size:1.4rem;font-weight:900;color:{_color_cur};">{_cur_score:.0f}</div>'
                    f'</div>'
                    f'<div style="font-size:1.2rem;color:{_dc};font-weight:700;">{_arrow}</div>'
                    f'<div style="text-align:center;">'
                    f'<div style="font-size:0.55rem;color:#6B7A95;text-transform:uppercase;">Stress</div>'
                    f'<div style="font-size:1.4rem;font-weight:900;color:{_color_str};">{_stressed:.0f}</div>'
                    f'</div>'
                    f'</div>'
                    f'<div style="font-size:0.82rem;color:{_dc};font-weight:600;">{_arrow} {_delta:+.1f} pts</div>'
                    + _flip_html
                    + _affected_html +
                    f'</div>',
                    unsafe_allow_html=True,
                )

# ── Signal impact table ────────────────────────────────────────────────────────
if _signal_impacts:
    with st.expander("📡 Signal-level impacts (all affected signals)", expanded=False):
        _impact_rows = []
        for _sig_id, _impact in sorted(_signal_impacts.items(), key=lambda x: -abs(x[1])):
            if abs(_impact) < 0.2:
                continue
            _cfg = SIGNALS.get(_sig_id, {})
            _cur_sv = all_sv.get(_sig_id, {})
            _impact_rows.append({
                "Signal":         _cfg.get("name", _sig_id),
                "Current Score":  f'{_cur_sv.get("score", 50):.0f}/100',
                "Status":         _cur_sv.get("status", "—").capitalize(),
                "Est. Impact":    f'{_impact:+.1f} pts',
            })

        if _impact_rows:
            import pandas as _pd_st
            st.dataframe(
                _pd_st.DataFrame(_impact_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No signal impacts above threshold. Move sliders further from center.")

st.divider()
st.caption(
    "⚠️ Estimates use 52-week volatility to scale z-score shifts. "
    "Actual Confluence Scores recompute from live data and use correlation-weighted signal contributions. "
    "This tool shows directional sensitivity — move it ≥0.5% / 5 pts to see meaningful effects."
)
