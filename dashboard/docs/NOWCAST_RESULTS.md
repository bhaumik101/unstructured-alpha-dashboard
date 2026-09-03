# Nowcast results

A dated record of every backtest run, including the ones that lost. New runs
append; nothing here is edited after the fact.

The point of the nowcast pivot is that the question has an answer. A negative
answer is still an answer, and publishing it is the whole differentiator — so
this file exists to make deleting a bad result require a visible commit.

---

## 2026-09-03 — first run — **the model loses**

**Target:** Philadelphia Fed Manufacturing Index (`GACDFSA066MSFRBPHI`),
first-print. *Not ISM* — the ISM PMI is licensed and is not redistributed on
FRED, which is also why `utils/config.py` mis-keys this series as `ism_pmi`.

**Task:** predict month M's level using predictor changes through the end of
month M−1 (`feature_lag_months=1`, a one-month-ahead forecast, not a true
within-month nowcast).

**Window:** 2011-09 → 2026-09, 136 target months, 98 scored out-of-sample.

### Result

| | model | naive ("same as last month") |
|---|---|---|
| RMSE | **20.79** | **17.99** |
| MAE | 15.33 | 13.28 |

**Skill = −0.156. The model does not beat persistence.**

Seven predictors survived the coverage rule: `rail_traffic`, `jobless_claims`,
`credit_spread`, `yield_curve`, `copper`, `crude_oil`, `semiconductor_etf`.
Two were dropped for insufficient history and are named in the output:
`shipping_index` (102/136 months) and `lumber_futures` (49/136 — the CME
relaunched lumber futures as LBR in 2022).

### What the run exposed

**A data-source change nobody had noticed.** `hy_spread` (`BAMLH0A0HYM2`) was
the original credit predictor. FRED's own note on it reads *"Starting in April
2026, this series will only include 3 years of observations."* ICE BofA changed
the licence, so it returns 37 months however wide a window is requested. Through
the inner join, that one series had silently capped the entire design matrix at
32 aligned months — seven predictors with a decade of history were being thrown
away by two that did not have one. Replaced with `BAA10Y` (Moody's Baa over the
10-year Treasury, daily since 1986, same mechanism, no cap).

**This also affects the live Signal Dashboard**, which still scores `hy_spread`
on a rolling three-year history without saying so.

**An extrapolation defect.** The first run scored **−0.844**. Diagnosis: in April
2020 the model predicted a change of +182 on an index whose largest observed
monthly change was +71, giving a level of +169.6 against an actual of −56.6.
A linear model handed inputs far outside their training range extrapolates
without limit. A sanity clamp — predicted change clipped to the envelope
observed in training, specified a priori — moved the score to −0.156.

Both numbers are recorded. The clamp fixed a real defect; it did not change the
verdict.

**Where the loss sits.** By year, the model beat naive in 3 of 9 (2019, 2023,
2025). Excluding 2020 entirely the skill is −0.074 — still a loss. That figure
is a diagnostic only and is **not** the result: dropping the hardest period to
report a better number is the tuning this harness exists to prevent.

### What was NOT done in response

- `RIDGE_ALPHA` was not tuned. It stays a stated prior.
- No predictor was added or removed to improve the score. The two that were
  dropped failed a coverage rule specified before the run.
- 2020 was not excluded.

### Honest read

The pre-specified predictors do not forecast this target better than
persistence. The Philadelphia Fed index is extremely volatile — the standard
deviation of its monthly change is 16.1 points, with a range of −49 to +71 —
and persistence is a hard baseline against that.

Two legitimate next steps, neither of which is tuning:

1. **A different target.** Industrial production (`INDPRO`) is far less volatile
   and has a genuine release lag, which this target lacks — the Philadelphia Fed
   index is published within its own month, so a one-month-ahead forecast of it
   is a harder task than a true nowcast would be.
2. **A true nowcast (`feature_lag_months=0`)**, which needs the intra-month
   release calendar the harness currently refuses to approximate.

If neither works, the honest conclusion is that this data does not nowcast
manufacturing activity, and that is publishable exactly as it stands.

---

## 2026-09-03 — second run — **the nowcast wins, then the win evaporates**

Prompted by the first run's honest read: try a target with a genuine release
lag. Six configurations were searched — three targets x two lags. **All six are
reported below**, because reporting only the best of a search is the same
p-hacking this project was already caught by once.

### The search

| target | lag 1 (forecast) | lag 0 (nowcast) | lag 0 safe? |
|---|---|---|---|
| Philadelphia Fed Mfg | −0.156 | +0.057 | **no** — publishes within its own month |
| Industrial Production | −0.250 | **+0.106** | yes — ~6-week release lag |
| IP: Manufacturing | −0.416 | **+0.280** | yes — ~6-week release lag |

**A correction to the first run's reasoning.** It argued a smoother target would
be easier. That was wrong: skill is *relative*, so a smoother target makes
persistence smoother too. INDPRO's monthly change has a standard deviation of
1.36 on a ~100 index, and a random walk is close to unbeatable there. INDPRO at
lag 1 scored *worse* than the volatile Philadelphia Fed index, not better.

