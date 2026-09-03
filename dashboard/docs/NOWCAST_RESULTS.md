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
