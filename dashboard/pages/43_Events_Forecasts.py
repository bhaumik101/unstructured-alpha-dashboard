# pages/43_Events_Forecasts.py
# Unstructured Alpha — Events & Forecasts
# Combines Macro Calendar and Event Impact Forecaster into one page.

import streamlit as st

st.set_page_config(page_title="Events & Forecasts — UA", layout="wide")

from utils.header import render_header, render_sidebar_base, render_page_header, disclose_unavailable_signals
from utils.theme import inject_premium_css

render_header("Events & Forecasts")
_events_section = render_sidebar_base(
    page_title="Events & Forecasts",
    sections=("Macro Calendar", "Event Forecaster"),
    section_key="events_forecasts_section_rail",
)
inject_premium_css()

render_page_header(
    "Events & Forecasts",
    "Upcoming macro events with UA signal alignment and historical market impact.",
    icon="",
)

# Data-integrity disclosure: this page presents/acts on macro-signal scores. If
# any underlying signal is synthetic (no FRED/EIA key or a failed live fetch),
# that must be visible here, not only on the Signal Dashboard. Same cached call
# the page's own logic uses, so no extra network cost.
from utils.signals_cache import get_all_signal_scores as _gas_disc
disclose_unavailable_signals(_gas_disc())

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — MACRO CALENDAR
# ─────────────────────────────────────────────────────────────────────────────
if _events_section == "Macro Calendar":
    from datetime import date, datetime, timedelta
    import pandas as pd
    import plotly.graph_objects as go

    TODAY = date.today()

    EVENTS = [
        dict(name="CPI Release",    category="Inflation",   color="#F59E0B", icon="", series="CPIAUCSL",
             description="Consumer Price Index — the Fed's core inflation gauge.",
             signals=["ten_year_yield","hy_spread","tips_breakeven"],
             dates=["2026-01-15","2026-02-12","2026-03-12","2026-04-10","2026-05-13",
                    "2026-06-11","2026-07-15","2026-08-12","2026-09-11","2026-10-14"]),
        dict(name="FOMC Meeting",   category="Fed Policy",  color="#3B82F6", icon="", series="FEDFUNDS",
             description="Federal Reserve rate decision and policy statement.",
             signals=["ten_year_yield","yield_curve","hy_spread"],
             dates=["2026-01-29","2026-03-19","2026-05-07","2026-06-18","2026-07-30",
                    "2026-09-17","2026-11-05","2026-12-17"]),
        dict(name="NFP Report",     category="Labor",       color="#10B981", icon="", series="PAYEMS",
             description="Non-Farm Payrolls — broadest measure of US labor market strength.",
             signals=["jobless_claims","retail_sales","consumer_sentiment"],
             dates=["2026-01-10","2026-02-07","2026-03-07","2026-04-04","2026-05-09",
                    "2026-06-06","2026-07-11","2026-08-08","2026-09-05","2026-10-03"]),
        dict(name="GDP Advance",    category="Growth",      color="#8B5CF6", icon="", series="GDPC1",
             description="Advance estimate of real GDP growth — the broadest economic measure.",
             signals=["ism_pmi","retail_sales","durable_goods"],
             dates=["2026-01-30","2026-04-30","2026-07-30","2026-10-29"]),
        dict(name="PCE Release",    category="Inflation",   color="#EC4899", icon="", series="PCEPI",
             description="Personal Consumption Expenditures — the Fed's preferred inflation metric.",
             signals=["tips_breakeven","ten_year_yield"],
             dates=["2026-01-31","2026-02-28","2026-03-31","2026-04-30","2026-05-29",
                    "2026-06-30","2026-07-31","2026-08-29","2026-09-30","2026-10-30"]),
    ]

    upcoming = []
    for ev in EVENTS:
        for d_str in ev["dates"]:
            d = date.fromisoformat(d_str)
            if d >= TODAY:
                days_away = (d - TODAY).days
                upcoming.append({**ev, "next_date": d, "days_away": days_away, "date_str": d_str})
                break

    upcoming.sort(key=lambda x: x["days_away"])

    st.markdown("#### Next 30 Days")
    if not upcoming:
        st.info("No upcoming events in schedule.")
    else:
        for ev in upcoming[:8]:
            urgency = "" if ev["days_away"] <= 7 else "" if ev["days_away"] <= 14 else ""
            countdown = f"**Tomorrow**" if ev["days_away"] == 1 else (f"**Today**" if ev["days_away"] == 0 else f"in **{ev['days_away']} days**")
            st.markdown(
                f'<div style="background:rgba(255,255,255,0.025);border:0.5px solid rgba(255,255,255,0.08);'
                f'border-left:4px solid {ev["color"]};border-radius:8px;padding:12px 16px;margin-bottom:8px;'
                f'display:flex;justify-content:space-between;align-items:center;">'
                f'<div>'
                f'<span style="font-size:0.85rem;font-weight:600;color:#E8EEFF;">{ev["icon"]} {ev["name"]}</span>'
                f'<span style="font-size:0.65rem;color:#6B7FBF;margin-left:10px;padding:2px 7px;background:rgba(255,255,255,0.05);border-radius:8px;">{ev["category"]}</span>'
                f'<div style="font-size:0.65rem;color:#8892AA;margin-top:3px;">{ev["description"]}</div>'
                f'</div>'
                f'<div style="text-align:right;flex-shrink:0;margin-left:20px;">'
                f'<div style="font-size:0.85rem;color:#E8EEFF;">{ev["date_str"]}</div>'
                f'<div style="font-size:0.68rem;color:{ev["color"]};">{urgency} {countdown}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("#### Full Calendar")
        all_rows = []
        for ev in EVENTS:
            for d_str in ev["dates"]:
                d = date.fromisoformat(d_str)
                all_rows.append({
                    "Date": d_str, "Event": f"{ev['icon']} {ev['name']}",
                    "Category": ev["category"],
                    "Days Away": (d - TODAY).days,
                    "Key Signals": ", ".join(ev.get("signals", [])[:3]),
                })
        cal_df = pd.DataFrame(all_rows).sort_values("Date")
        cal_df = cal_df[cal_df["Days Away"] >= -7]
        st.dataframe(cal_df.drop(columns=["Days Away"]), use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — EVENT FORECASTER
# ─────────────────────────────────────────────────────────────────────────────
if _events_section == "Event Forecaster":
    import plotly.graph_objects as go

    st.markdown("### UA Signal Alignment for Upcoming Events")
    st.caption(
        "Before each major release, UA checks which signals are aligned with a bullish or bearish outcome. "
        "This is not a point prediction — it's the signal regime heading into the release."
    )

    with st.spinner("Loading signal alignment…"):
        from utils.signals_cache import get_all_signal_scores
        all_sv = get_all_signal_scores()

    EVENT_SIGNAL_MAP = {
        "CPI / Inflation":  ["tips_breakeven","ten_year_yield","hy_spread","michigan_sentiment","food_cpi"],
        "FOMC / Fed":       ["yield_curve","ten_year_yield","hy_spread","vix","copper_gold"],
        "NFP / Labor":      ["jobless_claims","retail_sales","consumer_sentiment","ata_trucking","retail_job_openings"],
        "GDP / Growth":     ["ism_pmi","durable_goods","retail_sales","ata_trucking","rail_traffic"],
        "PCE / Inflation":  ["tips_breakeven","ten_year_yield","vix","consumer_sentiment"],
    }

    for event_name, signal_ids in EVENT_SIGNAL_MAP.items():
        sigs = [sid for sid in signal_ids if sid in all_sv and not all_sv[sid].get("error")]
        if not sigs:
            continue
        bulls = [sid for sid in sigs if all_sv[sid].get("status") == "bullish"]
        bears = [sid for sid in sigs if all_sv[sid].get("status") == "bearish"]
        score = len(bulls) / max(len(sigs), 1) * 100

        if score >= 60:
            lean_color = "#00D566"; lean_text = "Bullish lean"
        elif score <= 40:
            lean_color = "#FF4444"; lean_text = "Bearish lean"
        else:
            lean_color = "#6B7FBF"; lean_text = "Mixed / uncertain"

        with st.expander(f"{event_name}  —  {lean_text} ({score:.0f}/100)", expanded=(score >= 60 or score <= 40)):
            cols = st.columns(len(sigs) if len(sigs) <= 5 else 5)
            for i, sid in enumerate(sigs[:5]):
                sv = all_sv[sid]
                sc = float(sv.get("score", 50))
                st_status = sv.get("status", "neutral")
                c = "#00D566" if st_status=="bullish" else "#FF4444" if st_status=="bearish" else "#6B7FBF"
                with cols[i]:
                    st.markdown(
                        f'<div style="background:rgba(255,255,255,0.03);border:0.5px solid {c}44;'
                        f'border-radius:8px;padding:8px 10px;text-align:center;">'
                        f'<div style="font-size:0.60rem;color:#8892AA;">{sv.get("name",sid)[:20]}</div>'
                        f'<div style="font-size:1.1rem;font-weight:700;color:{c};">{sc:.0f}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            st.markdown(
                f'<div style="margin-top:8px;font-size:0.70rem;color:#8892AA;">'
                f'▲ {len(bulls)} signals bullish · ▼ {len(bears)} bearish · '
                f'{len(sigs)-len(bulls)-len(bears)} neutral heading into this release.</div>',
                unsafe_allow_html=True,
            )

    st.caption(
        "Signal alignment does not predict the release outcome — it shows the macro regime heading in. "
        "A bullish-leaning signal regime into CPI means macro data generally supports lower inflation; "
        "the actual print can still surprise."
    )
