"""
Page 8 — About Unstructured Alpha
Mini research paper — methodology, validation, data sources, builder bio.
Designed to establish academic credibility for finance professors and
institutional reviewers. Dark glassmorphism throughout.
"""

import streamlit as st

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.product_metrics import ACTIVE_SIGNAL_COUNT, ACTIVE_SOURCE_COUNT, SUPPORTED_TICKER_COUNT

st.set_page_config(page_title="About — Unstructured Alpha", layout="wide")
render_header("About")
_about_section = render_sidebar_base(
    page_title="About & Methodology",
    sections=("Methodology", "Validation Evidence"),
    section_key="about_section_rail",
)

render_page_header(
    "About Unstructured Alpha",
    "Methodology, validation results, data sources, and the philosophy behind alternative data intelligence.",
    icon="",
)

if _about_section == "Methodology":
    # ── Helper ────────────────────────────────────────────────────────────────────
    def _section(title):
        st.markdown(
            f'<div style="font-size:0.62rem;font-weight:700;color:#8892AA;letter-spacing:0.13em;'
            f'text-transform:uppercase;border-bottom:1px solid rgba(255,255,255,0.05);'
            f'padding-bottom:8px;margin:28px 0 16px;font-family:Inter,sans-serif;">{title}</div>',
            unsafe_allow_html=True,
        )


    def _callout(title, body, color="#7C3AED"):
        st.markdown(
            f'<div style="background:rgba(18,21,30,0.85);border-left:3px solid {color};'
            f'border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:14px 18px;'
            f'margin-bottom:12px;font-family:Inter,sans-serif;">'
            f'<div style="font-size:0.62rem;font-weight:700;color:{color};letter-spacing:0.10em;'
            f'text-transform:uppercase;margin-bottom:6px;">{title}</div>'
            f'<div style="font-size:0.83rem;color:#B8C0D4;line-height:1.65;">{body}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


    # ── Abstract ──────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:rgba(124,58,237,0.06);border:1px solid rgba(124,58,237,0.15);
                 border-radius:12px;padding:20px 24px;margin-bottom:24px;font-family:Inter,sans-serif;">
      <div style="font-size:0.62rem;font-weight:700;color:#7C3AED;letter-spacing:0.12em;
                   text-transform:uppercase;margin-bottom:10px;">Abstract</div>
      <div style="font-size:0.90rem;color:#C8D0E4;line-height:1.75;">
        Unstructured Alpha is a systematic, signal-driven investment research platform that aggregates
        38 alternative data series spanning macroeconomic releases, commodity flows, credit spreads,
        insider transactions, institutional positioning, and short interest into a single
        <b style="color:#E8EEFF;">Confluence Score</b> for each equity ticker. The score summarizes
        whether the preponderance of non-price evidence is bullish, neutral, or bearish for a given
        security at a given moment. This document describes the construction methodology, statistical
        validation approach, data provenance, and known limitations of the platform.
      </div>
    </div>
    """, unsafe_allow_html=True)

    _section("1. Motivation & Philosophy")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div style="font-family:Inter,sans-serif;font-size:0.87rem;color:#B8C0D4;line-height:1.75;">
        <p>Most retail equity research is backward-looking: it explains why a stock moved after the fact.
        Unstructured Alpha is built around a single contrarian premise: <b style="color:#E8EEFF;">non-price
        data leads price data</b>. If you can identify the signals that systematically precede
        directional moves even by just 2-6 weeks you have an actionable edge that price-chart
        analysis alone cannot provide.</p>

        <p>The platform draws on the academic literature in empirical finance, particularly work showing
        that insider transactions (Seyhun 1986, Lakonishok and Lee 2001), short interest changes
        (Asquith et al. 2005), institutional positioning shifts (Brunnermeier and Nagel 2004), and
        macroeconomic surprise indices (Cieslak and Povala 2015) each carry statistically significant
        predictive content for future equity returns, measured over horizons of 4-16 weeks.</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        _callout("Core Thesis",
            "Price is a lagging indicator of fundamentals. Alternative data — insider filings, credit spreads, "
            "commodity flows, institutional 13F filings — reflects information that has not yet been fully "
            "incorporated into consensus prices. Systematic aggregation of these signals across multiple "
            "independent series reduces idiosyncratic noise and improves directional predictive accuracy.",
            color="#00C8E0")

        _callout("Design Constraint",
            "All signals use publicly available data sources (FRED, SEC EDGAR, FINRA, yfinance, EIA). "
            "No proprietary data feeds, no direct market data subscriptions. The platform is reproducible "
            "by any researcher with API keys for FRED and EIA.",
            color="#00D566")


    _section("2. Signal Construction")

    st.markdown("""
    <div style="font-family:Inter,sans-serif;font-size:0.87rem;color:#B8C0D4;line-height:1.75;margin-bottom:16px;">
    Each of the 38 signals is converted to a standardized 0-100 score using a consistent methodology:
    </div>
    """, unsafe_allow_html=True)

    math_cols = st.columns(3)

    with math_cols[0]:
        st.markdown("""
        <div style="background:rgba(18,21,30,0.85);border:1px solid rgba(255,255,255,0.07);
                    border-radius:10px;padding:16px;font-family:Inter,sans-serif;">
            <div style="font-size:0.62rem;color:#7C3AED;font-weight:700;letter-spacing:0.10em;
                        text-transform:uppercase;margin-bottom:10px;">Step 1: Z-Score Normalization</div>
            <div style="font-size:0.83rem;color:#B8C0D4;line-height:1.65;">
                For each signal series x at time t with a 52-week rolling window:
            </div>
            <div style="background:#0F1118;border-radius:8px;padding:10px 14px;margin:10px 0;
                        font-family:'Courier New',monospace;font-size:0.82rem;color:#00C8E0;text-align:center;">
                z(t) = (x(t) - mu_52w) / sigma_52w
            </div>
            <div style="font-size:0.80rem;color:#8892AA;line-height:1.6;">
                Where mu and sigma are the rolling 52-week mean and standard deviation of the signal. This
                removes level effects and makes signals from very different series (e.g. oil inventories
                and credit spreads) directly comparable.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with math_cols[1]:
        st.markdown("""
        <div style="background:rgba(18,21,30,0.85);border:1px solid rgba(255,255,255,0.07);
                    border-radius:10px;padding:16px;font-family:Inter,sans-serif;">
            <div style="font-size:0.62rem;color:#00D566;font-weight:700;letter-spacing:0.10em;
                        text-transform:uppercase;margin-bottom:10px;">Step 2: Score Mapping</div>
            <div style="font-size:0.83rem;color:#B8C0D4;line-height:1.65;">
                The z-score is mapped to [0, 100] via a sigmoid-like transform that is directionally
                consistent with the signal's empirically validated lead:
            </div>
            <div style="background:#0F1118;border-radius:8px;padding:10px 14px;margin:10px 0;
                        font-family:'Courier New',monospace;font-size:0.82rem;color:#00D566;text-align:center;">
                score = 50 + 30 * tanh(z/2)
            </div>
            <div style="font-size:0.80rem;color:#8892AA;line-height:1.6;">
                Signals that historically invert have their z-scores negated before mapping, so
                score above 65 is always bullish and below 35 is always bearish regardless of the
                signal's raw direction.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with math_cols[2]:
        st.markdown("""
        <div style="background:rgba(18,21,30,0.85);border:1px solid rgba(255,255,255,0.07);
                    border-radius:10px;padding:16px;font-family:Inter,sans-serif;">
            <div style="font-size:0.62rem;color:#F59E0B;font-weight:700;letter-spacing:0.10em;
                        text-transform:uppercase;margin-bottom:10px;">Step 3: Confluence Aggregation</div>
            <div style="font-size:0.83rem;color:#B8C0D4;line-height:1.65;">
                For a given ticker, only signals with statistically validated lead times
                (p below 0.05 after Bonferroni correction) are included. The Confluence Score is
                their equal-weighted average:
            </div>
            <div style="background:#0F1118;border-radius:8px;padding:10px 14px;margin:10px 0;
                        font-family:'Courier New',monospace;font-size:0.82rem;color:#F59E0B;text-align:center;">
                C = (1/N) * SUM( score_i )
            </div>
            <div style="font-size:0.80rem;color:#8892AA;line-height:1.6;">
                Insider, short-interest, and 13F signals each receive a fixed 12% weight cap regardless
                of N, since they reflect individual-security information rather than macro regime data.
            </div>
        </div>
        """, unsafe_allow_html=True)


    _section("3. Lead-Time Validation")

    with st.expander("Walk-forward out-of-sample lead time validation methodology", expanded=True):
        st.markdown("""
        <div style="font-family:Inter,sans-serif;font-size:0.87rem;color:#B8C0D4;line-height:1.75;">

        <b style="color:#E8EEFF;">Lag Scan.</b> For each signal i and ticker j, we compute
        the Pearson correlation between lagged signal values and forward equity returns across lags
        k = 1, 2, ..., 16 weeks:

        <div style="background:#0F1118;border-radius:8px;padding:10px 16px;margin:12px 0;
                    font-family:'Courier New',monospace;font-size:0.82rem;color:#00C8E0;text-align:center;">
            rho_k = corr( signal(t-k), return(t) )
        </div>

        The lag k* with the highest absolute rho is the "best lag" — the historical offset at which the signal
        most strongly predicts future returns.

        <b style="color:#E8EEFF;">Significance Testing.</b> To avoid data snooping, we:
        <br>— Apply <b>Bonferroni correction</b> for the 16 lags tested per signal-ticker pair:
            threshold becomes alpha' = 0.05/16 ≈ 0.003 instead of 0.05.
        <br>— Require the <b>out-of-sample</b> (OOS) Pearson r to remain ≥ 0.05 on a held-out
            validation window (the final 25% of the available series length).
        <br>— Signals are only included in the Confluence Score if both conditions are met.

        <br><br><b style="color:#E8EEFF;">Lag Decay Tracking.</b> A signal's validated lead time can erode as
        market structure changes. Every 30 days, we rerun the lag scan on the most recent 104 weeks of
        data and flag any signal whose best lag has shifted by more than 4 weeks, or whose OOS correlation
        has dropped below 0.03, as "decayed." Decayed signals are down-weighted until re-validated.

        </div>
        """, unsafe_allow_html=True)


    _section("4. Multiple-Comparisons Correction")

    _callout("Bonferroni Correction", (
        "With 38 signals tested against each ticker, and 16 lag values each, we perform up to 608 hypothesis "
        "tests per ticker. Without correction, we would expect ~30 spurious significant results by chance "
        "at alpha = 0.05. The Bonferroni correction sets the per-test threshold to alpha/m = 0.05/608 "
        "approximately 0.000082, drastically reducing false discovery. In practice, validated signal counts "
        "per ticker range from 3 to 12, well within the expected range for genuinely predictive relationships."
    ), color="#7C3AED")

    _callout("Predictive Contribution Score (PCS)", (
        "PCS is a 0-10 meta-score assigned to each signal based on: (1) the number of tickers for which "
        "it showed significant lead across the lag-scan, (2) the mean OOS correlation magnitude across those "
        "tickers, and (3) stability — whether the best lag has remained consistent over rolling 12-month "
        "windows. A PCS of 8+ indicates a signal that reliably leads a broad cross-section of tickers with "
        "consistent timing. PCS is displayed on each signal card in the Signal Dashboard."
    ), color="#F59E0B")


    _section("5. Data Sources")

    st.markdown("""
    <table style="width:100%;border-collapse:collapse;font-family:Inter,sans-serif;font-size:0.83rem;margin-bottom:16px;">
      <thead>
        <tr style="border-bottom:1px solid rgba(0,213,102,0.2);">
          <th style="padding:9px 12px;text-align:left;color:#00D566;font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">Source</th>
          <th style="padding:9px 12px;text-align:left;color:#00D566;font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">Signal Category</th>
          <th style="padding:9px 12px;text-align:left;color:#00D566;font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">Series Examples</th>
          <th style="padding:9px 12px;text-align:left;color:#00D566;font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">Update Frequency</th>
        </tr>
      </thead>
      <tbody>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <td style="padding:8px 12px;color:#E8EEFF;font-weight:600;">FRED (St. Louis Fed)</td>
          <td style="padding:8px 12px;color:#B8C0D4;">Macro, Credit, Liquidity</td>
          <td style="padding:8px 12px;color:#8892AA;">DGS10, BAMLH0A0HYM2, M2SL, DCOILWTICO</td>
          <td style="padding:8px 12px;color:#6B7FBF;">Daily / Weekly</td>
        </tr>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <td style="padding:8px 12px;color:#E8EEFF;font-weight:600;">EIA</td>
          <td style="padding:8px 12px;color:#B8C0D4;">Energy Supply/Demand</td>
          <td style="padding:8px 12px;color:#8892AA;">Crude inventories, nat-gas storage, rig count</td>
          <td style="padding:8px 12px;color:#6B7FBF;">Weekly</td>
        </tr>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <td style="padding:8px 12px;color:#E8EEFF;font-weight:600;">SEC EDGAR</td>
          <td style="padding:8px 12px;color:#B8C0D4;">Insider Transactions, 13F Filings</td>
          <td style="padding:8px 12px;color:#8892AA;">Form 4 (insiders), Form 13F (institutions)</td>
          <td style="padding:8px 12px;color:#6B7FBF;">As filed (2 business days)</td>
        </tr>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <td style="padding:8px 12px;color:#E8EEFF;font-weight:600;">FINRA</td>
          <td style="padding:8px 12px;color:#B8C0D4;">Short Interest</td>
          <td style="padding:8px 12px;color:#8892AA;">Short interest volume, short ratio by ticker</td>
          <td style="padding:8px 12px;color:#6B7FBF;">Semi-monthly</td>
        </tr>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <td style="padding:8px 12px;color:#E8EEFF;font-weight:600;">yfinance</td>
          <td style="padding:8px 12px;color:#B8C0D4;">Price, Volume, Earnings</td>
          <td style="padding:8px 12px;color:#8892AA;">OHLCV, earnings dates, news, financials</td>
          <td style="padding:8px 12px;color:#6B7FBF;">Real-time / Daily</td>
        </tr>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <td style="padding:8px 12px;color:#E8EEFF;font-weight:600;">Google Trends</td>
          <td style="padding:8px 12px;color:#B8C0D4;">Social Sentiment</td>
          <td style="padding:8px 12px;color:#8892AA;">Search interest index by ticker</td>
          <td style="padding:8px 12px;color:#6B7FBF;">Weekly</td>
        </tr>
        <tr>
          <td style="padding:8px 12px;color:#E8EEFF;font-weight:600;">USASpending.gov</td>
          <td style="padding:8px 12px;color:#B8C0D4;">Federal Contracts</td>
          <td style="padding:8px 12px;color:#8892AA;">Contract award velocity by vendor/ticker</td>
          <td style="padding:8px 12px;color:#6B7FBF;">Daily</td>
        </tr>
      </tbody>
    </table>
    """, unsafe_allow_html=True)


    _section("6. Known Limitations & Honest Disclosures")

    lim_col1, lim_col2 = st.columns(2)

    with lim_col1:
        _callout("Small Sample Problem",
            "Insider and 13F signals are highly ticker-specific. For most tickers, there are fewer than "
            "20 historical filing events, making the lag-scan correlation estimates noisy and sensitive "
            "to outliers. These signals are explicitly down-weighted (12% cap) and their small-N status "
            "is disclosed on each card.",
            color="#FF4444")

        _callout("Look-Ahead Bias Risk",
            "The 52-week z-score rolling window is backward-looking by construction, but the choice of "
            "signals and their bullish direction was determined by the platform author before seeing "
            "recent 2024-2025 data. There is a risk of inadvertent in-sample optimization. All claims "
            "about signal predictability should be treated as preliminary until independently replicated.",
            color="#F59E0B")

    with lim_col2:
        _callout("Regime Dependence",
            "Signal lead times can change dramatically across macro regimes. Signals validated during "
            "2010-2020 may perform differently in the post-2022 high-inflation, high-rate environment. "
            "The lag-decay tracker partially mitigates this but cannot eliminate regime-change risk.",
            color="#F59E0B")

        _callout("NOT Financial Advice",
            "Unstructured Alpha is a research and education platform. No Confluence Score or directional "
            "forecast on this platform constitutes investment advice, a trading recommendation, or a "
            "solicitation to buy or sell any security. Always conduct independent due diligence. "
            "Past signal accuracy does not predict future performance.",
            color="#FF4444")


    _section("7. How This Differs from Existing Platforms")

    st.markdown("""
    <div style="font-family:Inter,sans-serif;font-size:0.87rem;color:#B8C0D4;line-height:1.75;margin-bottom:16px;">
    TipRanks, Seeking Alpha Quant, and Bloomberg PORT all produce composite equity scores.
    None of them publish their scoring methodology, their statistical validation results, or the cases
    where their signals fail. This is not a cosmetic difference — it determines whether the number is
    trustworthy or opaque.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <table style="width:100%;border-collapse:collapse;font-family:Inter,sans-serif;font-size:0.82rem;margin-bottom:20px;">
      <thead>
        <tr style="border-bottom:1px solid rgba(0,197,102,0.25);">
          <th style="padding:10px 14px;text-align:left;color:#6B7FBF;font-size:0.60rem;letter-spacing:0.10em;text-transform:uppercase;font-weight:600;"></th>
          <th style="padding:10px 14px;text-align:center;color:#00D566;font-size:0.60rem;letter-spacing:0.10em;text-transform:uppercase;font-weight:700;">Unstructured Alpha</th>
          <th style="padding:10px 14px;text-align:center;color:#6B7FBF;font-size:0.60rem;letter-spacing:0.10em;text-transform:uppercase;">TipRanks Smart Score</th>
          <th style="padding:10px 14px;text-align:center;color:#6B7FBF;font-size:0.60rem;letter-spacing:0.10em;text-transform:uppercase;">Seeking Alpha Quant</th>
          <th style="padding:10px 14px;text-align:center;color:#6B7FBF;font-size:0.60rem;letter-spacing:0.10em;text-transform:uppercase;">Bloomberg PORT</th>
        </tr>
      </thead>
      <tbody>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <td style="padding:9px 14px;color:#B8C0D4;font-weight:600;">Methodology published</td>
          <td style="padding:9px 14px;text-align:center;color:#00D566;font-weight:700;">✓ Full, on this page</td>
          <td style="padding:9px 14px;text-align:center;color:#FF4444;">✗ Proprietary black box</td>
          <td style="padding:9px 14px;text-align:center;color:#FF4444;">✗ Factor weights undisclosed</td>
          <td style="padding:9px 14px;text-align:center;color:#F59E0B;">~ Partial (academic partner docs)</td>
        </tr>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <td style="padding:9px 14px;color:#B8C0D4;font-weight:600;">Out-of-sample validation</td>
          <td style="padding:9px 14px;text-align:center;color:#00D566;font-weight:700;">✓ Walk-forward, Bonferroni</td>
          <td style="padding:9px 14px;text-align:center;color:#FF4444;">✗ None disclosed</td>
          <td style="padding:9px 14px;text-align:center;color:#FF4444;">✗ None disclosed</td>
          <td style="padding:9px 14px;text-align:center;color:#F59E0B;">~ Internal (not user-facing)</td>
        </tr>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <td style="padding:9px 14px;color:#B8C0D4;font-weight:600;">Failed signals disclosed</td>
          <td style="padding:9px 14px;text-align:center;color:#00D566;font-weight:700;">✓ Model Validation page</td>
          <td style="padding:9px 14px;text-align:center;color:#FF4444;">✗ No</td>
          <td style="padding:9px 14px;text-align:center;color:#FF4444;">✗ No</td>
          <td style="padding:9px 14px;text-align:center;color:#FF4444;">✗ No</td>
        </tr>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <td style="padding:9px 14px;color:#B8C0D4;font-weight:600;">Alternative data sources</td>
          <td style="padding:9px 14px;text-align:center;color:#00D566;font-weight:700;">✓ 7 public APIs</td>
          <td style="padding:9px 14px;text-align:center;color:#B8C0D4;">Analyst consensus + news</td>
          <td style="padding:9px 14px;text-align:center;color:#B8C0D4;">Factor scores (valuation, growth)</td>
          <td style="padding:9px 14px;text-align:center;color:#B8C0D4;">Market data + fundamentals</td>
        </tr>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <td style="padding:9px 14px;color:#B8C0D4;font-weight:600;">Congressional trades</td>
          <td style="padding:9px 14px;text-align:center;color:#00D566;font-weight:700;">✓ Live EDGAR feed</td>
          <td style="padding:9px 14px;text-align:center;color:#F59E0B;">~ Some coverage</td>
          <td style="padding:9px 14px;text-align:center;color:#FF4444;">✗ Not included</td>
          <td style="padding:9px 14px;text-align:center;color:#FF4444;">✗ Not included</td>
        </tr>
        <tr>
          <td style="padding:9px 14px;color:#B8C0D4;font-weight:600;">Cost</td>
          <td style="padding:9px 14px;text-align:center;color:#00D566;font-weight:700;">Free (open source stack)</td>
          <td style="padding:9px 14px;text-align:center;color:#B8C0D4;">$29–$49 / month</td>
          <td style="padding:9px 14px;text-align:center;color:#B8C0D4;">$239 / month (Premium)</td>
          <td style="padding:9px 14px;text-align:center;color:#B8C0D4;">$24,000+ / year</td>
        </tr>
      </tbody>
    </table>
    """, unsafe_allow_html=True)


    _section("8. Platform Architecture")

    # Data flow diagram (HTML/CSS)
    st.markdown("""
    <div style="background:rgba(18,21,30,0.85);border:1px solid rgba(255,255,255,0.07);border-radius:12px;
                padding:24px;font-family:Inter,sans-serif;margin-bottom:16px;">
      <div style="font-size:0.62rem;font-weight:700;color:#8892AA;letter-spacing:0.10em;
                  text-transform:uppercase;margin-bottom:18px;">Data Flow</div>
      <div style="display:flex;align-items:center;gap:0;flex-wrap:wrap;justify-content:center;">

        <div style="text-align:center;">
          <div style="font-size:0.65rem;font-weight:700;color:#00C8E0;letter-spacing:0.06em;
                      text-transform:uppercase;margin-bottom:6px;">Public APIs</div>
          <div style="background:rgba(0,200,224,0.08);border:1px solid rgba(0,200,224,0.2);
                      border-radius:8px;padding:8px 14px;font-size:0.72rem;color:#8892AA;line-height:1.9;">
            FRED &nbsp;·&nbsp; EIA<br>SEC EDGAR<br>FINRA<br>yfinance<br>Google Trends
          </div>
        </div>

        <div style="font-size:1.2rem;color:#6B7FBF;padding:0 12px;">→</div>

        <div style="text-align:center;">
          <div style="font-size:0.65rem;font-weight:700;color:#7C3AED;letter-spacing:0.06em;
                      text-transform:uppercase;margin-bottom:6px;">Signal Engine</div>
          <div style="background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.2);
                      border-radius:8px;padding:8px 14px;font-size:0.72rem;color:#8892AA;line-height:1.9;">
            Z-score · tanh map<br>Lead-time scan<br>Bonferroni correction<br>PCS weighting
          </div>
        </div>

        <div style="font-size:1.2rem;color:#6B7FBF;padding:0 12px;">→</div>

        <div style="text-align:center;">
          <div style="font-size:0.65rem;font-weight:700;color:#F59E0B;letter-spacing:0.06em;
                      text-transform:uppercase;margin-bottom:6px;">Caching Layer</div>
          <div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2);
                      border-radius:8px;padding:8px 14px;font-size:0.72rem;color:#8892AA;line-height:1.9;">
            @st.cache_data<br>Signals: 2h TTL<br>Prices: 60s TTL<br>max_entries=1
          </div>
        </div>

        <div style="font-size:1.2rem;color:#6B7FBF;padding:0 12px;">→</div>

        <div style="text-align:center;">
          <div style="font-size:0.65rem;font-weight:700;color:#00D566;letter-spacing:0.06em;
                      text-transform:uppercase;margin-bottom:6px;">PostgreSQL</div>
          <div style="background:rgba(0,213,102,0.06);border:1px solid rgba(0,213,102,0.15);
                      border-radius:8px;padding:8px 14px;font-size:0.72rem;color:#8892AA;line-height:1.9;">
            Users · Watchlists<br>Score snapshots<br>Alerts · Predictions<br>Macro narratives
          </div>
        </div>

        <div style="font-size:1.2rem;color:#6B7FBF;padding:0 12px;">→</div>

        <div style="text-align:center;">
          <div style="font-size:0.65rem;font-weight:700;color:#E8EEFF;letter-spacing:0.06em;
                      text-transform:uppercase;margin-bottom:6px;">26-Page App</div>
          <div style="background:rgba(232,238,255,0.04);border:1px solid rgba(232,238,255,0.10);
                      border-radius:8px;padding:8px 14px;font-size:0.72rem;color:#8892AA;line-height:1.9;">
            Streamlit · Plotly<br>Auth + 2FA<br>Anthropic Claude API<br>Render auto-deploy
          </div>
        </div>

      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="background:rgba(18,21,30,0.85);border:1px solid rgba(255,255,255,0.07);border-radius:10px;
                padding:18px 22px;font-family:Inter,sans-serif;font-size:0.84rem;color:#B8C0D4;line-height:1.9;">
    <b style="color:#E8EEFF;">Stack:</b> Python 3.12 · Streamlit · Plotly · yfinance · pandas · scipy · SQLAlchemy · anthropic<br>
    <b style="color:#E8EEFF;">Database:</b> PostgreSQL (Render) — users, watchlists, alerts, score history, prediction log, macro narratives<br>
    <b style="color:#E8EEFF;">Deployment:</b> Render.com — auto-deploy from GitHub main; render.yaml blueprint with rootDir override<br>
    <b style="color:#E8EEFF;">Caching:</b> Two-tier — FRED/EIA signals at 2h TTL; live prices at 60s; <code>max_entries=1</code> to prevent heap bloat<br>
    <b style="color:#E8EEFF;">Auth:</b> Email verification + TOTP 2FA via Resend; bcrypt; remember-me tokens; multi-tenant row isolation<br>
    <b style="color:#E8EEFF;">AI:</b> Anthropic claude-haiku-4-5 — weekly macro research note generation + live signal-aware chat assistant
    </div>
    """, unsafe_allow_html=True)


    _section("9. About the Builder")

    bio_col, stats_col = st.columns([3, 1])
    with bio_col:
        st.markdown("""
        <div style="background:rgba(18,21,30,0.85);border:1px solid rgba(255,255,255,0.07);
                    border-radius:10px;padding:20px 24px;font-family:Inter,sans-serif;">
            <div style="font-size:1.1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">Bhaumik Giri</div>
            <div style="font-size:0.78rem;color:#6B7FBF;margin-bottom:14px;letter-spacing:0.04em;">
                Finance &amp; Data Science · UNC Kenan-Flagler Business School
            </div>
            <div style="font-size:0.87rem;color:#B8C0D4;line-height:1.80;">
                <p>Built Unstructured Alpha to close the gap between institutional-grade alternative data
                research and what's accessible to individual investors and academic researchers. The work
                began after noticing that most retail-facing equity platforms treat their scoring
                methodology as a trade secret — which makes it impossible to evaluate whether their scores
                are actually predictive or merely impressive-looking.</p>
                <p>The platform required writing a full-stack Python application from scratch: API
                integrations with FRED, EIA, SEC EDGAR, and FINRA; a custom statistical validation
                framework with Bonferroni-corrected walk-forward lag scans; a multi-tenant PostgreSQL
                database with email-verified auth; and 26 Streamlit pages with dark-mode Plotly
                visualizations, skeleton loading, and AI-generated macro research notes via the
                Anthropic API.</p>
                <p>Academic rigor was a first-order design constraint, not an afterthought.
                The Model Validation page publishes signal-level out-of-sample results openly,
                including the cases where signals didn't survive the stricter bar — a design
                choice deliberately opposite to how commercial platforms handle their failures.</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with stats_col:
        st.markdown("""
        <div style="background:rgba(0,213,102,0.05);border:1px solid rgba(0,213,102,0.15);
                    border-radius:10px;padding:16px;font-family:Inter,sans-serif;">
            <div style="font-size:0.62rem;color:#00D566;font-weight:700;letter-spacing:0.10em;
                        text-transform:uppercase;margin-bottom:12px;">By the Numbers</div>
            <div style="font-size:0.83rem;color:#B8C0D4;line-height:2.4;">
                <b style="color:#E8EEFF;">{ACTIVE_SIGNAL_COUNT}</b> registered signals<br>
                <b style="color:#E8EEFF;">26</b> app pages<br>
                <b style="color:#E8EEFF;">{ACTIVE_SOURCE_COUNT}</b> source families<br>
                <b style="color:#E8EEFF;">{SUPPORTED_TICKER_COUNT}</b> tracked tickers<br>
                <b style="color:#E8EEFF;">8</b> signal categories<br>
                <b style="color:#E8EEFF;">~6,000</b> lines of Python<br>
                <b style="color:#E8EEFF;">Live</b> on Render
            </div>
        </div>
        <div style="background:rgba(124,58,237,0.06);border:1px solid rgba(124,58,237,0.15);
                    border-radius:10px;padding:14px 16px;font-family:Inter,sans-serif;margin-top:10px;">
            <div style="font-size:0.62rem;color:#7C3AED;font-weight:700;letter-spacing:0.10em;
                        text-transform:uppercase;margin-bottom:10px;">Validated Features</div>
            <div style="font-size:0.78rem;color:#8892AA;line-height:2.0;">
                ✓ Bonferroni lag-scan<br>
                ✓ OOS walk-forward<br>
                ✓ Lag decay tracker<br>
                ✓ Cross-ticker pooling<br>
                ✓ Published failures
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("Version: 2026 · Platform: unstructuredalpha.com · Builder: bpgiri2005@gmail.com")


if _about_section == "Validation Evidence":
    from utils.config import SIGNALS, CATEGORIES as _VAL_CATEGORIES
    from utils.validation_status import validate_all_macro_signals, get_static_validation_summary
    from utils.theme import source_badge

    st.markdown("""
<div style="background:rgba(0,200,224,0.07);border-left:3px solid #00C8E0;border-radius:8px;
            padding:14px 18px;font-size:0.85rem;color:#B8C0D4;margin-bottom:20px;
            font-family:Inter,sans-serif;line-height:1.6;">
<b style="color:#E8EEFF;">What this is for:</b> every score on this site traces back to a
real, checkable validation status — backtested with real significance numbers, validated
per-ticker on demand, or explicitly <b>not</b> validated and documented as to why.
Most platforms that show a composite "smart score" disclose none of this.
</div>
""", unsafe_allow_html=True)

    with st.spinner("Running validation suite…"):
        try:
            _val_results = validate_all_macro_signals()
        except Exception:
            _val_results = {}

    if _val_results:
        import pandas as pd
        _val_rows = []
        for sig_id, res in _val_results.items():
            _val_rows.append({
                "Signal": SIGNALS.get(sig_id, {}).get("name", sig_id),
                "Best Lag (wk)": res.get("best_lag_weeks", "—"),
                "Sig. Tickers": res.get("significant_tickers", 0),
                "Total Tickers": res.get("total_tickers", 0),
                "Avg |r|": round(res.get("avg_abs_r", 0), 3),
                "Sig. Rate %": round(res.get("sig_rate", 0) * 100, 0),
            })
        _val_df = pd.DataFrame(_val_rows).sort_values("Sig. Rate %", ascending=False)
        st.dataframe(
            _val_df, use_container_width=True, hide_index=True,
            column_config={
                "Sig. Rate %": st.column_config.ProgressColumn("Sig. Rate %", min_value=0, max_value=100, format="%.0f%%"),
                "Avg |r|": st.column_config.NumberColumn("Avg |r|", format="%.3f"),
            }
        )
        source_badge("FRED · EIA · SEC EDGAR · yfinance")
    else:
        _static = get_static_validation_summary()
        st.markdown(f"<pre style='font-size:0.75rem;color:#8892AA;'>{_static}</pre>", unsafe_allow_html=True)
        st.caption("Live backtest unavailable — showing cached summary.")
