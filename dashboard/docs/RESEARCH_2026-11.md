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
