# Research round, Nov 22 2026: what would change the whole thing

The loop: measure → research → bet → set the numbers that would prove the bet
wrong → check them → correct. This file records one turn of it.

## 1. What the data said first

After three days of the new tracking (Nov 19–22):

- Site visitors kept rising (81 in the week of Nov 16, part of it before the
  visitor-id fix in #366).
- **Tool use: zero.** No visitor used the landing X-ray, the quiz, the game,
  What if? or the X-ray. Verified the pipeline is not the cause: a test event
  sent through the live relay was stored. Visitors arrive (the landing, single
  views of sector pages) and leave without doing anything.

So the problem is not only traffic: pages that need a click to give value do
not get the click. Value has to be on the page at arrival.

## 2. What the research said

| Finding | Source | What it means here |
|---|---|---|
| Queries like "stocks that benefit from rate cuts" are answered by forecast commentary ("3 stocks poised to win big", "could run if the Fed cuts"), not measured evidence | live search results, Nov 2026 (Motley Fool, Nasdaq, 24/7 Wall St, Barchart, Finviz) | The measured past is an open niche, and it is exactly the data this site holds |
| Wise's currency pages: one templated page per real query, each on live data nobody else has; estimated millions of organic visits | [Ahrefs case study](https://ahrefs.com/blog/wise-seo-case-study), [Failory](https://newsletter.failory.com/p/day-wise-created-250k-variants-calculator) | Build one page per question people type, each on original data |
| A travel site lost ~98% of 50,000 thin templated pages from the index in 2025 | [Omnius](https://www.omnius.so/blog/wise-case-study) (secondary) | Every page must be substantive; thin ones are noindex |
| Google's guidance and recent core updates favour original data and first-hand evidence for finance (YMYL) pages | [Google helpful-content guidance via iPullRank](https://ipullrank.com/eeat-ymyl-ai-search); agency commentary (directional, not Google-documented weights) | Measured, sourced pages with a method section fit the direction |
| Activation is the first moment of value, and should be inside the first session | [Amplitude](https://amplitude.com/blog/time-to-value-drives-user-retention), [UXCam](https://uxcam.com/blog/why-most-teams-have-the-wrong-aha-moment/) (vendor data, directional) | Answer the question on arrival; no interaction needed |
| Wordle spread through the copyable, spoiler-free result grid and a once-a-day ritual | [TechCrunch](https://techcrunch.com/2022/05/04/wordle-new-york-times-user-growth), [Wikipedia](https://wikipedia.com/wiki/Wordle) | Already built: share cards for both daily games (#370, #372) |

## 3. The bet: "What moved when" (#373)

28 pages, one per force and direction, titled the way the question is asked
("Stocks that went up when interest rates fell"), answered on arrival from the
measured readings: what went up, what went down, counts of no clear link, the
sector split, each figure with its 90% range and evidence label, and a link to
X-ray your own portfolio. Linear readings, stated on the page. Thin pages are
noindex.

Sanity check on real data: "when interest rates fell" ranks homebuilders (D.R.
Horton, PulteGroup, Lennar, ITB), REITs and the long-bond fund TLT at the top --
what the economics says should happen, which is evidence the engine measures
what it claims.

## 4. What the research round caught: a broken signal

Rendering the pages on real data exposed that **every natural-gas reading was
wrong**. The engine measured gas against FRED's daily Henry Hub spot price,
which ranged $1.21–$30.72 in the window, with a +904% week (Jan 2026) and a
+380% week (Jan 2024). Weekly changes had an 80% standard deviation against a
7% median move, so the few spike weeks set every slope: a gas producer (EQT)
read +0.11% per 10% gas move, "Clear". Fixed in #373:

- natural gas is now measured from UNG (front-month futures), the same remedy
  the engine already uses for gold (GLD) and copper (CPER);
- a general guard: any extra force whose weekly changes are spike-dominated
  (std / robust std > 3.0) is excluded and named, never shown. On three years
  of real data every other series scored 0.90–1.84 (VIX highest); gas spot 7.18;
- until the weekly job re-measures (data week ≥ 2026-11-20), the gas pages say
  why and stay out of search.

## 5. The numbers that decide it (check on these dates)

| Check | Pass | Fail → correct |
|---|---|---|
| Dec 1: natural-gas readings re-measured | data week ≥ Nov 20, gas producers (EQT, EXE) read several % per 10% move, notice gone | if the guard excluded UNG too, or producers still read ~0.1%, re-examine the series |
| **Result, checked Nov 25** | **Passed.** 540 of 545 gas rows dated Nov 20 (5 stragglers older), guard did not exclude UNG. EQT +0.11% → **+1.89%** per 10% (Clear), EXE **+1.78%** (Clear); 16 Clear, 127 Tentative overall. "Several %" was a loose bar: ~1.9% (elasticity ~0.19 with the market and oil held fixed) is the honest size. Notice gone from /forces/natgas and both /when gas pages; both indexable, in the sitemap, submitted to IndexNow (200). | — |
| Dec 22 (4 weeks): `/when/*` page views from search | ≥ 25 views/week on When pages, and ≥ 3 X-ray clicks from them | if < 5/week after IndexNow + sitemap, the titles do not match demand: rewrite titles from Search Console queries (needs GSC verification) |
| Dec 22: tool users per week | > 0, rising | if still 0, the first-session problem is on every page: put an answer above the fold on the landing too |

## 6. Does a reading matter? Out-of-sample evidence (2026-11-25)

Asked for: "clear evidence ... find some sort of correlation ... make it matter".
A Clear label is a statistic; the question a reader has is whether the
exposure showed up in real money and whether it lasts. `utils/evidence.py`
answers both from each report's own weekly data:

- **Big weeks.** For each Clear or Tentative force, its 8 largest weeks; in each,
  the portfolio's move beyond the market and the other forces (the joint fit's
  residual plus that force's term), and whether it went the reading's way.
- **New weeks.** Re-estimate on the first two-thirds of the weeks only, then in
  the last third's big weeks (|move| > 1 sd) count how often the beyond-market
  move pointed the way the earlier estimate said. A coin flip scores 50%.

Pooled across 14 test portfolios (Balanced, international-heavy, long bonds,
energy, gold, homebuilders, banks, high yield, growth, utilities, EM, TIPS,
small value, miners; 104 weeks to estimate, 52 to test, ending 2026-11-20):

| Force (Clear readings) | Readings | Matched on new weeks |
|---|---|---|
| Interest rates | 8 | **72 / 80 = 90%** |
| Credit spreads | 2 | 22 / 26 = 85% |
| U.S. dollar | 6 | **80 / 102 = 78%** |
| Oil | 4 | 77 / 116 = 66% |
| Inflation expectations | 4 | **20 / 40 = 50%** (a coin flip) |

Tentative readings: oil 61%, credit 51%, inflation 47%.

**What it means.** Rate and dollar exposures are real and persistent: a reader
can act on knowing them (e.g. how much a long-bond or international fund carries).
Inflation readings mostly did not survive new weeks; the exception was TIPS
(9 / 10), which hold inflation directly. This agrees with the Cleveland Fed
cross-check (#392), where the inflation reading depended on the time scale.

**Shipped (#398).** Every report now shows, per reading, its biggest weeks as
bars, the average gap in dollars, and the new-weeks verdict ("Held up on weeks
it had never seen" ≥ 70%, "Partly" 55–70%, "Did not hold up" < 55%); the
plain-English summary at the top repeats the verdict next to each finding and
says "treat it with caution" when a reading failed.

**Caveats.** One split, one 3-year window. The 14 portfolios share VTI, so they
are not independent; read the pooled rates as indicative. A reading that held
up in the past describes the past; it is not a forecast.

**Bug found on the way.** The first big-weeks view took out only the market.
Long bonds' credit reading then went the wrong way in 7 of 8 big weeks while
matching 13 / 13 out of sample: big credit weeks are big rate weeks, and the
rate effect swamped them. Both views now net out the other forces, as the
reading itself does (credit 8 / 8 and 13 / 13); a test pins it.

**Acted on (#399).** Inflation readings now keep "Clear" only if they pass the
new-weeks test themselves (≥ 70% of the later period's big weeks matched);
otherwise they are shown as Tentative, marked "was Clear", with the score. The
numbers are unchanged. Applied in the engine (`exposure._require_out_of_sample`),
so the report, stock pages, `/exposure.csv` and the "when" pages agree. On the
study's portfolios: banks (5/10), high yield (2/10) and small value (4/10) lost
Clear; TIPS (9/10) kept it.

## 7. More Clear readings? What the walk-forward test allows (2026-11-26)

Asked for: "more clears and more data to be actually useful or marketable".
Loosening the bar would add readings that do not last, so each candidate was
judged by how its Clear readings held up on a year they had never seen.

**Design.** 35 funds (broad, sector, bond, credit, commodity, international),
each alone. Three held-out test years ending 2024-11, 2025-11, 2026-11. Before
each, fit the engine's model on a window; label the five core forces; then in
the test year's big weeks (|move| > 1 sd) count how often the fund's move beyond
the market and the other forces went the way the fitted slope said. 1,050
readings per variant. Scripts: `/tmp` study harness, reproduced from
`utils/exposure.py` internals (`_fit_on_frame`, `to_changes`).

| Variant | Clear readings | Held up next year |
|---|---|---|
| 3 years weekly, Bonferroni (before) | 149 (28%) | 74% |
| 3 years weekly, **Holm step-down** | 161 (31%) | 73% |
| 3 years weekly, FDR 10% | 216 (41%) | 69% |
| 5 years weekly, Bonferroni | 180 (34%) | 71% |
| 5 years weekly, Holm | 193 (37%) | 70% |
| 3 years **daily** | 176 (34%) | 69% |
| 3 years, 2-day returns | 149 (28%) | 72% |
| *Tentative (any variant)* | — | *52–56%* |

The readings each loosening ADDS: Holm 64% (12), 5-year window 59% (62), FDR
55% (55). FDR and the longer window mostly add coin flips; daily data adds
noise from mismatched closing times. **Clear on both 3 and 5 years, same
direction: 76%** (118 readings); Clear on 3 years only: 64%.

Also: 87% of fund-years already have at least one Clear reading; a lack of
Clears is not what limits the product.

**Shipped (#400).**
- Holm's step-down for the five core forces (same 5% family-wise error; can
  only promote: its first bar is the old one). False-Clear rate re-measured on
  the null simulation: 10 of 1,000 (1.0%), none from the step-down.
- "5-yr confirmed": every Clear reading is re-fitted on 260 weeks (already
  loaded for the rolling chart); Clear again, same sign, earns the badge.
  Confirmed held 75%, unconfirmed Clear 65%. On the 14 study portfolios, 17 of
  21 Clear readings are confirmed.
- The track record itself, now stated in the report and on Methodology:
  Clear readings held their direction in 74% of the next year's big weeks
  (75% confirmed), weaker readings 55%.

**What would genuinely add more Clears** (not done here): more forces that
matter to specific holdings (sector and style spreads already exist as
extras), and per-holding readings for single stocks, where exposures are larger
than in diversified funds.

## 8. Single stocks: do their readings hold up? (2026-11-27)

Same walk-forward design as §7 on 70 large U.S. stocks across sectors (tech,
banks, energy producers and refiners, utilities, staples, homebuilders,
industrials, health care, REITs, materials, autos), three held-out years,
2,095 readings, 3-year window, Holm labels.

| Stock readings | Held up next year |
|---|---|
| Clear | **71%** (151) |
| Clear, 5-yr confirmed | **74%** (109) |
| Clear, not confirmed | 60% (42) |
| Tentative | 56% |
| Not distinguishable | 51% |

By force (Clear): rates 78%, oil 78%, dollar 62%, inflation **36%** (12; worse
than chance, which the §6 inflation check now screens), credit 6/8.

Single stocks give FEWER core Clears per reading than funds (14% vs ~30%):
company news is noise the five forces do not explain. In the stock library
(545 stocks, live `/exposure.csv`) 469 (86%) have at least one Clear reading,
mostly through style and extra forces (value 60%, size 31%, momentum 23%) plus
rates (23%) and oil (15%).

**Shipped (#401).** The stock page now opens with the plain-English answer
("If you had $10,000 in XOM…", in dollars, with each reading's held-up
verdict), shows the proof panel with the stock track record, the dollar view
and the glossary. Portfolio reports and stock pages also name the clearest of
the other forces (style, currency, commodity) in the summary, labelled "not yet
tested on new weeks" because this study covered the five core forces.
Check on XOM: oil Clear, 25 of 29 big new weeks matched, 5-yr confirmed; its
weekly beta of 0.09 over 2023-26 was verified against raw prices (corr 0.06).
