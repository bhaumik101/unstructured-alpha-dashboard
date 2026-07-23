"""
Page 9 — AI Research Assistant
Live signal-aware conversational analyst. Injects today's real signal state
into every Claude API call so answers reflect the actual current macro read,
not a static knowledge base.
"""

import os
from datetime import datetime

import streamlit as st

from utils.header import render_header, render_sidebar_base, render_page_header, disclose_unavailable_signals

st.set_page_config(page_title="AI Assistant — UA", layout="wide")
from utils.billing import require_pro
require_pro(
    "AI Research Assistant",
    "Use a live signal-aware research copilot grounded in the platform's current real-data state.",
)
render_header("AI Research Assistant")
render_sidebar_base()

render_page_header(
    "AI Research Assistant",
    "Ask anything about signals, tickers, or current macro conditions.",
    icon="",
)

# Data-integrity disclosure uses the same shared cache as the assistant context,
# so unavailable providers are excluded without another network request.
from utils.signals_cache import get_all_signal_scores as _gas_disc
disclose_unavailable_signals(_gas_disc())



# ─────────────────────────────────────────────────────────────────────────────
# Live signal context builder — injected into every API call
# ─────────────────────────────────────────────────────────────────────────────

def _build_live_signal_context() -> str:
    """
    Call get_all_signal_scores() (shared 6-hour cache — no extra HTTP hit)
    and format the result into a compact live-context block for the system
    prompt. Returns an empty string on any failure so the assistant still
    works if signal scoring is unavailable.
    """
    try:
        from utils.signals_cache import get_all_signal_scores
        all_sv = get_all_signal_scores()
    except Exception:
        return ""

    if not all_sv:
        return ""

    bulls = [(k, v) for k, v in all_sv.items() if v.get("status") == "bullish" and not v.get("error")]
    bears = [(k, v) for k, v in all_sv.items() if v.get("status") == "bearish" and not v.get("error")]
    neutrals = [(k, v) for k, v in all_sv.items() if v.get("status") == "neutral" and not v.get("error")]
    total = len(all_sv)

    nb, nr, nn = len(bulls), len(bears), len(neutrals)
    ratio = nb / max(nb + nr, 1)
    if ratio >= 0.60:
        regime = "BULLISH"
    elif ratio <= 0.35:
        regime = "BEARISH"
    else:
        regime = "MIXED / NEUTRAL"

    avg_score = sum(v.get("score", 50) for v in all_sv.values()) / max(total, 1)

    # Sort by score for top-5 each direction
    bulls_sorted = sorted(bulls, key=lambda x: x[1].get("score", 50), reverse=True)[:5]
    bears_sorted = sorted(bears, key=lambda x: x[1].get("score", 50))[:5]

    def _fmt_signal(k, v) -> str:
        score = v.get("score", 50)
        z = v.get("z_score", 0.0)
        cur = v.get("current", float("nan"))
        name = v.get("name", k)
        cur_str = f"{cur:.2f}" if cur == cur else "N/A"  # nan check
        return f"  • {name}: score={score:.0f}/100, z={z:+.2f}, current={cur_str}"

    top_bull_block = "\n".join(_fmt_signal(k, v) for k, v in bulls_sorted) or "  (none)"
    top_bear_block = "\n".join(_fmt_signal(k, v) for k, v in bears_sorted) or "  (none)"

    # Spot-check key signals the user is most likely to ask about
    key_ids = [
        "yield_curve", "hy_spread", "vix", "trucking", "jobless_claims",
        "crude_inventories", "nat_gas", "hyperscaler_capex", "copper", "uranium_proxy",
    ]
    spot_lines = []
    for sid in key_ids:
        v = all_sv.get(sid)
        if v and not v.get("error"):
            score = v.get("score", 50)
            status = v.get("status", "neutral").upper()
            z = v.get("z_score", 0.0)
            name = v.get("name", sid)
            spot_lines.append(f"  {name}: {status} (score={score:.0f}, z={z:+.2f})")
    spot_block = "\n".join(spot_lines) or "  (key signals unavailable)"

    ts = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    return f"""
══════════════════════════════════════════════════════════
LIVE SIGNAL STATE — {ts}
══════════════════════════════════════════════════════════
MACRO REGIME:   {regime}
SIGNAL COUNTS:  {nb} BULLISH  |  {nr} BEARISH  |  {nn} NEUTRAL  (of {total} total)
AVG MACRO SCORE: {avg_score:.1f}/100

TOP BULLISH SIGNALS (highest scores):
{top_bull_block}

TOP BEARISH SIGNALS (lowest scores):
{top_bear_block}

KEY SIGNAL SPOT-CHECK:
{spot_block}
══════════════════════════════════════════════════════════
When users ask about current market conditions, today's macro read, or specific signals,
use the LIVE DATA above — do NOT defer to general historical knowledge alone. The numbers
above are the actual scores computed from live FRED/EIA/yfinance data right now.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Static knowledge base — platform context (injected alongside live state)
# ─────────────────────────────────────────────────────────────────────────────
APP_CONTEXT = """
You are the Unstructured Alpha Research Assistant — an expert analyst on the
Unstructured Alpha alternative data intelligence platform. You help users understand
the platform's methodology, interpret signals, navigate pages, and think through
investment theses.

