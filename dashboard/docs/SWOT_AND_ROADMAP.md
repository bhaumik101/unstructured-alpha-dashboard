# Unstructured Alpha — Product & Company Assessment

**Date:** 19 July 2026
**Basis:** live walkthrough of app.unstructuredalpha.com, production database queries, Render service logs, and the codebase. Figures are measured, not estimated. Where evidence is missing it is marked as such rather than filled in.

---

## 1. The evidence base

Everything below rests on these numbers. They are small, and that is itself the most important finding.

| Measure | Value | Source |
|---|---|---|
| Registered users | 6 (2 Pro) | `users` table |
| Signups in last 7 days | 0 | `users.created_at` |
| Signup window | 21 Jun – 7 Jul 2026 | `users` |
| Distinct signed-in users active per day | 1 | `analytics_events` |
| Sessions recorded | 121 | `analytics_events` |
| Single-event sessions | 96.7% | `analytics_events` |
| Users with ≥1 watchlist ticker | 2 of 6 (33%) | `watchlist` |
| Onboarding steps recorded | 0 | `onboarding_progress` |
| Resolved predictions | 9 (reporting threshold is 20) | `prediction_log` |
| Tickers with full Confluence Score | 280 | `score_snapshots` |
| Tickers with macro+momentum score | 424 and rising | `score_snapshots` |
| Searchable symbols | 12,641 | NASDAQ Trader directory |
| Qualifying scoreable universe | 5,273 | `utils/scoring_universe` |
| Macro signals | 47 | `utils/config` |

**Page views, all time:** Screener 41 · Deep Dive 20 · Signal Dashboard 11 · Recommender 11 · Home 10 · Watchlist 10 · Admin 8 · Portfolio Suite 6 · Options Flow 2 · Today's Brief 2.

Two caveats that limit how far these numbers can be pushed. The single active user is the founder, so the page-view distribution reflects development, not demand. And session duration is unmeasurable — every percentile reads 0s because until today each session emitted exactly one event, so first and last event were the same. Instrumentation to fix that shipped today and has recorded one heartbeat; meaningful engagement data is days away, not available now.

---

## 2. SWOT

### Strengths

**Intellectual honesty is built into the product, not bolted on.** This is the genuine differentiator and it is unusual in retail fintech. The accuracy leaderboard withholds a hit rate below 20 resolved predictions and awards a medal only when the lower bound of a Wilson interval clears chance — so "3 of 3" cannot outrank "61% of 200". The backtest now withholds CAGR below a year of data rather than annualising four weeks. `score_kind` keeps the full Confluence Score and the cheaper macro+momentum score as distinct metrics rather than two precisions of one, because on AAPL they differ by 11 points. Most competitors would have shipped the flattering number.

**The signal research is real work.** 47 macro signals each carry a documented causal mechanism, a researched `lag_weeks` lead time, and cited historical cases. That corpus is the actual moat — it is slow to build and hard to copy, unlike any individual screen or chart.

**Infrastructure is beyond what the user count requires.** Circuit breakers, pooled retrying sessions, Redis-backed distributed rate limiting, structured JSON logging with correlation IDs, liveness/readiness split, 19 scheduled jobs, and a 575-test suite. The platform will not fall over when traffic arrives.

**Iteration speed is high.** A dozen substantive fixes shipped in a single session, each with regression tests.

### Weaknesses

**There is no traction, and no mechanism producing any.** Six users, zero signups in twelve days, one active user who is the founder. Every other weakness is downstream of this.

**Silent failure is a systemic pattern, not a series of unrelated bugs.** This session found, in one codebase:

- Three of four onboarding steps had no `mark_step()` call site, so the checklist sat at zero for every user regardless of behaviour.
- 25 of 27 declared analytics events had never been written; the taxonomy existed, the calls did not.
- The scoring cron was OOM-killed at Render's 512MB ceiling and left no trace in the product — weeks of scheduled runs produced 43 rows.
- The Portfolio Suite backtest selected positions using `method="nearest"`, which could resolve to a score dated *after* the rebalance, while the caption claimed the result was out-of-sample.
- `.env.render` cannot be sourced by bash, so a launch command aborted and did nothing while appearing to run.
- `utils.db` falls back to local SQLite when `DATABASE_URL` is absent, so a query against "production" returns zero rows and looks like an empty database.

None of these raised an error. Each looked exactly like a normal empty state. For a product whose entire positioning is precision, this is the central engineering risk: the failure mode is *quiet wrongness*, which is precisely what destroys the trust the product sells.

**The credibility centrepiece is empty.** Track Record has 9 resolved predictions against a reporting threshold of 20, so it correctly displays nothing. The one page that would prove the thesis cannot yet do so.

**43 failing tests have been normalised.** They are pre-existing and environment-related (`AppTest` lacks `segmented_control` in this Streamlit version), but a suite that is never green trains the team to ignore red.

**Feature breadth far exceeds validated depth.** Twenty-plus pages and six Pro-gated features, none of which has usage data justifying its maintenance cost.

**Known biases remain in the backtest.** Survivorship bias is unfixed — the universe is today's tracked tickers, so names delisted during the period are invisible. This is now disclosed rather than hidden, which is the right interim state but not a solution.

### Opportunities

