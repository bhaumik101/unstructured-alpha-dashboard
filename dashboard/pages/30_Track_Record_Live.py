"""
pages/30_Track_Record_Live.py
==============================
"The Machine Called It" — public, auditable signal prediction feed.

WHY THIS PAGE EXISTS:
The single most powerful conversion tool on the site is proof. Anyone can
build a signal dashboard; proving it actually works — with a real, auditable,
un-cherry-picked call history — is what separates signal products that retain
subscribers from those that churn. This page is publicly accessible (no login
required) so it functions as both a retention anchor for existing users and a
conversion proof point for prospective subscribers.

TWO DATA SOURCES shown in separate sections:

1. PREDICTION LOG (utils/prediction_log.py): Every convergence event and score
   crossing is auto-logged when it happens on Ticker Deep Dive. Forward returns
   at 4w / 8w / 12w are resolved automatically when windows expire. These are
   genuine advance predictions — logged BEFORE the outcome is known.

2. HIGH-CONFIDENCE SCORE HISTORY (utils/score_history.py): Historical moments
   where the confluence score hit ≥ 70 (strong bullish) or ≤ 30 (strong bearish),
   matched to actual 30-day price returns via yfinance. CLEARLY labeled as
   retrospective lookups — not advance predictions — to maintain full honesty.

Honesty constraints:
- Sample size warnings shown whenever n < 20
- "Correct" defined simply: bull → return > 0, bear → return < 0
- No cherry-picking: every qualifying call is shown, not just the hits
- Retrospective score history labeled as such, never conflated with the log
"""

from __future__ import annotations

import datetime as _dt

import streamlit as st

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.theme import inject_premium_css, inject_skeleton_css, section_label
from utils.prediction_log import (
    get_track_record,
    get_predictions_feed,
    get_signal_accuracy_stats,
    get_resolver_health,
    resolve_pending,
)
from utils.score_history import get_high_confidence_snapshot_calls

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Signal Call Log — Unstructured Alpha", layout="wide")
render_header("Signal Call Log")
_track_section = render_sidebar_base(
    page_title="Track Record",
    sections=("Signal Track Record", "Earnings Track Record"),
    section_key="track_record_section_rail",
)
try:
    from utils.instrumentation import record_once
    record_once("track_record_viewed")
except Exception:
    pass
inject_premium_css()
inject_skeleton_css()

render_page_header(
    "The Machine Called It",
    "Every high-confidence signal call the model has logged — with actual price outcomes.",
    icon="",
)

