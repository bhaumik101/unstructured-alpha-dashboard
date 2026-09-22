"""Methodology — what the exposure report measures, what it does not, and what failed.

Written for a reader who wants to decide whether to trust the product. The
numbers quoted from the engine are read from utils/exposure.py, so the page
cannot drift from the code.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Methodology — Unstructured Alpha", layout="wide")

from utils import exposure as ex  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from utils.app_theme import product_page_header  # noqa: E402
from utils.header import render_header  # noqa: E402

render_header("Methodology")
try:
    from utils.instrumentation import record_once
    record_once("methodology_viewed")
except Exception:
    pass

product_page_header(
    "Methodology",
    "How exposure is measured, how to read the uncertainty, and what we tested that did not work.",
    eyebrow="How this works",
    facts=("Newey-West standard errors", "90% ranges on every estimate",
           "A five-factor correction before anything is called clear"),
)

factor_rows = "\n".join(
    f"| {f.label} | {f.shock_phrase[0].upper() + f.shock_phrase[1:]} | FRED `{f.series_id}` |"
    for f in ex.FACTORS
)

st.markdown(f"""
### The short version
The exposure report measures how a portfolio **has moved** alongside five economic forces over roughly the past three years. It does not predict what the portfolio will do next. Every number comes with a range, the number of weeks behind it, and a label saying how much weight the evidence can bear.

### What is measured
For each portfolio we take up to {ex.WINDOW_WEEKS} weeks of Friday-to-Friday returns and compare them with weekly changes in:

| Economic force | Each result is expressed per | Source |
|---|---|---|
{factor_rows}

Prices come from Yahoo Finance and are adjusted for dividends and splits. Holdings are treated as fixed weights, rebalanced weekly.

### How
1. **One regression per portfolio.** Weekly portfolio returns are regressed on the five weekly factor changes **and on the U.S. stock market (SPY)** at the same time. Rates, oil and the dollar often move on the same days as stocks. Without the market in the regression, almost every stock portfolio would look sensitive to everything.
2. **Weekly data.** Interest rates and oil settle at different times of day than stock closes. Weekly changes remove most of that timing mismatch.
3. **Honest uncertainty.** Standard errors use the Newey-West method with {ex.NEWEY_WEST_LAGS} lags, because weekly returns are not fully independent. Each result shows a **90% range**.
4. **Holdings add up.** Each holding is measured on exactly the same weeks as the portfolio, so the holdings' contributions (weight × own sensitivity) add up to the portfolio figure.
5. **Missing data is never filled in.** A holding with less than {ex.MIN_WEEKS} weeks of history, or an economic series that fails to load, is left out and named in the report.

### Reading the evidence labels
| Label | What it takes | What it means |
|---|---|---|
| **Clear** | A t-statistic of at least {ex.CLEAR_T:.2f} | {ex.EVIDENCE_EXPLAINED['clear']} |
| **Tentative** | A t-statistic of at least {ex.Z90:.2f} | {ex.EVIDENCE_EXPLAINED['tentative']} |
| **Not distinguishable from zero** | Anything weaker | {ex.EVIDENCE_EXPLAINED['indistinct']} |
| **Not enough data** | Fewer than {ex.MIN_WEEKS} weeks | {ex.EVIDENCE_EXPLAINED['not_enough_data']} |

**Why "Clear" is strict.** Testing five factors at once gives five chances for noise to look like a finding. The Clear threshold is corrected for that (Bonferroni: a 5% error rate shared across five tests). On simulated portfolios with no real exposure, about 1 in 100 factor readings is labelled Clear.

### Sample size and power
Three years of weekly data gives about 156 observations. That is enough to detect moderate relationships, not subtle ones. **Economic growth is published monthly**, so it rests on about {ex.GROWTH_WINDOW_MONTHS} observations. With that few, only strong relationships can be told apart from noise, and the report always labels growth as limited evidence.

### What changed
The latest {ex.RECENT_WEEKS} weeks are compared with the {ex.EARLIER_WEEKS} weeks before them. The two periods don't overlap, so their uncertainties can be combined honestly. A change is shown only when the difference is larger than that combined uncertainty. The "recent weeks" table applies the measured sensitivities to what actually happened over the last {ex.RECENT_MOVE_WEEKS} weeks. It explains the recent past, and only for exposures labelled Clear or Tentative.

### What the report does not mean
- **It is not a forecast.** A portfolio that fell when rates rose over the past three years may not do so over the next three.
- **It is not advice.** It does not know your goals or circumstances, and it never suggests buying or selling anything.
- **It is not a complete risk model.** It covers five economic forces and growth. Company-specific risks, sector risks and liquidity are not measured.
- **A Clear label is not a cause.** It means the relationship was consistent and larger than noise, not that one thing caused the other.

### Known limitations
- The broad dollar index is published weekly with a short delay, which can hold the whole report about a week behind. The report shows its data date.
- Credit spreads use the Baa corporate spread (`BAA10Y`). FRED licenses only about three years of the high-yield spread series, which can't reliably fill the window.
- Funds and stocks with less than two years of history are left out.
- Short positions are not supported yet.

### What we tested that did not work
Before building this, we spent months testing whether this kind of public data could **predict** markets. It could not do so reliably, and we think that result matters as much as any finding.

- **Stock direction from macro signals:** no reliable edge.
- **Nowcasting U.S. industrial production:** about ten model configurations across three targets. The best one improved on a simple "no change" guess by a margin that was not statistically distinguishable from luck (p ≈ 0.13), and fell to about zero once 2020 was excluded. Best of ten tries is not evidence.
- **Look-ahead bias, found and corrected:** one early version used data before it would have been published, which made results look better than they were. It was corrected in the public record rather than quietly fixed.
- **Market fragility from signal dispersion:** no measurable relationship with later volatility.
- **Statistical power:** the original signal search could not detect correlations weaker than about 0.35, so it was never capable of finding the effects it looked for.

**Why this matters.** A product that only publishes what worked hides how many things were tried. We publish the failures so you can judge the successes.

### How hindsight is kept out of the research record
The one predictive test still running is a monthly nowcast published **before** each official number comes out. Each estimate is written once and can't be edited. Nothing is reported as skill until at least 12 months have been scored. New data candidates are registered with their reasoning before testing, tested once, and judged against a threshold that tightens as more are tried. See the research record page.

### Measuring exposure vs predicting returns
Exposure asks: *how has this portfolio behaved when rates, inflation, the dollar, oil or credit moved?* That can be measured from history, with honest uncertainty. Prediction asks: *what will happen next?* Our testing says this data cannot answer that reliably, so the product does not try.
""")

ui.render_report_footer()
