# Data sources that would make the product better — research, 2026-11-24

Asked for: "scour the web for more useful sources of info to better the
product". Each entry below was checked against the live web on 2026-11-24;
"verified" means the file or endpoint was actually fetched from this
environment, "documented" means its official page describes it but it was not
fetched here. Everything listed is free; two need a free key.

Already in the product (not repeated below): FRED series for the five forces,
ALFRED vintages (point-in-time audit), the Chicago Fed NFCI (nowcast), daily
Henry Hub gas (DHHNGSP), VIX, ICE BofA credit spreads, SEC EDGAR XBRL.

## Ranked by what it does for a reader

| # | Source | What it adds to the product | Effort | Status |
|---|--------|-----------------------------|--------|--------|
| 1 | **SEC Form N-PORT data sets** (quarterly ZIP of every fund's holdings) | **Explain a fund's exposure from what it owns.** Today the report says VXUS carries 78% of the dollar exposure; with look-through it can say *why* in beginner terms: "VXUS holds ~8,000 stocks outside the U.S., so a stronger dollar shrinks their value in dollars." Also: sector and country mix per fund, overlap between two funds. | **Shipped (#389)**: built per fund from EDGAR (latest NPORT-P per series), not the bulk file; 71 funds; `scripts/build_lookthrough.py` | **Verified** ([SEC](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets), [data.gov listing to 2026 Q2](https://catalog.data.gov/dataset/form-n-port-data-sets)) |
| 2 | **SEC `company_tickers.json`** | Full company name for ~10,400 listed tickers, so any stock in a report is spelled out. | Done in this PR (bundled 104 KB snapshot, `scripts/refresh_sec_tickers.py`) | **Verified** (fetched: 10,399 names) |
| 3 | **SEC Investment Company Series & Class data set** | Names for **mutual funds and ETF share classes** (the SEC's `company_tickers_mf.json` maps fund tickers to series/class IDs but carries no names; this data set has them). Closes the name gap for 401(k) funds. | Low–medium | `company_tickers_mf.json` **verified** (28,669 fund tickers, IDs only); names data set documented ([SEC](https://www.sec.gov/open/datasets-investment_company)) |
| 4 | ~~Weekly Henry Hub spot (FRED `WHHNGSP`)~~ | **Not adopted — measured worse than what is live.** The gas problem was already fixed in #373 by measuring against UNG (front-month futures). Over the same 3 years of weeks: daily spot sd 80% (max +904%), weekly-average spot sd 28% (max +301%), UNG sd 8% (max +35%). Weekly averaging still lets a +301% week through and lags a week. | — | **Verified** (EIA weekly/daily files vs UNG, 2026-11-24) |
| 5 | **Cleveland Fed expected inflation** (FRED `EXPINF1YR`…`EXPINF30YR`, monthly) | A second, model-based inflation-expectations measure next to the market breakeven (T10YIE), which also moves with bond liquidity. Lets the report say whether an inflation reading holds up on both. | Low | Documented ([Cleveland Fed](https://www.clevelandfed.org/indicators-and-data/inflation-expectations)) |
| 6 | **NY Fed ACM term premium** (daily, 1961–) | Splits "interest rates" into *expected future rates* vs *extra pay for holding long bonds* — the question advanced users ask when long-bond funds move. | Medium (site download, weekly update) | Documented ([Liberty Street Economics](https://libertystreeteconomics.newyorkfed.org/2014/05/treasury-term-premia-1961-present/)) |
| 7 | **Kenneth French data library** (weekly Fama-French factors) | Independent check on the product's market adjustment, and an optional "style" panel (size, value) beside the macro forces. | Low–medium | Documented ([Dartmouth](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_factors.html)) |
| 8 | **Tiingo end-of-day prices** | A second price provider when Yahoo fails, so a report degrades instead of erroring. Free tier ≈ 50 requests/hour, 1,000/day, 500 symbols/month (secondhand figures; confirm on Tiingo's pricing page). | Medium; **needs a free key** | Documented ([Tiingo docs](https://api.tiingo.com/documentation)) |
| 9 | **EIA API v2** | Energy detail beyond prices (inventories, production) for oil and gas readings. Free; **key required**; stay under ~5 requests/second. | Medium | Documented ([EIA FAQ](https://www.eia.gov/opendata/faqs.php)) |
| 10 | **Atlanta Fed GDPNow** (FRED `GDPNOW`) | Context on the "What changed" page: the Atlanta Fed's running estimate of this quarter's growth, clearly labelled as theirs. Never used as a signal or a forecast of ours. | Low | Documented ([FRED](https://fred.stlouisfed.org/data/GDPNOW)) |

## For beginners

- **Plain-language definitions.** Link the words a newcomer stops at (ETF,
  mutual fund, bond, Treasury yield, credit spread) to the SEC's investor
  education glossary at [Investor.gov](https://www.investor.gov/introduction-investing/investing-basics/glossary)
  rather than writing our own definitions of regulated terms. The glossary
  pages did not return their text to the search tool, so the exact URLs
  should be opened and checked before linking.
- **Look-through (source 1) is the biggest beginner win**: it turns "this
  fund carries the exposure" into "because of what it owns".

## Recommended order

1. ~~N-PORT look-through~~ shipped in #389 (71 funds); refreshed automatically every Tuesday by `cron/refresh_lookthrough.py` (#390), which parses only funds with a new filing.
2. ~~Weekly Henry Hub~~ measured and rejected: UNG (live since #373) is far calmer; see row 4.
3. Fund names from the series/class data set (finishes the names work).
4. Cleveland Fed expected inflation as a robustness check on one force.
5. Tiingo as a price fallback (needs the owner to create a free key).

## Rules any of these must follow (from CLAUDE.md)

- A failed source is excluded, never synthesized.
- Verify what a series *measures* matches what the copy *claims*.
- Prefer first-print / point-in-time data where revisions exist (ALFRED).
