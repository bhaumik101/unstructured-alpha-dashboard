"""
Page 8 — About & Methodology
Professional about page covering methodology, data sources, signal library,
research references, and legal disclosures.
"""

import streamlit as st

from utils.header import render_header, render_sidebar_base
from utils.config import SIGNALS, CATEGORIES

st.set_page_config(page_title="About — UA", layout="wide")
render_header("About & Methodology")

render_sidebar_base()


# ── Mission ────────────────────────────────────────────────────────────────────
col_text, col_quote = st.columns([3, 2])

with col_text:
    st.markdown('<div class="section-header">WHAT IS UNSTRUCTURED ALPHA</div>', unsafe_allow_html=True)
    st.markdown("""
    Unstructured Alpha is an alternative data intelligence platform built for serious retail
    investors who want institutional-grade signal analysis without a Bloomberg Terminal subscription.

    The premise is straightforward: the most predictive market data is not price data. It is
    physical economic activity — freight volumes, energy contracts, labor dislocations, credit
    spreads — that reflects the real economy weeks or months before it appears in earnings reports
    or analyst forecasts.

    Hedge funds have known this for two decades. They pay $50,000–$500,000 annually for
    proprietary datasets from satellite imagery companies, credit card processors, and
    geolocation firms. We replicate the same *analytical logic* using free government data
    sources: the Federal Reserve, the CFTC, the SEC, the Census Bureau, and the BLS.

    The result is a dashboard that can answer: "What does the physical economy look like right
    now for this specific stock?" — not what the price chart looks like.
    """)

