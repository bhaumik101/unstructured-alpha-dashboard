"""
Page 1 — Signal Dashboard
Clean, accessible signal library with Simple / Pro mode toggle.
Tab-based category filter. Searchable signal list.
"""

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.config import CATEGORIES, SIGNALS, TICKERS
from utils.header import render_header, render_sidebar_base, render_page_header, ticker_chips, render_data_unavailable_banner, render_footer
from utils.score_history import get_signal_flips, get_signal_trends, get_signal_streaks, compute_signal_correlation_matrix
from utils.signals_cache import get_all_signal_scores
from utils.analysis import compute_signal_confidence
from utils.theme import (
    inject_skeleton_css, skeleton_cards, source_badge, inject_premium_css,
    PLOTLY_CONFIG, render_disclaimer, render_signal_legend, render_data_freshness,
    signal_confidence_badge, chart_insight_caption,
)

def _clip(text: str, limit: int = 120) -> str:
    """
    Truncate at a WORD boundary and add an ellipsis — never mid-word.
    Fixes broken card text like "...busines." and "Known as ." that the old
    naive `desc[:120].rstrip('.') + '.'` produced by cutting at a fixed char.
    """
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        # Full text fits — keep its own terminal punctuation, else add a period.
        return text if text[-1] in ".!?" else text.rstrip(" .,;:") + "."
    cut = text[:limit]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]          # back up to the last full word
    return cut.rstrip(" .,;:") + "…"


st.set_page_config(page_title="Signal Dashboard — UA", layout="wide")
render_header("Signal Dashboard")
_signal_section = render_sidebar_base(
    page_title="Signal Dashboard",
    sections=("Signal Library", "Regime Playbook"),
    section_key="signal_dashboard_section_rail",
)

# Credits the view_signals onboarding step, which had no call site anywhere and
# so could never complete. record_once, not record: Streamlit reruns the whole
# script on every widget interaction.
try:
    from utils.instrumentation import record_once
    record_once("signal_dashboard_viewed")
except Exception:
    pass
inject_premium_css()
render_page_header(
    "Signal Dashboard",
    "47 alternative data signals across macro, commodity, credit, energy, and more.",
    icon="",
)