IMPORTANT: You have access to LIVE signal data in this system prompt (see the
LIVE SIGNAL STATE block). When users ask "what is the market saying right now",
"what does [signal] look like today", or any present-tense question about macro
conditions — answer using the live data, not generic commentary.

PLATFORM OVERVIEW:
Unstructured Alpha uses non-traditional, "alternative" data sources to give investors a
forward-looking edge over conventional financial data. The core idea: alternative data
leads price by weeks or months, while earnings reports and consensus estimates lag reality.

THE SIGNAL SCORING SYSTEM:
- Each signal is scored 0–100 based on recent trend vs. historical distribution (Z-score → percentile)
- Scores below 35 = BEARISH, 35–65 = NEUTRAL, above 65 = BULLISH
- Confluence Score = weighted average across relevant signals for a ticker
- Weights = max(0.15, |Pearson r|) × (PCS/10)
- Statistical significance: signals are tested at p<0.05 against each ticker's price history
- PCS (Predictive Capability Score) 1-10: our assessment of historical signal reliability
- Backtested honestly: walk-forward over 6 tickers, 19 monthly checkpoints showed no
  statistically significant relationship with 1/2/3-month forward returns (|r| < 0.07).
  Treat the score as a real-time read of signal AGREEMENT, not a validated forecast.

THE PAGES:
1. Signal Dashboard — Real-time overview of every tracked macro signal with bull/bear/neutral
   status, sparklines, z-scores, percentiles. Simple mode (traffic-light) and Pro mode (stats).

2. Ticker Deep Dive — Flagship page: Confluence Score, forward probability model, signal
   breakdown filtered to p<0.05 significance, Deep Correlation Scan (optimal lag, rolling
   correlation stability), federal contract overlay, insider transaction overlay, earnings overlay,
   news, radar chart, "What Would Change My Mind" block, Playbook Mode.

3. Power Supercycle — Five-leg thesis: nuclear fuel, grid & copper, gas bridge, AI demand,
   macro backdrop. Small-multiple signal charts per leg.

4. Market Overview — Daily macro snapshot: major indices, sector performance, rates, commodities,
   Signal Snapshot (VIX, yield curve, HY credit, 10Y trend, risk appetite).

5. Stock Screener — All 280+ tickers ranked by a Macro + Momentum Rank (70% macro / 30% momentum).
   Filters by sector, signal bias, PCS, score range. Quick-analyze any ticker outside the universe.
   (The full Confluence Score, with insider/13F/short-interest overlays, is on the Ticker Deep Dive.)

6. Watchlist — Personal ticker tracking with price alerts and 30-day confluence sparklines.

7. Weekly Brief — AI-generated macro research note, published automatically each Sunday.

8. Signal Backtester — Build custom signal combinations and backtest against any ticker.

9. Short Squeeze Radar — Combines short interest (FINRA), macro signals, and insider clusters
   to surface potential squeeze candidates.

