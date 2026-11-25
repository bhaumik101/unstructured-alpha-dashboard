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
| 3 | **SEC Investment Company Series & Class data set** | Names for **mutual funds and ETF share classes** (the SEC's `company_tickers_mf.json` maps fund tickers to series/class IDs but carries no names; this data set has them). Closes the name gap for 401(k) funds. | **Shipped (#391)**: 28,845 fund and share-class names bundled (`utils/data/sec_fund_names.json.gz`) | **Verified** (2026 file fetched, 43,123 classes) |
| 4 | ~~Weekly Henry Hub spot (FRED `WHHNGSP`)~~ | **Not adopted — measured worse than what is live.** The gas problem was already fixed in #373 by measuring against UNG (front-month futures). Over the same 3 years of weeks: daily spot sd 80% (max +904%), weekly-average spot sd 28% (max +301%), UNG sd 8% (max +35%). Weekly averaging still lets a +301% week through and lags a week. | — | **Verified** (EIA weekly/daily files vs UNG, 2026-11-24) |
| 5 | **Cleveland Fed expected inflation** (FRED `EXPINF10YR`, monthly) | **Shipped (#392)**: every report cross-checks its inflation reading against the model measure (60 monthly fits, market held fixed; direction and evidence compared, never size). Verdicts: holds on both / same direction / not confirmed / the two disagree. First real result (Balanced sample): same direction, weaker on the model -- and on monthly data the breakeven itself points the other way, which the panel now says. | — | **Verified** (fetched by the app's FRED path, 2026-11-25) |
| 6 | **NY Fed ACM term premium** (daily, 1961–) | **Shipped (#393)**: every report splits its interest-rate reading into the expected path of short-term rates (ACMRNY10) and the term premium (ACMTP10), which add up to the 10-year yield, fitted the headline's way. Bundled daily snapshot from 2014 plus a weekly cron that stores new days (`cron/refresh_acm.py`; the 10 MB .xls is parsed only there, +46 MB). First result (Balanced mix): both parts Clear, expected path −0.66%, term premium −0.51% per 0.25 pt. | — | **Verified** (NY Fed file fetched, current to 2026-11-23) |
| 7 | **Kenneth French data library** (weekly Fama-French factors) | Independent check on the product's market adjustment, and an optional "style" panel (size, value) beside the macro forces. | **Shipped (#394)**: weekly Mkt-RF/SMB/HML/RF snapshot from 2014 (665 weeks) plus a weekly cron (`cron/refresh_famafrench.py`, table `ff_weekly`). Every report re-measures market beta against Mkt-RF+RF on the same weeks (agrees within 0.05 or 5%) and fits SMB/HML tilts with the market held fixed, compared with its own IWM/IWB and IWD/IWF readings. Growth mix: SMB −0.27, HML −0.80, both Clear. | **Verified** (Dartmouth weekly zip fetched, current to 2026-09-25) |
| 8 | **Tiingo end-of-day prices** | A second price provider when Yahoo fails, so a report degrades instead of erroring. Free tier ≈ 50 requests/hour, 1,000/day, 500 symbols/month (secondhand figures; confirm on Tiingo's pricing page). | Medium; **needs a free key** | Documented ([Tiingo docs](https://api.tiingo.com/documentation)) |
| 9 | **EIA API v2** | Energy detail beyond prices (inventories, production) for oil and gas readings. Free; **key required**; stay under ~5 requests/second. | Medium | Documented ([EIA FAQ](https://www.eia.gov/opendata/faqs.php)) |
| 10 | **Atlanta Fed GDPNow** (FRED `GDPNOW`) | Context on the "What changed" page: the Atlanta Fed's running estimate of this quarter's growth, clearly labelled as theirs. Never used as a signal or a forecast of ours. | **Shipped (#395)**: on "What changed", with the estimate's path through each update (ALFRED vintages: daily for the last 12 days, weekly before) and its 8-quarter record against BEA's current figures. Cached 6 hours in the app; a failed download shows nothing. Feeds no reading. | **Verified** (FRED and ALFRED fetched, 2026-11-25: Q4 2026 +3.21%, updated 2026-11-18) |

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
3. ~~Fund names~~ shipped in #391 (28,845 mutual fund and ETF share classes).
4. ~~Cleveland Fed cross-check~~ shipped in #392.
5. ~~Fama-French check~~ shipped in #394.
6. ~~GDPNow context~~ shipped in #395.
7. Tiingo as a price fallback (needs the owner to create a free key).

## Rules any of these must follow (from CLAUDE.md)

- A failed source is excluded, never synthesized.
- Verify what a series *measures* matches what the copy *claims*.
- Prefer first-print / point-in-time data where revisions exist (ALFRED).