**What did change the result was lag 0.** A one-month-ahead forecast was never
the task the pivot proposed. Because IP for month M is not published until
mid-M+1, using all of month M's high-frequency data is legitimate — at the
moment the number prints, every input was already known. That is a genuine
nowcast, and it is leak-free *for this target specifically*. It is not
leak-free for the Philadelphia Fed index, which publishes inside its own month,
and that row is excluded from consideration for exactly that reason.

### And then it evaporated

| | IP: Manufacturing | Industrial Production |
|---|---|---|
| skill | +0.280 | +0.106 |
| Diebold-Mariano p | **0.200 — not significant** | **0.530 — not significant** |
| Bonferroni over 6 configs | does not survive | does not survive |
| **skill excluding 2020** | **−0.105** | **−0.104** |
| months the model was closer | **45%** | **37%** |
| years the model won | 2 of 9 | 2 of 13 |

**The entire apparent win is 2020.** RMSE squares errors, so three crisis months
— where the random walk was catastrophically wrong and the model merely very
wrong — own the whole figure. In ordinary months the model is *worse* than
persistence: it lands closer to the truth in fewer than half of them.

### The honest conclusion

**The nowcast does not beat persistence.** Not at lag 1, and not at lag 0 once
the result is tested rather than admired.

There is one genuine, narrow finding inside this: the high-frequency data *did*
see the 2020 collapse when a random walk could not. That is what nowcasting is
supposed to be for — turning points, where persistence fails by construction.
But "this helps during once-a-decade shocks" is not a product claim, and one
crisis is n=1.

### What this changed in the code

`score_predictions` now reports `dm_p_value`, `significant` and
`months_model_closer` alongside skill. Skill on its own produced a confident
+0.280 off three observations and would have been shipped as a 28% improvement.
A scorecard that can do that is not a scorecard.

### What was NOT done

- The best of six configurations was not reported as the result.
- 2020 was not excluded to rescue the number.
- `RIDGE_ALPHA` was still not tuned.

---

## 2026-09-03 — third run — **the best available theory does not rescue it**

Twelve predictors, expanded from seven on mechanism grounds, not on results.
Target moved to **Industrial Production: Manufacturing** (`IPMANSICS`) because
the Philadelphia Fed index publishes inside its own month — a true nowcast of
it is not leak-free — and because regional Fed surveys are far more useful as
inputs than as the thing being predicted.

### What was added, and the theory behind each

| added | mechanism |
|---|---|
| `empire_state`, `philly_fed` | Regional Fed surveys ask firms the same question the IP index later answers, ~4 weeks earlier. The strongest mechanism available and the practitioner standard. |
| `financial_conditions` (NFCI) | Adrian, Boyarchenko & Giannone (2019): financial conditions shape the downside of the growth distribution. Weekly, so continuously available. |
| `initial_claims`, `continued_claims` | The fastest hard labour series that exist. |
| `mfg_hours` (AWHMAN) | Firms flex hours before headcount. Ships with the Employment Situation on the first Friday of M+1 — ahead of IP's mid-month print. |

### What was excluded, and why each looked helpful

- **`NEWORDER`, `AMTMNO`, `ISRATIO`** — Advance Durable Goods for month M
  releases ~26 days after month end, *after* Industrial Production for month M.
  "Orders lead production" is mechanically true and using them at lag 0 is
  still look-ahead.
- **`IPG2211S`** — a component of the target index.
- **`WEI`** — itself a nowcast. Including it means re-serving the NY Fed's model.

### Result

| | IP: Manufacturing (12) | Industrial Production (10) |
|---|---|---|
| skill | **+0.338** | +0.252 |
| Diebold-Mariano p | **0.140 — not significant** | 0.205 |
| months the model was closer | **49%** | 49% |
| **skill excluding 2020** | **−0.015** | −0.082 |
| years the model won | 3 of 9 | 3 of 10 |

**The answer did not change.** The best theoretically-motivated predictors
available moved headline skill from +0.280 to +0.338 and left every honest
metric where it was: a coin flip month to month, and approximately zero once
2020 is removed.

One real thing did improve: skill excluding 2020 went from **−0.105 to −0.015**.
The theory-grounded predictors genuinely are better than the market-heavy set.
"Less bad than a random walk" is not a product, but it is a signal about which
direction is worth anything.

### The search is now spent

Counting honestly: 3 targets × 2 lags, then a second feature set on 2 targets —
**at least eight configurations against the same sample.** Every additional one
makes an eventual "win" less believable, and a Bonferroni correction over eight
would require p < 0.006 where the best observed is 0.140.

**Further exploration on this history is worth nothing.** The only clean test
left is out-of-time: publish a nowcast each month before the print, score it,
and in twelve months there is an uncontaminated record. That is exactly the
cadence the pivot was chosen for.

### What was NOT done

- Predictors were not added because they improved the score; every one has a
  mechanism recorded above, written before the run.
- 2020 was not excluded.
- `RIDGE_ALPHA` was still not tuned.
- No fourth feature set was tried after seeing these numbers.

