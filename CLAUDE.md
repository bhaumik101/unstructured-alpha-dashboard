# Unstructured Alpha — working notes for agents

Macro-signal product. Streamlit app (Render) + Next.js landing (Vercel), one repo.

## Layout — read this before touching anything

```
dashboard/                      the Streamlit app + crons  → Render builds this
dashboard/unstructured-alpha-web/   the Next.js landing    → Vercel builds this subdir
dashboard/cron/                 scheduled workers
dashboard/utils/                shared logic (fetchers, scoring, db)
```

There used to be a second repo, `bhaumik101/unstructured-alpha-web`. It was a
near-complete duplicate of this one — 383 shared files, 30 with different content —
running green CI over stale code. **Archived 2026-08-05.** Vercel now builds this repo
with root directory `dashboard/unstructured-alpha-web`. If you find yourself editing a
repo called `unstructured-alpha-web`, stop: you are in the archive.

## Tests — measured on an M5 MacBook Pro, use the fast ones

| command | time | when |
|---|---|---|
| `pytest tests/test_foo.py -q` | 0.04s | while writing code |
| `pytest -q -n auto -m "not slow"` | 17s | before every commit |
| `pytest -q -n auto` | 92s | before opening a PR |
| `pytest -q` | 248s | never — this is the serial run |

`-n auto` needs `pytest-xdist` (not yet in `requirements-dev.txt`). The `slow` marker
covers tests that touch the network or spawn subprocesses. CI runs Python **3.12**.

## The rule that has burned this project most: merged ≠ live

Three separate incidents. A fix merged to `main` was not live because Vercel pointed at
a different repo; a CSS change looked unapplied because the file has no cache-control
header; a commit reported success and silently did not land.

- Verify deploys **at the origin**, not in a browser tab.
- `raw.githubusercontent.com` serves a **stale CDN copy even with `cache: 'reload'`**.
  Use `api.github.com/repos/.../contents/<path>?ref=<branch>` to confirm what actually
  landed. A successful commit read as a failure twice because of this.
- `app/static/ua-global.css` has no cache-control and no content hash. Verify CSS with
  `fetch(url, {cache:'reload'})`, not by looking at the page.

## Scoring crons — the part with the most hard-won detail

`cron/score_universe.py` scores tickers into `score_snapshots`. Two tiers: `core`
(full Confluence Score, daily) and `rest` (macro+momentum, Mon/Wed/Fri).

**Memory budget, measured live on Render (Starter, 512MB, guard at 390MB):**

```
interpreter          14.4 MB
+ heavy imports     270.1 MB   ← 255.7MB of imports; 70.6% of the guard
+ universe/signals  275.2 MB
= headroom          ~115 MB    ← all the room a pass actually has
```

That headroom carries **~215–250 targets per pass**. Three consequences:

1. **`--budget` must stay near per-pass capacity.** Targets are re-selected
   stalest-first at the *start of every pass*, so a budget far above capacity means
   later passes refill their slots with tickers the same run already scored. With
   `--budget 600` a run wrote 516 rows and still ended `remaining=525` — rescoring
   itself, which reads as a memory problem and is not one.
2. **The supervisor must not stop on `remaining <= 0`.** That counts what is left of
   *this pass's slice*, so once budget ≈ capacity every healthy pass ends at 0 and the
   run quits after one pass. It stops on `already_fresh >= targets` (even the stalest
   slice is fresh), no-progress, or the shared deadline.
3. **The import baseline is not reducible.** pandas 74.2, scipy 48.3, streamlit 30.3,
   yfinance 23.7, numpy 19.0, sqlalchemy 7.4 (marginal MB). scipy looked removable —
   only `pearsonr` and `percentileofscore` — but `score_signal` calls one per signal
   and `compute_quick_correlation_stats` calls the other in the correlation loop with
   no tier guard, so deferring the import saves nothing. Recovering it means
   hand-rolling a Student's-t survival function for the p-values. **Don't.**

**Gated tickers.** A ticker failing the price gate hits `continue` before
`record_score_snapshot`, so it earns no dated row — and an empty date sorts ahead of
every real one, pinning rejects to the head of the queue forever. `scoring_gate_log`
records "examined today, rejected"; `_last_seen_map` folds that in so rejects rotate.
Never write a non-score row into `score_snapshots` to solve this — that table feeds the
product's scores.

Progression, for reference: **218 → 1,000 → 2,138** scored per run across PRs #118–#120.
Currently bounded by `--passes 10` with ~880s of the deadline unused.

## Signal integrity — the product's whole pitch

- A failed signal is **excluded, never synthesized**. Do not invent fallback values.
- Signal count is 47 and comes from a single source of truth (`product_metrics`).
  Do not hard-code counts in copy.
- `hyperscaler_capex` was once named "CapEx", described as capital expenditure, cited
  to SEC EDGAR — and actually computed a share-price index. Now reads real XBRL. When
  adding a signal, verify what it *measures* matches what it *claims*.
- SEC XBRL: a fact is a discrete quarter only if it has a `"frame": "CY2025Q1"` key;
  rows without it are cumulative YTD and summing blindly overstates ~3x. Earliest
  `filed` date = first print, which makes EDGAR natively point-in-time.

## App gotchas

- The session user dict has **no `subscription_tier`** — use
  `billing.effective_is_pro` / `is_admin`.
- Screener and Deep Dive blend scores **differently**; `full` and `macro_momentum` are
  different metrics and must never be conflated (AAPL: 45.6 vs 56.3).
- Streamlit page-to-page nav uses a hidden `st.page_link` proxy (16x faster). Routes are
  **slugs** (`/upgrade-to-pro`), not `/pages/29_Upgrade`.

## Working style that has paid off here

Write the test so it fails on the bug, then mutate the fix and confirm the test fails.
A test suite that stays green while you delete the fix is not testing the fix — that
happened on PR #120, where removing the single `record_gate_outcome` call left every
test passing and the whole change would have shipped as a no-op.
