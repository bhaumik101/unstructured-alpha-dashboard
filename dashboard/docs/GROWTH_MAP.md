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
