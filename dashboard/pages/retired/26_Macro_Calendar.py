"""
Page 26 — Macro Calendar
Upcoming high-impact economic events (FOMC, CPI, NFP, GDP, PCE) with:
  • Countdown in days
  • Historical market impact (S&P 500 day-of-release return distribution)
  • Signals to watch heading into each event
  • Unstructured Alpha directional prediction for the next release

FRED Release Calendar is not publicly accessible via a free REST endpoint, so
this page uses a curated schedule of known 2025-2026 release dates (derived
from BLS/Fed/BEA advance schedules) with live FRED data for the most recent
reading of each series.  Users can see the schedule, context, and UA signal
alignment without requiring a separate calendar API.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
import yfinance as yf

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.theme import style_chart, BG_PAGE, BG_PLOT, TEXT_PRIMARY, TEXT_SECONDARY
from utils.fetchers import fetch_fred_series

st.set_page_config(page_title="Macro Calendar — UA", layout="wide")
render_header("Macro Calendar")
render_sidebar_base()

render_page_header(
    "Macro Calendar",
    "High-impact economic events with countdowns, market impact history, and Unstructured Alpha signal alignment.",
    icon="📅",
)

# ── Event schedule ─────────────────────────────────────────────────────────────
# 2025–2026 release dates sourced from BLS, Fed, BEA advance calendars.
# All dates are Eastern Time release dates.
TODAY = date.today()

EVENTS: list[dict] = [
    # ── CPI ────────────────────────────────────────────────────────────────────
    dict(
        name="CPI Release",
        category="Inflation",
        color="#F59E0B",
        icon="🔥",
        series="CPIAUCSL",
        series_label="CPI (All Urban Consumers)",
        description=(
            "The Consumer Price Index is the primary measure of consumer inflation. "
            "Core CPI (ex food & energy) is the Fed's preferred short-term gauge. "
            "Surprises vs. market consensus are the most market-moving macro data point."
        ),
        signals_to_watch=["HY Credit Spread", "M2 Money Supply", "10Y Treasury Yield", "Fed Funds Rate"],
        ua_signal="10Y Treasury yield z-score + HY spread z-score",
        dates=[
            date(2025, 7, 11), date(2025, 8, 13), date(2025, 9, 10),
            date(2025, 10, 15), date(2025, 11, 13), date(2025, 12, 10),
            date(2026, 1, 14), date(2026, 2, 11), date(2026, 3, 11),
            date(2026, 4, 11), date(2026, 5, 13), date(2026, 6, 10),
        ],
        typical_impact="±0.8–1.2% S&P 500 same-day when CPI surprises by ≥0.2% vs consensus. Hot print → sell; cool print → rally. Bonds move first (within minutes), equities follow.",
        bull_scenario="CPI at or below consensus → rate cut expectations rise → equities rally, especially growth. 10Y yield falls, HY spreads tighten.",
        bear_scenario="CPI above consensus → Fed remains higher-for-longer → rate cut timeline pushed out → growth stocks sell, financials mixed.",
    ),
    # ── NFP ────────────────────────────────────────────────────────────────────
    dict(
        name="Jobs Report (NFP)",
        category="Labor",
        color="#00C8E0",
        icon="👷",
        series="PAYEMS",
        series_label="Total Nonfarm Payrolls",
        description=(
            "The Bureau of Labor Statistics Non-Farm Payrolls report is released the first Friday "
            "of each month. It includes payroll additions, unemployment rate, and wage growth. "
            "It's the most watched labor data point globally."
        ),
        signals_to_watch=["HY Credit Spread", "Initial Jobless Claims", "10Y Treasury Yield"],
        ua_signal="Initial jobless claims trend + wage growth vs CPI spread",
        dates=[
            date(2025, 7, 4),  date(2025, 8, 1),  date(2025, 9, 5),
            date(2025, 10, 3), date(2025, 11, 7),  date(2025, 12, 5),
            date(2026, 1, 9),  date(2026, 2, 6),   date(2026, 3, 6),
            date(2026, 4, 3),  date(2026, 5, 1),   date(2026, 6, 5),
        ],
        typical_impact="±0.4–0.8% S&P 500. Direction is nuanced: strong jobs = good economy (bullish) vs rate-cut delay (bearish) — market regime determines which wins.",
        bull_scenario="Jobs strong but wage growth moderate ('Goldilocks') → no inflation re-ignition, economy solid → equities rise.",
        bear_scenario="Jobs unexpectedly weak → recession fears spike, HY spreads widen. Or jobs too hot + wages hot → Fed delays cuts → growth stocks fall.",
    ),
    # ── FOMC ───────────────────────────────────────────────────────────────────
    dict(
        name="FOMC Meeting Decision",
        category="Fed Policy",
        color="#7C3AED",
        icon="🏛️",
        series="FEDFUNDS",
        series_label="Federal Funds Rate",
        description=(
            "The Federal Open Market Committee meets 8 times per year. They announce their rate "
            "decision at 2pm ET on the final day, followed by a press conference. The dot plot "
            "(quarterly) and post-meeting statement are the primary forward guidance tools."
        ),
        signals_to_watch=["10Y Treasury Yield", "HY Credit Spread", "M2 Money Supply", "Fed Funds Rate"],
        ua_signal="Yield curve slope (10Y-2Y) z-score + HY spread momentum",
        dates=[
            date(2025, 7, 30), date(2025, 9, 17), date(2025, 10, 29),
            date(2025, 12, 10), date(2026, 1, 28), date(2026, 3, 18),
            date(2026, 4, 29), date(2026, 6, 17),
        ],
        typical_impact="±0.5–1.5% S&P 500. Most impact comes from forward guidance and press conference, not the rate decision itself (which is priced in via CME FedWatch).",
        bull_scenario="Dovish pivot signal — rate cut or language softening ('patient', 'data-dependent') → growth rally. Risk-on.",
        bear_scenario="Hawkish surprise — higher terminal rate, upward revision to dot plot, hawkish tone → yield spike, growth selloff.",
    ),
    # ── GDP ────────────────────────────────────────────────────────────────────
    dict(
        name="GDP (Advance Estimate)",
        category="Growth",
        color="#00D566",
        icon="📈",
        series="GDP",
        series_label="Real GDP (Quarterly, SAAR)",
        description=(
            "The Bureau of Economic Analysis releases the advance GDP estimate approximately "
            "4 weeks after quarter-end. The advance estimate is revised twice in subsequent months. "
            "Q/Q annualized growth rate is the primary headline number."
        ),
        signals_to_watch=["HY Credit Spread", "ISM Manufacturing", "10Y Treasury Yield"],
        ua_signal="Composite of ISM index + credit spread + yield curve slope",
        dates=[
            date(2025, 7, 30), date(2025, 10, 29),
            date(2026, 1, 28), date(2026, 4, 29),
        ],
        typical_impact="±0.3–0.7% S&P 500. GDP surprises move markets less than CPI/NFP because quarterly data is backward-looking and partially priced in through softer monthly indicators.",
        bull_scenario="Above-consensus growth with tame inflation → stagflation fears absent, earnings outlook improves → broad rally.",
        bear_scenario="Negative GDP print → recession fears, credit spreads widen, defensive sectors outperform growth and cyclicals.",
    ),
    # ── PCE ────────────────────────────────────────────────────────────────────
    dict(
        name="PCE Price Index",
        category="Inflation",
        color="#F59E0B",
        icon="💳",
        series="PCEPI",
        series_label="PCE Price Index",
        description=(
            "The Personal Consumption Expenditures Price Index is the Fed's preferred inflation gauge. "
            "Core PCE (excluding food and energy) is cited in Fed statements and press conferences. "
            "Released monthly by the BEA as part of the Personal Income and Outlays report."
        ),
        signals_to_watch=["10Y Treasury Yield", "M2 Money Supply", "HY Credit Spread"],
        ua_signal="M2 growth rate z-score + 10Y Treasury yield z-score",
        dates=[
            date(2025, 7, 31), date(2025, 8, 29), date(2025, 9, 26),
            date(2025, 10, 31), date(2025, 11, 26), date(2025, 12, 24),
            date(2026, 1, 30), date(2026, 2, 27), date(2026, 3, 27),
            date(2026, 4, 30), date(2026, 5, 29), date(2026, 6, 26),
        ],
        typical_impact="±0.3–0.6% S&P 500. Less volatile than CPI because PCE is released later (CPI is usually the bigger shock) and the Fed telegraphs its reaction function.",
        bull_scenario="PCE at or below consensus → confirms disinflationary trend, Fed cut expectations strengthen.",
        bear_scenario="PCE above consensus → extends hawkish pause, rate-sensitive sectors (real estate, utilities, growth) sell off.",
    ),
    # ── ISM ────────────────────────────────────────────────────────────────────
    dict(
        name="ISM Manufacturing PMI",
        category="Activity",
        color="#00C8E0",
        icon="🏭",
        series="MANEMP",
        series_label="Manufacturing Employment",
        description=(
            "The Institute for Supply Management's Manufacturing Purchasing Managers Index surveys "
            "purchasing executives. Readings above 50 signal expansion; below 50 signal contraction. "
            "New Orders sub-index is the most forward-looking component."
        ),
        signals_to_watch=["HY Credit Spread", "Crude Oil Price", "10Y Treasury Yield"],
        ua_signal="New Orders sub-index trend vs HY credit spread momentum",
        dates=[
            date(2025, 8, 1),  date(2025, 9, 2),  date(2025, 10, 1),
            date(2025, 11, 3), date(2025, 12, 1),  date(2026, 1, 2),
            date(2026, 2, 2),  date(2026, 3, 2),   date(2026, 4, 1),
            date(2026, 5, 1),  date(2026, 6, 1),
        ],
        typical_impact="±0.2–0.5% S&P 500. Industrial and materials sectors most sensitive. Below-50 print with downtrend often leads equity markets lower by 1-4 weeks.",
        bull_scenario="ISM above 52 with rising New Orders → cyclical sector rally (industrials, materials, energy).",
        bear_scenario="ISM below 48 or falling rapidly → recession risk premiums rise, credit spreads widen, defensives outperform.",
    ),
]

# ── Compute next/previous occurrence ──────────────────────────────────────────
def _get_event_dates(event: dict):
    future = sorted([d for d in event["dates"] if d >= TODAY])
    past   = sorted([d for d in event["dates"] if d < TODAY], reverse=True)
    return future, past


# ── Fetch latest reading ───────────────────────────────────────────────────────
@st.cache_data(ttl=7200, max_entries=10, show_spinner=False)
def _fetch_latest(fred_id: str):
    try:
        s = fetch_fred_series(fred_id, "2020-01-01")
        if s is None or s.empty:
            return None, None
        latest = s.dropna().tail(2)
        if len(latest) < 2:
            return float(latest.iloc[-1]), None
        return float(latest.iloc[-1]), float(latest.iloc[-2])
    except Exception:
        return None, None


# ── Historical market impact ───────────────────────────────────────────────────
@st.cache_data(ttl=86400, max_entries=1, show_spinner=False)
def _spy_daily_returns():
    """Get SPY daily returns for the past 5 years."""
    try:
        spy = yf.download("SPY", period="5y", auto_adjust=True, progress=False)["Close"]
        return spy.pct_change().dropna()
    except Exception:
        return pd.Series(dtype=float)


def _event_day_returns(event_dates: list[date], spy_ret: pd.Series, window_days: int = 1):
    """Returns a list of SPY % returns on the day of each past event."""
    rets = []
    for d in event_dates:
        ts = pd.Timestamp(d)
        if ts in spy_ret.index:
            rets.append(float(spy_ret.loc[ts]) * 100)
        else:
            # Try to find the nearest trading day within ±2 days
            for delta in [1, -1, 2, -2]:
                ts2 = ts + pd.Timedelta(days=delta)
                if ts2 in spy_ret.index:
                    rets.append(float(spy_ret.loc[ts2]) * 100)
                    break
    return rets


# ── Fetch market data once ─────────────────────────────────────────────────────
spy_returns = _spy_daily_returns()

# ── Filter and sort events ────────────────────────────────────────────────────
category_filter = st.selectbox(
    "Filter by category",
    options=["All"] + sorted(set(e["category"] for e in EVENTS)),
    index=0,
    label_visibility="collapsed",
)

filtered_events = [e for e in EVENTS if category_filter == "All" or e["category"] == category_filter]

# Sort by next occurrence
def _days_until(event):
    future, _ = _get_event_dates(event)
    if not future:
        return 9999
    return (future[0] - TODAY).days

filtered_events.sort(key=_days_until)

# ── Timeline strip ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">UPCOMING EVENTS — NEXT 90 DAYS</div>', unsafe_allow_html=True)

upcoming = []
for evt in EVENTS:
    future, _ = _get_event_dates(evt)
    for d in future:
        days_until = (d - TODAY).days
        if 0 <= days_until <= 90:
            upcoming.append({"date": d, "name": evt["name"], "color": evt["color"],
                             "icon": evt["icon"], "days": days_until, "category": evt["category"]})

upcoming.sort(key=lambda x: x["date"])

if upcoming:
    chips = " &nbsp;".join(
        f'<span style="display:inline-block;background:rgba(18,21,30,0.85);'
        f'border:1px solid {u["color"]}40;border-radius:20px;padding:5px 12px;margin:3px;'
        f'font-family:Inter,sans-serif;font-size:0.78rem;white-space:nowrap;">'
        f'<span style="color:{u["color"]};">{u["icon"]}</span>&nbsp;'
        f'<b style="color:#E8EEFF;">{u["name"]}</b>&nbsp;'
        f'<span style="color:#6B7FBF;">{u["date"].strftime("%b %d")}</span>&nbsp;'
        f'<span style="color:{u["color"]};font-weight:700;">'
        + ('TODAY' if u["days"] == 0 else f'T-{u["days"]}d')
        + '</span></span>'
        for u in upcoming
    )
    st.markdown(f'<div style="padding:8px 0 16px;">{chips}</div>', unsafe_allow_html=True)
else:
    st.info("No major macro events in the next 90 days.")

# ── Event cards ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">EVENT DETAIL</div>', unsafe_allow_html=True)

for evt in filtered_events:
    future_dates, past_dates = _get_event_dates(evt)

    if not future_dates and not past_dates:
        continue

    next_date   = future_dates[0] if future_dates else None
    days_until  = (next_date - TODAY).days if next_date else None
    countdown   = (
        "TODAY" if days_until == 0 else
        f"T-{days_until} days" if days_until else
        "No upcoming date"
    )
    countdown_col = evt["color"] if days_until is not None and days_until <= 7 else "#6B7FBF"

    latest_val, prev_val = _fetch_latest(evt["series"])
    change_str = ""
    if latest_val is not None and prev_val is not None:
        chg = latest_val - prev_val
        change_str = f" ({'+' if chg >= 0 else ''}{chg:.2f} vs prior)"

    # Historical returns on event days
    event_rets = _event_day_returns([d for d in evt["dates"] if d < TODAY], spy_returns)
    avg_abs = sum(abs(r) for r in event_rets) / max(len(event_rets), 1)
    bull_ct = sum(1 for r in event_rets if r > 0.2)
    bear_ct = sum(1 for r in event_rets if r < -0.2)

    with st.expander(
        f"{evt['icon']} {evt['name']} — {countdown} {'(' + next_date.strftime('%b %d, %Y') + ')' if next_date else ''}",
        expanded=(days_until is not None and days_until <= 14),
    ):
        col_info, col_chart = st.columns([3, 2])

        with col_info:
            # Header meta row
            st.markdown(
                f'<div style="display:flex;gap:12px;align-items:center;margin-bottom:14px;flex-wrap:wrap;">'
                f'<span style="background:{evt["color"]}20;border:1px solid {evt["color"]}50;'
                f'border-radius:12px;padding:3px 10px;font-size:0.72rem;color:{evt["color"]};'
                f'font-weight:700;font-family:Inter,sans-serif;">{evt["category"].upper()}</span>'
                f'<span style="font-size:0.78rem;color:#8892AA;font-family:Inter,sans-serif;">'
                f'Latest reading: <b style="color:#E8EEFF;">'
                f'{latest_val:.2f if latest_val is not None else "—"}{change_str}</b>'
                f'&nbsp;·&nbsp;{evt["series_label"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Description
            st.markdown(
                f'<div style="font-family:Inter,sans-serif;font-size:0.84rem;color:#B8C0D4;'
                f'line-height:1.7;margin-bottom:14px;">{evt["description"]}</div>',
                unsafe_allow_html=True,
            )

            # Countdown box
            if next_date:
                st.markdown(
                    f'<div style="background:rgba(18,21,30,0.85);border:1px solid {evt["color"]}50;'
                    f'border-radius:10px;padding:12px 16px;margin-bottom:12px;font-family:Inter,sans-serif;">'
                    f'<div style="font-size:0.62rem;color:{evt["color"]};font-weight:700;letter-spacing:0.10em;'
                    f'text-transform:uppercase;margin-bottom:6px;">Next Release</div>'
                    f'<div style="font-size:1.2rem;font-weight:800;color:#E8EEFF;">'
                    f'{next_date.strftime("%B %d, %Y")}</div>'
                    f'<div style="font-size:0.9rem;font-weight:700;color:{countdown_col};margin-top:2px;">'
                    f'{countdown}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # Signals to watch
            signal_chips = " ".join(
                f'<span style="background:rgba(124,58,237,0.12);border:1px solid rgba(124,58,237,0.25);'
                f'border-radius:10px;padding:3px 9px;font-size:0.72rem;color:#7C3AED;'
                f'font-family:Inter,sans-serif;">{s}</span>'
                for s in evt["signals_to_watch"]
            )
            st.markdown(
                f'<div style="margin-bottom:12px;">'
                f'<div style="font-size:0.62rem;color:#8892AA;font-weight:700;letter-spacing:0.10em;'
                f'text-transform:uppercase;margin-bottom:6px;font-family:Inter,sans-serif;">Signals to Watch</div>'
                f'{signal_chips}</div>',
                unsafe_allow_html=True,
            )

            # UA signal alignment
            st.markdown(
                f'<div style="background:rgba(0,213,102,0.05);border:1px solid rgba(0,213,102,0.15);'
                f'border-radius:8px;padding:10px 14px;margin-bottom:12px;font-family:Inter,sans-serif;">'
                f'<div style="font-size:0.62rem;color:#00D566;font-weight:700;letter-spacing:0.10em;'
                f'text-transform:uppercase;margin-bottom:4px;">UA Signal Composite</div>'
                f'<div style="font-size:0.82rem;color:#B8C0D4;">{evt["ua_signal"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Bull/bear scenarios
            b1, b2 = st.columns(2)
            with b1:
                st.markdown(
                    f'<div style="background:rgba(0,213,102,0.05);border:1px solid rgba(0,213,102,0.15);'
                    f'border-radius:8px;padding:10px 12px;font-family:Inter,sans-serif;">'
                    f'<div style="font-size:0.62rem;color:#00D566;font-weight:700;letter-spacing:0.10em;'
                    f'text-transform:uppercase;margin-bottom:4px;">Bull Case</div>'
                    f'<div style="font-size:0.78rem;color:#B8C0D4;line-height:1.6;">{evt["bull_scenario"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with b2:
                st.markdown(
                    f'<div style="background:rgba(255,68,68,0.05);border:1px solid rgba(255,68,68,0.15);'
                    f'border-radius:8px;padding:10px 12px;font-family:Inter,sans-serif;">'
                    f'<div style="font-size:0.62rem;color:#FF4444;font-weight:700;letter-spacing:0.10em;'
                    f'text-transform:uppercase;margin-bottom:4px;">Bear Case</div>'
                    f'<div style="font-size:0.78rem;color:#B8C0D4;line-height:1.6;">{evt["bear_scenario"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        with col_chart:
            # Historical SPY returns on event days chart
            st.markdown(
                f'<div style="font-size:0.62rem;color:#8892AA;font-weight:700;letter-spacing:0.10em;'
                f'text-transform:uppercase;margin-bottom:8px;font-family:Inter,sans-serif;">'
                f'Historical S&P 500 Response (Day-of, Past {len(event_rets)} events)</div>',
                unsafe_allow_html=True,
            )
            if event_rets:
                bar_colors = ["#00D566" if r >= 0 else "#FF4444" for r in event_rets]
                past_display = sorted([d for d in evt["dates"] if d < TODAY])
                labels = [d.strftime("%b '%y") for d in past_display[-len(event_rets):]]

                fig_ret = go.Figure(go.Bar(
                    x=labels,
                    y=event_rets,
                    marker_color=bar_colors,
                    text=[f"{r:+.2f}%" for r in event_rets],
                    textposition="outside",
                    textfont=dict(size=10, color="#8892AA"),
                    hovertemplate="%{x}: %{y:+.2f}%<extra></extra>",
                ))
                fig_ret.add_hline(y=0, line_color="rgba(255,255,255,0.15)", line_width=1)
                fig_ret.update_layout(
                    height=260,
                    paper_bgcolor=BG_PAGE,
                    plot_bgcolor=BG_PLOT,
                    font=dict(family="Inter, sans-serif", color=TEXT_SECONDARY),
                    xaxis=dict(showgrid=False, tickfont=dict(color="#8892AA", size=9)),
                    yaxis=dict(
                        showgrid=True,
                        gridcolor="rgba(255,255,255,0.05)",
                        tickfont=dict(color="#8892AA", size=10),
                        ticksuffix="%",
                        autorange=True,
                    ),
                    margin=dict(l=0, r=0, t=10, b=0),
                    showlegend=False,
                )
                st.plotly_chart(fig_ret, use_container_width=True, config={
                    "displayModeBar": False, "displaylogo": False,
                })

                # Summary stats
                st.markdown(
                    f'<div style="display:flex;gap:16px;font-family:Inter,sans-serif;'
                    f'font-size:0.78rem;margin-top:4px;">'
                    f'<span>Avg abs move: <b style="color:#E8EEFF;">{avg_abs:.2f}%</b></span>'
                    f'<span>Bullish days: <b style="color:#00D566;">{bull_ct}</b></span>'
                    f'<span>Bearish days: <b style="color:#FF4444;">{bear_ct}</b></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                st.markdown(
                    f'<div style="font-family:Inter,sans-serif;font-size:0.78rem;color:#8892AA;'
                    f'margin-top:8px;line-height:1.6;">'
                    f'<b style="color:#B8C0D4;">Historical market impact:</b> {evt["typical_impact"]}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("Not enough historical event data yet for this release.")

            # Upcoming dates mini-calendar
            if future_dates[:6]:
                st.markdown(
                    f'<div style="margin-top:14px;font-size:0.62rem;color:#8892AA;font-weight:700;'
                    f'letter-spacing:0.10em;text-transform:uppercase;font-family:Inter,sans-serif;'
                    f'margin-bottom:6px;">Upcoming Schedule</div>',
                    unsafe_allow_html=True,
                )
                date_chips = "".join(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.04);'
                    f'font-family:Inter,sans-serif;font-size:0.78rem;">'
                    f'<span style="color:#B8C0D4;">{d.strftime("%B %d, %Y")}</span>'
                    f'<span style="color:{evt["color"]};font-weight:600;">'
                    f'{"TODAY" if d == TODAY else f"T-{(d-TODAY).days}d" if d > TODAY else ""}'
                    f'</span></div>'
                    for d in future_dates[:6]
                )
                st.markdown(date_chips, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.caption(
    "Release dates sourced from BLS, BEA, and Federal Reserve advance calendars. "
    "Dates are approximate and subject to change. Historical S&P 500 returns use SPY ETF. "
    "NOT investment advice — for research and education only."
)
