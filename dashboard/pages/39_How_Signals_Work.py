"""
How Signals Work — Unstructured Alpha
Educational methodology page explaining signal construction, scoring, data sources,
and limitations. Public (no login required). SEO-friendly.
"""

import streamlit as st

st.set_page_config(
    page_title="How Macro Signals Work — Unstructured Alpha",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.header import render_header, render_sidebar_base, render_footer
from utils.theme import inject_all_css

render_header("How Signals Work")
inject_all_css()
_method_section = render_sidebar_base(
    page_title="How Signals Work",
    sections=("What Are Signals", "How Scores Work", "Signal Categories", "Data Sources", "Limitations", "FAQ"),
    section_key="how_signals_section_rail",
)

try:
    from utils.analytics import track, Event
    _u = st.session_state.get("user")
    track(Event.HOW_IT_WORKS_VIEWED, user_id=_u.get("id") if _u else None)
except Exception:
    pass


# ── Page header ────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:40px 0 28px;font-family:Inter,sans-serif;">
  <div style="font-size:0.60rem;color:#00D566;letter-spacing:0.18em;font-weight:700;
              text-transform:uppercase;margin-bottom:10px;">Methodology</div>
  <div style="font-size:clamp(1.9rem,3.5vw,2.7rem);font-weight:800;color:#E8EEFF;
              letter-spacing:-1.2px;line-height:1.1;margin-bottom:14px;">
    How macro signals work
  </div>
  <div style="font-size:0.96rem;color:#8892AA;max-width:580px;margin:0 auto;line-height:1.75;">
    Every signal, score, and threshold on Unstructured Alpha explained plainly —
    what the data is, where it comes from, what it means, and what it doesn't mean.
  </div>
</div>
""", unsafe_allow_html=True)

# ── Navigation tabs ────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — What are signals
# ─────────────────────────────────────────────────────────────────────────────
if _method_section == "What Are Signals":
    st.markdown("""
<div style="max-width:780px;margin:28px auto 0;font-family:Inter,sans-serif;">

  <h2 style="font-size:1.25rem;font-weight:700;color:#E8EEFF;margin-bottom:10px;">
    What is a macro signal?
  </h2>
  <p style="color:#8892AA;line-height:1.8;margin-bottom:20px;">
    A macro signal is a publicly available economic or financial data series that has historically
    moved <em>before</em> broad market prices responded. They include things like the shape of
    the yield curve, how wide credit spreads are, how much crude oil is sitting in storage,
    and how aggressively corporate insiders are buying their own company stock.
  </p>
  <p style="color:#8892AA;line-height:1.8;margin-bottom:28px;">
    Unstructured Alpha tracks 43 of these signals across six categories.
    Each one is scored daily on a 0–100 scale. The goal is not to predict individual stock prices —
    it is to give you a clear read on whether the <em>macro environment</em> is supportive
    or hostile to risk assets at any given time.
  </p>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:32px;">
""", unsafe_allow_html=True)

    for _card in [
        ("", "Based on public data", "Every signal uses official government or exchange data sources. No proprietary estimates, no surveys of uncertain reliability."),
        ("", "Historically leading", "We only include signals that have shown statistically measurable lead times ahead of market moves — typically 4 to 16 weeks."),
        ("", "Percentile-scored", "Raw data values are converted to 0–100 percentile scores relative to the past 12 months so they are directly comparable across signals."),
        ("", "Updated every ~2 hours", "Signal data is refreshed approximately every 2 hours from live API feeds. Timestamps are shown on every signal card."),
    ]:
        st.markdown(f"""
<div style="background:rgba(18,21,30,0.7);border:1px solid rgba(255,255,255,0.07);
     border-radius:12px;padding:18px;">
  <div style="font-size:1.4rem;margin-bottom:8px;">{_card[0]}</div>
  <div style="font-size:0.85rem;font-weight:700;color:#E8EEFF;margin-bottom:6px;">{_card[1]}</div>
  <div style="font-size:0.75rem;color:#8892AA;line-height:1.6;">{_card[2]}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
  <div style="background:rgba(107,127,191,0.07);border:1px solid rgba(107,127,191,0.15);
       border-radius:12px;padding:18px 22px;margin-bottom:28px;">
    <div style="font-size:0.75rem;font-weight:700;color:#6B7FBF;letter-spacing:0.1em;
                text-transform:uppercase;margin-bottom:6px;">Important distinction</div>
    <div style="font-size:0.85rem;color:#B8C0D4;line-height:1.7;">
      Macro signals describe the <strong style="color:#E8EEFF;">economic environment</strong>,
      not individual stock price direction. A bullish macro backdrop does not guarantee
      every stock will go up — it means the conditions that have historically supported
      risk-on asset performance are present. Context, not prediction.
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — How scores work
# ─────────────────────────────────────────────────────────────────────────────
if _method_section == "How Scores Work":
    st.markdown("""
<div style="max-width:780px;margin:28px auto 0;font-family:Inter,sans-serif;">

  <h2 style="font-size:1.25rem;font-weight:700;color:#E8EEFF;margin-bottom:10px;">
    How the 0–100 score is calculated
  </h2>
  <p style="color:#8892AA;line-height:1.8;margin-bottom:24px;">
    Every signal score is a <strong style="color:#B8C0D4;">rolling percentile</strong> of the current raw reading
    versus the trailing 252 trading days (approximately one calendar year). A score of 72 means
    the current reading is more bullish than 72% of all daily readings in the past year.
    It is not an arbitrary threshold — it reflects where today sits relative to recent history.
  </p>

  <div style="display:flex;flex-direction:column;gap:10px;margin-bottom:28px;">
""", unsafe_allow_html=True)

    for _row in [
        ("#00D566", "≥ 65", "Bullish zone",  "The signal is in the top third of its 1-year history. Conditions historically associated with risk-on environments."),
        ("#6B7FBF", "35–64", "Neutral zone", "The signal is in the middle range. Neither confirming a strong macro tailwind nor a headwind."),
        ("#FF4444", "≤ 34", "Bearish zone",  "The signal is in the bottom third of its 1-year history. Conditions historically associated with risk-off or defensive positioning."),
    ]:
        st.markdown(f"""
<div style="background:rgba(18,21,30,0.6);border:1px solid rgba(255,255,255,0.07);
     border-radius:10px;padding:14px 18px;display:flex;align-items:flex-start;gap:16px;">
  <div style="flex-shrink:0;min-width:56px;text-align:center;">
    <div style="font-size:1.2rem;font-weight:800;color:{_row[0]};letter-spacing:-0.5px;">{_row[1]}</div>
    <div style="font-size:0.58rem;color:{_row[0]};letter-spacing:0.1em;font-weight:700;
                text-transform:uppercase;margin-top:2px;">{_row[2]}</div>
  </div>
  <div style="font-size:0.80rem;color:#8892AA;line-height:1.65;">{_row[3]}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
  <h3 style="font-size:1.0rem;font-weight:700;color:#E8EEFF;margin-bottom:10px;">
    What is the Confluence Score?
  </h3>
  <p style="color:#8892AA;line-height:1.8;margin-bottom:16px;">
    The <strong style="color:#B8C0D4;">Confluence Score</strong> is a weighted composite of the signals
    most relevant to a specific stock's sector and business model. An energy company
    is weighted more heavily toward crude inventory and rig count signals.
    A semiconductor company gets more weight on capex cycle and credit signals.
  </p>
  <p style="color:#8892AA;line-height:1.8;margin-bottom:24px;">
    The word "confluence" is intentional: a score above 65 means <em>multiple</em>
    relevant signals are simultaneously in bullish territory — not just one.
    A single outlier signal rarely drives the composite far into either extreme.
    When it does, it is usually worth investigating why.
  </p>

  <div style="background:rgba(0,213,102,0.05);border:1px solid rgba(0,213,102,0.18);
       border-radius:12px;padding:18px 22px;margin-bottom:28px;">
    <div style="font-size:0.75rem;font-weight:700;color:#00D566;letter-spacing:0.1em;
                text-transform:uppercase;margin-bottom:6px;">No lookahead bias</div>
    <div style="font-size:0.82rem;color:#B8C0D4;line-height:1.7;">
      Every score is calculated using only data available at the time of calculation.
      Percentile rankings use only historical data up to the current date.
      Backtests in the Signal Backtester page use <code>score.shift(1)</code>
      (yesterday's score drives today's position) to prevent lookahead bias.
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Signal categories
# ─────────────────────────────────────────────────────────────────────────────
if _method_section == "Signal Categories":
    st.markdown("""
<div style="max-width:860px;margin:28px auto 0;font-family:Inter,sans-serif;">
  <p style="color:#8892AA;line-height:1.8;margin-bottom:24px;">
    Unstructured Alpha's 47 signals are grouped into six categories.
    Each category captures a different dimension of the macro environment.
  </p>
""", unsafe_allow_html=True)

    _categories = [
        {
            "icon": "",
            "name": "Rates & Yield Curve",
            "color": "#00C8E0",
            "desc": "The shape of the Treasury yield curve is one of the most studied macroeconomic indicators. An inverted curve (2Y > 10Y) has preceded every U.S. recession since 1955. We track the 10Y–2Y spread, the 10Y Treasury yield level, and TIPS breakeven inflation expectations.",
            "signals": ["10Y–2Y Yield Curve", "10Y Treasury Yield", "TIPS Breakeven Inflation (T10YIE)"],
            "sources": ["FRED", "Yahoo Finance"],
        },
        {
            "icon": "",
            "name": "Credit Spreads",
            "color": "#FF6B6B",
            "desc": "Credit markets move before equity markets. When institutional investors become risk-averse, they demand higher yields on corporate debt, widening spreads. We track high-yield and investment-grade spreads as leading risk sentiment indicators.",
            "signals": ["HY Credit Spread (BAMLH0A0HYM2)", "IG Credit Spread", "Bank Lending Standards"],
            "sources": ["FRED"],
        },
        {
            "icon": "",
            "name": "Energy & Commodities",
            "color": "#F59E0B",
            "desc": "Energy markets reflect real economic activity. EIA weekly inventory data for crude oil and natural gas, rig count trends, and the Copper/Gold ratio (an economic vs. safety-asset barometer) are all included.",
            "signals": ["EIA Crude Inventory Change", "EIA Natural Gas Storage", "Baker Hughes Rig Count", "Copper/Gold Ratio", "Gasoline Price Trend"],
            "sources": ["EIA", "Yahoo Finance"],
        },
        {
            "icon": "",
            "name": "Sentiment & Positioning",
            "color": "#7C3AED",
            "desc": "Fear, greed, and positioning extremes tend to be contrarian or confirming depending on context. We track VIX level and term structure, the CBOE put/call ratio, institutional 13F positioning, and insider buying clusters from SEC Form 4 filings.",
            "signals": ["VIX (CBOE Volatility Index)", "VIX Term Structure (VIX9D–VIX spread)", "CBOE Put/Call Ratio", "Insider Buy Ratio (Form 4)", "Insider Cluster Detection", "13F Institutional Positioning", "Short Interest (FINRA)", "Michigan Consumer Sentiment"],
            "sources": ["CBOE", "SEC EDGAR", "FINRA", "FRED", "Yahoo Finance"],
        },
        {
            "icon": "",
            "name": "Manufacturing & Growth",
            "color": "#00D566",
            "desc": "Manufacturing PMI, jobless claims, and M2 money supply growth capture the real-economy cycle. Slowing manufacturing and rising claims often precede margin compression and earnings disappointments.",
            "signals": ["ISM Manufacturing PMI (FRED NAPM)", "Initial Jobless Claims", "M2 Money Supply Growth", "Industrial Production"],
            "sources": ["FRED"],
        },
        {
            "icon": "",
            "name": "Insider & Alternative",
            "color": "#00C8E0",
            "desc": "SEC-reported insider transactions, congressional trades, and unusual options activity provide a window into informed positioning. These are scored using event-rate methods rather than level percentiles.",
            "signals": ["Congressional Trade Activity", "Unusual Options Activity", "Earnings Transcript Sentiment", "Social Sentiment Index"],
            "sources": ["SEC EDGAR", "EDGAR Congressional Disclosures", "Public API"],
        },
    ]

    for _cat in _categories:
        _sigs_html = "".join(
            f'<span style="font-size:0.68rem;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);'
            f'color:#8892AA;border-radius:5px;padding:2px 8px;white-space:nowrap;">{s}</span> '
            for s in _cat["signals"]
        )
        _srcs_html = "".join(
            f'<span style="font-size:0.65rem;background:rgba(107,127,191,0.08);border:1px solid rgba(107,127,191,0.18);'
            f'color:#6B7FBF;border-radius:5px;padding:2px 8px;font-weight:600;">{s}</span> '
            for s in _cat["sources"]
        )
        st.markdown(f"""
<div style="background:rgba(18,21,30,0.65);border:1px solid rgba(255,255,255,0.07);
     border-radius:14px;padding:20px 24px;margin-bottom:14px;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
    <span style="font-size:1.3rem;">{_cat["icon"]}</span>
    <span style="font-size:1.0rem;font-weight:700;color:{_cat["color"]};">{_cat["name"]}</span>
  </div>
  <p style="font-size:0.80rem;color:#8892AA;line-height:1.7;margin-bottom:12px;">{_cat["desc"]}</p>
  <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px;">{_sigs_html}</div>
  <div style="border-top:1px solid rgba(255,255,255,0.05);padding-top:10px;display:flex;flex-wrap:wrap;gap:5px;align-items:center;">
    <span style="font-size:0.60rem;color:#4A5280;letter-spacing:0.1em;font-weight:700;text-transform:uppercase;margin-right:4px;">Sources:</span>
    {_srcs_html}
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — Data sources
# ─────────────────────────────────────────────────────────────────────────────
if _method_section == "Data Sources":
    st.markdown("""
<div style="max-width:780px;margin:28px auto 0;font-family:Inter,sans-serif;">
  <p style="color:#8892AA;line-height:1.8;margin-bottom:24px;">
    Every data point on Unstructured Alpha comes from official public sources — government agencies,
    regulatory bodies, and exchange-operated feeds. We do not use proprietary estimates,
    paid data vendors, or scraped social media sentiment as primary inputs.
  </p>
""", unsafe_allow_html=True)

    _sources_detail = [
        {
            "name": "FRED — Federal Reserve Economic Data",
            "org":  "Federal Reserve Bank of St. Louis",
            "url":  "https://fred.stlouisfed.org",
            "signals": "Yield curve, credit spreads, M2, jobless claims, CPI, manufacturing PMI, consumer sentiment, TIPS breakeven",
            "notes": "Free public API. No authentication required for standard series. Updated daily or weekly depending on series.",
        },
        {
            "name": "SEC EDGAR — Form 4 Insider Filings",
            "org":  "U.S. Securities and Exchange Commission",
            "url":  "https://www.sec.gov/cgi-bin/browse-edgar",
            "signals": "Insider buy/sell ratios, insider cluster detection, congressional stock trades",
            "notes": "Form 4 filings are required within 2 business days of a transaction. XML feed is fully public.",
        },
        {
            "name": "FINRA — Short Interest Data",
            "org":  "Financial Industry Regulatory Authority",
            "url":  "https://www.finra.org/investors/tools-calculators/short-interest",
            "signals": "Short interest as % of float, short interest trend",
            "notes": "Published twice monthly. Data reflects settlement-date positions, not real-time.",
        },
        {
            "name": "EIA — Energy Information Administration",
            "org":  "U.S. Department of Energy",
            "url":  "https://www.eia.gov",
            "signals": "Weekly crude oil inventory change, natural gas in storage, Baker Hughes rig count",
            "notes": "Weekly releases every Wednesday (crude/gas) and Friday (rig count). Free public API.",
        },
        {
            "name": "CBOE — Volatility & Options Data",
            "org":  "Chicago Board Options Exchange",
            "url":  "https://www.cboe.com",
            "signals": "VIX spot, VIX9D (9-day VIX), VIX term structure, CBOE equity put/call ratio",
            "notes": "Accessed via Yahoo Finance API for historical VIX data. CPCE series also available on FRED.",
        },
        {
            "name": "Yahoo Finance (yfinance)",
            "org":  "Informal market data aggregator",
            "url":  "https://finance.yahoo.com",
            "signals": "Price data for VIX, Treasury yields (^TNX), copper (HG=F), gold (GLD), stock prices",
            "notes": "Used for price-derived signals and ticker Confluence Scores. Best-effort availability — not suitable for mission-critical trading infrastructure.",
        },
    ]

    for _src in _sources_detail:
        st.markdown(f"""
<div style="background:rgba(18,21,30,0.65);border:1px solid rgba(255,255,255,0.07);
     border-radius:13px;padding:18px 22px;margin-bottom:12px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
    <div>
      <div style="font-size:0.90rem;font-weight:700;color:#E8EEFF;margin-bottom:2px;">{_src["name"]}</div>
      <div style="font-size:0.70rem;color:#6B7FBF;">{_src["org"]}</div>
    </div>
  </div>
  <div style="margin-top:10px;font-size:0.78rem;color:#8892AA;line-height:1.65;">
    <strong style="color:#B8C0D4;">Signals:</strong> {_src["signals"]}
  </div>
  <div style="margin-top:6px;font-size:0.75rem;color:#6B7FBF;line-height:1.6;">
    <strong>Notes:</strong> {_src["notes"]}
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — Limitations
# ─────────────────────────────────────────────────────────────────────────────
if _method_section == "Limitations":
    st.markdown("""
<div style="max-width:780px;margin:28px auto 0;font-family:Inter,sans-serif;">
  <h2 style="font-size:1.15rem;font-weight:700;color:#E8EEFF;margin-bottom:10px;">
    What Unstructured Alpha does not do
  </h2>
  <p style="color:#8892AA;line-height:1.8;margin-bottom:24px;">
    We believe transparent limitations are a feature, not a weakness.
    This section exists so you can make an informed decision about how to use this tool.
  </p>
""", unsafe_allow_html=True)

    _limits = [
        ("Not price predictions", "Signal scores describe the macro <em>environment</em>. A score of 80 does not mean the market will go up. It means the macro backdrop is historically supportive. Markets can decline sharply even in favorable macro environments, and they can rally hard in hostile ones."),
        ("Signals can stay extreme", "A signal in the bearish zone can stay bearish for many months. 'Oversold' in macro terms is not the same as a short-term mean reversion in price. Do not use these scores as short-term trading triggers."),
        ("Coverage is organic", "Score history is only built for tickers that users have searched. We do not run a nightly batch across every stock in the market. The universe covered by historical data grows with user activity."),
        ("Data source delays", "FINRA short interest is updated twice monthly, not daily. Congressional trade disclosures lag by up to 45 days. Form 4 insider filings are required within 2 days but often arrive late. Signal freshness is shown on every card."),
        ("Not investment advice", "This platform is educational and informational only. Nothing here is personalized financial advice. We are not registered investment advisers. Always consult a licensed professional before making investment decisions."),
        ("Model validation is ongoing", "We publish our validation results publicly on the Model Validation page. Some signals have stronger lead-time evidence than others. We label validation status honestly — including when a signal lacks sufficient out-of-sample data."),
        ("Yahoo Finance data quality", "Price data accessed via the yfinance library is best-effort and may have gaps, stale values, or API errors. Pages that rely on this source show error states when data is unavailable rather than silently serving stale data."),
    ]

    for _i, (_title, _desc) in enumerate(_limits):
        st.markdown(f"""
<div style="background:rgba(18,21,30,0.55);border:1px solid rgba(255,255,255,0.06);
     border-left:3px solid rgba(255,68,68,0.4);border-radius:0 12px 12px 0;
     padding:16px 20px;margin-bottom:10px;">
  <div style="font-size:0.85rem;font-weight:700;color:#E8EEFF;margin-bottom:5px;">{_title}</div>
  <div style="font-size:0.78rem;color:#8892AA;line-height:1.7;">{_desc}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("""
  <div style="background:rgba(255,68,68,0.05);border:1px solid rgba(255,68,68,0.2);
       border-radius:12px;padding:18px 22px;margin-top:20px;margin-bottom:28px;">
    <div style="font-size:0.75rem;font-weight:700;color:#FF6B6B;letter-spacing:0.1em;
                text-transform:uppercase;margin-bottom:6px;">Full disclaimer</div>
    <div style="font-size:0.78rem;color:#B8C0D4;line-height:1.75;">
      Unstructured Alpha is an educational and informational platform only.
      Nothing on this platform constitutes personalized financial, investment,
      tax, or legal advice. Macro signal scores reflect historical percentile rankings
      of public economic data and are not guarantees of future performance.
      They should not be interpreted as recommendations to buy, sell, or hold any security.
      Always consult a licensed financial adviser before making investment decisions.
      Past signal behavior is not indicative of future results.
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 6 — FAQ
# ─────────────────────────────────────────────────────────────────────────────
if _method_section == "FAQ":
    st.markdown("<div style='max-width:780px;margin:28px auto 0;'>", unsafe_allow_html=True)

    _faqs = [
        ("What does a score of 50 mean?",
         "A score of 50 means the current signal reading is exactly at the median of the past year's readings — neither unusually high nor low. It signals no particular macro tailwind or headwind from that specific indicator."),

        ("Why do some signals show 'Insufficient data'?",
         "Some signals require a minimum number of data points to calculate a reliable percentile. If a series has been recently added or if the data source returned too few observations, the signal defaults to 'insufficient data' rather than showing a potentially misleading score."),

        ("How often does data refresh?",
         "Most signals refresh approximately every 2 hours via Streamlit's cache layer. FRED economic series refresh daily or weekly depending on release frequency. Short interest (FINRA) is biweekly. The timestamp on each signal card shows the last confirmed data point."),

        ("What is the rolling window?",
         "252 trading days — approximately one calendar year. This captures a full economic cycle of seasonal variation without overweighting distant historical regimes. A shorter window (e.g., 90 days) would be too sensitive to recent extremes. A longer window would dilute the signal's responsiveness."),

        ("How is the Confluence Score weighted?",
         "Sector-relevant signals receive higher weights for each stock. A semiconductor company has higher weighting on credit spreads, M2, and capex indicators. An energy company has higher weighting on crude inventory, rig count, and oil price trend. The exact weights are defined in our open configuration file."),

        ("Can I trust the backtest results on the Signal Backtester page?",
         "The backtest uses a strict no-lookahead rule (yesterday's score drives today's position), includes 0.1% round-trip transaction costs, and compares performance to a buy-and-hold SPY benchmark. However, backtest performance is inherently optimistic — it does not capture liquidity, slippage, behavioral friction, or regime changes that break historical patterns. Treat it as exploratory context, not a proof of future returns."),

        ("Why isn't [specific signal X] included?",
         "We only add signals that clear two bars: (1) the data must be consistently available from a public source, and (2) the signal must show statistically meaningful lead time in our lag-scan analysis. Many popular indicators fail one or both of these requirements. We prefer 43 well-validated signals over 200 noisy ones."),

        ("What's the difference between this and a Bloomberg Terminal?",
         "Bloomberg Terminal costs approximately $27,000/year and is designed for professional institutional desks. It provides real-time pricing, news, messaging, and a full universe of financial data tools. Unstructured Alpha focuses specifically on the macro signal layer — the 'should I be risk-on or risk-off right now' question — at $20/month for active individual investors. Different scope, different audience, very different price."),
    ]

    for _q, _a in _faqs:
        with st.expander(_q):
            st.markdown(f'<div style="font-size:0.82rem;color:#8892AA;line-height:1.8;padding:6px 0;">{_a}</div>',
                        unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ── Bottom CTA ─────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("""
<div style="background:rgba(0,213,102,0.04);border:1px solid rgba(0,213,102,0.15);
     border-radius:16px;padding:28px;text-align:center;max-width:620px;margin:0 auto 40px;
     font-family:Inter,sans-serif;">
  <div style="font-size:1.1rem;font-weight:700;color:#E8EEFF;margin-bottom:8px;">
    See the signals live
  </div>
  <div style="font-size:0.82rem;color:#8892AA;margin-bottom:20px;line-height:1.7;">
    The Signal Dashboard shows all 47 signals with live scores, trend direction,
    and the regime read. No account required to browse.
  </div>
""", unsafe_allow_html=True)

_c1, _c2, _c3 = st.columns([2, 1.5, 2])
with _c2:
    if st.button("→ Open Signal Dashboard", type="primary", use_container_width=True, key="hsw_cta"):
        st.switch_page("pages/1_Signal_Dashboard.py")

st.markdown("""
  <div style="margin-top:16px;font-size:0.72rem;color:#6B7FBF;">
    Also see: <a href="#" style="color:#6B7FBF;">Model Validation</a> ·
    <a href="#" style="color:#6B7FBF;">About & Methodology</a> ·
    <a href="#" style="color:#6B7FBF;">Track Record</a>
  </div>
</div>
""", unsafe_allow_html=True)

render_footer()