10. Portfolio Macro Analyzer — Multi-ticker macro exposure analysis.

11. Sector Rotation Signal Map — Sector-level alternative data read.

12. Pre-Earnings Track Record — Historical signal accuracy in the 30/60/90 days before earnings.

13. Decision Queue — Pro daily research triage that ranks saved holdings by persisted score
    movement, upcoming earnings, thesis/evidence conflict, thesis review horizon, missing score
    coverage, and portfolio concentration. It never creates trade instructions or synthetic facts;
    completed work automatically reopens when the underlying evidence fingerprint changes.

14. Portfolio Fit Lab — A pre-trade research simulation inside Portfolio Intelligence. It
    models a candidate or resized holding at a proposed target weight, funds it pro rata from
    the other saved holdings, and compares portfolio macro score, factor concentration, and
    hidden factor overlap using matched persisted full-score components. It does not forecast
    returns or recommend a position size.

15. Catalyst Command Center — A live event workflow that uses official FRED macro release
    dates and provider-supplied, explicitly provisional earnings dates. Pro members see which
    saved holdings and portfolio weight are affected, can write private base/upside/downside
    plans, and compare them with post-event outcomes. The existing Pro morning digest includes
    events inside seven days and recent plans awaiting review without adding another cron job.
    Missing dates and signals are excluded, never replaced with synthetic calendar entries or predictions.

16. Notification Policy Center — A Pro section in My Profile that controls the server-side
    catalyst agenda: 1/3/7-day lead window, one-to-four item hard cap, macro and earnings
    categories, saved-plan-only filtering, and post-event review reminders. The policy changes
    delivery only; it never changes scores, holdings, plans, or the canonical research record.
    Everyday investors can apply Essentials, Balanced, or Active presets without understanding
    every underlying control. Morning briefs and watchlist emails provide a calm Start Here cue
    and plain-language Why It Matters context; alerts remain research prompts, not trade instructions.

17. Portfolio Checkup — A free, investor-friendly workflow for up to five entered tickers or
    the signed-in user's watchlist. It reads recent persisted full-score evidence in one database
    query, excludes stale or missing rows, explains supportive/mixed/challenging in plain English,
    ranks the next research page to open, and shows bounded provisional earnings context. The list
    is equally weighted and explicitly not a substitute for Pro weighted portfolio analysis.

KEY SIGNALS:
- ATA Trucking (PCS 9): Monthly freight tonnage. Leads ISM PMI by 6-8 weeks. FRED TRUCKD11.
- Rail Traffic (PCS 9): Weekly intermodal volume. Leads trade data by 4-8 weeks. FRED RAILFRTINTERMODAL.
- Jobless Claims (PCS 9): Weekly initial claims. INVERSE. FRED IC4WSA.
- Yield Curve 10Y-2Y (PCS 9): INVERSE — inversion precedes every recession since 1955 (6-18mo lag). FRED T10Y2Y.
- HY Credit Spread (PCS 9): ICE BofA OAS. INVERSE — widening = bearish. Leads equity repricing 4-8 weeks. FRED BAMLH0A0HYM2.
- VIX (PCS 8): INVERSE. <15 = calm/bullish, >25 = stress/bearish, >40 = crisis/contrarian buy.
- 10Y Treasury Yield (PCS 8): INVERSE — rising yields compress growth multiples.
- Crude Inventories (PCS 8): EIA weekly stocks ex-SPR. INVERSE — draws bullish, builds bearish.
- Natural Gas Storage (PCS 7): EIA Lower-48 working gas. INVERSE vs 5-year average.
- Senior Loan Officer Survey (PCS 8): Net % banks tightening C&I standards. INVERSE. FRED DRTSCILM.
- Hyperscaler CapEx (PCS 8): MSFT+AMZN+GOOGL+META quarterly CapEx. Primary AI infrastructure demand signal.
- Uranium Proxy (PCS 8): URA ETF. Direct uranium demand. Leads nuclear utility revenue 12-24 months.
- FDA Approval Velocity (PCS 6): Weekly FDA drug approvals from openFDA. Regulatory tailwind signal for biotech/pharma.
- Quantum arXiv Velocity (PCS 5): Weekly quant-ph preprint count. Intentionally low PCS — unbacktested.

