"""
How Signals Work — Unstructured Alpha
Educational methodology page explaining signal construction, scoring, data sources,
and limitations. Public (no login required). SEO-friendly.
"""

from collections import Counter

import streamlit as st

from utils.config import SIGNALS
from utils.product_metrics import (
    ACTIVE_SIGNAL_COUNT,
    PRO_PRICE_MONTHLY,
    SCORE_REFRESH_DESCRIPTION,
    signal_sources_phrase,
)
from utils.provider_health import canonical_provider, provider_label

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
    sections=("What Are Signals", "How Scores Work", "Why It Works", "Signal Categories", "Data Sources", "Limitations", "FAQ"),
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
  <div style="font-size:0.60rem;color:var(--ua-green);letter-spacing:0.18em;font-weight:700;
              text-transform:uppercase;margin-bottom:10px;">Methodology</div>
  <div style="font-size:clamp(1.9rem,3.5vw,2.7rem);font-weight:800;color:var(--ua-ink);
              letter-spacing:-1.2px;line-height:1.1;margin-bottom:14px;">
    How macro signals work
  </div>
  <div style="font-size:0.96rem;color:var(--ua-ink-mut);max-width:580px;margin:0 auto;line-height:1.75;">
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
    st.markdown(f"""
<div style="max-width:780px;margin:28px auto 0;font-family:Inter,sans-serif;">

  <h2 style="font-size:1.25rem;font-weight:700;color:var(--ua-ink);margin-bottom:10px;">
    What is a macro signal?
  </h2>
  <p style="color:var(--ua-ink-mut);line-height:1.8;margin-bottom:20px;">
    A macro signal is a publicly available economic or financial data series that has historically
    moved <em>before</em> broad market prices responded. They include things like the shape of
    the yield curve, how wide credit spreads are, how much crude oil is sitting in storage,
    and how physical freight or supply-chain pressure is changing.
  </p>
  <p style="color:var(--ua-ink-mut);line-height:1.8;margin-bottom:28px;">
    Unstructured Alpha tracks {ACTIVE_SIGNAL_COUNT} of these signals across six research categories.
    Each one is scored daily on a 0–100 scale. The goal is not to predict individual stock prices —
    it is to give you a clear read on whether the <em>macro environment</em> is supportive
    or hostile to risk assets at any given time.
  </p>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:32px;">
""", unsafe_allow_html=True)

    for _card in [
        ("", "Based on attributable data", f"The registry currently draws from {signal_sources_phrase(limit=20)}. Every reading retains its provider and timestamp."),
        ("", "Lead-time tested", "Each signal has an intended lead window and can be evaluated against forward returns. Validation status is shown rather than assumed."),
        ("", "Percentile-scored", "Raw data values are converted to 0–100 percentile scores relative to the past 12 months so they are directly comparable across signals."),
        ("", SCORE_REFRESH_DESCRIPTION.capitalize(), "The platform refreshes provider data on its configured cadence. The underlying release date remains visible on each signal."),
    ]:
        st.markdown(f"""
<div style="background:rgba(var(--ua-card-rgb),0.7);border:1px solid rgba(var(--ua-onbg-rgb),0.07);
     border-radius:12px;padding:18px;">
  <div style="font-size:1.4rem;margin-bottom:8px;">{_card[0]}</div>
  <div style="font-size:0.85rem;font-weight:700;color:var(--ua-ink);margin-bottom:6px;">{_card[1]}</div>
  <div style="font-size:0.75rem;color:var(--ua-ink-mut);line-height:1.6;">{_card[2]}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
  <div style="background:rgba(var(--ua-label-rgb),0.07);border:1px solid rgba(var(--ua-label-rgb),0.15);
       border-radius:12px;padding:18px 22px;margin-bottom:28px;">
    <div style="font-size:0.75rem;font-weight:700;color:var(--ua-ink-label);letter-spacing:0.1em;
                text-transform:uppercase;margin-bottom:6px;">Important distinction</div>
    <div style="font-size:0.85rem;color:var(--ua-ink-soft);line-height:1.7;">
      Macro signals describe the <strong style="color:var(--ua-ink);">economic environment</strong>,
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

  <h2 style="font-size:1.25rem;font-weight:700;color:var(--ua-ink);margin-bottom:10px;">
    How the 0–100 score is calculated
  </h2>
  <p style="color:var(--ua-ink-mut);line-height:1.8;margin-bottom:24px;">
    Every signal score is a <strong style="color:var(--ua-ink-soft);">rolling percentile</strong> of the current raw reading
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
<div style="background:rgba(var(--ua-card-rgb),0.6);border:1px solid rgba(var(--ua-onbg-rgb),0.07);
     border-radius:10px;padding:14px 18px;display:flex;align-items:flex-start;gap:16px;">
  <div style="flex-shrink:0;min-width:56px;text-align:center;">
    <div style="font-size:1.2rem;font-weight:800;color:{_row[0]};letter-spacing:-0.5px;">{_row[1]}</div>
    <div style="font-size:0.58rem;color:{_row[0]};letter-spacing:0.1em;font-weight:700;
                text-transform:uppercase;margin-top:2px;">{_row[2]}</div>
  </div>
  <div style="font-size:0.80rem;color:var(--ua-ink-mut);line-height:1.65;">{_row[3]}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
  <h3 style="font-size:1.0rem;font-weight:700;color:var(--ua-ink);margin-bottom:10px;">
    What is the Confluence Score?
  </h3>
  <p style="color:var(--ua-ink-mut);line-height:1.8;margin-bottom:16px;">
    The <strong style="color:var(--ua-ink-soft);">Confluence Score</strong> is a weighted composite of the signals
    most relevant to a specific stock's sector and business model. An energy company
    is weighted more heavily toward crude inventory and rig count signals.
    A semiconductor company gets more weight on capex cycle and credit signals.
  </p>
  <p style="color:var(--ua-ink-mut);line-height:1.8;margin-bottom:24px;">
    The word "confluence" is intentional: a score above 65 means <em>multiple</em>
    relevant signals are simultaneously in bullish territory — not just one.
    A single outlier signal rarely drives the composite far into either extreme.
    When it does, it is usually worth investigating why.
  </p>

  <div style="background:rgba(var(--ua-green-rgb),0.05);border:1px solid rgba(var(--ua-green-rgb),0.18);
       border-radius:12px;padding:18px 22px;margin-bottom:28px;">
    <div style="font-size:0.75rem;font-weight:700;color:var(--ua-green);letter-spacing:0.1em;
                text-transform:uppercase;margin-bottom:6px;">No lookahead bias</div>
    <div style="font-size:0.82rem;color:var(--ua-ink-soft);line-height:1.7;">
      Every score is calculated using only data available at the time of calculation.
      Percentile rankings use only historical data up to the current date.
      Backtests in the Signal Backtester page use <code>score.shift(1)</code>
      (yesterday's score drives today's position) to prevent lookahead bias.
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2.5 — Why it works (mechanism + honest expectations)
# ─────────────────────────────────────────────────────────────────────────────
if _method_section == "Why It Works":
    st.markdown("""
<div style="max-width:780px;margin:28px auto 0;font-family:Inter,sans-serif;">
  <h2 style="font-size:1.25rem;font-weight:700;color:var(--ua-ink);margin-bottom:10px;">
    Why a signal can lead price — and what that's honestly worth
  </h2>
  <p style="color:var(--ua-ink-mut);line-height:1.8;margin-bottom:24px;">
    A signal is only worth watching if there's a <em>reason</em> it moves before price does,
    and only worth trusting if we're honest about how large that edge really is. Both matter,
    so both are spelled out here.
  </p>

  <div style="background:rgba(var(--ua-card-rgb),0.55);border:1px solid rgba(var(--ua-onbg-rgb),0.06);
       border-left:3px solid rgba(var(--ua-cyan-rgb),0.5);border-radius:0 12px 12px 0;
       padding:18px 22px;margin-bottom:14px;">
    <div style="font-size:0.9rem;font-weight:700;color:var(--ua-ink);margin-bottom:6px;">
      The mechanism: markets under-react to slow-moving information
    </div>
    <div style="font-size:0.82rem;color:#9AA4BC;line-height:1.8;">
      Prices don't instantly and fully absorb every new macro data point. Information about the
      real economy — freight volumes, credit conditions, energy inventories, hiring — spreads
      through the market gradually as more participants notice it and act. That slow diffusion is
      why a shift in, say, high-yield spreads or trucking tonnage can show up in equity prices
      <em>weeks</em> later rather than the same day. It's the same well-documented effect behind
      <strong style="color:#B7DCE2;">time-series momentum</strong> (Moskowitz, Ooi &amp; Pedersen,
      2012) and gradual information diffusion (Hong &amp; Stein, 1999). It's also why every signal
      here carries a <em>researched lead time</em> instead of being treated as instantaneous — the
      edge lives in the lag.
    </div>
  </div>

  <div style="background:rgba(var(--ua-card-rgb),0.55);border:1px solid rgba(var(--ua-onbg-rgb),0.06);
       border-left:3px solid rgba(255,180,60,0.5);border-radius:0 12px 12px 0;
       padding:18px 22px;margin-bottom:14px;">
    <div style="font-size:0.9rem;font-weight:700;color:var(--ua-ink);margin-bottom:6px;">
      What to realistically expect: small, stackable edges — not forecasts
    </div>
    <div style="font-size:0.82rem;color:#9AA4BC;line-height:1.8;">
      The honest academic picture is sobering: most macro predictors explain only a small and
      unstable fraction of future returns out-of-sample, and many that look strong in-sample fail
      to hold up (Welch &amp; Goyal, 2008). We don't claim to beat that. A high Confluence Score
      <strong style="color:#E8C97B;">tilts the odds modestly</strong> in your favour; it is not a
      prediction, and it will be wrong a meaningful share of the time. The value isn't any single
      call — it's stacking several individually-weak, <em>de-correlated</em> signals and staying
      disciplined about the horizon. That's why the score also reports how many <em>effectively
      independent</em> signals stand behind it, not just a raw count.
    </div>
  </div>

  <div style="background:rgba(var(--ua-card-rgb),0.55);border:1px solid rgba(var(--ua-onbg-rgb),0.06);
       border-left:3px solid rgba(var(--ua-green-rgb),0.5);border-radius:0 12px 12px 0;
       padding:18px 22px;margin-bottom:14px;">
    <div style="font-size:0.9rem;font-weight:700;color:var(--ua-ink);margin-bottom:6px;">
      How we hold ourselves to it
    </div>
    <div style="font-size:0.82rem;color:#9AA4BC;line-height:1.8;">
      Every signal's lead time and out-of-sample validation — <em>including the ones that don't
      hold up</em> — is published on the Model Validation page. Those backtests run on
      <strong style="color:#8FE3AD;">first-print data</strong>: each macro series is fed the value
      that was actually published at the time, not today's revised number, so a signal only gets
      credit for what was knowable then. Where the evidence is thin, we label it thin rather than
      dressing it up. The point of this page is that you shouldn't have to take any of it on faith.
    </div>
  </div>

  <p style="color:var(--ua-ink-label);line-height:1.7;font-size:0.8rem;margin-top:6px;">
    See the measured, per-signal numbers on the <strong style="color:#9EDBE3;">Model Validation</strong>
    page, and how much independent evidence stands behind any score on a ticker's
    <strong style="color:#9EDBE3;">Deep Dive</strong>.
  </p>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Signal categories
# ─────────────────────────────────────────────────────────────────────────────
if _method_section == "Signal Categories":
    st.markdown(f"""
<div style="max-width:860px;margin:28px auto 0;font-family:Inter,sans-serif;">
  <p style="color:var(--ua-ink-mut);line-height:1.8;margin-bottom:24px;">
    Unstructured Alpha's {ACTIVE_SIGNAL_COUNT} signals are grouped into six research categories.
    Each category captures a different dimension of the macro environment.
  </p>
""", unsafe_allow_html=True)

    _categories = [
        {
            "icon": "",
            "name": "Rates & Yield Curve",
            "color": "#00C8E0",
            "desc": "The shape of the Treasury yield curve is one of the most studied macroeconomic indicators. An inverted curve (2Y > 10Y) has preceded every U.S. recession since 1955. We track the 10Y–2Y spread, the 10Y Treasury yield level, and TIPS breakeven inflation expectations.",
            "signals": ["Yield Curve Spread (10Y–2Y)", "10-Year Treasury Yield", "10Y TIPS Breakeven Inflation Rate"],
            "sources": ["FRED", "Yahoo Finance"],
        },
        {
            "icon": "",
            "name": "Credit Spreads",
            "color": "#FF6B6B",
            "desc": "Credit markets move before equity markets. When institutional investors become risk-averse, they demand higher yields on corporate debt, widening spreads. We track high-yield and investment-grade spreads as leading risk sentiment indicators.",
            "signals": ["High-Yield Credit Spread (ICE BofA)", "Investment Grade Credit (LQD ETF)", "Senior Loan Officer Survey — C&I Lending Standards", "Credit Card Delinquency Rate (All Commercial Banks)"],
            "sources": ["FRED", "Yahoo Finance"],
        },
        {
            "icon": "",
            "name": "Energy & Commodities",
            "color": "#F59E0B",
            "desc": "Energy markets reflect real economic activity. EIA weekly inventory data for crude oil and natural gas, spot energy prices, and the Copper/Gold ratio (an economic vs. safety-asset barometer) are all included.",
            "signals": ["US Crude Oil Inventories (EIA Weekly)", "US Natural Gas Storage (EIA Weekly)", "WTI Crude Oil (Daily)", "Henry Hub Natural Gas Spot", "US Retail Gasoline Price", "Copper/Gold Ratio", "Copper Futures (COMEX HG)"],
            "sources": ["EIA", "FRED", "Yahoo Finance"],
        },
        {
            "icon": "",
            "name": "Sentiment & Positioning",
            "color": "#7C3AED",
            "desc": "Fear, greed, and positioning extremes tend to be contrarian or confirming depending on context. We track VIX level and term structure, the CBOE equity put/call ratio, retail search behaviour, and consumer sentiment.",
            "signals": ["CBOE Volatility Index (VIX)", "VIX Term Structure (9D/30D Ratio)", "CBOE Equity Put/Call Ratio", "U. Michigan Consumer Sentiment", "Retail Fear Index (Google Trends)", "US Dollar Index (DXY)"],
            "sources": ["FRED", "Yahoo Finance", "Google Trends"],
        },
        {
            "icon": "",
            "name": "Manufacturing & Growth",
            "color": "#00D566",
            "desc": "Manufacturing PMI, jobless claims, and M2 money supply growth capture the real-economy cycle. Slowing manufacturing and rising claims often precede margin compression and earnings disappointments.",
            "signals": ["Philly Fed Manufacturing Index (ISM PMI proxy)", "Initial Jobless Claims (WARN Proxy)", "M2 Money Supply Growth", "JOLTS Job Openings (Labor Demand)", "Layoffs & Discharges Rate (BLS JOLTS)", "Durable Goods Orders ex. Defense", "Housing Starts (New Residential Construction)"],
            "sources": ["FRED"],
        },
        {
            "icon": "",
            "name": "Supply Chain & Alternative Data",
            "color": "#00C8E0",
            "desc": "The non-obvious series: physical freight movement, supply-chain pressure, and research/approval velocity. These are the signals least likely to already be priced in, because they are not on a standard terminal dashboard.",
            "signals": ["NY Fed Global Supply Chain Pressure Index", "ATA Trucking Tonnage Index", "AAR Rail Traffic (Intermodal)", "Breakwave Dry Bulk Shipping ETF (BDRY)", "Total Business Inventory/Sales Ratio", "Quantum Computing arXiv Paper Velocity", "FDA Drug Approval Velocity (openFDA)", "Fed Policy Hawkishness (FOMC AI Score)"],
            "sources": ["New York Fed", "FRED", "arXiv", "openFDA", "Yahoo Finance"],
        },
    ]

    for _cat in _categories:
        _sigs_html = "".join(
            f'<span style="font-size:0.68rem;background:rgba(var(--ua-onbg-rgb),0.04);border:1px solid rgba(var(--ua-onbg-rgb),0.08);'
            f'color:var(--ua-ink-mut);border-radius:5px;padding:2px 8px;white-space:nowrap;">{s}</span> '
            for s in _cat["signals"]
        )
        _srcs_html = "".join(
            f'<span style="font-size:0.65rem;background:rgba(var(--ua-label-rgb),0.08);border:1px solid rgba(var(--ua-label-rgb),0.18);'
            f'color:var(--ua-ink-label);border-radius:5px;padding:2px 8px;font-weight:600;">{s}</span> '
            for s in _cat["sources"]
        )
        st.markdown(f"""
<div style="background:rgba(var(--ua-card-rgb),0.65);border:1px solid rgba(var(--ua-onbg-rgb),0.07);
     border-radius:14px;padding:20px 24px;margin-bottom:14px;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
    <span style="font-size:1.3rem;">{_cat["icon"]}</span>
    <span style="font-size:1.0rem;font-weight:700;color:{_cat["color"]};">{_cat["name"]}</span>
  </div>
  <p style="font-size:0.80rem;color:var(--ua-ink-mut);line-height:1.7;margin-bottom:12px;">{_cat["desc"]}</p>
  <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px;">{_sigs_html}</div>
  <div style="border-top:1px solid rgba(var(--ua-onbg-rgb),0.05);padding-top:10px;display:flex;flex-wrap:wrap;gap:5px;align-items:center;">
    <span style="font-size:0.60rem;color:#4A5280;letter-spacing:0.1em;font-weight:700;text-transform:uppercase;margin-right:4px;">Sources:</span>
    {_srcs_html}
  </div>
</div>""", unsafe_allow_html=True)

    # ── Per-ticker / Pro data, explicitly NOT part of the macro signal library ──
    # SEC EDGAR insider filings, 13F positioning and FINRA short interest are
    # genuinely fetched and used -- but by Ticker Deep Dive, not by any of the
    # scored macro signals. They used to be listed above as if they were signals,
    # which overstated the library. Kept, and kept credited, but scoped honestly.
    _pro_rows = [
        ("Insider filings (SEC Form 4)", "Buy/sell transactions and cluster detection for a single ticker.", "SEC EDGAR"),
        ("13F institutional positioning", "Quarterly fund holdings for the tickers you look up.", "SEC EDGAR"),
        ("Short interest", "Reported short interest and trend for a single ticker.", "FINRA"),
        ("Options activity", "Per-ticker options flow on the Options Flow page.", "Yahoo Finance"),
    ]
    _pro_html = "".join(
        f'<div style="display:flex;gap:10px;align-items:baseline;padding:7px 0;'
        f'border-bottom:1px solid rgba(var(--ua-onbg-rgb),0.05);">'
        f'<span style="font-size:0.76rem;font-weight:650;color:var(--ua-ink-soft);min-width:210px;">{_n}</span>'
        f'<span style="font-size:0.74rem;color:var(--ua-ink-mut);flex:1;">{_d}</span>'
        f'<span style="font-size:0.62rem;color:var(--ua-ink-label);font-weight:700;">{_s}</span>'
        f'</div>'
        for _n, _d, _s in _pro_rows
    )
    st.markdown(f"""
<div style="background:rgba(var(--ua-royal-rgb),0.05);border:1px solid rgba(var(--ua-royal-rgb),0.20);
     border-radius:14px;padding:20px 24px;margin-top:18px;">
  <div style="font-size:1.0rem;font-weight:700;color:var(--ua-royal-2);margin-bottom:6px;">
    Per-ticker data — not part of the {len(SIGNALS)}-signal library
  </div>
  <p style="font-size:0.79rem;color:var(--ua-ink-mut);line-height:1.7;margin-bottom:10px;">
    These run on demand for a single ticker in Ticker Deep Dive and the Pro tools. They are
    <strong style="color:var(--ua-ink-soft);">not</strong> scored macro signals and do not feed the
    Confluence Score, so they are listed separately rather than counted in the {len(SIGNALS)}.
  </p>
  {_pro_html}
</div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — Data sources
# ─────────────────────────────────────────────────────────────────────────────
if _method_section == "Data Sources":
    st.markdown(f"""
<div style="max-width:780px;margin:28px auto 0;font-family:Inter,sans-serif;">
  <p style="color:var(--ua-ink-mut);line-height:1.8;margin-bottom:24px;">
    The {ACTIVE_SIGNAL_COUNT}-signal registry currently draws from
    <strong style="color:var(--ua-ink-soft);">{signal_sources_phrase(limit=20)}</strong>.
    This list is generated from the same configuration that powers the Signal Dashboard, so a
    provider cannot be credited here unless at least one registered macro signal uses it.
  </p>
""", unsafe_allow_html=True)

    _provider_roles = {
        "fred": "Economic, rates, credit, labor, inflation, freight, and market series.",
        "yahoo": "Market-price and ratio inputs used by price-derived macro signals.",
        "eia": "Weekly U.S. crude-oil inventory and natural-gas storage series.",
        "ny_fed": "The Global Supply Chain Pressure Index.",
        "arxiv": "Published research metadata used for research-velocity measures.",
        "openfda": "Public regulatory-event data used for approval-velocity measures.",
        "google_trends": "Aggregated search interest used by the retail fear measure.",
        "federal_reserve": "Federal Reserve communications used by the policy-language measure.",
    }
    _provider_counts = Counter(
        canonical_provider(_cfg.get("source")) for _cfg in SIGNALS.values()
    )
    for _provider, _count in _provider_counts.most_common():
        _names = [
            str(_cfg.get("name", _signal_id))
            for _signal_id, _cfg in SIGNALS.items()
            if canonical_provider(_cfg.get("source")) == _provider
        ]
        _preview = ", ".join(_names[:4])
        if len(_names) > 4:
            _preview += f", +{len(_names) - 4} more"
        st.markdown(f"""
<div style="background:rgba(var(--ua-card-rgb),0.65);border:1px solid rgba(var(--ua-onbg-rgb),0.07);
     border-radius:13px;padding:18px 22px;margin-bottom:12px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
    <div style="font-size:0.90rem;font-weight:700;color:var(--ua-ink);">
      {provider_label(_provider)}
    </div>
    <div style="font-size:0.64rem;color:var(--ua-ink-label);font-weight:700;
         letter-spacing:0.08em;text-transform:uppercase;">
      {_count} registered signal{"s" if _count != 1 else ""}
    </div>
  </div>
  <div style="margin-top:10px;font-size:0.78rem;color:var(--ua-ink-mut);line-height:1.65;">
    {_provider_roles.get(_provider, "Publicly attributable inputs used by the macro signal library.")}
  </div>
  <div style="margin-top:6px;font-size:0.75rem;color:var(--ua-ink-label);line-height:1.6;">
    <strong>Registered series:</strong> {_preview}
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown(f"""
<div style="background:rgba(var(--ua-royal-rgb),0.05);border:1px solid rgba(var(--ua-royal-rgb),0.20);
     border-radius:13px;padding:18px 22px;margin-top:18px;">
  <div style="font-size:0.89rem;font-weight:700;color:var(--ua-royal-2);margin-bottom:7px;">
    Separate per-ticker providers
  </div>
  <div style="font-size:0.78rem;color:var(--ua-ink-mut);line-height:1.7;">
    SEC EDGAR and FINRA support ticker-specific filings, institutional-positioning, and
    short-interest features. Those are real product capabilities, but they do not feed the
    {ACTIVE_SIGNAL_COUNT}-signal macro registry and are not counted above.
  </div>
</div>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — Limitations
# ─────────────────────────────────────────────────────────────────────────────
if _method_section == "Limitations":
    st.markdown("""
<div style="max-width:780px;margin:28px auto 0;font-family:Inter,sans-serif;">
  <h2 style="font-size:1.15rem;font-weight:700;color:var(--ua-ink);margin-bottom:10px;">
    What Unstructured Alpha does not do
  </h2>
  <p style="color:var(--ua-ink-mut);line-height:1.8;margin-bottom:24px;">
    We believe transparent limitations are a feature, not a weakness.
    This section exists so you can make an informed decision about how to use this tool.
  </p>
""", unsafe_allow_html=True)

    _limits = [
        ("Not price predictions", "Signal scores describe the macro <em>environment</em>. A score of 80 does not mean the market will go up. It means the macro backdrop is historically supportive. Markets can decline sharply even in favorable macro environments, and they can rally hard in hostile ones."),
        ("Signals can stay extreme", "A signal in the bearish zone can stay bearish for many months. 'Oversold' in macro terms is not the same as a short-term mean reversion in price. Do not use these scores as short-term trading triggers."),
        ("Coverage is organic", "Score history is only built for tickers that users have searched. We do not run a nightly batch across every stock in the market. The universe covered by historical data grows with user activity."),
        ("Data source delays", "Macro releases arrive on different schedules, from market days to monthly. Separate per-ticker sources also have their own delays: FINRA short interest is reported twice monthly, and SEC filing data is event-driven. The product shows freshness and unavailable states rather than treating every source as real-time."),
        ("Not investment advice", "This platform is educational and informational only. Nothing here is personalized financial advice. We are not registered investment advisers. Always consult a licensed professional before making investment decisions."),
        ("Model validation is ongoing", "We publish our validation results publicly on the Model Validation page. Some signals have stronger lead-time evidence than others. We label validation status honestly — including when a signal lacks sufficient out-of-sample data."),
        ("Yahoo Finance data quality", "Price data accessed via the yfinance library is best-effort and may have gaps, stale values, or API errors. Pages that rely on this source show error states when data is unavailable rather than silently serving stale data."),
    ]

    for _i, (_title, _desc) in enumerate(_limits):
        st.markdown(f"""
<div style="background:rgba(var(--ua-card-rgb),0.55);border:1px solid rgba(var(--ua-onbg-rgb),0.06);
     border-left:3px solid rgba(var(--ua-red-rgb),0.4);border-radius:0 12px 12px 0;
     padding:16px 20px;margin-bottom:10px;">
  <div style="font-size:0.85rem;font-weight:700;color:var(--ua-ink);margin-bottom:5px;">{_title}</div>
  <div style="font-size:0.78rem;color:var(--ua-ink-mut);line-height:1.7;">{_desc}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("""
  <div style="background:rgba(var(--ua-red-rgb),0.05);border:1px solid rgba(var(--ua-red-rgb),0.2);
       border-radius:12px;padding:18px 22px;margin-top:20px;margin-bottom:28px;">
    <div style="font-size:0.75rem;font-weight:700;color:#FF6B6B;letter-spacing:0.1em;
                text-transform:uppercase;margin-bottom:6px;">Full disclaimer</div>
    <div style="font-size:0.78rem;color:var(--ua-ink-soft);line-height:1.75;">
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
         f"The platform cache is {SCORE_REFRESH_DESCRIPTION}, while each underlying provider retains its own publication schedule. A monthly economic release does not become newer merely because the app refreshed. Signal cards show the last confirmed observation."),

        ("What is the rolling window?",
         "252 trading days — approximately one calendar year. This captures a full economic cycle of seasonal variation without overweighting distant historical regimes. A shorter window (e.g., 90 days) would be too sensitive to recent extremes. A longer window would dilute the signal's responsiveness."),

        ("How is the Confluence Score weighted?",
         "Sector-relevant signals receive higher weights for each stock. A semiconductor company has higher weighting on credit spreads, M2, and capex indicators. An energy company has higher weighting on crude inventory, rig count, and oil price trend. The exact weights are defined in our open configuration file."),

        ("Can I trust the backtest results on the Signal Backtester page?",
         "The backtest uses a strict no-lookahead rule (yesterday's score drives today's position), includes 0.1% round-trip transaction costs, and compares performance to a buy-and-hold SPY benchmark. However, backtest performance is inherently optimistic — it does not capture liquidity, slippage, behavioral friction, or regime changes that break historical patterns. Treat it as exploratory context, not a proof of future returns."),

        ("Why isn't [specific signal X] included?",
         f"The live registry currently contains {ACTIVE_SIGNAL_COUNT} signals. Candidates need an attributable, maintainable data path and a defensible economic mechanism. Validation strength is then reported explicitly; inclusion is not presented as proof that every signal is equally predictive."),

        ("Who is this designed for?",
         f"Unstructured Alpha is built for individual investors who want a structured macro and ticker-research workflow without pretending it is institutional execution infrastructure. Pro is currently ${PRO_PRICE_MONTHLY}/month and adds deeper research workflows; it does not replace a broker, licensed adviser, or professional market-data terminal."),
    ]

    for _q, _a in _faqs:
        with st.expander(_q):
            st.markdown(f'<div style="font-size:0.82rem;color:var(--ua-ink-mut);line-height:1.8;padding:6px 0;">{_a}</div>',
                        unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ── Bottom CTA ─────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(f"""
<div style="background:rgba(var(--ua-green-rgb),0.04);border:1px solid rgba(var(--ua-green-rgb),0.15);
     border-radius:16px;padding:28px;text-align:center;max-width:620px;margin:0 auto 40px;
     font-family:Inter,sans-serif;">
  <div style="font-size:1.1rem;font-weight:700;color:var(--ua-ink);margin-bottom:8px;">
    See the signals live
  </div>
  <div style="font-size:0.82rem;color:var(--ua-ink-mut);margin-bottom:20px;line-height:1.7;">
    The Signal Dashboard shows all {ACTIVE_SIGNAL_COUNT} signals with live scores, trend direction,
    and the regime read. No account required to browse.
  </div>
""", unsafe_allow_html=True)

_c1, _c2, _c3 = st.columns([2, 1.5, 2])
with _c2:
    if st.button("→ Open Signal Dashboard", type="primary", width="stretch", key="hsw_cta"):
        st.switch_page("pages/1_Signal_Dashboard.py")

st.markdown("""
  <div style="margin-top:16px;font-size:0.72rem;color:var(--ua-ink-label);">
    Also see:
    <a href="/signal-research?section=validation" style="color:var(--ua-ink-label);">Validation</a> ·
    <a href="/signal-research?section=data-quality" style="color:var(--ua-ink-label);">Data Quality</a> ·
    <a href="/signal-research?section=track-record" style="color:var(--ua-ink-label);">Track Record</a>
  </div>
</div>
""", unsafe_allow_html=True)

render_footer()