---

## 2026-09-03 — fourth run — **factor model: best yet, still not evidence**

A different *model*, not another feature set: principal-components regression
over the same twelve predictors, three factors, fixed a priori.

The argument was made before the run. Twelve macro predictors are not twelve
pieces of information — regional surveys, claims and financial conditions all
move with the same cycle. Ridge handles that collinearity by shrinking every
coefficient; a factor model admits there are only a few underlying drivers,
which denoises the inputs and cuts effective parameters from twelve to three.
On ~100 training months that is the difference that matters.

Not a full Bańbura-Modugno dynamic factor model: no Kalman filter, no ragged
edges, no mixed frequencies. Everything is aggregated to monthly complete cases
first, so PCA is the right-sized tool. Named accordingly.

### Result — both estimators, identical data

| | ridge | factor |
|---|---|---|
| skill | +0.338 | **+0.370** |
| RMSE model / naive | 1.255 / 1.894 | **1.192** / 1.894 |
| Diebold-Mariano p | 0.140 | **0.113** |
| significant | no | **no** |
| months the model was closer | 49% | **51%** |
| **skill excluding 2020** | −0.015 | **+0.051** |
| years the model won | 3 of 9 | **5 of 9** (2018, 2019, 2020, 2021, 2022) |

**The first configuration whose skill survives removing 2020.** Also the first
to win a majority of months and a majority of years. The prediction made before
running it — that collinearity was hurting ridge — held.

### And it is still not evidence

p = 0.113 uncorrected. With roughly ten configurations now run against this
sample, a Bonferroni correction needs p < 0.005. A 51% hit rate is a coin flip
with a lean. +0.051 excluding 2020 is a 5% RMSE improvement over a random walk.

**Best specification tested. Still no evidence it beats persistence.**

### What that changes

This is no longer a question about this history — it is a hypothesis about
future months. The specification is now fixed:

    target      IPMANSICS (Industrial Production: Manufacturing)
    predictors  the twelve in NOWCAST_PREDICTORS, mechanism-documented
    lag         0 (leak-free: IP for month M prints mid-M+1)
    model       factor, 3 components, RIDGE_ALPHA = 10.0
    baseline    last month's level

Nothing above may be changed while the forward record accumulates without
starting the record over. Twelve monthly observations produce a clean,
uncontaminated answer — which is worth more than anything further that can be
extracted from 2011-2026.

### What was NOT done

- The factor count was not searched; three is a constant with a stated reason.
- `RIDGE_ALPHA` was still not tuned.
- 2020 was still not excluded.
- No fifth model was tried after seeing these numbers.

---

## 2026-09-03 — **correction: the backtest had look-ahead**, and the forward record starts

Found by running the cron against live data, not by any amount of backtesting.

`rail_traffic` (`RAILFRTINTERMODAL`, first-print) publishes roughly **two months
late**: on 2026-09-03 its most recent observation was **2026-06**, while the open
nowcast month was **2026-08**. Historically the value for month M exists in the
data, so a lag-0 backtest uses it happily. In real time it does not exist until
about M+2. That is look-ahead, and it was inflating the result.

### Corrected numbers

| | contaminated (12 predictors) | **corrected (11)** |
|---|---|---|
| skill | +0.370 | **+0.348** |
| Diebold-Mariano p | 0.113 | **0.131** |
| months the model was closer | 51% | **50%** |
| **skill excluding 2020** | +0.051 | **−0.006** |

**The one genuine "first" claimed for the factor model was the look-ahead.**
Skill surviving the removal of 2020 came from rail_traffic. Corrected, it is
zero, and the hit rate is a literal coin flip.

This is the most useful thing the exercise has produced. **No amount of
backtesting would have caught it** — the bias is invisible in history, because
history contains the value. It surfaced the moment a job tried to fetch that
month in real time and could not.

`predictors_for_lag()` now enforces it structurally: at lag 0 only predictors
whose month-M value publishes before the target's are used, so the mistake
cannot be made again by forgetting.

### The forward record

`cron/run_nowcast.py`, monthly on the **8th**. That date is the only window
where every input exists and the answer does not:

    first Friday   Employment Situation publishes AWHMAN for the month
    the 8th        the job runs
    ~the 15th      Industrial Production publishes the month being nowcast

Running on the 1st was tried first and is wrong — AWHMAN has not published, and
the job refuses rather than dropping a required predictor.

One row per (target, month), written once, never updated. Scoring may fill
`actual` and `scored_at` and nothing else. A skill score is withheld until
twelve scored months exist, because a ratio of two RMSEs over a handful of
observations is what produced the +0.280 that started this correction chain.

**The locked specification:**

    target      IPMANSICS (Industrial Production: Manufacturing)
    predictors  the 11 lag-0-safe entries in NOWCAST_PREDICTORS
    lag         0, asserted leak-free via NOWCAST_TARGET_RELEASE_LAG_MONTHS
    model       factor, 3 components, RIDGE_ALPHA = 10.0
    baseline    last published level

Changing any of it restarts the record. The cron exposes no flags that could.
