# Growth map

A living map of how Unstructured Alpha grows: the funnel, the measured numbers at
each step, the current bottleneck, what has shipped against it, and what is next.
Update the numbers when you ship; every figure here is measured, with its source.
Supersedes the July `ROADMAP.md` / `SWOT_AND_ROADMAP.md` / `DISTRIBUTION_PLAYBOOK.md`,
which describe the retired signals product.

**Goal:** retail investors (and advisers) use the free tools to see how their stocks
and portfolios move with economic forces, come back weekly, and some pay for
Investor Pro (alerts, weekly tracking). Uncertainty always shown; never a forecast
or advice.

**North-star metric:** weekly *tool users* — people who did something on a public
tool (`tool_used`, added in #360), not just loaded a page.

## The funnel

```
 discovery          arrive               use                 report               keep                  pay
 search / social -> www public pages  -> a tool (X-ray,   -> app report       -> account: saved      -> Investor Pro
 / links            (landing, 545       quiz, what-if...)    (free, no           portfolio, weekly      (alerts,
                    stock pages, ...)                        account)            email, streak          $20/mo)
```

## Numbers (last full week, Nov 9–15 2026)

| Step | Measure | Value | Source |
|---|---|---|---|
| Arrive | marketing-site visitors | 51 last week, 40 in the first 3 days of this week — **overcounted, see below** | `analytics_events` page_view site=marketing, scripted bursts excluded |
| Return | returning visitors (seen in an earlier week) | app: 8 of 125 came back on another day (6%) over two months; site: **not measurable before #366** | `growth_metrics` `returning` |
| Arrive | public-tool page views | **36** (2–8 before) | same, page ≠ Landing |
| Use | tool users | *not measured until #360* | `tool_used` |
| Report | landing → app clicks | 2 in 14 days (~4% of landing visitors) | `app_opened` |
| Report | reports generated | 3 in 14 days | `exposure_report_generated` |
| App | "app visitors" | 61 — **inflated**: 30 were one-page crawler-like sessions on Nov 13 | page_view, site≠marketing |
| Keep | accounts | 7 total, last signup Jul 23; no signup attempt since | `users`, `signup_started` |
| Keep | weekly-email opt-ins | 0 | `users.exposure_email_opted_in` |
| Pay | Pro | 2 (likely internal) | billing |

**Visitor ids on the marketing site were broken until #366.** The beacon relay goes
www → SEO service, and Render's Cloudflare front stamps `cf-connecting-ip` with the
Vercel server that relayed it; the visitor id hashed that changing server address,
not the person. Evidence: of 279 marketing visitor ids since Sep 20, none spanned
more than 11.7 minutes (90% were a single event), while app ids span up to 32 days.
So site visitor counts before Nov 19 are inflated by an unknown factor, and returning
site visitors were invisible. The trend (more traffic in November) still holds, since
the error was the same every week. From #366 the id is the visitor's.
Separately, the SEO service and the app hash with different keys (the SEO service has
no `ANALYTICS_HASH_SALT`), so one person is two ids across site and app — which is
why "crossed" has always been 0. That needs the owner action below.

Indexing (Nov 19): stock and sector pages appear in a public web-search index with
their data; one result was on the origin host (seo.unstructuredalpha.com), whose pages
carry a www canonical -- engines consolidate on www. IndexNow accepted all 600 URLs.
Confirm coverage in Search Console once verified.

Product health (Nov 19): 545 stocks + 46 ETFs measured, data through Nov 13; all 593
sitemap URLs and 640 internal links return 200; 22 key pages clean at 390px and
1280px (no JS errors, no overflow, one h1). Neon usage ~0.74 CU-h/day (~51 of ~100/month).

## The bottleneck, in order

1. **Discovery.** ~50 people a week. Nothing downstream matters until this grows.
   Google Search Console is not yet verified, so there is no search data at all.
2. **Activation.** ~4% of landing visitors click into the app. Whether the live
   hero X-ray engages people was unmeasured until #360.
3. **Retention.** The learning streak is browser-only; the weekly public email is
   built (#363) and waits on one env var to switch on.
4. **Monetisation.** Pro alerts shipped (#357). The weekly job sends from our own
   verified domain (brief@unstructuredalpha.com) -- no setup needed (#362).

## Shipped (newest first)

| PR | What | Moves |
|---|---|---|
| #373 | **"What moved when"**: 28 pages answering "which stocks went up when rates fell / oil rose / …" with measured evidence (research-driven bet, see `docs/RESEARCH_2026-11.md`). Also fixes every natural-gas reading (spot-price spikes) and adds a guard that excludes any spike-dominated force — *verified Nov 25: re-measured from UNG, EQT +0.11% → +1.89% per 10% gas move (Clear); gas /when pages indexable and submitted to IndexNow* | discovery, activation, trust |
| #374 | **Internal traffic flag + calmer pages.** `?ua_internal=1` marks the owner's browsers; their visits and our checks never count. Stock and When pages show the answer first and fold the detail into labelled panels with a one-line preview (XOM: 5,308 → 2,640 px), all still in the HTML for search | measurement, activation, retention |
| #375 | **Visual redesign, landing + report.** Dark editorial hero with a real dated report panel and a starfield of the 545 real stocks; market map (any two forces, live); holdings→forces flow; force sparklines. Report leads with the answer: workspace header, summary tiles, takeaway, aligned exposure table, flow diagram; skeleton loading; brand tokens across the app | activation, retention, trust |
| #376 | **Public pages in the new brand**, and "Where XOM sits among 545 stocks" on every stock page: a server-drawn map of every stock on its two largest readings, sector lit, the stock ringed | activation, discovery |
| #380 | **Answers on arrival** for Compare and X-ray: a bare page shows a worked example instead of an empty form; the last X-ray mix is remembered; the owner's phone excluded from visitor counts | activation |
| #381 | **Coming back.** "Your desk" on the landing for a returning visitor (level, streak, path with the next step, recent stocks, today's games) and a ⌘K / `/` command palette on every page (stocks, forces, tools, questions) | retention, navigation |
| #382 | **Desk v2: growing on the platform.** 12-week practice heatmap with longest run; eight practice-only milestones with progress rings and a one-time "New"; "N changes since you looked" in the stocks you viewed, same rule as My list. Landing logic now has its own `npm test` in CI | retention, learning |
| #383 | **Glass command bar in the app.** Nav and account controls become one frosted object: blueprint grid, teal→gold light rail with a one-time glint, glass chips of one height; a bell with a corner count badge and a ring-avatar account chip, docked inside the bar wherever it fits (≥1320px, 680–1000px) | trust, retention |
| #384 | **A calmer first page, edge to edge.** The report's first page leads with one glass "Measure a portfolio" card (samples as a quiet way in), the four numbers as one slim strip, and the stored record in tabs below; the app now spans the full desktop width instead of stopping at 1200px | activation |
| #385 | **First-visit walkthrough + dashboard row.** A newcomer's first front-page visit gets a 10-step glass spotlight tour; two steps are click-it steps (measure the Balanced sample, open Change holdings) that block everything but the highlighted button; ends with three places to explore. "What the forces did" becomes a dashboard row above the builder; "Take the one-minute tour" relaunches it | activation |
| #387 | **Full names beside every ticker.** The report spells out each holding ("BND · Vanguard Total Bond Market ETF") in the takeaway, main-holding column, flow diagram, per-force table, holdings grid and editor; names from local sources only, an unknown ticker shown alone | activation, trust |
| #388 | **Names for any listed stock + data-source research.** A bundled SEC ticker snapshot (10,399 companies) as the last local name source; `docs/DATA_SOURCES_2026-11.md` ranks ten free sources (N-PORT fund look-through first, weekly Henry Hub for the gas spikes, fund names from the SEC series/class data set) | activation, trust |
| #389 | **What your funds hold (SEC N-PORT look-through).** For 71 funds, each fund's latest public N-PORT becomes a card: holdings count and date, asset mix bar, bond issuers, currencies and countries, largest holdings, and a plain "why it carries this exposure here" line (VXUS: priced in other currencies → dollar; BND: bonds → rates). Funds that file no N-PORT (GLD, SPY) are named as such | activation, trust |
| #390 | **Look-through refreshes itself; the gas swap measured and rejected.** A weekly job (Tuesdays, in the universe group) checks every fund's N-PORT feed and re-parses only new filings into the database; the report prefers the newer filing. Weekly-average gas spot was measured against the live UNG futures series and rejected (largest weekly jump +301% vs +35%) | trust |
| #391 | **Names for mutual funds and share classes.** 28,845 fund names from the SEC's Investment Company Series and Class data set ("Dodge & Cox Stock Fund (Class I)", "Vanguard Total World Stock Index Fund (Admiral Shares)"), so a 401(k) portfolio reads in full; all-caps filings tidied | activation |
| #392 | **Inflation cross-check + a denser glass report.** Every report checks its inflation reading against the Cleveland Fed's model of inflation expectations (60 monthly fits; verdict pill + aligned evidence-strength bars), and says when the reading depends on the time scale. Report density: tighter section rhythm, headings with a light rail, all cards in one glass treatment, actions in one glass bar | trust |
| #393 | **Interest rates, split (NY Fed term premium).** Every report splits its interest-rate reading into the expected path of Fed policy and the term premium (NY Fed ACM model), shown beside the inflation cross-check in an equal-height glass pair; refreshed weekly | trust |
| #394 | **Checked against the Fama-French factors.** Every report re-measures its market beta against the academic Mkt-RF factor (Kenneth French's library) and fits size (SMB) and value (HML) tilts, compared with its own fund-spread readings, in a three-cell glass strip. First results: Balanced beta 0.58 vs SPY / 0.57 vs Fama-French (agrees); Growth SMB −0.27, HML −0.80, both Clear; Small value +0.76 / +0.61, both Clear. Weekly snapshot bundled, refreshed by `cron/refresh_famafrench.py` | trust |
| #395 | **The economy this quarter (Atlanta Fed GDPNow), as context.** "What changed" now shows the Atlanta Fed's latest estimate of this quarter's real GDP growth, how it moved with each update (read from ALFRED vintages, so the update date is proven, not guessed), and its record: each past quarter's final estimate beside BEA's figure. First reading: Q4 2026 +3.2%, updated Nov 18; off by 1.3 points on average over 8 quarters, widest Q4 2025 (+4.2% vs +0.2%). Labelled theirs, feeds no reading | trust |
| #397 | **Readable for a first-time investor: tap-to-define glossary and a dollar view.** Words a newcomer stops at (credit spreads, 90% range, Clear, beta, term premium, SMB/HML, ETF…) are dotted-underlined; hover or tap opens a plain definition, linking to the SEC's Investor.gov where it has a page (9 confirmed pages; our own one-liners elsewhere). A "See it in dollars" box turns every estimate into "≈ −$56 on $10,000", instantly in the browser, and a "Words used in this report" card lists them all. Also: Render build filters, so docs, tests and landing changes stop rebuilding all 18 services, and the 8 retired crons no longer rebuild at all | activation, trust, cost |
| #398 | **Proof that a reading matters, and the answer in plain English.** Every report opens with "In plain English": if you had $X in this mix, what the market and the clearest force did to it in a typical week, in dollars, and whether that held up on weeks the estimate never saw. A new "Did it show up in real weeks?" panel shows each reading's 8 biggest weeks as bars and an out-of-sample test. Study across 14 portfolios: rate readings matched 90% of big new weeks, dollar 78%, oil 66%, inflation 50% (a coin flip), so inflation readings now carry a caution when they fail | activation, trust |
| #399 | **Inflation readings must prove themselves.** An inflation reading keeps "Clear" only if it held up on weeks the estimate never saw (≥ 70% of big new weeks); otherwise it shows as Tentative, marked "was Clear" with the score. Engine-level, so reports, stock pages, the CSV and the when pages agree; stated on Methodology. Banks, high yield and small value lost Clear; TIPS kept it | trust |
| #372 | Fingerprint-game share cards (same as the quiz) | discovery |
| #371 | Landing "Today's challenge": the two daily games, with a returning player's streak and today's results (same browser store as the tool pages) | retention, activation |
| #370 | Quiz share cards: a result link (`/quiz?g=…&d=…`) previews as a card of the score and its squares (no spoilers); a native Share button on phones | discovery |
| #369 | "Since your last visit": stock pages remember the readings shown; on return a card on any page says how many changed (a link started/stopped holding up, or a held reading moved 0.5+ points), with the full list and "mark all as seen" on My list. Browser only | retention |
| #367 | Redesign of all ~600 public pages: the landing's navy-and-gold header band, numbers as a stat strip, no pill rows, softer cards, footnote-style disclaimers, gold primary buttons; the quiz as a game (progress segments, arrow tiles, verdict); a streak badge in the bar for returning learners; the weekly email as a brand panel | retention, activation |
| #366 | Marketing visitor ids hash the visitor, not the relay server; `returning` column | measurement |
| #365 | Growth report excludes scripted bursts (20+ page views in 5 min): scrapers and our own site checks (one logged 42 views in 56s). Force pages rendered once per data week (were 0.5–3.6s per request) | measurement, speed |
| #364 | X-ray share cards: a shared mix (`/xray?p=`) previews with its own title and a drawn card of its fingerprint; customers' email addresses masked in logs | discovery, trust |
| #363 | Weekly public email: sign-up box on Quiz/Guess/Learn/X-ray/What changed, double opt-in, scanner-safe confirm/unsubscribe, weekly "what moved" send. Dark until the SEO service has `RESEND_API_KEY` | retention |
| #362 | Fix #360's sender guard: it checked the raw variable and would have refused the working built-in sender | monetisation |
| #361 | IndexNow: announce the ~600 re-measured pages to Bing/Yandex/Seznam/Naver weekly | discovery |
| #360 | `tool_used` + `tool_users`; app noindex (crawler sessions); /go utm | measurement, cost |
| #359 | Real pages for SPY/VOO/IVV/VTI (were a JSON 404) and unmeasured tickers; stale notice | discovery, trust |
| #358 | Learning track: streaks, XP, levels, five-step path | retention |
| #357 | Investor Pro exposure alerts | monetisation |
| #356 | Live X-ray in the landing hero | activation |
| #355 | Portfolio X-ray (click to add, balance, share link) | use |
| #353 | Bulk library read, 24h cache — Neon usage cut to ~half the free quota | cost |
| #344–#348 | Outage handling: 503 + Redis snapshot instead of errors | trust |

## Next experiments (each with the number it should move)

| # | Experiment | Metric | Needs |
|---|---|---|---|
| E0 | **Post the launch kit** (`docs/LAUNCH_KIT.md`): Show HN + three Reddit posts, accurate to today's product, built on measured hooks (only 28% of stock–force readings hold up; Financials mostly *fell* when yields rose) | site visitors, tool users | owner: posting from their accounts |
| E1 | Verify Google Search Console, submit the sitemap | impressions, indexed pages | owner: verification code |
| E2 | ~~Email capture on public tools~~ shipped #363; switch on with the owner action below | weekly subscribers (`public_subscribers`, status confirmed) | owner: one env var |
| E3 | ~~Share cards~~ shipped: X-ray mixes #364, quiz scores #370 | arrivals on `/xray?p=`, `/quiz?g=` | — |
| E4 | Sync the learning streak to an account | signups | — |
| E5 | Bing Webmaster Tools (confirms IndexNow pickup) | Bing indexed pages | owner: optional sign-in |

## Research loop

Each round: measure → research → bet → write the numbers that would prove the
bet wrong → check them → correct. Round 1 (Nov 22): `docs/RESEARCH_2026-11.md`
-- zero tool use despite rising traffic; bet on query-matched measured pages;
checks due Dec 1 and Dec 22.

## Owner actions (only the owner can do these)

- **Make site and app visitors one person:** Render → **unstructured-alpha-seo** →
  Environment → add `ANALYTICS_HASH_SALT` with the same value the app service has.
  Until then "crossed" (site → app) reads 0 whatever happens.
- **Switch on the weekly public email:** in Render, open **unstructured-alpha-seo** →
  Environment → add `RESEND_API_KEY` with the same value the app service uses. The
  sign-up box then appears on Quiz, Guess, Learn, X-ray and What changed. (It sends
  from brief@unstructuredalpha.com, already verified.)
- Send the Google Search Console verification code (a meta tag is a one-line change).
- Swap `DATABASE_URL` for the read-only login (scratchpad file from the Nov session).
- Opt in to the weekly email from your own account, so the first real send goes to you.

## Known debt (found, not yet fixed)

- `SHOW_HN_DRAFT.md`, `REDDIT_POSTS.md`, `PRODUCT_HUNT.md` (repo root) pitch the retired
  signals product; use `docs/LAUNCH_KIT.md` instead.
- `lifecycle` and `watchlist-insights` cron groups run daily and complete as no-ops
  (they serve the retired signals product; no Resend key). Candidates to retire.
- PSKY / KVUE no longer meet the two-year price rule; their pages now say so (#359).