TICKER CATEGORIES:
- Nuclear/Uranium: CCJ, LEU, UEC, UUUU, URA, NLR, CEG, VST, SMR
- AI Infrastructure: FCX, WMB, GEV, PWR, VRT, NVDA, MSFT, AMZN, GOOGL, META, EQIX, DLR
- Macro/Transport: SPY, QQQ, IWM, UNP, CSX, ODFL, JBHT, UPS, FDX, CAT, DE
- Energy: XOM, CVX, OXY, COP, HAL, SLB, BKR
- Financials: JPM, BAC, GS, KRE
- Agriculture: ADM, BG, MOS, NTR
- Homebuilders: DHI, LEN, PHM, TOL
- Utilities: NEE, D, EXC, DUK, SO

IMPORTANT DISCLAIMERS:
- All signals are research tools, not buy/sell recommendations
- Without required provider credentials, affected signals are unavailable and excluded
- yfinance data is typically 15-minute delayed for equities
- The confluence score measures signal AGREEMENT, not proven forecasting accuracy
"""


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based fallback answers (fast, no API needed)
# ─────────────────────────────────────────────────────────────────────────────
QUICK_ANSWERS = {
    ("how do i start", "where do i begin", "getting started", "new user", "first time"): """
**Welcome to Unstructured Alpha!** Here's how to get started:

1. **Signal Dashboard** — Start here. See all macro signals color-coded by status.
2. **Market Overview** — Daily macro snapshot: indices, sectors, rates, commodities.
3. **Stock Screener** — Find tickers ranked by alternative data strength. Filter by sector or bias.
4. **Ticker Deep Dive** — Enter any ticker for a full signal breakdown and confluence score.

Tip: Add free **FRED** and **EIA API keys** in the sidebar Setup section for live macro data.
""",

    ("signal dashboard", "what is signal dashboard", "explain signal dashboard"): """
**Signal Dashboard** is your real-time macro signal overview.

It shows every tracked alternative data signal with **bullish/bearish/neutral** status based on recent trend vs. history.

- **Green (Bull)**: Signal pointing positive for equities
- **Red (Bear)**: Signal pointing negative — risk-off
- **Gold (Neutral)**: Signal in normal range, no strong directional read

Simple mode shows plain-English summaries. Pro mode shows z-scores, percentiles, and lag-correlation data.
""",

    ("ticker deep dive", "deep dive", "how does the analysis work", "explain the score"): """
**Ticker Deep Dive** is the flagship page. Key features:

**Confluence Score (0–100):**
- 0–35 = BEAR case · 35–65 = NEUTRAL · 65–100 = BULL case

The score is a **weighted average** of all signals assigned to that ticker:
- Weight = max(0.15, |Pearson r|) × (PCS/10)
- Only signals with p<0.05 statistical significance against that ticker's price history drive the main score
- Two tickers in the same sector get *different* scores because weights are calibrated per-ticker

**Deep Correlation Scan** — pick any signal and see the optimal lag (0-16 week scan), rolling 26-week correlation stability, and a signal+price overlay chart.
""",

    ("confluence score", "what does score mean", "how is score calculated"): """
The **Confluence Score** (0-100) measures how many alternative data signals currently align for a ticker.

**Formula:** Weight = max(0.15, |Pearson r|) × (PCS/10) → Confluence = weighted average

**Thresholds:** >65 = BULL · <35 = BEAR · 35-65 = NEUTRAL/MIXED
**Conviction levels:** Extreme (>80/<20) · Strong (>70/<30) · Moderate (>60/<40)

**Backtested honestly:** Walk-forward over 6 tickers, 19 monthly checkpoints.
Result: no statistically significant relationship with 1/2/3-month forward returns (|r| < 0.07).
Treat this as a real-time signal AGREEMENT read, not a proven forecast.
""",

    ("vix", "fear index", "volatility index"): """
**VIX — CBOE Volatility Index** (PCS 8/10) — The "fear gauge."

INVERSE signal: low VIX = calm = bullish for equities.

