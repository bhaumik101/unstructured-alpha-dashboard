# Reliability

_How Unstructured Alpha stays up under slow providers, traffic spikes, refresh
storms, and provider outages. Last updated 2026-07-17._

## Design principles

- **One broken provider must not break a page.** Every external call is wrapped
  so a failure degrades gracefully instead of cascading.
- **Never present stale data as current.** Fallbacks are explicit; cache TTLs are
  chosen for the data's real update cadence.
- **Fail open on infrastructure, fail closed on abuse.** If Redis is down, rate
  limiting falls back rather than blocking users; if a user floods an endpoint,
  they're throttled.
- **Bounded everything** — timeouts, retries, worker pools, breaker thresholds.

## 1. Provider resilience (`utils/resilience.py`)

All REST provider calls in `utils/fetchers.py` go through `resilient_get` /
`resilient_post` (verified: 0 raw `requests.get/post` remain). Each provider gets:

- **Circuit breaker** (`CircuitBreaker`, thread-safe): opens after
  `fail_max=4` consecutive failures, stays open for `reset_timeout=60s`, then
  half-opens for a trial. When OPEN it fast-fails with `CircuitOpenError`
  (a `RequestException` subclass, so existing `except` blocks treat it like any
  provider failure and fall back). This stops one slow/down provider from
  stacking multi-second waits across a page.
- **Shared pooled session** (`get_session`): one `requests.Session` with an
  `HTTPAdapter(pool_connections=10, pool_maxsize=20)` and a bounded
  `urllib3.Retry(total=2, backoff_factor=0.4,
  status_forcelist=(429,500,502,503,504), allowed_methods={"GET"},
  respect_retry_after_header=True)`. Only idempotent GETs retry; POSTs never do.

yfinance calls have an explicit **8s timeout** on the hot path
(`fetch_price` / `fetch_volume` / `fetch_prices_batch`).

**Providers covered:** FRED, EIA, SEC EDGAR (×9 call sites), FINRA, USASpending,
NY Fed (GSCPI), CFTC, arXiv, FDA, Fed FOMC, plus yfinance.

## 2. Distributed rate limiting (`utils/ratelimit.py`)

- **Backend:** Render Key Value (managed Redis). Atomic fixed-window counter via
  a Lua script (`INCR` + `EXPIRE` + `TTL`) so counting is correct across
  concurrent requests and multiple instances.
- **Fallback:** if `REDIS_URL` is unset or Redis is unreachable, an in-process
  limiter takes over and the limiter **fails open** (never blocks a legit user
  because of an infra problem). `backend()` reports `"redis"` / `"memory"`; the
  Admin page shows a 🟢/🟡 indicator.
- **Identity:** `session_actor()` = `u<id>` (signed-in), else `s<session>`, else
  `anon`; `client_ip()` reads `X-Forwarded-For` (used for login/signup IP limits,
  a supplement to the DB lockout, since XFF can be spoofed).
- **Policies** (`POLICIES`): `ticker_analysis` 30/5min, `ai_research` 10/hr,
  `export` 10/10min, `login_ip` 25/15min, `signup_ip` 10/hr, plus
  `screener_scan` / `anon_page` (available, cache-backed low-risk).
- **Wired at:** Ticker Deep Dive analysis, AI Assistant (Claude path only —
  rule-based answers stay free), Export PDF, login, signup.

Full policy reference: [../RATE_LIMITS.md](../RATE_LIMITS.md).

## 3. Health checks

Liveness vs readiness are split so a data-store/provider outage cannot trigger a
restart loop.

| Service | Path | Type | Behavior |
|---|---|---|---|
| Web (Streamlit) | `/_stcore/health` | liveness | 200 "ok" when the server is up; **no deps** — this is the Render `healthCheckPath` |
| SEO (FastAPI) | `/healthz` | liveness | `{"status":"ok"}` |
| SEO | `/readyz` | readiness | DB required (→ 503 if down), Redis degraded-not-fatal; strict 3s/1.5s timeouts |
| SEO | `/version` | info | `{service, commit, signals}` (commit from `RENDER_GIT_COMMIT`) |

**Gotcha:** `/readyz`'s DB check uses `from utils.db import engine` directly —
NOT `_get_engine()`, which runs `init_db()`/`create_all` and is too slow for the
3s budget (caused a false `db:down`).

## 4. Database

- One module-level pooled SQLAlchemy engine per process: `pool_size=5`,
  `max_overflow=10`, `pool_pre_ping=True` (stale-connection safe),
  `pool_recycle=300` (beats PaaS NAT idle drops). No per-rerun engine creation.
- **Login abuse:** DB-backed lockout — 5 failed attempts → 15-min lockout per
  account. Survives restarts and works across instances (it's in the DB).

## 5. Observability (`utils/observability.py`)

- Single idempotent JSON log handler to stdout (Render captures stdout).
  Fixes Streamlit forcing the root logger to WARNING (INFO `[circuit]` /
  `[ratelimit]` events were being dropped).
- Per-request / per-session **correlation id** (`cid`) on every line via a
  contextvar. SEO middleware honors inbound `X-Request-ID` and echoes it.
- `log_event(name, **fields)` emits structured events (e.g. `rate_limit_block`,
  `http_request`). Level via `LOG_LEVEL` (default INFO).

## 6. Memory / OOM safety

Covered in [PERFORMANCE.md](PERFORMANCE.md): 3yr price window (was 15yr),
bounded worker pools, `gc.collect()` + glibc `malloc_trim` after heavy scans,
`MALLOC_ARENA_MAX`. On the Standard (2 GB) instance there is comfortable
headroom; these keep RSS lean regardless.

## Tests

- `python scripts/production_audit.py` — one deploy-time, network-free gate for
  route registration, Render/env configuration, cron count/memory/deadline
  budgets, a 30-second external-call ceiling, bounded provider caches, and a
  health/freshness contract for every advertised data source. Use `--json` for
  machine-readable CI output; any violation exits non-zero.
- `tests/test_resilience.py` — breaker CLOSED/OPEN/HALF-OPEN logic.
- `tests/test_ratelimit.py` — fallback + policy behavior.
- `tests/test_observability.py` — JSON shape, correlation id, `log_event`.
- `tests/load/` — Locust load/resilience suite (see PERFORMANCE.md).