with col_quote:
    st.markdown("""
    <div style="background:#1C2B4A;border-radius:8px;padding:28px 24px;margin-top:10px;font-family:Georgia,serif;">
        <div style="color:#C9A84C;font-size:0.75rem;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:16px;">
            The Edge
        </div>
        <div style="color:#FAF7F0;font-size:1.0rem;line-height:1.7;font-style:italic;">
            "Markets are efficient at processing public information that's in obvious form.
            They're inefficient at processing information that requires effort to collect
            and synthesize."
        </div>
        <div style="color:#C9A84C;font-size:0.82rem;margin-top:14px;">
            — The core premise behind alternative data investing
        </div>
        <div style="color:#8B9BB5;font-size:0.78rem;margin-top:20px;line-height:1.6;">
            Every signal in this dashboard is sourced from a government or regulated entity.
            No data is purchased or proprietary. The edge is in the synthesis.
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Methodology ────────────────────────────────────────────────────────────────
st.divider()
st.markdown('<div class="section-header">METHODOLOGY</div>', unsafe_allow_html=True)

m1, m2 = st.columns(2)

with m1:
    st.markdown("**Signal Construction**")
    st.markdown("""
    Each signal is constructed through a four-step process:

    1. **Data collection** — Raw series fetched from FRED, CFTC, SEC EDGAR, or Yahoo Finance
       on each page load. Where possible, data is cached for 1–4 hours to reduce API calls.

    2. **Normalization** — Each series is z-scored against its own trailing 52-week history.
       This makes signals comparable across different scales and units.

    3. **Scoring** — The z-score is converted to a 0–100 signal score. A score of 50 means
       the series is at its historical average. Above 65 is bullish; below 35 is bearish.
       Inverse signals (e.g., jobless claims) are flipped: a rising claims number scores
       lower, not higher.

    4. **Confluence** — Multiple signal scores for a given ticker are combined using a
       weighted average, where each signal's Predictive Confidence Score (PCS) serves as
       its weight. Higher-quality signals have proportionally more influence on the
       final confluence score.
    """)

with m2:
    st.markdown("**Lead Time Optimization**")
    st.markdown("""
    The most important feature of alternative data is *when* it leads price. A signal that
    predicts prices 8 weeks ahead is much more actionable than one that correlates
    contemporaneously.

    The Deep Correlation Scan on the Ticker Deep Dive page runs an automated lag scan from
    0 to 16 weeks. For each lag, it computes the Pearson correlation between the signal
    (at time T) and the stock price (at time T + lag). The lag with the highest absolute
    correlation is identified as the "optimal lead time."

    This approach mirrors the lag-optimization methodology described in Kolanovic &
    Krishnamachari (2017), "Big Data and AI Strategies," J.P. Morgan Quantitative Research.
    """)

    st.markdown("**Confluence Scoring**")
    st.markdown("""
    The Confluence Score (0–100) aggregates independent signals into a single alignment metric.
    When 5–7 unrelated signals from different data domains (trucking, credit, labor, energy)
    all currently read the same direction, that is a stronger *description* of the present data
    than any single signal alone — but see the Backtest Results section directly below before
    treating that description as a forecast.

    - Score >65 = Signals currently aligned bullish
    - Score 35–65 = Mixed / low agreement
    - Score <35 = Signals currently aligned bearish
    """)

st.markdown("**Backtest Results — Confluence & Power Supercycle Scores**")
st.markdown("""
<div style="background:#FFF0F0;border-radius:6px;padding:14px 18px;border:1px solid #E8B4B4;
            font-size:0.86rem;color:#5D2020;margin-bottom:8px;font-family:Georgia,serif;line-height:1.7;">
We walk-forward backtested the actual scoring functions above (not a simplified version — the
real production code) against 6 tickers spanning the Power Supercycle thesis (CEG, VST, NEE, ETN,
VRT, PWR — chosen because none are mechanical constituents of any signal being tested, e.g. URA's
largest holding is Cameco, so CCJ was excluded to avoid circularity), at ~19 monthly checkpoints,
using only data available as of each checkpoint date (no lookahead).

<b>Result:</b> pooled across all 6 tickers (96–108 observations depending on horizon), there is
no statistically significant relationship between either score and 1/2/3-month forward returns
(all |r| &lt; 0.07, p &gt; 0.5). Two of the six tickers — the two with the most narrative-extended,
momentum-driven price action in the test window — showed a significant <i>negative</i> relationship
in isolation (high score coincided with a cyclical top, not a forward rally); the other four showed
no significant relationship in either direction. None of the individual-ticker results survive
correction for testing multiple tickers/horizons at once.

<b>What this means in practice:</b> these scores are an honest, real-time read of how many
independent alternative-data signals currently agree — useful context, and the methodology behind
them (lag-scanning, statistical significance filtering on individual signals, PCS weighting) is
sound. But the combined score has not been shown to predict forward price moves, on this sample.
Treat it as descriptive, not predictive, until a larger backtest says otherwise. We are not hiding
this finding because it's the inconvenient one — building this product on a score we can verify
beats building it on a score that just sounds good.
</div>
""", unsafe_allow_html=True)

# ── Signal Library ─────────────────────────────────────────────────────────────
st.divider()
st.markdown('<div class="section-header">SIGNAL LIBRARY</div>', unsafe_allow_html=True)
st.caption(f"Current library: {len(SIGNALS)} signals across {len(CATEGORIES)} categories.")

import pandas as pd
from datetime import datetime, timedelta
from utils.fetchers import fetch_signal_series, fetch_price
from utils.analysis import compute_backtested_pcs

st.markdown("""
<div style="background:#FFF8E7;border-radius:6px;padding:12px 16px;border:1px solid #E8D9A8;
            font-size:0.85rem;color:#5D4426;margin-bottom:12px;font-family:Georgia,serif;">
<b>About the PCS column:</b> the "Static PCS" below is a hand-assigned 1–10 estimate made when
each signal was written — useful as a starting prior, but not validated against real data on its
own. Click "Run Live Backtest" to compute an actual Predictive Confidence Score from each signal's
real historical correlation and statistical significance (p&lt;0.05) across up to 5 of its relevant
tickers, not just one — a signal that only works on a single name doesn't get credit for broad
predictive power. Where they disagree, trust the backtested number.
</div>
""", unsafe_allow_html=True)

run_backtest = st.button("Run Live Backtest (tests real correlation + significance)", key="run_pcs_backtest")

BT_END   = datetime.now().strftime("%Y-%m-%d")
BT_START = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")


@st.cache_data(ttl=86400, show_spinner=False)
def _backtest_all_signals(_v: int = 2) -> dict:
    """Backtest every signal's PCS against up to 5 of its relevant tickers
    (not just the first one) so a signal that only correlates with one
    ticker doesn't get an inflated, falsely-broad PCS. Cached for 24h since
    this is a real-data validation pass, not a live score."""
    out = {}
    for sig_id, cfg in SIGNALS.items():
        try:
            sig_series = fetch_signal_series(cfg, BT_START, BT_END)
            test_tickers = (cfg.get("relevant_tickers") or [])[:5]
            price_series_list = [fetch_price(t, BT_START, BT_END) for t in test_tickers]
            out[sig_id] = compute_backtested_pcs(
                sig_series, price_series_list,
                lag_weeks=cfg.get("lag_weeks", 0), tickers=test_tickers,
            )
        except Exception:
            out[sig_id] = {"pcs": None, "backtested": False, "n_tested": 0,
                            "significance_rate": 0.0, "avg_abs_r": 0.0, "details": []}
    return out


backtest_results = {}
if run_backtest:
    with st.spinner("Backtesting every signal against real price history — this fetches live data, may take a minute…"):
        backtest_results = _backtest_all_signals()
    n_validated = sum(1 for r in backtest_results.values() if r["backtested"])
    st.success(
        f"Backtest complete: {n_validated} of {len(SIGNALS)} signals had enough overlapping data "
        f"to validate. The rest fall back to the static estimate below (shown as \"unvalidated\")."
    )

rows = []
for sig_id, cfg in SIGNALS.items():
    cat = CATEGORIES.get(cfg["category"], {})
    bt = backtest_results.get(sig_id, {})
    if bt.get("backtested"):
        pcs_display = f"{bt['pcs']}/10 (backtested)"
        validation  = (
            f"{bt['significance_rate']*100:.0f}% significant, r={bt['avg_abs_r']:.2f} "
            f"(n={bt['n_tested']} tickers tested)"
        )
    else:
        pcs_display = f"{cfg['pcs']}/10 (static, unvalidated)"
        validation  = "Click Run Live Backtest →"

    rows.append({
        "Signal":        cfg["name"],
        "Category":      cat.get("name", cfg["category"]),
        "PCS":           pcs_display,
        "Validation":    validation,
        "Lead":          f"~{cfg['lag_weeks']}w",
        "Direction":     "Inverse (bearish when rising)" if cfg.get("inverse") else "Direct (bullish when rising)",
        "Source":        {
            "fred": "FRED (Federal Reserve)",
            "eia": "EIA (Energy Information Administration)",
            "yfinance": "Yahoo Finance",
            "yfinance_multi": "SEC + Yahoo Finance",
            "yfinance_basket": "Equal-weight basket",
            "arxiv": "arXiv.org (research papers)",
            "fda": "openFDA (FDA drug approvals)",
        }.get(cfg["source"], cfg["source"]),
        "Key Tickers":   ", ".join(cfg.get("relevant_tickers", [])[:5]),
    })

lib_df = pd.DataFrame(rows)
st.dataframe(
    lib_df, use_container_width=True, hide_index=True,
    column_config={
        "PCS": st.column_config.TextColumn("PCS", help="Predictive Confidence Score 1–10. Backtested = computed from real correlation/significance. Static = hand-assigned prior, unvalidated."),
        "Validation": st.column_config.TextColumn("Validation", help="Significance rate and average |r| from the live backtest, when run."),
        "Lead": st.column_config.TextColumn("Lead Time", help="How many weeks ahead this signal historically leads price"),
    },
)

# ── Data Sources ──────────────────────────────────────────────────────────────
st.divider()
st.markdown('<div class="section-header">DATA SOURCES</div>', unsafe_allow_html=True)

sources = [
    ("Federal Reserve (FRED)", "fred.stlouisfed.org",
     "Macro series: trucking, rail freight, jobless claims, yield curve, retail sales, consumer sentiment, PMI, durable goods, housing starts, oil price, food CPI, credit spreads."),
    ("Energy Information Administration (EIA)", "api.eia.gov",
     "Weekly US crude oil inventories excluding SPR and weekly Lower-48 working natural gas in underground storage. The two highest-frequency energy fundamentals — both move oil and gas prices same-day on release."),
    ("Federal Reserve — Senior Loan Officer Survey (SLOOS)", "federalreserve.gov/data/sloos.htm",
     "Quarterly survey of bank lending standards. A genuine alt-data differentiator: credit desks track this closely, but it's quarterly and easy to overlook, so it rarely appears on retail platforms."),
    ("openFDA", "api.fda.gov",
     "Free, keyless FDA drug application database. Used here to compute industry-wide drug approval velocity — the kind of regulatory-tailwind read healthcare analysts normally track by hand off press releases."),
    ("CFTC — Commitments of Traders", "cftc.gov",
     "Weekly positioning data for commodity futures: copper, oil, natural gas, gold, silver. Shows commercial hedger vs. speculator net positioning."),
    ("Yahoo Finance (yfinance)", "finance.yahoo.com",
     "Equity price data, ETF prices, commodity ETFs, VIX, dollar index, 10-year yield proxy. Used for signal proxies and ticker price data."),
    ("SEC EDGAR Full-Text Search", "efts.sec.gov",
     "Form 4 insider transactions (executives buying/selling company stock). Free public API with no key required."),
    ("USASpending.gov API", "usaspending.gov",
     "Federal contract awards by company. DoE, DoD, and agency-level award velocity for energy, defense, and infrastructure companies."),
    ("University of Michigan", "sca.isr.umich.edu",
     "Consumer Sentiment Index (UMCSENT). Monthly survey of ~500 US consumers on personal finance and economic outlook."),
    ("ICE BofA via FRED", "fred.stlouisfed.org/series/BAMLH0A0HYM2",
     "High yield corporate bond OAS spread. Measures the credit risk premium investors demand over Treasuries for junk bonds."),
]

for name, url, desc in sources:
    st.markdown(f"""
    <div style="background:#F0EBE1;border-radius:6px;padding:14px 16px;border:1px solid #D4C9B0;
                border-left:4px solid #B8860B;margin-bottom:10px;font-family:Georgia,serif;">
        <div style="font-size:0.95rem;font-weight:700;color:#1C2B4A;">{name}</div>
        <div style="font-size:0.78rem;color:#8B7355;margin-bottom:6px;">{url}</div>
        <div style="font-size:0.84rem;color:#1A1612;line-height:1.6;">{desc}</div>
    </div>
    """, unsafe_allow_html=True)

# ── Research References ────────────────────────────────────────────────────────
st.divider()
st.markdown('<div class="section-header">RESEARCH REFERENCES</div>', unsafe_allow_html=True)

refs = [
    ("Kolanovic & Krishnamachari (2017)",
     "J.P. Morgan Quantitative Research — Big Data and AI Strategies. "
     "Introduced systematic lag-optimization framework for alternative data signals."),
    ("Ke, Kelly, Xiu (2019)",
     "Predicting Returns with Text Data. University of Chicago Booth. "
     "Formalized the use of non-price data streams in return prediction."),
    ("Kogan, Moskowitz & Niessner (2021)",
     "Fake News in Financial Markets. NBER Working Paper. "
     "Demonstrated that search trend velocity leads price discovery."),
    ("Fama & French (1992)",
     "The Cross-Section of Expected Stock Returns. Journal of Finance. "
     "Foundation of factor-based investing; our signal framework extends this to alternative factors."),
    ("Grantham (2022)",
     "GMO Letters on Commodity Supercycles. "
     "Provided the theoretical basis for the Power Supercycle thesis tracked in our dedicated page."),
    ("Chen, Roll & Ross (1986)",
     "Economic Forces and the Stock Market. Journal of Business. "
     "First systematic study linking macroeconomic variables to stock returns with lead-lag analysis."),
]

for title, desc in refs:
    st.markdown(f"""
    <div style="margin-bottom:10px;padding-left:14px;border-left:2px solid #B8860B;font-family:Georgia,serif;">
        <div style="font-size:0.88rem;font-weight:700;color:#1C2B4A;">{title}</div>
        <div style="font-size:0.82rem;color:#6B6560;line-height:1.6;">{desc}</div>
    </div>
    """, unsafe_allow_html=True)

# ── Legal Disclaimer ──────────────────────────────────────────────────────────
st.divider()
st.markdown('<div class="section-header">LEGAL DISCLAIMER</div>', unsafe_allow_html=True)

st.markdown("""
<div style="background:#F0EBE1;border:1px solid #D4C9B0;border-radius:6px;padding:20px 24px;
            font-family:Georgia,serif;font-size:0.82rem;color:#6B6560;line-height:1.8;">

<b style="color:#1C2B4A;font-size:0.90rem;">NOT FINANCIAL ADVICE — GENERAL, IMPERSONAL COMMENTARY ONLY</b><br><br>

Unstructured Alpha is an analytical research tool intended for educational and informational purposes only.
Nothing on this platform constitutes investment advice, financial advice, trading advice, or any other
sort of advice, and you should not treat any of the content as such.

Every signal score, Confluence Score, Power Supercycle score, and bull/bear case on this platform is
<b>general and impersonal</b>: it is generated by the same published methodology applied identically to
every reader, is not tailored to any individual's portfolio, financial situation, risk tolerance, or
investment objectives, and is not based on any information about you personally. We do not know who is
reading any given page, and the content does not change based on who is reading it. This platform does
not manage money, does not exercise discretion over any reader's investments, and does not provide
ongoing or individualized investment management services to anyone.

Unstructured Alpha does not recommend that any security should be bought, sold, or held by you. A score
above or below any threshold described on this platform is a description of how current publicly
available data compares to its own historical range — it is not, and should not be read as, a
recommendation or solicitation to buy or sell any financial instrument or to make any investment.

<b>Unstructured Alpha is not a registered investment adviser or broker-dealer</b> with the SEC, FINRA, or
any state securities regulator, and nothing on this platform should be construed as implying otherwise.

All signals, confluence scores, and analyses are based on publicly available data and the application of
quantitative methods that may have significant limitations. We have walk-forward backtested the Confluence
and Power Supercycle scores against historical data and found no statistically significant relationship
with forward returns on the sample tested (see Methodology, above) — past performance of any signal or
indicator, and any current reading of any signal or indicator, is not indicative of future results.

<br><b style="color:#1C2B4A;">DATA ACCURACY</b><br><br>

While we strive to ensure the accuracy of the information displayed, we make no warranty, expressed or
implied, as to the accuracy, completeness, or timeliness of the data. All data is sourced from third-party
providers (FRED, CFTC, SEC, Yahoo Finance, USASpending.gov) and is subject to errors, omissions,
and revisions by those providers.

<br><b style="color:#1C2B4A;">RISK DISCLOSURE</b><br><br>

Investing in securities involves substantial risk of loss. You should carefully consider your investment
objectives, risk tolerance, and financial situation before making any investment decisions. You should
consult with a licensed financial advisor before making any investment decisions.

<br><b style="color:#1C2B4A;">NO AFFILIATION</b><br><br>

Unstructured Alpha is not affiliated with, endorsed by, or sponsored by Bloomberg L.P., the Wall Street
Journal, the Federal Reserve, the CFTC, the SEC, or any other data provider referenced on this platform.

</div>
""", unsafe_allow_html=True)
