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
| Arrive | marketing-site visitors | **51** (record; 17–43 in the 6 weeks before) | `analytics_events` page_view site=marketing |
| Arrive | public-tool page views | **36** (2–8 before) | same, page ≠ Landing |
| Use | tool users | *not measured until #360* | `tool_used` |
| Report | landing → app clicks | 2 in 14 days (~4% of landing visitors) | `app_opened` |
| Report | reports generated | 3 in 14 days | `exposure_report_generated` |
| App | "app visitors" | 61 — **inflated**: 30 were one-page crawler-like sessions on Nov 13 | page_view, site≠marketing |
| Keep | accounts | 7 total, last signup Jul 23; no signup attempt since | `users`, `signup_started` |
| Keep | weekly-email opt-ins | 0 | `users.exposure_email_opted_in` |
| Pay | Pro | 2 (likely internal) | billing |

Product health (Nov 19): 545 stocks + 46 ETFs measured, data through Nov 13; all 593
sitemap URLs and 640 internal links return 200; 22 key pages clean at 390px and
1280px (no JS errors, no overflow, one h1). Neon usage ~0.74 CU-h/day (~51 of ~100/month).

## The bottleneck, in order

1. **Discovery.** ~50 people a week. Nothing downstream matters until this grows.
   Google Search Console is not yet verified, so there is no search data at all.
2. **Activation.** ~4% of landing visitors click into the app. Whether the live
   hero X-ray engages people was unmeasured until #360.
3. **Retention.** No reason yet to make an account: the learning streak is
   browser-only, the weekly email has no subscribers.
4. **Monetisation.** Pro alerts shipped (#357); the weekly sender needs its
   `RESEND_FROM_EMAIL` set before the first real send (see owner actions).

## Shipped (newest first)

| PR | What | Moves |
|---|---|---|
| #361 | IndexNow: announce the ~600 re-measured pages to Bing/Yandex/Seznam/Naver weekly | discovery |
| #360 | `tool_used` + `tool_users`; app noindex (crawler sessions); /go utm; weekly sender guard | measurement, cost |
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
| E2 | Email capture on public tools ("next week's quiz and movers"), via the landing's existing Resend audience | weekly subscribers | — |
| E3 | Share cards for a quiz score / an X-ray mix (OG image per result) | shares → arrivals | — |
| E4 | Sync the learning streak to an account | signups | — |
| E5 | Bing Webmaster Tools (confirms IndexNow pickup) | Bing indexed pages | owner: optional sign-in |

## Owner actions (only the owner can do these)

- Set `RESEND_FROM_EMAIL` on **unstructured-alpha-exposure-weekly** (Render → service →
  Environment) to the same value the app uses. Until then the job refuses to send.
- Send the Google Search Console verification code (a meta tag is a one-line change).
- Swap `DATABASE_URL` for the read-only login (scratchpad file from the Nov session).
- Opt in to the weekly email from your own account, so the first real send goes to you.

## Known debt (found, not yet fixed)

- `SHOW_HN_DRAFT.md`, `REDDIT_POSTS.md`, `PRODUCT_HUNT.md` (repo root) pitch the retired
  signals product; use `docs/LAUNCH_KIT.md` instead.
- `unstructured-alpha-web/app/api/subscribe` is unused by the landing, and when the
  Resend audience is not configured it logs the address to stdout and reports success.
  Replace with real capture (E2) and remove.

- `lifecycle` and `watchlist-insights` cron groups run daily with no Resend key; they
  email users of the retired signals product. Candidates to retire.
- The digest job logs recipients' full email addresses (log hygiene).
- PSKY / KVUE no longer meet the two-year price rule; their pages now say so (#359).
- Cold force pages take 2–3.6s on first hit.