if _signal_section == "Signal Library":
    STATUS_COLOR = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#6B7FBF", "insufficient_data": "#6B7FBF"}
    STATUS_LABEL = {"bullish": " Bullish", "bearish": " Bearish", "neutral": " Neutral", "insufficient_data": " No Data"}
    STATUS_SYM   = {"bullish": "▲", "bearish": "▼", "neutral": "●", "insufficient_data": "○"}


    _load_ts = datetime.now().strftime("%I:%M %p")
    _hdr_col, _ref_col = st.columns([6, 1])
    with _hdr_col:
        st.markdown(
            render_data_freshness(
                source="FRED / EIA / SEC EDGAR / FINRA / yfinance",
                cadence=f"Cached up to 2 hours · computed ~{_load_ts}",
            ),
            unsafe_allow_html=True,
        )
    with _ref_col:
        if st.button("↺ Refresh", key="sd_refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ── Methodology Callout ───────────────────────────────────────────────────────
    with st.expander("How these signals work", expanded=False):
        _m_css = (
            "background:rgba(18,21,30,0.8);border:1px solid rgba(255,255,255,0.07);"
            "border-radius:10px;padding:14px 16px;height:100%;"
        )
        _m_title = (
            "font-weight:700;font-size:0.82rem;letter-spacing:0.04em;"
            "color:#E8EEFF;margin-bottom:6px;font-family:Inter,sans-serif;"
        )
        _m_body = (
            "font-size:0.78rem;color:#8892AA;line-height:1.55;font-family:Inter,sans-serif;"
        )
        _m_badge = (
            "display:inline-block;font-size:0.68rem;font-weight:600;letter-spacing:0.05em;"
            "padding:2px 7px;border-radius:4px;margin-right:4px;margin-bottom:4px;"
        )
        _mc1, _mc2, _mc3, _mc4 = st.columns(4)
        with _mc1:
            st.markdown(f"""
    <div style="{_m_css}">
      <div style="{_m_title}"> DATA SOURCES</div>
      <div style="{_m_body}">
        Signals are fetched daily from public APIs and government data releases — no scraped or
        estimated data. Each series is mapped to an official source ID so you can verify it directly.
      </div>
      <div style="margin-top:10px;">
        <span style="{_m_badge}background:rgba(0,200,224,0.12);color:#00C8E0;">FRED</span>
        <span style="{_m_badge}background:rgba(0,200,224,0.12);color:#00C8E0;">EIA</span>
        <span style="{_m_badge}background:rgba(0,200,224,0.12);color:#00C8E0;">SEC EDGAR</span>
        <span style="{_m_badge}background:rgba(0,200,224,0.12);color:#00C8E0;">FINRA</span>
        <span style="{_m_badge}background:rgba(0,200,224,0.12);color:#00C8E0;">yfinance</span>
      </div>
    </div>""", unsafe_allow_html=True)
        with _mc2:
            st.markdown(f"""
    <div style="{_m_css}">
      <div style="{_m_title}"> SCORING METHOD</div>
      <div style="{_m_body}">
        Each signal is converted to a 0–100 percentile rank within its own trailing 2-year
        distribution. Values above 65 are bullish, below 35 are bearish. This normalises
        across very different units (yield spreads, barrel counts, filing counts).
      </div>
    </div>""", unsafe_allow_html=True)
        with _mc3:
            st.markdown(f"""
    <div style="{_m_css}">
      <div style="{_m_title}"> CONFLUENCE SCORE</div>
      <div style="{_m_body}">
        The per-ticker Confluence Score is a correlation-weighted average of all {len(SIGNALS)} signals,
        where signals that historically co-move with that ticker's price get more weight.
        It is re-computed every time you load Ticker Deep Dive.
      </div>
    </div>""", unsafe_allow_html=True)
        with _mc4:
            st.markdown(f"""
    <div style="{_m_css}">
      <div style="{_m_title}">WHAT'S VALIDATED</div>
      <div style="{_m_body}">
        Signal lead-times are tested out-of-sample with Bonferroni correction for multiple
        comparisons. Many signals have <em>not</em> been validated and are marked as such.
        See the <b>Model Validation</b> page for full per-signal results.
      </div>
    </div>""", unsafe_allow_html=True)

    inject_skeleton_css()
    _sk_ph = st.empty()
    # Branded loading panel (logo, filled brand shape, a true macro fact) while
    # the 47-signal fetch runs — the heaviest wait on the highest-traffic page.
    from utils.theme import loading_splash
    _sk_ph.markdown(loading_splash(), unsafe_allow_html=True)
    all_signals = get_all_signal_scores()
    _sk_ph.empty()

    render_data_unavailable_banner(
        sum(1 for sv in all_signals.values() if sv.get("unavailable") or sv.get("error")),
        len(all_signals),
    )

    # ── Mode + Display Toggles ────────────────────────────────────────────────────
    col_mode, col_display, col_spacer = st.columns([2, 2, 3])
    with col_mode:
        mode = st.radio(
            "View mode",
            ["Simple", "Pro"],
            horizontal=True,
            index=0,
            help="Simple: plain-English signals for any investor. Pro: full z-score and correlation data.",
            key="dash_mode",
        )
    with col_display:
        _view_layout = st.radio(
            "Layout",
            ["Cards", "Heatmap"],
            horizontal=True,
            index=0,
            help="Cards: full-detail cards. Heatmap: compact color grid showing all signals at once.",
            key="dash_layout",
        )

    st.markdown("")

    # ── Category Filter — segmented pills with icons + live signal counts ─────────
    _cat_counts = {
        ck: sum(1 for sv in all_signals.values() if sv["config"].get("category") == ck)
        for ck in CATEGORIES
    }
    _cat_options = ["all"] + list(CATEGORIES.keys())

    def _cat_fmt(k: str) -> str:
        if k == "all":
            return f"All  ({len(all_signals)})"
        cat = CATEGORIES[k]
        return f"{cat['icon']} {cat['name']}  ({_cat_counts.get(k, 0)})"

    _cat_sel = st.segmented_control(
        "Category",
        options=_cat_options,
        format_func=_cat_fmt,
        default="all",
        key="dash_cat_sc",
        label_visibility="collapsed",
    )
    selected_cat = None if (_cat_sel is None or _cat_sel == "all") else _cat_sel

    # ── Search ────────────────────────────────────────────────────────────────────
    search_term = st.text_input(
        "Search signals",
        placeholder="e.g. trucking, uranium, yield…",
        label_visibility="visible",
        key="dash_search",
    ).strip().lower()

    # ── Filtered Signals — sorted by significance (most bullish/bearish first) ────
    visible_signals = sorted(
        [
            (sid, sv) for sid, sv in all_signals.items()
            if (selected_cat is None or sv["config"].get("category") == selected_cat)
            and (not search_term or search_term in sv["config"]["name"].lower()
                 or search_term in sv["config"].get("description", "").lower())
        ],
        key=lambda x: abs(x[1].get("score", 50) - 50),
        reverse=True,
    )

    # ── Summary Banner ────────────────────────────────────────────────────────────
    _vals     = [sv for _, sv in visible_signals]
    bull_n    = sum(1 for v in _vals if v.get("status") == "bullish")
    bear_n    = sum(1 for v in _vals if v.get("status") == "bearish")
    neut_n    = sum(1 for v in _vals if v.get("status") == "neutral")
    total_n   = len(_vals)

    scope_lbl = (cat_sel_idx if selected_cat else "All Categories")
    if search_term:
        scope_lbl = f'Search: "{search_term}"'

    # Overall market temperature
    if total_n > 0:
        bull_pct = bull_n / total_n * 100
        temp_color = "#00D566" if bull_pct >= 60 else ("#FF4444" if bull_pct <= 35 else "#6B7FBF")
        temp_label = "Risk-On " if bull_pct >= 60 else ("Risk-Off " if bull_pct <= 35 else "Mixed ")
    else:
        temp_color, temp_label = "#6B7FBF", "No Data"

    st.markdown(f"""
    <div class="ua-slide-up" style="background:rgba(18,21,30,0.78);border-radius:14px;padding:18px 22px;
                border:1px solid rgba(255,255,255,0.08);border-left:5px solid {temp_color};
                backdrop-filter:blur(18px) saturate(150%);-webkit-backdrop-filter:blur(18px) saturate(150%);
                box-shadow:0 4px 24px rgba(0,0,0,0.4),inset 0 1px 0 rgba(255,255,255,0.04);
                font-family:Inter,sans-serif;margin-bottom:16px;">
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
            <div>
                <div style="display:flex;align-items:center;gap:6px;font-size:0.60rem;color:#8892AA;
                            letter-spacing:0.12em;text-transform:uppercase;margin-bottom:6px;">
                    <span class="ua-pulse-dot"></span>MARKET TEMPERATURE — {scope_lbl}
                </div>
                <div style="font-size:1.5rem;font-weight:800;color:{temp_color};margin-top:2px;
                            letter-spacing:-0.3px;">{temp_label}</div>
            </div>
            <div style="display:flex;gap:24px;text-align:center;">
                <div>
                    <div class="ua-number-in" style="font-size:1.8rem;font-weight:800;color:#00D566;
                                 letter-spacing:-1px;line-height:1.0;text-shadow:0 0 20px rgba(0,213,102,0.3);">{bull_n}</div>
                    <div style="font-size:0.60rem;color:#00D566;letter-spacing:0.10em;font-weight:700;margin-top:3px;">BULLISH</div>
                </div>
                <div style="width:1px;background:rgba(255,255,255,0.06);"></div>
                <div>
                    <div class="ua-number-in" style="font-size:1.8rem;font-weight:800;color:#FF4444;
                                 letter-spacing:-1px;line-height:1.0;text-shadow:0 0 20px rgba(255,68,68,0.25);">{bear_n}</div>
                    <div style="font-size:0.60rem;color:#FF4444;letter-spacing:0.10em;font-weight:700;margin-top:3px;">BEARISH</div>
                </div>
                <div style="width:1px;background:rgba(255,255,255,0.06);"></div>
                <div>
                    <div class="ua-number-in" style="font-size:1.8rem;font-weight:800;color:#6B7FBF;
                                 letter-spacing:-1px;line-height:1.0;">{neut_n}</div>
                    <div style="font-size:0.60rem;color:#6B7FBF;letter-spacing:0.10em;font-weight:700;margin-top:3px;">NEUTRAL</div>
                </div>
                <div style="width:1px;background:rgba(255,255,255,0.06);"></div>
                <div>
                    <div class="ua-number-in" style="font-size:1.8rem;font-weight:800;color:#E8EEFF;
                                 letter-spacing:-1px;line-height:1.0;">{total_n}</div>
                    <div style="font-size:0.60rem;color:#8892AA;letter-spacing:0.10em;font-weight:700;margin-top:3px;">TOTAL</div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Signal Flips (since yesterday) ───────────────────────────────────────────
    try:
        _flips = get_signal_flips(days_back=1)
        if _flips:
            _FLIP_COLOR = {
                "bullish":  "#00D566",
                "bearish":  "#FF4444",
                "neutral":  "#6B7FBF",
                "insufficient_data": "#6B7FBF",
            }
            _FLIP_SYM = {"bullish": "▲", "bearish": "▼", "neutral": "●", "insufficient_data": "○"}

            st.markdown(
                f'<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;'
                f'color:#6B7FBF;margin-bottom:4px;font-family:Inter,sans-serif;">'
                f' {len(_flips)} signal{"s" if len(_flips) != 1 else ""} changed status since yesterday'
                f'</div>',
                unsafe_allow_html=True,
            )
            _flip_cols = st.columns(min(len(_flips), 4))
            for _fi, _flip in enumerate(_flips[:4]):
                _fsid   = _flip["signal_id"]
                _fname  = SIGNALS.get(_fsid, {}).get("name", _fsid)
                _from_c = _FLIP_COLOR.get(_flip["from_status"], "#8892AA")
                _to_c   = _FLIP_COLOR.get(_flip["to_status"],   "#8892AA")
                _from_s = _FLIP_SYM.get(_flip["from_status"],  "●")
                _to_s   = _FLIP_SYM.get(_flip["to_status"],    "●")
                _to_lbl = _flip["to_status"].replace("_", " ").title()
                with _flip_cols[_fi]:
                    st.markdown(
                        f'<div class="ua-pop-in" style="background:rgba(18,21,30,0.80);border-radius:8px;padding:10px 12px;'
                        f'border:1px solid rgba(255,255,255,0.08);border-top:3px solid {_to_c};'
                        f'backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);'
                        f'margin-bottom:8px;font-family:Inter,sans-serif;">'
                        f'<div style="font-size:0.75rem;font-weight:700;color:#E8EEFF;'
                        f'line-height:1.3;margin-bottom:4px;">{_fname[:36]}</div>'
                        f'<div style="font-size:0.80rem;">'
                        f'<span style="color:{_from_c};">{_from_s} {_flip["from_status"].title()}</span>'
                        f' <span style="color:#8892AA;">→</span> '
                        f'<span style="color:{_to_c};font-weight:700;">{_to_s} {_to_lbl}</span>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            if len(_flips) > 4:
                st.caption(f"+ {len(_flips) - 4} more flips — see Today's Brief for the full list.")
            st.markdown("")
    except Exception:
        pass  # Never crash the dashboard if flip history isn't available yet

    # ── Flip Lookup (last 60 days) — used by cards to show "changed X days ago" ──
    # Separate from the banner above, which only looks back 1 day for the flip
    # announcement strip. This wider window feeds each card's footer line.
    _flip_lookup: dict[str, int] = {}  # signal_id → days since last directional flip
    try:
        _flips_60 = get_signal_flips(days_back=60)
        for _f60 in _flips_60:
            _fsid60 = _f60["signal_id"]
            if _fsid60 not in _flip_lookup:   # list comes newest-first; keep first hit
                try:
                    _fd60 = datetime.strptime(_f60["to_date"], "%Y-%m-%d")
                    _flip_lookup[_fsid60] = (datetime.now() - _fd60).days
                except Exception:
                    pass
    except Exception:
        pass

    # 7-day trend lookup: signal_id → {"trend": "up"|"down"|"flat"|"new", "delta": float}
    _trend_lookup: dict[str, dict] = {}
    try:
        _trend_lookup = get_signal_trends(days_back=7)
    except Exception:
        pass

    # Signal fatigue streaks: signal_id → {"label": str, "days": int, ...}
    _streak_lookup: dict[str, dict] = {}
    try:
        _streak_lookup = get_signal_streaks(days_back=90)
    except Exception:
        pass

    # ── Live Pulse CSS ────────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    @keyframes ua-sd-pulse {
      0%   { box-shadow: 0 0 0 0 rgba(255,255,255,0.6); }
      60%  { box-shadow: 0 0 0 6px rgba(255,255,255,0); }
      100% { box-shadow: 0 0 0 0 rgba(255,255,255,0); }
    }
    .ua-sd-live-dot {
      display: inline-block;
      width: 7px; height: 7px;
      border-radius: 50%;
      vertical-align: middle;
      margin-right: 5px;
      animation: ua-sd-pulse 1.5s ease-in-out infinite;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Theme Context Banner ──────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:rgba(0,200,224,0.05);border-radius:8px;padding:14px 20px;
                border-left:5px solid #E8EEFF;margin-bottom:14px;font-family:Inter,sans-serif;">
        <div style="font-size:0.75rem;color:#00C8E0;font-weight:700;letter-spacing:0.08em;
                    text-transform:uppercase;margin-bottom:4px;">
            What This Dashboard Tracks
        </div>
        <div style="font-size:0.82rem;color:#B8C0D4;line-height:1.6;">
            Core themes: <b>Natural Gas · Copper · AI Infrastructure · Quantum Computing</b>
            — the four forces reshaping the global economy.
            But every signal here also <b>flows through to mainstream stocks</b>:
            rising copper lifts industrials, energy capex flows move S&amp;P 500 utilities,
            AI power demand reshapes the whole grid sector.
            Any ticker in the Screener or Deep Dive shows you exactly how these forces hit it.
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not visible_signals:
        st.info("No signals match your filter. Try broadening the category or search term.")
        st.stop()

    # ── Score legend ──────────────────────────────────────────────────────────────
    st.html(render_signal_legend())

    # ── Heatmap View (alternative to card grid) ───────────────────────────────────
    # Shows every signal as a small colored cell — great for at-a-glance scanning
    # across all signals at once, similar to a Bloomberg heat map or Finviz's
    # sector overview. Score intensity drives the shade depth (same palette as cards).
    if _view_layout == "Heatmap":
        try:
            _hm_cells = ""
            for _hm_id, _hm_sv in visible_signals:
                _hm_status = _hm_sv.get("status", "neutral")
                _hm_score  = _hm_sv.get("score", 50)
                _hm_name   = _hm_sv["config"]["name"][:28]
                # Background + text color by score intensity
                if _hm_status == "bullish":
                    _strength = (_hm_score - 60) / 40  # 0.0 to 1.0
                    _g = int(94 + _strength * 100)
                    _hm_bg    = f"rgb(15,{_g},20)"
                    _hm_fc    = "#0F1118"
                    _hm_bdr   = "#00D566"
                elif _hm_status == "bearish":
                    _strength = (40 - _hm_score) / 40
                    _r = int(100 + _strength * 100)
                    _hm_bg    = f"rgb({_r},10,10)"
                    _hm_fc    = "#0F1118"
                    _hm_bdr   = "#FF2222"
                else:
                    _hm_bg    = "#0B0D12"
                    _hm_fc    = "#8892AA"
                    _hm_bdr   = "rgba(255,255,255,0.08)"

                _hm_cells += (
                    f'<div title="{_hm_sv["config"]["name"]} — {_hm_score:.0f}/100" '
                    f'style="background:{_hm_bg};border:1px solid {_hm_bdr};border-radius:5px;'
                    f'padding:7px 10px;min-width:130px;flex:1;cursor:default;'
                    f'font-family:Inter,sans-serif;">'
                    f'<div style="font-size:0.70rem;color:{_hm_fc};opacity:0.85;line-height:1.3;'
                    f'margin-bottom:3px;">{_hm_name}</div>'
                    f'<div style="font-size:1.1rem;font-weight:700;color:{_hm_fc};">{_hm_score:.0f}</div>'
                    f'</div>'
                )

            st.markdown(
                f'<div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:16px;">'
                f'{_hm_cells}'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.caption("Each cell: score/100. Darker = stronger conviction. Hover for full name.")
        except Exception as _hm_err:
            st.warning(f"Heatmap render failed: {_hm_err}")
        st.stop()

    # ── Signal Cards ──────────────────────────────────────────────────────────────
    COLS = 3
    for row_start in range(0, len(visible_signals), COLS):
        row_items = visible_signals[row_start : row_start + COLS]
        cols = st.columns(COLS)

        for col, (sig_id, sv) in zip(cols, row_items):
            cfg    = sv["config"]
            status = sv.get("status", "neutral")
            score  = sv.get("score", 50)
            dev    = sv.get("deviation_pct", 0)
            trend  = sv.get("trend_4w_pct", 0)
            cat    = CATEGORIES.get(cfg.get("category", "macro"), {})
            sym    = STATUS_SYM.get(status, "●")
            lbl    = STATUS_LABEL.get(status, "●")
            trend_arrow = "↑" if trend > 1 else ("↓" if trend < -1 else "→")

            # Score-intensity border color: deeper shade = stronger conviction
            # Bullish: 60-69 = #00D566, 70-79 = #00A847, 80+ = #34D399
            # Bearish: 31-40 = #FF4444, 21-30 = #CC3333, ≤20 = #FF2222
            if status == "bullish":
                border = "#34D399" if score >= 80 else ("#00A847" if score >= 70 else "#00D566")
            elif status == "bearish":
                border = "#FF2222" if score <= 20 else ("#CC3333" if score <= 30 else "#FF4444")
            else:
                border = STATUS_COLOR.get(status, "#8892AA")

            # Pre-compute border RGB components for gradient backgrounds
            _bc_r = int(border[1:3], 16)
            _bc_g = int(border[3:5], 16)
            _bc_b = int(border[5:7], 16)

            # "Changed X days ago" footer — from the 60-day flip lookup
            _days_flipped = _flip_lookup.get(sig_id)
            if _days_flipped is not None:
                if _days_flipped == 0:
                    _flip_note = " changed today"
                elif _days_flipped == 1:
                    _flip_note = " changed yesterday"
                else:
                    _flip_note = f"↺ changed {_days_flipped}d ago"
            else:
                _flip_note = None

            # 7-day trend badge
            _trend_data  = _trend_lookup.get(sig_id, {})
            _trend_dir   = _trend_data.get("trend", "new")
            _trend_delta = _trend_data.get("delta", 0.0)
            if _trend_dir == "up":
                _trend_badge = f'<span style="color:#00D566;font-size:0.68rem;font-weight:700;" title="Score up {_trend_delta:+.1f} pts vs 7 days ago">▲ +{_trend_delta:.0f}</span>'
            elif _trend_dir == "down":
                _trend_badge = f'<span style="color:#FF4444;font-size:0.68rem;font-weight:700;" title="Score down {_trend_delta:.1f} pts vs 7 days ago">▼ {_trend_delta:.0f}</span>'
            elif _trend_dir == "flat":
                _trend_badge = f'<span style="color:#6B7FBF;font-size:0.68rem;" title="Score unchanged vs 7 days ago">→ flat</span>'
            else:
                _trend_badge = ""  # "new" — no prior history yet

            # Signal fatigue streak badge
            _streak = _streak_lookup.get(sig_id, {})
            _streak_label = _streak.get("label", "")
            _streak_days  = _streak.get("days", 0)
            # Only show fatigue for Extended/Exhausted — Fresh/Established add noise
            _fatigue_html = (
                f'<span style="font-size:0.64rem;color:#6B7FBF;margin-left:6px;" '
                f'title="{_streak_days} days in current status">{_streak_label}</span>'
                if _streak_label.startswith(("", "")) else
                f'<span style="font-size:0.64rem;color:#00D566;margin-left:6px;" '
                f'title="{_streak_days} days in current status">{_streak_label}</span>'
                if _streak_label.startswith("") else ""
            )

            # Live pulse indicator — shown for signals that flipped today or yesterday
            _is_live = _days_flipped is not None and _days_flipped <= 1
            _pulse_dot = (
                f'<span class="ua-sd-live-dot" style="background:rgba({_bc_r},{_bc_g},{_bc_b},1);'
                f'box-shadow:0 0 5px rgba({_bc_r},{_bc_g},{_bc_b},0.8);"></span>'
                if _is_live else ""
            )

            with col:
                try:
                    if mode == "Simple":
                        # ── SIMPLE card: big status + plain English + confidence ──
                        _dev_abs   = abs(dev) if dev == dev else 0.0   # guard NaN
                        _lbl_text  = lbl.split(" ", 1)[-1] if " " in lbl else lbl
                        _cat_icon  = cat.get("icon", "")
                        _cat_name  = cat.get("name", "")
                        _sig_name  = cfg["name"]  # full name; CSS clamps to 2 lines w/ ellipsis

                        # Compute confidence level from z-score, momentum, PCS
                        _conf = compute_signal_confidence(sv, pcs=sv.get("pcs"))
                        _conf_badge = signal_confidence_badge(_conf["level"])

                        # Better "what this means" note — uses signal description
                        # if available, otherwise falls back to deviation phrasing
                        _sig_desc = cfg.get("description", "")
                        if status == "bullish":
                            if _sig_desc:
                                _bottom_note = (
                                    f"<b>Bullish:</b> {_clip(_sig_desc, 120)} "
                                    f"Currently <b>{_dev_abs:.0f}% above</b> its 52-week average."
                                )
                            else:
                                _bottom_note = f"Running <b>{_dev_abs:.0f}% above</b> its 52-week average — positive signal."
                        elif status == "bearish":
                            if _sig_desc:
                                _bottom_note = (
                                    f"<b>Bearish:</b> {_clip(_sig_desc, 120)} "
                                    f"Currently <b>{_dev_abs:.0f}% below</b> its 52-week average."
                                )
                            else:
                                _bottom_note = f"Running <b>{_dev_abs:.0f}% below</b> its 52-week average — negative signal."
                        elif status == "insufficient_data":
                            _bottom_note = "Not enough data yet — check back as more history accumulates."
                        else:
                            _bottom_note = (
                                (f"{_clip(_sig_desc, 100)} " if _sig_desc else "")
                                + "Within normal range — no clear directional edge right now."
                            )

                        _lag_weeks = cfg.get("lag_weeks", 0)
                        _lag_html  = (
                            f"<br><span style='color:#6B7FBF;font-size:0.70rem;'>"
                            f"~{_lag_weeks}w lead time to price</span>"
                            if _lag_weeks > 0 else ""
                        )

                        _flip_html = (
                            f'<div style="font-size:0.65rem;color:#6B7FBF;margin-top:5px;'
                            f'border-top:1px solid rgba(255,255,255,0.06);padding-top:4px;">{_flip_note}</div>'
                            if _flip_note else ""
                        )
                        _src_badge = source_badge(cfg.get("source", ""), cfg.get("series_id", ""))
                        _cat_color = cat.get("color", "#6B7FBF")
                        _cat_cr, _cat_cg, _cat_cb = int(_cat_color[1:3], 16), int(_cat_color[3:5], 16), int(_cat_color[5:7], 16)
                        st.markdown(
                            f'<div style="background:linear-gradient(180deg,'
                            f'rgba({_bc_r},{_bc_g},{_bc_b},0.10) 0%,rgba(18,21,30,0.82) 44%);'
                            f'border-radius:12px;padding:14px 16px;'
                            f'border:1px solid rgba(255,255,255,0.08);border-top:2px solid {border};'
                            f'margin-bottom:10px;font-family:Inter,sans-serif;'
                            f'backdrop-filter:blur(12px) saturate(150%);'
                            f'-webkit-backdrop-filter:blur(12px) saturate(150%);'
                            f'box-shadow:0 4px 20px rgba(0,0,0,0.30);'
                            f'transition:all 0.18s cubic-bezier(0.4,0,0.2,1);">'
                            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;'
                            f'margin-bottom:8px;">'
                            f'<div title="{_sig_name}" style="font-size:0.80rem;font-weight:700;color:#E8EEFF;line-height:1.3;'
                            f'flex:1;letter-spacing:-0.1px;overflow:hidden;display:-webkit-box;'
                            f'-webkit-line-clamp:2;-webkit-box-orient:vertical;">{_pulse_dot}{_sig_name}</div>'
                            f'<div style="text-align:right;margin-left:8px;flex-shrink:0;">'
                            f'<div style="font-size:0.80rem;font-weight:800;color:{border};'
                            f'background:rgba({_bc_r},{_bc_g},{_bc_b},0.12);'
                            f'border:1px solid rgba({_bc_r},{_bc_g},{_bc_b},0.25);'
                            f'border-radius:6px;padding:2px 8px;white-space:nowrap;'
                            f'letter-spacing:0.02em;">{sym} {_lbl_text}</div>'
                            f'<div style="display:flex;align-items:center;justify-content:flex-end;'
                            f'gap:4px;margin-top:4px;">'
                            f'<div style="font-size:0.64rem;color:{border};opacity:0.80;'
                            f'font-weight:600;letter-spacing:0.02em;">{score:.0f}/100</div>'
                            f'{_conf_badge}'
                            f'</div>'
                            f'</div>'
                            f'</div>'
                            f'<div style="font-size:0.77rem;color:#B8C0D4;line-height:1.55;margin-bottom:8px;">'
                            f'{_bottom_note}{_lag_html}'
                            f'</div>'
                            f'<div style="display:flex;justify-content:space-between;align-items:center;'
                            f'flex-wrap:wrap;gap:4px;">'
                            f'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
                            f'<span style="font-size:0.62rem;'
                            f'background:rgba({_cat_cr},{_cat_cg},{_cat_cb},0.12);'
                            f'color:rgba({_cat_cr},{_cat_cg},{_cat_cb},1);'
                            f'border:1px solid rgba({_cat_cr},{_cat_cg},{_cat_cb},0.28);'
                            f'border-radius:8px;padding:1px 7px;font-weight:600;white-space:nowrap;">'
                            f'{_cat_icon} {_cat_name}</span>'
                            f'{_fatigue_html}'
                            f'{_src_badge}'
                            f'</div>'
                            f'<div style="font-size:0.68rem;">{_trend_badge}</div>'
                            f'</div>'
                            f'{_flip_html}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                    else:
                        # ── PRO card: full metrics ───────────────────────────────
                        z_score  = sv.get("z_score", 0.0)
                        pct_rank = sv.get("percentile", 50.0)
                        _dev_fmt = f"{dev:+.1f}" if dev == dev else "n/a"
                        _z_fmt   = f"{z_score:.1f}" if z_score == z_score else "n/a"
                        _trend_fmt = f"{trend:+.1f}" if trend == trend else "n/a"
                        _cat_icon  = cat.get("icon", "")
                        _cat_name  = cat.get("name", "").upper()
                        _pro_conf  = compute_signal_confidence(sv, pcs=sv.get("pcs"))
                        _pro_conf_badge = signal_confidence_badge(_pro_conf["level"])

                        _pro_flip_html = (
                            f'<div style="font-size:0.67rem;color:#6B7FBF;margin-top:6px;'
                            f'border-top:1px solid rgba(255,255,255,0.08);padding-top:4px;">{_flip_note}</div>'
                            if _flip_note else ""
                        )
                        st.markdown(
                            f'<div style="background:linear-gradient(180deg,'
                            f'rgba({_bc_r},{_bc_g},{_bc_b},0.10) 0%,rgba(18,21,30,0.82) 44%);'
                            f'border-radius:12px;padding:14px 16px;'
                            f'border:1px solid rgba(255,255,255,0.08);border-top:2px solid {border};'
                            f'backdrop-filter:blur(12px) saturate(150%);'
                            f'-webkit-backdrop-filter:blur(12px) saturate(150%);'
                            f'box-shadow:0 4px 20px rgba(0,0,0,0.30);'
                            f'margin-bottom:10px;font-family:Inter,sans-serif;min-height:140px;">'
                            f'<div style="font-size:0.66rem;letter-spacing:0.03em;margin-bottom:2px;">'
                            f'<span style="background:rgba({_bc_r},{_bc_g},{_bc_b},0.12);'
                            f'color:rgba({_bc_r},{_bc_g},{_bc_b},1);'
                            f'border:1px solid rgba({_bc_r},{_bc_g},{_bc_b},0.28);'
                            f'border-radius:6px;padding:1px 6px;font-weight:600;">'
                            f'{_cat_icon} {_cat_name}</span>'
                            f'<span style="color:#6B7FBF;margin-left:6px;">PCS {cfg["pcs"]}/10</span></div>'
                            f'<div title="{cfg["name"]}" style="font-weight:700;font-size:0.88rem;color:#E8EEFF;margin-bottom:8px;line-height:1.3;'
                            f'overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;">'
                            f'{_pulse_dot}{cfg["name"]}</div>'
                            f'<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">'
                            f'<div><div style="display:flex;align-items:center;gap:8px;">'
                            f'<div style="font-size:1.6rem;font-weight:700;color:{border};">{sym} {score:.0f}</div>'
                            f'<div style="display:flex;flex-direction:column;gap:3px;">'
                            f'<span style="font-size:0.75rem;">{_trend_badge}</span>'
                            f'{_pro_conf_badge}'
                            f'</div>'
                            f'</div>'
                            f'<div style="font-size:0.65rem;color:#8892AA;">score/100 · 7d trend · confidence</div></div>'
                            f'<div style="font-size:0.76rem;color:#B8C0D4;line-height:1.7;">'
                            f'<div>Dev: <b>{_dev_fmt}%</b> vs 52w</div>'
                            f'<div>Z-score: <b>{_z_fmt}σ</b> · P{pct_rank:.0f}</div>'
                            f'<div>Trend: {trend_arrow} {_trend_fmt}% / 4w · Lead ~{cfg.get("lag_weeks", 0)}w{("  " + _streak_label) if _streak_label else ""}</div>'
                            f'</div></div>'
                            f'{_pro_flip_html}'
                            f'<div style="margin-top:8px;">'
                            f'{source_badge(cfg.get("source",""), cfg.get("series_id",""))}'
                            f'</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                except Exception as _card_err:
                    st.warning(f"Could not render card for **{cfg.get('name', sig_id)}**: {_card_err}")

                # Expander shows in both modes
                with st.expander("Details & chart"):
                    if mode == "Simple":
                        st.markdown(f"**What it is:** {cfg.get('description', '')}")
                        st.markdown(f"**Why it matters:** {cfg.get('causal_mechanism', '')}")
                        cases = cfg.get("documented_cases", [])
                        if cases:
                            st.markdown("**Historical examples:**")
                            for c in cases:
                                st.caption(f"→ {c}")
                    else:
                        st.markdown(f"**{cfg['name']}**")
                        st.caption(cfg.get("description", ""))
                        st.markdown(f"**Causal mechanism:** {cfg.get('causal_mechanism', '')}")
                        st.markdown(f"""
    | Metric | Value |
    |---|---|
    | Current | {sv.get('current', float('nan')):.3g} {cfg.get('unit','')} |
    | 52w avg | {sv.get('mean_52w', float('nan')):.3g} |
    | Z-score | {sv.get('z_score', 0):.2f}σ |
    | Percentile | {sv.get('percentile', 50):.0f}th |
    | PCS | {cfg['pcs']}/10 |
    | Lead time | ~{cfg.get('lag_weeks', 0)} weeks |
    """)
                        cases = cfg.get("documented_cases", [])
                        if cases:
                            st.markdown("**Historical precedents:**")
                            for c in cases:
                                st.markdown(f"- {c}")

                    # Sparkline — both modes
                    data = sv.get("data", pd.Series(dtype=float))
                    if not data.empty and len(data) > 4:
                        _r = int(border[1:3], 16)
                        _g = int(border[3:5], 16)
                        _b = int(border[5:7], 16)
                        spark = go.Figure(go.Scatter(
                            x=data.index[-104:],
                            y=data.values[-104:],
                            mode="lines",
                            line=dict(color=border, width=2),
                            fill="tozeroy",
                            fillcolor=f"rgba({_r},{_g},{_b},0.09)",
                        ))
                        spark.add_hline(
                            y=float(data.tail(104).mean()),
                            line_dash="dash", line_color="#8892AA",
                            annotation_text="2Y avg", annotation_font_size=9,
                        )
                        spark.update_layout(
                            height=140, margin=dict(l=0, r=0, t=8, b=0),
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0F1118",
                            xaxis=dict(showgrid=False, showticklabels=False),
                            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)",
                                       tickfont=dict(size=8, color="#8892AA")),
                            showlegend=False,
                        )
                        st.plotly_chart(spark, use_container_width=True, config=PLOTLY_CONFIG, key=f"spark_{sig_id}_{mode}", theme=None)

                        # Insight caption below the sparkline
                        _cur_val  = sv.get("current", float("nan"))
                        _mean_val = sv.get("mean_52w", float("nan"))
                        _unit     = cfg.get("unit", "")
                        _cur_str  = f"{_cur_val:.3g} {_unit}".strip() if _cur_val == _cur_val else "n/a"
                        _mean_str = f"{_mean_val:.3g} {_unit}".strip() if _mean_val == _mean_val else "n/a"
                        if status == "bullish":
                            _spark_caption = (
                                f"Current: <b>{_cur_str}</b> vs 52w avg {_mean_str} — "
                                f"elevated reading supports the bullish read. "
                                f"Trend is {trend_arrow} over 4 weeks."
                            )
                        elif status == "bearish":
                            _spark_caption = (
                                f"Current: <b>{_cur_str}</b> vs 52w avg {_mean_str} — "
                                f"depressed reading supports the bearish read. "
                                f"Trend is {trend_arrow} over 4 weeks."
                            )
                        else:
                            _spark_caption = (
                                f"Current: <b>{_cur_str}</b> vs 52w avg {_mean_str} — "
                                f"within normal range. No strong directional signal yet."
                            )
                        st.markdown(
                            chart_insight_caption(_spark_caption, icon="", muted=True),
                            unsafe_allow_html=True,
                        )

                    # Ticker chips
                    rel_tickers = cfg.get("relevant_tickers", [])[:6]
                    if rel_tickers:
                        st.caption("Related tickers (click to open Deep Dive):")
                        ticker_chips(rel_tickers, key_prefix=f"sd_{sig_id}")

    st.divider()

    # ── Signal Insight Callout ────────────────────────────────────────────────────
    # Plain-English synthesis of the current bull/bear distribution
    if total_n > 0:
        _bull_pct_int = int(round(bull_pct))
        if bull_pct >= 60:
            _insight_border = "#00D566"
            _insight_icon = ""
            _insight_headline = "The macro backdrop is risk-on."
            _insight_body = (
                f"<b>{bull_n} of {total_n} signals</b> are bullish right now ({_bull_pct_int}%). "
                "Broad agreement across macro, commodity, and credit indicators often precedes "
                "sustained upside in cyclical sectors. Tickers with high Confluence Scores "
                "historically outperform in this regime — check Ticker Deep Dive for your names."
            )
        elif bull_pct <= 35:
            _insight_border = "#FF4444"
            _insight_icon = ""
            _insight_headline = "The macro backdrop is risk-off."
            _bear_pct_int = int(round(bear_n / total_n * 100))
            _insight_body = (
                f"<b>{bear_n} of {total_n} signals</b> are bearish right now ({_bear_pct_int}%). "
                "Broad bearish agreement across indicators has historically preceded weakness in "
                "rate-sensitive and cyclical names. Consider tightening stops and reviewing exposure — "
                "open Ticker Deep Dive on any position to see how signals hit it specifically."
            )
        else:
            _insight_border = "#6B7FBF"
            _insight_icon = ""
            _insight_headline = "The macro picture is mixed — no clear directional edge."
            _insight_body = (
                f"<b>{bull_n} bullish / {bear_n} bearish / {neut_n} neutral</b> across {total_n} signals. "
                "When signals disagree this broadly, it often means a regime transition is underway. "
                "Watch for the next 2–3 signal flips — they can confirm the new direction early. "
                "Today's Brief shows exactly what changed since yesterday."
            )

        st.markdown(f"""
        <div style="background:rgba(18,21,30,0.78);border-radius:14px;padding:20px 24px;
                    border:1px solid rgba(255,255,255,0.08);border-left:5px solid {_insight_border};
                    backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);
                    box-shadow:0 4px 24px rgba(0,0,0,0.35);font-family:Inter,sans-serif;margin-bottom:16px;">
            <div style="font-size:0.62rem;letter-spacing:0.14em;font-weight:700;color:#6B7FBF;
                        text-transform:uppercase;margin-bottom:6px;">
                {_insight_icon} SIGNAL INTERPRETATION
            </div>
            <div style="font-size:1.0rem;font-weight:800;color:#E8EEFF;margin-bottom:8px;letter-spacing:-0.2px;">
                {_insight_headline}
            </div>
            <div style="font-size:0.82rem;color:#B8C0D4;line-height:1.65;">
                {_insight_body}
            </div>
            <div style="margin-top:14px;font-size:0.75rem;color:#6B7FBF;
                        border-top:1px solid rgba(255,255,255,0.06);padding-top:10px;">
                 <b style="color:#8892AA;">Next step:</b>
                Pick a ticker → run
                <b style="color:#A78BFA;">Ticker Deep Dive</b> to see exactly which of these {total_n} signals
                are driving its Confluence Score and what they imply for forward returns.
                Or check <b style="color:#00C8E0;">Today's Brief</b> for a digest of what moved overnight.
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Confluence Heat Map ───────────────────────────────────────────────────────
    if mode == "Pro":
        st.markdown('<div class="section-header">MULTI-SIGNAL HEAT MAP</div>', unsafe_allow_html=True)
        st.caption("Which tickers have the most signals aligned in the same direction?")

        ht_tickers = ["SPY", "QQQ", "UNP", "DHI", "CCJ", "CEG", "FCX", "WMB", "VST", "NVDA", "PWR", "NEE"]
        ht_sig_names = {sid: sv["config"]["name"][:24] for sid, sv in all_signals.items()}

        heat_data, heat_rows = [], []
        for tkr in ht_tickers:
            tkr_cfg = TICKERS.get(tkr, {})
            relevant = tkr_cfg.get("signals", list(SIGNALS.keys()))
            row = [
                all_signals[sid]["score"] if sid in all_signals and sid in relevant else None
                for sid in SIGNALS
            ]
            heat_data.append(row)
            heat_rows.append(tkr)

        heat_arr = pd.DataFrame(heat_data, index=heat_rows,
                                columns=list(ht_sig_names.values())).values.astype(float)

        fig_heat = go.Figure(go.Heatmap(
            z=heat_arr, x=list(ht_sig_names.values()), y=heat_rows,
            colorscale=[[0.0, "#5C0A0A"], [0.35, "#B71C1C"], [0.5, "#0F1118"],
                        [0.65, "#00D566"], [1.0, "#003300"]],
            zmid=50, zmin=0, zmax=100,
            hovertemplate="%{y} × %{x}<br>Score: %{z:.0f}/100<extra></extra>",
            colorbar=dict(title="Score", tickfont=dict(size=10, color="#8892AA")),
        ))
        fig_heat.update_layout(
            height=380, paper_bgcolor="#0B0D12",
            xaxis=dict(tickangle=-35, tickfont=dict(size=9, color="#8892AA")),
            yaxis=dict(tickfont=dict(size=10, color="#E8EEFF")),
            margin=dict(l=60, r=20, t=10, b=80),
        )
        st.plotly_chart(fig_heat, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
        st.caption(
            "Each cell is a 0–100 macro signal score for that ticker's relevant indicators. "
            " ≥65 = elevated bullish signal ·  ≤35 = bearish · gray = neutral or no relevant data. "
            "Columns ordered by signal category (macro, commodity, credit, energy, sentiment)."
        )
    else:
        # Simple mode: show a clean ranked list
        st.markdown('<div class="section-header">TOP SIGNALS TO WATCH</div>', unsafe_allow_html=True)
        st.caption("The signals with the strongest current readings — furthest from normal.")

        ranked = sorted(
            [(sid, sv) for sid, sv in visible_signals],
            key=lambda x: abs(x[1].get("score", 50) - 50),
            reverse=True,
        )[:8]

        for sid, sv in ranked:
            cfg    = sv["config"]
            status = sv.get("status", "neutral")
            score  = sv.get("score", 50)
            border = STATUS_COLOR.get(status, "#8892AA")
            sym    = STATUS_SYM.get(status, "●")
            dev    = sv.get("deviation_pct", 0)
            direction = "above" if dev > 0 else "below"

            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:16px;padding:10px 14px;
                        background:rgba(18,21,30,0.85);border-radius:6px;border-left:4px solid {border};
                        border:1px solid rgba(255,255,255,0.07);margin-bottom:6px;font-family:Inter,sans-serif;">
                <div style="font-size:1.3rem;color:{border};font-weight:700;min-width:36px;">{sym}</div>
                <div style="flex:1;">
                    <div style="font-weight:700;font-size:0.85rem;color:#E8EEFF;">{cfg['name']}</div>
                    <div style="font-size:0.75rem;color:#B8C0D4;margin-top:2px;">
                        {abs(dev):.0f}% {direction} average · Score {score:.0f}/100
                        {f" · leads stocks ~{cfg['lag_weeks']}w" if cfg.get('lag_weeks') else ""}
                    </div>
                </div>
                <div style="font-size:0.80rem;color:{border};font-weight:700;text-align:right;">
                    {STATUS_LABEL.get(status,'').split(' ',1)[-1]}
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ── Signal Correlation Matrix (Pro mode) ─────────────────────────────────────
    if mode == "Pro":
        st.divider()
        st.markdown(
            '<div class="section-header">SIGNAL INDEPENDENCE — PAIRWISE CORRELATION MATRIX</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "How correlated are our signals with each other? If 6 signals are bullish but they're "
            "all reading the same underlying phenomenon, that's really only 1 independent data point. "
            "'Effective N' is the number of truly independent signals based on eigenvalue decomposition."
        )

        with st.spinner("Computing pairwise correlations across signal history…"):
            _corr_data = compute_signal_correlation_matrix(days_back=90)

        if _corr_data.get("sparse") or not _corr_data.get("signals"):
            st.info(
                "Not enough signal history yet to compute correlations. "
                "This section populates after Today's Brief has been visited daily for 14+ days — "
                f"each visit records a snapshot of all {len(SIGNALS)} signals."
            )
        else:
            _eff_n      = _corr_data["effective_n"]
            _total_n    = _corr_data["total_signals"]
            _matrix     = _corr_data["matrix"]
            _sig_names  = _corr_data["names"]
            _days_used  = _corr_data["days_used"]

            # Effective N interpretation
            _indep_pct  = round(100 * _eff_n / max(_total_n, 1), 0)
            _eff_color  = "#00D566" if _indep_pct >= 60 else ("#F59E0B" if _indep_pct >= 40 else "#FF4444")

            _cn1, _cn2, _cn3 = st.columns(3)
            with _cn1:
                st.markdown(
                    f'<div class="stat-box">'
                    f'<div class="stat-label">Signals with history</div>'
                    f'<div class="stat-value">{_total_n}</div>'
                    f'<div class="stat-change flat">of 38 total</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with _cn2:
                st.markdown(
                    f'<div class="stat-box">'
                    f'<div class="stat-label">Effective Independent N</div>'
                    f'<div class="stat-value" style="color:{_eff_color};">{_eff_n:.1f}</div>'
                    f'<div class="stat-change flat">{_indep_pct:.0f}% truly independent</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with _cn3:
                st.markdown(
                    f'<div class="stat-box">'
                    f'<div class="stat-label">History window</div>'
                    f'<div class="stat-value">{_days_used}d</div>'
                    f'<div class="stat-change flat">rolling pairwise</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("<br>", unsafe_allow_html=True)

            import numpy as np
            _mat_arr = np.array(_matrix)

            # Truncate names for readability
            _short_names = [n[:20] for n in _sig_names]

            _fig_corr = go.Figure(go.Heatmap(
                z=_mat_arr,
                x=_short_names,
                y=_short_names,
                colorscale=[
                    [0.0,  "#FF4444"],
                    [0.25, "#C0392B"],
                    [0.45, "#0F1118"],
                    [0.55, "#0F1118"],
                    [0.75, "#00D566"],
                    [1.0,  "#003300"],
                ],
                zmid=0, zmin=-1, zmax=1,
                text=np.round(_mat_arr, 2).tolist(),
                texttemplate="%{text:.1f}",
                textfont=dict(size=7),
                hovertemplate="%{y} × %{x}<br>Correlation: %{z:.3f}<extra></extra>",
                colorbar=dict(
                    title="r",
                    tickvals=[-1, -0.5, 0, 0.5, 1],
                    ticktext=["-1.0", "-0.5", "0", "+0.5", "+1.0"],
                    tickfont=dict(size=9),
                ),
            ))
            _matrix_height = max(400, len(_sig_names) * 18)
            _fig_corr.update_layout(
                height=_matrix_height,
                paper_bgcolor="#0B0D12",
                plot_bgcolor="#0B0D12",
                margin=dict(l=140, r=20, t=10, b=140),
                xaxis=dict(tickangle=-45, tickfont=dict(size=8, color="#8892AA"), side="bottom"),
                yaxis=dict(tickfont=dict(size=8, color="#8892AA"), autorange="reversed"),
                font=dict(family="Inter, sans-serif"),
            )
            st.plotly_chart(_fig_corr, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
            st.caption(
                "Pearson correlation of weekly signal values over the trailing 2-year window. "
                "Pairs with r ≥ 0.70 (dark green) are measuring similar phenomena — "
                "treat as one signal when counting bullish/bearish confirmations. "
                "Pairs with r ≤ −0.50 move opposite and can act as natural hedges."
            )

            # Find and call out the most highly correlated pairs (≥0.7)
            _high_pairs = []
            _names_arr = _sig_names
            for _i in range(len(_names_arr)):
                for _j in range(_i + 1, len(_names_arr)):
                    _r = _mat_arr[_i, _j]
                    if abs(_r) >= 0.70:
                        _high_pairs.append((_names_arr[_i], _names_arr[_j], round(_r, 2)))

            if _high_pairs:
                _high_pairs.sort(key=lambda x: -abs(x[2]))
                _pair_html = " &nbsp;·&nbsp; ".join(
                    f'<b>{a[:20]}</b> & <b>{b[:20]}</b> (r={r:+.2f})'
                    for a, b, r in _high_pairs[:6]
                )
                st.markdown(
                    f'<div style="background:rgba(245,158,11,0.07);border-left:3px solid #F59E0B;padding:8px 12px;'
                    f'border-radius:8px;font-family:Inter,sans-serif;font-size:0.75rem;color:#B8C0D4;">'
                    f'<b>High-correlation pairs (r ≥ 0.70)</b> — these signal pairs are reading similar '
                    f'phenomena and should not be double-counted as independent confirmation:<br>'
                    f'{_pair_html}</div>',
                    unsafe_allow_html=True,
                )

    # Financial disclaimer
    st.html(render_disclaimer(compact=True))


if _signal_section == "Regime Playbook":
    import pandas as _pd_rp
    import plotly.graph_objects as _go_rp
    import yfinance as _yf_rp
    from utils.signals_cache import get_all_signal_scores as _rp_get_scores
    from utils.config import SIGNALS as _RP_SIGNALS, CATEGORIES as _RP_CATS

    @st.cache_data(ttl=7200, show_spinner=False, max_entries=1)
    def _rp_live_regime():
        sv = _rp_get_scores()
        bulls  = sum(1 for s in sv.values() if s.get("status") == "bullish" and not s.get("error"))
        bears  = sum(1 for s in sv.values() if s.get("status") == "bearish" and not s.get("error"))
        neuts  = sum(1 for s in sv.values() if s.get("status") == "neutral"  and not s.get("error"))
        total  = bulls + bears + neuts
        pct    = bulls / max(total, 1) * 100
        if pct >= 60:
            regime, color = "BULLISH", "#00D566"
        elif pct <= 40:
            regime, color = "BEARISH", "#FF4444"
        else:
            regime, color = "MIXED", "#F59E0B"
        return regime, color, bulls, bears, total, pct

    _regime, _rp_color, _rp_bulls, _rp_bears, _rp_total, _rp_pct = _rp_live_regime()

    _bg_r = "rgba(0,213,102,0.10)" if _regime == "BULLISH" else ("rgba(255,68,68,0.10)" if _regime == "BEARISH" else "rgba(245,158,11,0.10)")
    st.markdown(
        f'<div style="background:{_bg_r};border:2px solid {_rp_color};border-radius:10px;'
        f'padding:18px 24px;text-align:center;margin-bottom:20px;font-family:Inter,sans-serif;">'
        f'<div style="font-size:1.6rem;font-weight:900;color:{_rp_color};">{_regime} MACRO</div>'
        f'<div style="font-size:0.82rem;color:#8892AA;margin-top:6px;">'
        f'{_rp_bulls} bullish · {_rp_bears} bearish · {_rp_total} signals · {_rp_pct:.0f}% alignment'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("#### Signal Category Breakdown")
    _sv_rp = _rp_get_scores()
    _cat_data = {}
    for _sid_rp, _sv in _sv_rp.items():
        if _sv.get("error"):
            continue
        _cat = _RP_SIGNALS.get(_sid_rp, {}).get("category", "macro")
        _cat_info = _RP_CATS.get(_cat, {})
        _cat_name = _cat_info.get("label", _cat) if isinstance(_cat_info, dict) else str(_cat_info or _cat)
        _cat_data.setdefault(_cat_name, {"bull": 0, "bear": 0, "neut": 0, "scores": []})
        _status = _sv.get("status", "neutral")
        if _status == "bullish":
            _cat_data[_cat_name]["bull"] += 1
        elif _status == "bearish":
            _cat_data[_cat_name]["bear"] += 1
        else:
            _cat_data[_cat_name]["neut"] += 1
        _sc = _sv.get("score")
        if _sc is not None:
            _cat_data[_cat_name]["scores"].append(float(_sc))

    _cat_items = sorted(_cat_data.items(), key=lambda x: -(sum(x[1]["scores"]) / max(len(x[1]["scores"]), 1)))
    _rp_ncols = min(4, max(len(_cat_items), 1))
    _rp_cols = st.columns(_rp_ncols)
    for _ci, (_cn, _cd) in enumerate(_cat_items):
        _avg = sum(_cd["scores"]) / max(len(_cd["scores"]), 1)
        _c   = "#00D566" if _avg >= 60 else "#FF4444" if _avg <= 40 else "#6B7FBF"
        _rp_cols[_ci % _rp_ncols].markdown(
            f'<div style="background:rgba(255,255,255,0.025);border:1px solid {_c}33;'
            f'border-radius:8px;padding:10px 12px;margin-bottom:8px;">'
            f'<div style="font-size:0.72rem;font-weight:600;color:#E8EEFF;">{_cn}</div>'
            f'<div style="font-size:1.4rem;font-weight:800;color:{_c};">{_avg:.0f}</div>'
            f'<div style="font-size:0.60rem;color:#8892AA;">▲{_cd["bull"]} ▼{_cd["bear"]} {_cd["neut"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("#### Sector ETF Performance")
    SECTOR_ETFS_RP = {
        "XLK": "Technology", "XLE": "Energy", "XLF": "Financials", "XLV": "Healthcare",
        "XLI": "Industrials", "XLY": "Consumer Disc.", "XLP": "Consumer Staples",
        "XLU": "Utilities", "XLRE": "Real Estate", "SPY": "S&P 500",
    }

    @st.cache_data(ttl=3600, show_spinner=False, max_entries=2)
    def _rp_etf_returns():
        etfs = list(SECTOR_ETFS_RP.keys())
        px = _yf_rp.download(etfs, period="6mo", auto_adjust=True, progress=False)["Close"]
        if isinstance(px, _pd_rp.Series):
            px = px.to_frame(name=etfs[0])
        r30 = (px.iloc[-1] - px.iloc[-22]) / px.iloc[-22] * 100 if len(px) >= 22 else _pd_rp.Series()
        r90 = (px.iloc[-1] - px.iloc[-66]) / px.iloc[-66] * 100 if len(px) >= 66 else _pd_rp.Series()
        return r30, r90

    with st.spinner("Loading ETF returns…"):
        try:
            _ret30, _ret90 = _rp_etf_returns()
        except Exception:
            _ret30, _ret90 = _pd_rp.Series(), _pd_rp.Series()

    if not _ret30.empty:
        _etf_df = _pd_rp.DataFrame({
            "Sector": [SECTOR_ETFS_RP.get(t, t) for t in _ret30.index],
            "ETF":    list(_ret30.index),
            "30d %":  _ret30.values.round(1),
            "90d %":  _ret90.reindex(_ret30.index).values.round(1) if not _ret90.empty else [None]*len(_ret30),
        }).sort_values("30d %", ascending=False)
        st.dataframe(
            _etf_df, use_container_width=True, hide_index=True,
            column_config={
                "30d %": st.column_config.NumberColumn("30d %", format="%.1f%%"),
                "90d %": st.column_config.NumberColumn("90d %", format="%.1f%%"),
            }
        )
        st.caption(
            f"Regime: **{_regime}** ({_rp_pct:.0f}% bullish). "
            "Returns are recent realized performance grouped by current regime state."
        )
    else:
        st.info("ETF data loading — try again in a moment.")

# ── Footer ────────────────────────────────────────────────────────────────────
render_footer(page="signals")