**Honesty as market position.** The retail-fintech norm is confident numbers with hidden caveats. A product that visibly withholds figures it cannot support is differentiated, defensible, and hard for a hype-driven competitor to copy without dismantling their own marketing. This is worth making explicit in positioning rather than leaving as an implementation detail.

**Score history compounds into the moat.** Every day of snapshots makes Track Record and the backtest more credible. Today's backfill took coverage from 25 tickers to 700+. In roughly a year that becomes a genuine out-of-sample record — an asset that cannot be bought or rushed, only accumulated. Starting the clock is the highest-leverage thing available.

**The macro-to-equity mapping is a real gap in the market.** Retail tools are overwhelmingly price-and-fundamentals. Signals like rig counts, freight rates, and utility filings mapped to tickers with researched lead times is not a crowded space.

**Distribution surfaces already exist but are unused.** The SEO service, weekly brief, digest, and Twitter crons are built. They are infrastructure waiting on content strategy, not new engineering.

### Threats

**Data licensing is the largest unmanaged risk.** yfinance scrapes Yahoo Finance and its terms do not clearly permit commercial redistribution. The product is a paid service built on it. This is a legal and existential dependency, not a technical one, and it has not been reviewed. It should be.

**Single-provider dependency.** yfinance failure degrades prices, quotes, options chains, and earnings simultaneously. Circuit breakers handle transient outages; they do not handle a provider going away or blocking access.

**Regulatory framing.** The product outputs directional calls on specific securities to paying subscribers. The line between tooling and investment advice is jurisdiction-dependent and worth a professional opinion before scaling.

**The credibility trap.** With this positioning, one user checking one number and finding it wrong costs more than a missing feature. This session found several numbers that were wrong in ways a knowledgeable user *would* have caught: a "1Y" chart showing 17.6 months, a Call/Put table with inverted labels, a backtest annualising four weeks into tens of percent. They are fixed. The pattern that produced them is the threat.

**Key-person concentration.** Solo founder, no documented handover, credentials in one place.

---

## 3. What the analysis says to do

Three conclusions follow from the evidence, in priority order.

**The bottleneck is distribution, not product.** Six users after a month, zero in twelve days, against a feature surface larger than most funded seed-stage products. More features will not fix this; nothing in the data suggests users arrive and bounce off a missing capability, because users do not arrive. Every further feature increases maintenance load against zero validated demand.

**The differentiator requires time, not code.** Honest statistics need sample size. Track Record, the backtest, and the accuracy leaderboard all become compelling with a year of accumulated snapshots and cannot be made compelling sooner. The correct move is to guarantee accumulation runs reliably every day starting now, and to stop optimising the surfaces that display it until they have something to display.

**Quiet wrongness is the risk that matters.** Not downtime, not missing features. The product's value proposition is that its numbers can be trusted, and the codebase has repeatedly produced numbers that were wrong without complaint. Detection needs to be systemic rather than dependent on someone happening to look.

---

## 4. Roadmap

Ordered by expected value, not by effort.

### Now — the next two weeks

**Get the first ten real users.** Not a feature. Pick one narrow, credible audience — the uranium and nuclear thesis is the sharpest wedge, given CCJ/LEU/UEC/CEG/VST coverage and a genuinely differentiated signal set — and go where they already are. The goal is conversations, not signups; six users cannot tell you what is wrong, and ten engaged ones can.

**Verify the nightly cron actually runs.** Check Render events tomorrow. Today's backfill was manual; the value comes from it happening unattended every night. The memory guard and stalest-first ordering are in place, but neither has survived a real scheduled run yet.

**Resolve the yfinance licensing question.** One conversation with a lawyer. This gates everything else — it is not worth scaling a business on an unreviewed dependency of this kind.

**Let instrumentation accumulate.** It shipped today. Do not draw conclusions from it for at least a week.

### Next — the following month

**Fix the 43 failing tests or delete them.** A suite that is never green provides no signal. Either update them for the current Streamlit or remove them, but do not leave them.

**Add end-to-end assertions on displayed numbers.** The bugs this session shared a shape: a rendered figure that no test checked. A small suite that loads key pages and asserts the headline numbers are internally consistent — chart span matches its label, table labels match their rows, score matches its components — would have caught most of them.

**Address survivorship bias, or restrict the backtest's claims.** Either source a delisted-securities universe or narrow what the feature asserts. Disclosure is an acceptable interim state, not an endpoint.

**Pick three features to keep and deprecate the rest.** Once a week of usage data exists, the page-view distribution will show what earns its maintenance. Screener and Deep Dive currently lead by a wide margin; Options Flow has two views ever.

### Later — once there is traction

Second data provider for redundancy. Point-in-time/vintage macro data, since FRED revisions make any backtest on current vintages silently optimistic. Per-ticker notes and journaling. Position sizing. Dunning and cancellation flows. A documented handover.

### Explicitly not now

Anything that widens the feature surface. The constraint is demand and evidence, and neither is relieved by building more.

---

## 5. Honest limits of this assessment

The usage data covers one active user and cannot support conclusions about real behaviour. Instrumentation to fix this landed today. Session duration is unmeasured. The engagement half of this analysis should be revisited in two weeks with real numbers; until then, the product half rests on code and database inspection, which is solid, and the market half rests on judgement, which is not evidence.
