# Launch kit — current product (Nov 2026)

Ready-to-post copy for the product as it is now: the free Portfolio X-ray and the
public exposure pages. **Supersedes** `SHOW_HN_DRAFT.md`, `REDDIT_POSTS.md` and
`PRODUCT_HUNT.md` at the repo root, which pitch the retired signals product
("28/38 signals", bull/bear scores) and would misdescribe the site today.

Every number below was measured from the live library (data through Nov 13, 2026,
`/xray.json`). Re-check them before posting; they move weekly.

| Fact | Value |
|---|---|
| Stocks and ETFs measured | 545 (every S&P 500 company + 46 ETFs) |
| Stock–force readings (five core forces) | 2,725 |
| Readings that hold up (Clear or Tentative) | 765 — **28%** |
| Stocks with no link that holds up to any core force | 143 — **26%** |
| Most common link that holds up | interest rates (45% of stocks); then oil (34%), inflation expectations (28%), the dollar (18%), credit spreads (16%) |
| Rates, by sector | Real estate 27/30 hold up, all down (median −2.8%); Financials 29 of 31 holding readings are down; Energy 0/21 hold up |

**Rules for every post:** say you built it; link to something people can use without
signing up (`/xray`); never claim it predicts anything; answer every comment within a
couple of hours; one community at a time, a few days apart.

---

## Show HN

**Title:** Show HN: X-ray a portfolio against rates, oil and the dollar, with error bars

**URL:** https://www.unstructuredalpha.com/xray

**First comment (post it yourself right after submitting):**

> I built this because every "how will rates affect my stocks" answer I found was a
> story, not a measurement.
>
> For every S&P 500 company and 46 popular ETFs, it regresses three years of weekly
> returns on weekly moves in five forces (the 10-year yield, inflation expectations,
> the dollar, oil, credit spreads), after taking out the market's own move. Every
> figure comes with a 90% range and a label: Clear, Tentative, or not distinguishable
> from zero.
>
> The most interesting result is how little survives. Of 2,725 stock-force readings,
> 28% hold up; a quarter of stocks show no link that holds up to any of the five.
> Interest rates is the most common real link (45% of stocks).
>
> The X-ray lets you click in holdings (no account) and see the mix's weighted
> fingerprint and which holding drives it. There is also a "balance the forces"
> option that finds the weights that would historically have been least moved —
> labelled as arithmetic on the past, not a recommendation.
>
> What it is not: a forecast, a signal, or advice. Relationships change; there is a
> published track record of how often readings held their direction a year later.
>
> Method: https://www.unstructuredalpha.com/learn — happy to go into the regression
> details, the multiple-testing bar for "Clear", or what I tried that did not work.

---

## Reddit

Read each sub's self-promotion rules first; some allow a link only in comments or only
in a weekly thread. Comment in the sub for a while before posting.

### r/dataisbeautiful — [OC] (needs a chart)

**Title:** [OC] How many S&P 500 stocks have a measurable link to each economic force? Fewer than you'd think

**Chart:** five bars — share of stocks whose reading holds up: rates 45%, oil 34%,
inflation 28%, dollar 18%, credit 16%. Screenshot `/forces` or build from `/xray.json`.

**Comment (required for OC):**

> Source: weekly returns, Nov 2023–Nov 2026, for 498 S&P 500 companies and 46 ETFs;
> each stock regressed on weekly changes in the 10-year yield, inflation expectations,
> the trade-weighted dollar, oil and credit spreads, after the market's own move.
> "Holds up" = the 90% range excludes zero (Tentative or Clear). Tool: Python (ordinary least
> squares with numpy), charts in the browser. Interactive version, per stock:
> https://www.unstructuredalpha.com/forces — I built it; nothing here is a forecast.

### r/financialindependence or r/Bogleheads — the index-fund angle

**Title:** If you hold mostly an S&P 500 fund, your portfolio's economic "tilt" comes almost entirely from what else you own

**Body:**

> I've been measuring how stocks move with rates, oil and the dollar *beyond* what the
> market does. One consequence surprised me: an S&P 500 fund has zero tilt by
> construction (it *is* the market), so in a 70/30 index-plus-picks portfolio, the
> 30% is the whole story. A few energy names or a utilities ETF can give a mostly-index
> portfolio a noticeable oil or rates tilt.
>
> Measured over three years, with a 90% range on every number — and most single-stock
> links don't survive that test (only 28% of stock-force readings do).
>
> Free tool if you want to check your own mix, no account: https://www.unstructuredalpha.com/xray
> (I built it; it describes the past, it's not advice.)

### r/investing — discussion first, link only if the rules allow

**Title:** Which stocks actually moved with interest rates over the last three years? I measured all 500

**Body:**

> Took every S&P 500 company, three years of weekly returns, and asked: in a week the
> 10-year yield rose 0.25 points, how did each stock move beyond the market?
> 45% have a link that holds up statistically, the most of the five forces I tested.
> Some of it is the textbook: real estate is hit hardest (27 of 30 real estate stocks hold up, all
> down; median -2.8%). Some of it isn't: in Financials, 29 of the 31 readings that hold
> up are *down* when yields rose, not up -- and not one energy stock has a rates link
> that holds up at all.
>
> Happy to share the method and the full table. Describes the past, not a forecast.

---

## Product Hunt (when there is a share card per result)

**Tagline (≤60):** X-ray your portfolio against rates, oil and the dollar

**Description (≤260):** Click in what you own and see how the mix has moved with
interest rates, inflation, the dollar, oil and credit — measured from three years of
weekly returns, with a 90% range and an evidence label on every number. Free, no
account. Describes the past; not a forecast or advice.