**Level thresholds:**
- VIX < 15 = Complacency / Calm → Bullish
- VIX 15-25 = Normal range → Neutral
- VIX > 25 = Elevated stress → Bearish
- VIX > 40 = Crisis / Capitulation (contrarian buy historically)

**Key history:** VIX hit 66 in March 2020. Peak marked a generational buying opportunity within 3 trading days.
""",

    ("yield curve", "10y 2y", "inversion", "inverted", "spread"): """
**Yield Curve Spread (10Y–2Y)** (PCS 9/10) — Most reliable recession predictor in modern history.

- **Positive spread (normal):** Banks earn more lending long → credit expansion → growth
- **Inverted (negative):** Market expects Fed rate cuts as growth slows → recession watch

**Historical accuracy:** Every U.S. recession since 1955 preceded by inversion, typically 6-18 months early.

**In the app:** Scored as INVERSE. Inversion = bearish. Lag ~52 weeks — the longest-leading signal in the library.
""",

    ("ata trucking", "trucking", "freight", "tonnage"): """
**ATA Trucking Tonnage Index** (PCS 9/10)

Monthly index of freight weight moved by U.S. Class-8 trucks — covers ~70% of domestic freight by value.
Officially part of the Conference Board Leading Economic Indicators.

**Why it leads:** Trucks move almost everything. A drop precedes inventory drawdowns and spending slowdowns by 6-8 weeks.

**Relevant tickers:** JBHT, ODFL, SAIA, WERN, UPS, FDX, XLI, SPY
**Source:** FRED series TRUCKD11
""",

    ("hy spread", "credit spread", "high yield", "hyg"): """
**High-Yield Credit Spread** (PCS 9/10) — The market's forward-looking stress detector.

ICE BofA US High Yield OAS — extra yield demanded to hold junk bonds vs. Treasuries.

**Why it leads:** HY spreads widen when credit markets price in default risk *before* equity analysts react. Hits leveraged companies 4-8 weeks before equity repricing.

INVERSE: widening = bearish, tightening = bullish.

**Source:** FRED series BAMLH0A0HYM2 (requires FRED API key for live data).
""",

    ("fred", "fred api", "api key", "fred key", "live data", "real data"): """
**FRED API Key** — Required for live macro signal data.

FRED (Federal Reserve Economic Data) powers signals like ATA Trucking, Yield Curve, HY Credit Spread, Jobless Claims, Consumer Sentiment, Retail Sales, and more.

**Without a key:** FRED-backed signals are marked unavailable and excluded from scores. The app never substitutes placeholder observations.

**To get a free key:**
1. Go to https://fred.stlouisfed.org/docs/api/api_key.html
2. Create a free St. Louis Fed account
3. Request API key (instant)
4. Paste it in the **Setup > Configure API Keys** sidebar section
""",

    ("nuclear", "uranium", "nuclear power", "ccj", "leu", "smr"): """
**Nuclear/Uranium Thesis**

Tickers tracked: CCJ, UEC, UUUU, LEU (miners) · URA, NLR (ETFs) · CEG, VST, SMR (utilities)

**Key signals for nuclear:**
- `uranium_proxy` (URA price) — direct demand signal
- `hyperscaler_capex` — AI data center power demand drives nuclear offtake agreements
- `natural_gas` — competing power source affects nuclear economics
- `ten_year_yield` — rate-sensitive for capital-intensive utilities
- `hy_spread` — credit conditions for leveraged names

**Score differentiation:** CCJ (pure miner) responds more to uranium_proxy. VST (generator) responds more to nat gas and hyperscaler CapEx. Same sector, different weights.
""",

    ("power supercycle", "supercycle", "ai power", "energy demand"): """
**Power Supercycle Thesis**

Five-leg thesis: AI compute → unprecedented electricity demand → largest grid upgrade since 1930s rural electrification.

**Three catalysts:**
1. AI Compute Demand — Hyperscaler CapEx (MSFT+AMZN+GOOGL+META) at all-time highs
2. Nuclear Renaissance — Data centers signing direct nuclear offtake deals (CEG, VST, SMR)
3. Grid Infrastructure — Copper, transformers, transmission (FCX, PWR, GEV) in multi-year supercycle