if _track_section == "Signal Track Record":
    # ── Quietly resolve any pending predictions whose windows have expired ─────────
    try:
        resolve_pending(max_resolve=10)
    except Exception:
        pass

    # ── Colour / label constants ───────────────────────────────────────────────────
    BULL_COLOR  = "#00D566"
    BEAR_COLOR  = "#FF4444"
    CYAN        = "#00C8E0"
    AMBER       = "#F59E0B"
    PURPLE      = "#7C3AED"

    EVENT_LABELS = {
        "convergence":      "3+ Signals Converged",
        "score_cross_bull": "Score Crossed 70",
        "score_cross_bear": "Score Crossed 30",
    }


    def _dir_color(direction: str) -> str:
        return BULL_COLOR if direction == "bull" else BEAR_COLOR


    def _dir_sym(direction: str) -> str:
        return "▲ BULL" if direction == "bull" else "▼ BEAR"


    def _hit_html(correct: int | None, ret: float | None, label: str) -> str:
        if correct is None or ret is None:
            return f'<span style="color:#8892AA;font-size:0.72rem;">{label}: —</span>'
        color = BULL_COLOR if correct == 1 else BEAR_COLOR
        sym   = "✓" if correct == 1 else "✗"
        return (
            f'<span style="color:{color};font-weight:700;font-size:0.72rem;">'
            f'{sym} {label}: {ret:+.1f}%</span>'
        )


    # ── Aggregate stats (hero banner) ─────────────────────────────────────────────
    _tr = get_track_record()

    _total    = _tr["total"]
    _resolved = _tr["resolved"]
    _pending  = _tr["pending"]
    _acc_4w   = _tr["accuracy_4w"]
    _acc_12w  = _tr["accuracy_12w"]
    _med_12w  = _tr["median_ret_12w"]

    st.html(f"""
    <div class="ua-gradient-border" style="margin-bottom:24px;">
      <div style="display:flex;align-items:center;gap:0;flex-wrap:wrap;">

        <div class="ua-spotlight ua-kpi-animate" style="--ua-spotlight-accent:{CYAN};
             flex:1;min-width:130px;text-align:center;padding:18px 16px;">
          <div style="font-size:0.58rem;font-weight:700;color:#8892AA;text-transform:uppercase;
                      letter-spacing:0.12em;margin-bottom:6px;">Calls Logged</div>
          <div style="font-size:2.2rem;font-weight:900;color:{CYAN};
                      text-shadow:0 0 24px {CYAN}45;line-height:1;">{_total}</div>
          <div style="font-size:0.68rem;color:#8892AA;margin-top:4px;">
            {_resolved} resolved · {_pending} pending
          </div>
        </div>

        <div class="ua-spotlight ua-kpi-animate" style="--ua-spotlight-accent:{BULL_COLOR};
             flex:1;min-width:130px;text-align:center;padding:18px 16px;">
          <div style="font-size:0.58rem;font-weight:700;color:#8892AA;text-transform:uppercase;
                      letter-spacing:0.12em;margin-bottom:6px;">4-Week Accuracy</div>
          <div style="font-size:2.2rem;font-weight:900;color:{BULL_COLOR};
                      text-shadow:0 0 24px {BULL_COLOR}45;line-height:1;">
            {"—" if _acc_4w is None else f"{_acc_4w:.0f}%"}
          </div>
          <div style="font-size:0.68rem;color:#8892AA;margin-top:4px;">
            {"not enough resolved data yet" if _acc_4w is None else "direction correct"}
          </div>
        </div>

        <div class="ua-spotlight ua-kpi-animate" style="--ua-spotlight-accent:{AMBER};
             flex:1;min-width:130px;text-align:center;padding:18px 16px;">
          <div style="font-size:0.58rem;font-weight:700;color:#8892AA;text-transform:uppercase;
                      letter-spacing:0.12em;margin-bottom:6px;">12-Week Accuracy</div>
          <div style="font-size:2.2rem;font-weight:900;color:{AMBER};
                      text-shadow:0 0 24px {AMBER}45;line-height:1;">
            {"—" if _acc_12w is None else f"{_acc_12w:.0f}%"}
          </div>
          <div style="font-size:0.68rem;color:#8892AA;margin-top:4px;">
            {"building history…" if _acc_12w is None else "direction correct"}
          </div>
        </div>

        <div class="ua-spotlight ua-kpi-animate" style="--ua-spotlight-accent:{PURPLE};
             flex:1;min-width:130px;text-align:center;padding:18px 16px;">
          <div style="font-size:0.58rem;font-weight:700;color:#8892AA;text-transform:uppercase;
                      letter-spacing:0.12em;margin-bottom:6px;">Median 12w Return</div>
          <div style="font-size:2.2rem;font-weight:900;
                      color:{"#00D566" if (_med_12w or 0) >= 0 else "#FF4444"};
                      text-shadow:0 0 24px {"#00D56645" if (_med_12w or 0) >= 0 else "#FF444445"};
                      line-height:1;">
            {"—" if _med_12w is None else f"{_med_12w:+.1f}%"}
          </div>
          <div style="font-size:0.68rem;color:#8892AA;margin-top:4px;">on resolved calls</div>
        </div>

      </div>
    </div>
    """)

    if _total < 5:
        st.info(
            "The prediction log is still building. Every time a high-confidence "
            "convergence event or score crossing is detected on Ticker Deep Dive, "
            "it's logged here automatically. Check back as more tickers are analyzed."
        )

    # ── Section 1: Prediction Log ─────────────────────────────────────────────────
    st.html(section_label("Prediction Log", color=CYAN, dot=CYAN))
    st.caption(
        "Every convergence event and score crossing logged **in advance** — before the outcome is known. "
        "Forward returns at 4w / 8w / 12w are filled in automatically once the window expires."
    )

    # Filters
    _fc1, _fc2, _fc3 = st.columns([1, 1, 1])
    with _fc1:
        _dir_f = st.selectbox(
            "Direction", ["All", "Bull", "Bear"], key="pred_dir_filter", label_visibility="collapsed"
        )
    with _fc2:
        _stat_f = st.selectbox(
            "Status", ["All", "Pending", "Resolved"], key="pred_stat_filter", label_visibility="collapsed"
        )
    with _fc3:
        _limit_f = st.selectbox(
            "Show", [25, 50, 100], key="pred_limit_filter", label_visibility="collapsed"
        )

    _feed = get_predictions_feed(
        limit=int(_limit_f),
        direction_filter=_dir_f.lower() if _dir_f != "All" else "all",
        status_filter=_stat_f.lower() if _stat_f != "All" else "all",
    )

    if not _feed:
        st.markdown(
            '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);'
            'border-radius:10px;padding:24px;text-align:center;color:#8892AA;font-size:0.88rem;">'
            'No predictions logged yet matching these filters. '
            'Predictions are logged automatically when the Confluence Score crosses '
            'a high-confidence threshold on Ticker Deep Dive.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        # Render prediction cards — 2 per row
        _pairs = [_feed[i:i+2] for i in range(0, len(_feed), 2)]
        for pair in _pairs:
            cols = st.columns(len(pair))
            for col, row in zip(cols, pair):
                dc        = _dir_color(row["direction"])
                dsym      = _dir_sym(row["direction"])
                ev_label  = EVENT_LABELS.get(row["event_type"], row["event_type"])
                score     = row.get("score_at_event") or 0
                sig_ct    = row.get("signal_count") or 0
                entry_px  = row.get("price_at_event")
                is_res    = row["status"] == "resolved"

                # Outcome section
                if is_res:
                    outcome_html = (
                        f'<div style="border-top:1px solid rgba(255,255,255,0.07);'
                        f'margin-top:10px;padding-top:10px;display:flex;flex-wrap:wrap;gap:8px;">'
                        + _hit_html(row.get("correct_4w"),  row.get("return_4w"),  "4w")
                        + "&nbsp;&nbsp;"
                        + _hit_html(row.get("correct_8w"),  row.get("return_8w"),  "8w")
                        + "&nbsp;&nbsp;"
                        + _hit_html(row.get("correct_12w"), row.get("return_12w"), "12w")
                        + "</div>"
                    )
                else:
                    # Compute when 4w window expires
                    try:
                        ev_date   = _dt.date.fromisoformat(row["event_date"])
                        exp_date  = ev_date + _dt.timedelta(weeks=4)
                        days_left = (exp_date - _dt.date.today()).days
                        if days_left > 0:
                            exp_str = f"4w result due in {days_left}d"
                        else:
                            exp_str = "4w window passed — resolving soon"
                    except Exception:
                        exp_str = "Outcome pending"
                    outcome_html = (
                        f'<div style="border-top:1px solid rgba(255,255,255,0.07);'
                        f'margin-top:10px;padding-top:8px;">'
                        f'<span style="font-size:0.70rem;color:#8892AA;font-style:italic;">'
                        f' {exp_str}</span></div>'
                    )

                entry_str = f"${entry_px:,.2f}" if entry_px else "—"
                sig_str   = f" · {sig_ct} signals" if sig_ct else ""

                with col:
                    st.markdown(f"""
    <div class="ua-spotlight ua-kpi-animate" style="--ua-spotlight-accent:{dc};
         padding:16px 18px 14px;margin-bottom:12px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
        <span style="font-size:0.60rem;font-weight:700;color:{dc};text-transform:uppercase;
                     letter-spacing:0.10em;">{dsym}</span>
        <span style="font-size:0.60rem;color:#8892AA;">{row["event_date"]}</span>
      </div>
      <div style="font-size:1.55rem;font-weight:900;color:#E8EEFF;line-height:1.1;
                   margin-bottom:4px;">{row["ticker"]}</div>
      <div style="font-size:0.72rem;color:#8892AA;margin-bottom:6px;">
        {ev_label}{sig_str}
      </div>
      <div style="display:flex;align-items:center;gap:14px;">
        <div>
          <div style="font-size:0.58rem;color:#8892AA;text-transform:uppercase;letter-spacing:0.08em;">
            Score</div>
          <div style="font-size:1.4rem;font-weight:900;color:{dc};
                      text-shadow:0 0 16px {dc}40;line-height:1.1;">{score:.0f}</div>
        </div>
        <div>
          <div style="font-size:0.58rem;color:#8892AA;text-transform:uppercase;letter-spacing:0.08em;">
            Entry</div>
          <div style="font-size:0.88rem;font-weight:700;color:#B8C0D4;">{entry_str}</div>
        </div>
        <div style="margin-left:auto;">
          <span style="font-size:0.66rem;font-weight:700;
                       padding:3px 8px;border-radius:4px;
                       background:{"rgba(0,213,102,0.12)" if is_res else "rgba(255,255,255,0.06)"};
                       color:{"#00D566" if is_res else "#8892AA"};">
            {"✓ RESOLVED" if is_res else "PENDING"}
          </span>
        </div>
      </div>
      {outcome_html}
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Section 2: High-Confidence Score History ─────────────────────────────────
    st.markdown(
        section_label("High-Confidence Score History", color=AMBER, dot=AMBER),
        unsafe_allow_html=True,
    )
    st.caption(
        "**Retrospective analysis** — not advance predictions. "
        "These are historical moments where the confluence score hit ≥ 70 (bullish) or ≤ 30 (bearish), "
        "matched to the actual 30-day price return. Every qualifying instance is shown, not just the wins."
    )

    @st.cache_data(ttl=3600, max_entries=1, show_spinner=False)
    def _load_history_calls() -> list[dict]:
        """
        Pull high-confidence snapshot calls and compute actual 30-day returns.
        Cached 1hr because the yfinance batch download is the slow part.
        """
        import yfinance as yf
        import pandas as pd

        snaps = get_high_confidence_snapshot_calls(min_score=70.0, days_back=180, min_days_ago=35)
        if not snaps:
            return []

        # Batch download unique tickers
        tickers = list({s["ticker"] for s in snaps})
        try:
            px = yf.download(tickers, period="1y", auto_adjust=True, progress=False,
                             group_by="ticker")
        except Exception:
            return []

        results = []
        for snap in snaps:
            tk    = snap["ticker"]
            score = snap["score"]
            case  = (snap.get("case") or "").lower()
            dt    = snap["snapshot_date"]

            try:
                if len(tickers) == 1:
                    closes = px["Close"].squeeze().dropna()
                else:
                    closes = px["Close"][tk].squeeze().dropna()

                snap_dt = pd.Timestamp(dt)
                fwd_dt  = snap_dt + pd.Timedelta(days=30)

                entry_px = float(closes.asof(snap_dt))
                fwd_px   = float(closes.asof(fwd_dt))
                if entry_px <= 0 or fwd_px <= 0:
                    continue

                ret_30d = (fwd_px / entry_px - 1) * 100
                direction = "bull" if score >= 70 else "bear"
                correct   = 1 if (direction == "bull" and ret_30d > 0) or \
                                 (direction == "bear" and ret_30d < 0) else 0

                results.append({
                    "ticker":      tk,
                    "snapshot_date": dt,
                    "score":       round(score, 1),
                    "case":        case or direction,
                    "direction":   direction,
                    "entry_price": round(entry_px, 2),
                    "fwd_price":   round(fwd_px, 2),
                    "return_30d":  round(ret_30d, 2),
                    "correct":     correct,
                })
            except Exception:
                continue

        # Sort newest first
        results.sort(key=lambda x: x["snapshot_date"], reverse=True)
        return results


    with st.spinner("Loading score history…"):
        _hist_calls = _load_history_calls()

    if not _hist_calls:
        st.info(
            "No high-confidence score history found yet. As more tickers are analyzed "
            "on Ticker Deep Dive, high-confidence moments are recorded and appear here."
        )
    else:
        # Aggregate stats
        _h_bull = [h for h in _hist_calls if h["direction"] == "bull"]
        _h_bear = [h for h in _hist_calls if h["direction"] == "bear"]
        _h_hits = sum(1 for h in _hist_calls if h["correct"] == 1)
        _h_acc  = round(100 * _h_hits / len(_hist_calls), 1) if _hist_calls else None
        _h_rets = [h["return_30d"] for h in _hist_calls]

        import statistics as _stats
        _h_med  = round(_stats.median(_h_rets), 1) if _h_rets else None
        _h_avg  = round(sum(_h_rets) / len(_h_rets), 1) if _h_rets else None

        # Mini stat row
        st.markdown(f"""
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
      <div class="ua-spotlight" style="--ua-spotlight-accent:{CYAN};padding:12px 18px;flex:1;min-width:120px;text-align:center;">
        <div style="font-size:0.58rem;color:#8892AA;text-transform:uppercase;letter-spacing:0.10em;margin-bottom:4px;">Instances</div>
        <div style="font-size:1.5rem;font-weight:900;color:{CYAN};">{len(_hist_calls)}</div>
        <div style="font-size:0.64rem;color:#8892AA;">{len(_h_bull)} bull · {len(_h_bear)} bear</div>
      </div>
      <div class="ua-spotlight" style="--ua-spotlight-accent:{BULL_COLOR};padding:12px 18px;flex:1;min-width:120px;text-align:center;">
        <div style="font-size:0.58rem;color:#8892AA;text-transform:uppercase;letter-spacing:0.10em;margin-bottom:4px;">30d Hit Rate</div>
        <div style="font-size:1.5rem;font-weight:900;color:{BULL_COLOR};">{"—" if _h_acc is None else f"{_h_acc:.0f}%"}</div>
        <div style="font-size:0.64rem;color:#8892AA;">direction correct</div>
      </div>
      <div class="ua-spotlight" style="--ua-spotlight-accent:{AMBER};padding:12px 18px;flex:1;min-width:120px;text-align:center;">
        <div style="font-size:0.58rem;color:#8892AA;text-transform:uppercase;letter-spacing:0.10em;margin-bottom:4px;">Median 30d Return</div>
        <div style="font-size:1.5rem;font-weight:900;
                    color:{"#00D566" if (_h_med or 0) >= 0 else "#FF4444"};">
          {"—" if _h_med is None else f"{_h_med:+.1f}%"}
        </div>
        <div style="font-size:0.64rem;color:#8892AA;">all qualifying instances</div>
      </div>
      <div class="ua-spotlight" style="--ua-spotlight-accent:{PURPLE};padding:12px 18px;flex:1;min-width:120px;text-align:center;">
        <div style="font-size:0.58rem;color:#8892AA;text-transform:uppercase;letter-spacing:0.10em;margin-bottom:4px;">Avg 30d Return</div>
        <div style="font-size:1.5rem;font-weight:900;
                    color:{"#00D566" if (_h_avg or 0) >= 0 else "#FF4444"};">
          {"—" if _h_avg is None else f"{_h_avg:+.1f}%"}
        </div>
        <div style="font-size:0.64rem;color:#8892AA;">mean across all calls</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

        if len(_hist_calls) < 15:
            st.caption(
                f"Small sample ({len(_hist_calls)} instances). "
                "Statistics are not statistically significant at this size — treat as directional context only."
            )

        # Cards — 3 per row
        _triples = [_hist_calls[i:i+3] for i in range(0, len(_hist_calls), 3)]
        for triple in _triples:
            cols = st.columns(len(triple))
            for col, h in zip(cols, triple):
                dc   = _dir_color(h["direction"])
                dsym = _dir_sym(h["direction"])
                ret  = h["return_30d"]
                ret_c = BULL_COLOR if ret >= 0 else BEAR_COLOR
                ret_sym = "▲" if ret >= 0 else "▼"
                hit_badge = (
                    f'<span style="color:{BULL_COLOR};font-weight:700;">✓ HIT</span>'
                    if h["correct"] == 1 else
                    f'<span style="color:{BEAR_COLOR};font-weight:700;">✗ MISS</span>'
                )
                with col:
                    st.markdown(f"""
    <div class="ua-spotlight" style="--ua-spotlight-accent:{dc};
         padding:14px 16px 12px;margin-bottom:10px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
        <span style="font-size:0.58rem;font-weight:700;color:{dc};text-transform:uppercase;
                     letter-spacing:0.10em;">{dsym}</span>
        <span style="font-size:0.60rem;color:#8892AA;">{h["snapshot_date"]}</span>
      </div>
      <div style="font-size:1.35rem;font-weight:900;color:#E8EEFF;margin-bottom:2px;">{h["ticker"]}</div>
      <div style="font-size:0.70rem;color:{dc};margin-bottom:8px;">
        Score: <b style="text-shadow:0 0 12px {dc}40;">{h["score"]:.0f}/100</b>
      </div>
      <div style="border-top:1px solid rgba(255,255,255,0.07);padding-top:8px;
                   display:flex;align-items:center;justify-content:space-between;">
        <span style="font-size:0.80rem;font-weight:700;color:{ret_c};">
          {ret_sym} {ret:+.1f}% <span style="font-size:0.64rem;color:#8892AA;">30d</span>
        </span>
        {hit_badge}
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Section 3: Signal Accuracy Leaderboard ───────────────────────────────────
    st.html(section_label("Signal Accuracy Leaderboard", color=PURPLE, dot=PURPLE))
    st.caption(
        "Which macro signals have the best track record of predicting price direction? "
        "Aggregated from all resolved predictions where specific signals were recorded at the time of the call."
    )

    try:
        from utils.accuracy import MIN_REPORTABLE as _MIN_REPORTABLE
    except Exception:
        _MIN_REPORTABLE = 20

    _sig_stats = get_signal_accuracy_stats()

    if not _sig_stats:
        st.markdown(
            '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);'
            'border-radius:10px;padding:24px;text-align:center;color:#8892AA;font-size:0.88rem;">'
            'Signal-level accuracy data not yet available. As predictions resolve, each signal\'s '
            'track record will appear here automatically.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        def _acc_bar(val: float | None, width_px: int = 80) -> str:
            """Tiny horizontal accuracy bar."""
            if val is None:
                return '<span style="color:#8892AA;font-size:0.75rem;">—</span>'
            color  = BULL_COLOR if val >= 55 else (AMBER if val >= 45 else BEAR_COLOR)
            filled = int(width_px * val / 100)
            return (
                f'<span style="font-weight:700;color:{color};font-size:0.82rem;">{val:.0f}%</span>'
                f'<div style="margin-top:3px;background:rgba(255,255,255,0.08);'
                f'border-radius:3px;height:4px;width:{width_px}px;">'
                f'<div style="background:{color};width:{filled}px;height:4px;border-radius:3px;'
                f'box-shadow:0 0 6px {color}60;"></div></div>'
            )

        # Table header
        st.markdown(f"""
    <div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr;gap:4px;
         padding:8px 14px;background:rgba(255,255,255,0.04);border-radius:8px 8px 0 0;
         border:1px solid rgba(255,255,255,0.08);border-bottom:none;margin-top:8px;">
      <div style="font-size:0.60rem;font-weight:700;color:#8892AA;text-transform:uppercase;letter-spacing:0.10em;">Signal</div>
      <div style="font-size:0.60rem;font-weight:700;color:#8892AA;text-transform:uppercase;letter-spacing:0.10em;text-align:center;">Predictions</div>
      <div style="font-size:0.60rem;font-weight:700;color:#8892AA;text-transform:uppercase;letter-spacing:0.10em;text-align:center;">4w Acc.</div>
      <div style="font-size:0.60rem;font-weight:700;color:#8892AA;text-transform:uppercase;letter-spacing:0.10em;text-align:center;">8w Acc.</div>
      <div style="font-size:0.60rem;font-weight:700;color:#8892AA;text-transform:uppercase;letter-spacing:0.10em;text-align:center;">12w Acc.</div>
    </div>
    """, unsafe_allow_html=True)

        for i, sig in enumerate(_sig_stats):
            bg = "rgba(255,255,255,0.02)" if i % 2 == 0 else "rgba(255,255,255,0.00)"
            border_r = "0 0 8px 8px" if i == len(_sig_stats) - 1 else "0"
            # Medals are EARNED, not positional. A signal only places if the
            # lower bound of its confidence interval actually clears a coin flip
            # — otherwise ranking first just means "least bad small sample", and
            # a gold medal on 3-of-3 would be an outright overclaim.
            medal = ""
            if sig.get("beats_chance"):
                medal = {0: " 1", 1: " 2", 2: " 3"}.get(i, "")

            # Evidence context shown inline, so a rate is never read without its
            # sample size. Tier colour: green only when it beats chance.
            _tier_col = (BULL_COLOR if sig.get("beats_chance")
                         else (BEAR_COLOR if sig.get("stats_12w", {}).get("worse_than_chance")
                               else "#8892AA"))
            _n12 = sig.get("sample_12w") or 0
            _ci_lo, _ci_hi = sig.get("ci_low_12w"), sig.get("ci_high_12w")
            _ci_txt = (f" · 95% CI {_ci_lo:.0f}–{_ci_hi:.0f}%"
                       if (_ci_lo is not None and _ci_hi is not None and _n12) else "")
            _evidence = (f'<div style="font-size:0.60rem;color:{_tier_col};margin-top:2px;">'
                         f'{sig.get("tier_label", "")} · n={_n12}{_ci_txt}</div>')
            st.markdown(f"""
    <div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr;gap:4px;
         padding:10px 14px;background:{bg};border-radius:{border_r};
         border:1px solid rgba(255,255,255,0.06);border-top:none;
         align-items:center;">
      <div>
        <div style="font-size:0.84rem;font-weight:700;color:#E8EEFF;">{sig["signal_name"]}{medal}</div>
        <div style="font-size:0.64rem;color:#8892AA;margin-top:1px;">{sig["signal_id"]}</div>
        {_evidence}
      </div>
      <div style="text-align:center;font-size:0.88rem;font-weight:700;color:{CYAN};">{sig["predictions"]}</div>
      <div style="text-align:center;">{_acc_bar(sig["accuracy_4w"])}</div>
      <div style="text-align:center;">{_acc_bar(sig["accuracy_8w"])}</div>
      <div style="text-align:center;">{_acc_bar(sig["accuracy_12w"])}</div>
    </div>
    """, unsafe_allow_html=True)

        st.caption(
            f" ≥55% ·  45–55% ·  <45%.  **A rate is only shown once a signal has "
            f"at least {_MIN_REPORTABLE} resolved predictions** — below that the sample is too "
            "small to mean anything, so we show “—” rather than a number you might act on. "
            "Ranking is by the *lower* bound of the 95% confidence interval, not the raw "
            "percentage, so a well-evidenced 61% outranks a 3-for-3 100%. A medal is only "
            "awarded when that lower bound clears 50% — i.e. the signal is statistically "
            "distinguishable from a coin flip. Directional calls, so 50% is the baseline."
        )

    st.divider()

    # ── Section 4: How it works ───────────────────────────────────────────────────
    with st.expander("How predictions are logged — methodology and data coverage"):
        st.markdown("""
    **Prediction Log (Section 1)**

    Predictions are logged automatically when:
    - **Convergence event**: 3 or more macro/alternative data signals align in the same direction simultaneously on a Ticker Deep Dive view.
    - **Score crossing**: The Confluence Score crosses the 70 threshold (bullish) or 30 threshold (bearish) on a ticker view.

    Each log entry records: ticker, event type, direction (bull/bear), Confluence Score, entry price, and the date.

    Forward returns at **4 weeks, 8 weeks, and 12 weeks** are filled in automatically the next time anyone views any page after the forward date has passed (via `resolve_pending()` in utils/prediction_log.py).

    **"Correct"** is defined simply and conservatively:
    - Bull prediction correct if 4w / 8w / 12w return > 0
    - Bear prediction correct if 4w / 8w / 12w return < 0

    No cherry-picking: every logged prediction is shown. Predictions are logged in the moment, never backdated.

    ---

    **High-Confidence Score History (Section 2)**

    These are **retrospective lookups** — not advance predictions. We identify historical moments where the Confluence Score was ≥ 70 (bullish) or ≤ 30 (bearish), then look up the actual 30-day price return from that moment. This supplements the prediction log while it's still building and gives a larger historical sample to work with.

    Key limitation: score history only exists for tickers people have viewed on Ticker Deep Dive, since this app has no background scheduler. The sample is organic and traffic-driven.

    ---

    **Data coverage limitation**

    Both data sources depend on the app receiving traffic. A ticker that nobody has viewed recently will have sparse history. Coverage grows over time as the user base grows.

    **This is not financial advice.** Past performance is not indicative of future results. The Confluence Score is an aggregation of macro and alternative data signals, not a prediction model trained on forward returns. Always do your own research.
        """)

    # ── Resolver health expander ─────────────────────────────────────────────────
    # For transparency: shows whether the nightly resolver cron is actually
    # chipping away at pending predictions, so anyone can verify the pipeline.
    try:
        _rh = get_resolver_health()
        _overdue   = _rh["overdue_pending"]
        _last_date = _rh["last_resolved_date"]
        _recent7d  = _rh["recently_resolved_7d"]
        _overdue_label = (
            " None overdue" if _overdue == 0
            else f"{_overdue} overdue"
        )
        _last_label = _last_date if _last_date else "—"
        with st.expander("Resolver pipeline health"):
            st.caption(
                "The nightly cron (`cron/resolve_predictions.py`) runs at 02:00 UTC to fill in "
                "forward returns for predictions whose 4w/8w/12w windows have expired. "
                "This page also runs a lightweight on-demand pass (`resolve_pending(max_resolve=10)`) "
                "each time it loads, as a fallback. The table below shows current pipeline state."
            )
            _h1, _h2, _h3 = st.columns(3)
            with _h1:
                st.metric("Pending total", _rh["pending_total"])
            with _h2:
                st.metric("Overdue (≥4w old, still pending)", _overdue_label)
            with _h3:
                st.metric("Resolved in last 7 days", _recent7d)
            st.caption(
                f"Most recent resolved prediction event date: **{_last_label}**. "
                "Note: 'event date' is when the prediction was logged, not when it was resolved — "
                "there's no separate `resolved_at` timestamp in the current schema. "
                "Overdue = 0 means the resolver is keeping up; overdue > 0 means some predictions "
                "passed their 4-week window without being resolved (typically a cron failure or "
                "a ticker with no yfinance data)."
            )
    except Exception:
        pass

    # ── CTA for non-subscribers ───────────────────────────────────────────────────
    st.markdown("""
    <div class="ua-pro-banner" style="margin-top:24px;">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
        <div>
          <div style="font-size:1.0rem;font-weight:800;color:#E8EEFF;margin-bottom:4px;">
            Get alerted the moment a new convergence call is logged
          </div>
          <div style="font-size:0.82rem;color:#B8C0D4;">
            Pro subscribers receive instant alerts via Discord, Slack, or email when a new
            high-confidence call is detected — so you don't have to check this page manually.
          </div>
        </div>
        <a href="/upgrade-to-pro" target="_self"
           style="background:linear-gradient(135deg,#7C3AED,#5B21B6);color:#fff;
                  font-weight:700;font-size:0.88rem;padding:10px 22px;border-radius:8px;
                  text-decoration:none;white-space:nowrap;flex-shrink:0;">
          Get Pro Alerts →
        </a>
      </div>
    </div>
    """, unsafe_allow_html=True)


if _track_section == "Earnings Track Record":
    from utils.fetchers import fetch_earnings_dates
    from utils.score_history import get_score_history
    import datetime as _dt
    import pandas as pd

    st.markdown("### Pre-Earnings Signal Track Record")
    st.caption(
        "Compare what the Confluence Score said 7–45 days before past earnings events "
        "against actual EPS results. History grows as tickers are viewed on Ticker Deep Dive."
    )

    STATUS_COLOR_E = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#6B7FBF"}

    _tr_col1, _tr_col2 = st.columns([3, 1])
    with _tr_col1:
        _tr_ticker = st.text_input(
            "Ticker", value=st.query_params.get("ticker", "AAPL"), max_chars=12,
            placeholder="e.g. AAPL, NVDA, XOM", key="tr_tab_ticker",
            label_visibility="collapsed",
        ).upper().strip()
    with _tr_col2:
        _tr_run = st.button("Analyze", use_container_width=True, type="primary", key="tr_tab_run")

    if _tr_ticker:
        with st.spinner(f"Loading earnings history for {_tr_ticker}…"):
            _tr_earnings = fetch_earnings_dates(_tr_ticker)
            _tr_history  = get_score_history(_tr_ticker, days=730)

        if not _tr_earnings:
            st.warning(f"No earnings data found for **{_tr_ticker}**.")
        else:
            # Build snapshot lookup
            _tr_snap_map: dict = {}
            for snap in _tr_history:
                d = snap.get("snapshot_date")
                if d:
                    try:
                        _d = _dt.date.fromisoformat(str(d))
                        _tr_snap_map[_d] = snap
                    except Exception:
                        pass

            _results = []
            for earning in _tr_earnings:
                _earn_date = earning.get("date")
                if not _earn_date:
                    continue
                try:
                    _earn_d = _dt.date.fromisoformat(str(_earn_date))
                except Exception:
                    continue

                # Find nearest snapshot 7-45 days before
                _candidates = [(d, s) for d, s in _tr_snap_map.items()
                               if 7 <= (_earn_d - d).days <= 45]
                if not _candidates:
                    continue

                _nearest_d, _snap = max(_candidates, key=lambda x: x[0])
                _score = _snap.get("score", 50)
                _prediction = "Beat" if _score >= 60 else "Miss" if _score <= 40 else "No call"
                _surprise = earning.get("eps_surprise_pct", None)
                _actual   = "Beat" if (_surprise or 0) > 0 else "Miss" if (_surprise or 0) < 0 else "Met"
                _correct  = None
                if _prediction != "No call" and _actual != "Met":
                    _correct = _prediction == _actual

                _results.append({
                    "Earnings Date": str(_earn_d),
                    "Score Snap": f"{_score:.0f}",
                    "Prediction": _prediction,
                    "EPS Surprise": f"{_surprise:+.1f}%" if _surprise is not None else "—",
                    "Actual": _actual,
                    "Correct": "" if _correct else ("" if _correct is False else "—"),
                })

            if _results:
                _res_df = pd.DataFrame(_results)
                _hits   = sum(1 for r in _results if r["Correct"] == "")
                _called = sum(1 for r in _results if r["Correct"] in ("", ""))
                if _called > 0:
                    _acc = _hits / _called * 100
                    st.metric(f"Accuracy on {_tr_ticker}", f"{_acc:.0f}%",
                              help=f"{_hits}/{_called} directional calls correct (excludes No call)")
                st.dataframe(_res_df, use_container_width=True, hide_index=True)
                st.caption(
                    "Score ≥60 → predicted Beat · Score ≤40 → predicted Miss · 40-60 → No call. "
                    "Small samples dominate — treat as exploratory context, not a validated edge."
                )
            else:
                st.info("No snapshot data within 7-45 days before past earnings. "
                        "Browse tickers on Ticker Deep Dive to build history.")
    else:
        st.info("Enter a ticker above.")