**Key signals:** hyperscaler_capex (primary), uranium_proxy, copper, natural_gas, ten_year_yield
""",

    ("stock screener", "screener", "how do i find stocks", "best tickers"): """
**Stock Screener** ranks 280+ tickers by a Macro + Momentum Rank (70% macro signal confluence / 30% price momentum).

**How to use:**
1. Sidebar filters: sector, signal bias (bull/bear/neutral), min PCS, score range
2. Text search: filter by ticker or company name
3. Click any row for inline preview
4. Click Ticker Deep Dive link for full analysis

**"Quick Analyze Any Ticker"** at the top: enter any ticker (TSLA, PLTR, etc.) even outside the tracked universe.
""",
}


def find_quick_answer(query: str) -> str | None:
    q = query.lower()
    for triggers, answer in QUICK_ANSWERS.items():
        if any(t in q for t in triggers):
            return answer.strip()
    return None


def try_claude_api(messages: list, system: str) -> str | None:
    """
    Call Claude API using the server-side ANTHROPIC_API_KEY environment variable.
    The key is a Render env var — never read from session_state or user input.
    """
    try:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            system=system,
            messages=messages,
        )
        return response.content[0].text
    except Exception:
        return None


def _get_system_prompt() -> str:
    """Build the full system prompt: static context + live signal state."""
    live_ctx = _build_live_signal_context()
    return APP_CONTEXT + ("\n\n" + live_ctx if live_ctx else "")


def get_fallback_response(query: str) -> str:
    q = query.lower()

    if any(w in q for w in ["hello", "hi", "hey", "greetings"]):
        return "Hello! I'm the Unstructured Alpha research assistant. Ask me about any signal, ticker, page, or what the macro is saying right now."

    if any(w in q for w in ["thanks", "thank you", "great", "perfect", "awesome"]):
        return "You're welcome! Let me know if you have other questions."

    if any(w in q for w in ["buy", "sell", "trade", "invest", "position", "recommend"]):
        return (
            "I can't give personalized investment advice — this is a research tool, not a trading advisor. "
            "What I can do is explain what the signals are saying and how to interpret confluence scores. "
            "Always do your own due diligence."
        )

    return (
        "I don't have a specific answer for that yet. Try asking about:\n"
        "- **Current conditions**: *What is the macro environment saying right now?*\n"
        "- **A specific signal**: VIX, ATA Trucking, Yield Curve, HY Spread...\n"
        "- **A ticker theme**: Nuclear, AI Infrastructure, Energy...\n"
        "- **Methodology**: Confluence Score, PCS weights, correlation...\n"
        "- **A page walkthrough**: Signal Dashboard, Ticker Deep Dive, Stock Screener...\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Live regime banner — shown at top of chat
# ─────────────────────────────────────────────────────────────────────────────

def _render_live_regime_banner() -> str:
    """Return a greeting suffix with live regime, or empty string on failure."""
    try:
        from utils.signals_cache import get_all_signal_scores
        all_sv = get_all_signal_scores()
        if not all_sv:
            return ""
        bulls = sum(1 for v in all_sv.values() if v.get("status") == "bullish" and not v.get("error"))
        bears = sum(1 for v in all_sv.values() if v.get("status") == "bearish" and not v.get("error"))
        total = len(all_sv)
        ratio = bulls / max(bulls + bears, 1)
        if ratio >= 0.60:
            regime, color = "BULLISH", "#4CAF50"
        elif ratio <= 0.35:
            regime, color = "BEARISH", "#EF5350"
        else:
            regime, color = "MIXED", "#C9A84C"
        return f"\n\n**Live read right now:** :{color[1:]}[{regime}] — {bulls}/{total} signals positive."
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────

has_claude = bool(os.environ.get("ANTHROPIC_API_KEY", ""))

st.markdown("## AI Research Assistant")
st.caption(
    "Powered by live signal data — ask what the macro is saying right now, "
    "interpret a signal, walk through a thesis, or explore any ticker."
)

if has_claude:
    st.success("Live signal-aware AI active — answers reflect today's real signal state.", icon="")
else:
    st.info("Using built-in knowledge base. AI responses available when Claude API key is configured on the server.")

# Quick topic buttons
st.markdown("**Quick topics:**")
topic_cols = st.columns(4)
quick_topics = [
    ("Macro right now", "What is the macro environment telling us right now? Give me the full live read."),
    ("Confluence Score", "How is the confluence score calculated?"),
    ("Nuclear thesis", "Tell me about the nuclear/uranium thesis and which signals matter most"),
    ("Getting started", "How do I get started with the platform?"),
]
for i, (label, prompt) in enumerate(quick_topics):
    if topic_cols[i % 4].button(label, key=f"qt_{i}", use_container_width=True):
        if "messages" not in st.session_state:
            st.session_state.messages = []
        st.session_state.messages.append({"role": "user", "content": prompt})
        answer = find_quick_answer(prompt) or try_claude_api(
            [{"role": "user", "content": prompt}], _get_system_prompt()
        ) or get_fallback_response(prompt)
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()

st.divider()

# Initialize chat history with live-aware greeting
if "messages" not in st.session_state:
    st.session_state.messages = []
    live_suffix = _render_live_regime_banner()
    st.session_state.messages.append({
        "role": "assistant",
        "content": (
            "Hello! I'm the Unstructured Alpha research assistant — now connected to live signal data."
            + live_suffix +
            "\n\n**Try asking:**\n"
            "- *What is the macro environment saying right now?*\n"
            "- *What does the yield curve look like today?*\n"
            "- *Which signals are most bearish right now?*\n"
            "- *Walk me through the Ticker Deep Dive page*\n"
            "- *Which signals matter most for nuclear tickers?*"
        )
    })

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Ask about current macro conditions, signals, tickers, or methodology…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            # 1) Rule-based quick answers (instant, no API)
            answer = find_quick_answer(prompt)

            # 2) Claude API with live signal context — rate-limited (Anthropic $)
            if not answer:
                try:
                    from utils.ratelimit import guard as _rl_guard
                    _ai_ok, _ai_retry = _rl_guard("ai_research")
                except Exception:
                    _ai_ok, _ai_retry = True, 0
                if not _ai_ok:
                    _mins = max(1, _ai_retry // 60)
                    answer = (
                        f" You've reached the AI-assistant question limit for now — this keeps "
                        f"the feature fast and affordable for everyone. Please try again in about "
                        f"{_mins} min. In the meantime, the **Signal Dashboard** and **Ticker Deep "
                        f"Dive** have the same live data you can explore directly."
                    )
                else:
                    system_prompt = _get_system_prompt()  # rebuilds live context each call
                    claude_messages = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages[:-1]
                    ] + [{"role": "user", "content": prompt}]
                    answer = try_claude_api(claude_messages, system_prompt)

            # 3) Rule-based generic fallback
            if not answer:
                answer = get_fallback_response(prompt)

        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})

# Clear chat
if len(st.session_state.get("messages", [])) > 1:
    if st.button("Clear conversation", key="clear_chat"):
        st.session_state.messages = []
        st.rerun()

# Suggested questions
with st.expander("More suggested questions"):
    suggestions = [
        "What is the macro environment telling us right now?",
        "Which signals are currently most bearish?",
        "What does the HY credit spread look like today?",
        "Explain the ATA Trucking signal and why it matters",
        "How do I find the most bullish tickers in the screener?",
        "What's the difference between PCS and correlation weight?",
        "Walk me through using the Stock Screener to find AI infrastructure plays",
        "Why might two uranium tickers have different confluence scores?",
        "What does it mean when the yield curve is inverted?",
        "How do federal contract awards relate to stock performance?",
        "What is the Power Supercycle thesis?",
        "Which signals are the most reliable historically?",
    ]
    for s in suggestions:
        if st.button(s, key=f"sug_{s[:20]}", use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": s})
            answer = find_quick_answer(s) or try_claude_api(
                [{"role": "user", "content": s}], _get_system_prompt()
            ) or get_fallback_response(s)
            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.rerun()
