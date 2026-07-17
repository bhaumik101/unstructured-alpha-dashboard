"""
utils/observability.py — structured JSON logging + correlation IDs.

WHY THIS EXISTS
---------------
Two long-standing gaps in how this app logged:

1. **INFO logs never surfaced.** Streamlit installs its own root logging
   config at WARNING level, so the `[circuit]` / `[ratelimit]` INFO events
   emitted by utils.resilience / utils.ratelimit were silently dropped — you
   could not see a breaker trip or the rate-limiter backend choice in Render
   logs. FastAPI/uvicorn is similar (its own formatters, no app-level shape).

2. **No correlation.** Every log line stood alone — you could not tell which
   lines belonged to the same page view / HTTP request / user session, which
   makes triaging a production incident slow.

This module installs ONE idempotent logging configuration that:
  - emits single-line JSON to stdout (Render captures stdout → Logs),
  - honours the LOG_LEVEL env var (default INFO),
  - stamps every record with a correlation id (`cid`) taken from a
    contextvar, set once per Streamlit rerun / per HTTP request,
  - merges any structured `extra={...}` fields onto the JSON line,
  - quiets noisy third-party loggers (urllib3, yfinance, watchdog, …).

Pure standard library — no new dependencies. Safe to import everywhere and
safe to call configure_logging() repeatedly (Streamlit reruns do).

USAGE
-----
    from utils.observability import configure_logging, set_correlation_id, log_event
    configure_logging()                     # once, early in the process
    set_correlation_id()                    # start of a request / rerun
    log_event("ticker_analysis", ticker="NVDA", ms=812)

    # or plain stdlib logging — still gets JSON + cid automatically:
    logging.getLogger(__name__).info("scan complete", extra={"n": 280})
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar

# ── correlation id (per request / per Streamlit rerun) ────────────────────────
_CID: ContextVar[str] = ContextVar("correlation_id", default="-")

# Attributes that live on a *stock* LogRecord — anything NOT in here that a
# caller attached via `extra={...}` is treated as a structured field and
# merged onto the JSON line.
_RESERVED = set(
    logging.makeLogRecord({}).__dict__.keys()
) | {"message", "asctime", "cid", "taskName"}

_configured = False


class _JsonFormatter(logging.Formatter):
    """One compact JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "cid": getattr(record, "cid", "-"),
        }
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info).splitlines()[-8:]
        # Merge structured extras (json-serialisable only; stringify the rest).
        for key, val in record.__dict__.items():
            if key in _RESERVED or key in out or key.startswith("_"):
                continue
            try:
                json.dumps(val)
                out[key] = val
            except (TypeError, ValueError):
                out[key] = str(val)
        return json.dumps(out, separators=(",", ":"), ensure_ascii=False)


class _CorrelationFilter(logging.Filter):
    """Stamp every record with the current correlation id."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if not hasattr(record, "cid"):
            record.cid = _CID.get()
        return True


def configure_logging(force: bool = False) -> None:
    """Install the JSON stdout handler on the root logger. Idempotent.

    Streamlit / uvicorn may install their own handlers first; we replace the
    root handler set with a single JSON handler so output shape is consistent
    regardless of entrypoint. Third-party libraries keep logging — we just
    reformat and (for the noisy ones) raise their threshold.
    """
    global _configured
    if _configured and not force:
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(level)

    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(_CorrelationFilter())
    root.addHandler(handler)

    # Tame chatty libraries so app signal isn't buried.
    for noisy in ("urllib3", "yfinance", "peewee", "asyncio",
                  "watchdog", "matplotlib", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


# ── correlation id helpers ────────────────────────────────────────────────────
def new_correlation_id() -> str:
    """A fresh short id (12 hex chars)."""
    return uuid.uuid4().hex[:12]


def set_correlation_id(cid: str | None = None) -> str:
    """Set (or generate) the correlation id for the current context."""
    cid = cid or new_correlation_id()
    _CID.set(cid)
    return cid


def get_correlation_id() -> str:
    return _CID.get()


# ── convenience structured event logger ───────────────────────────────────────
_event_logger = logging.getLogger("ua.event")


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    """Emit a structured event line: {msg:<event>, event:<event>, ...fields}.

    Never raises — observability must not break a request. Values that aren't
    JSON-serialisable are stringified by the formatter.
    """
    try:
        _event_logger.log(level, event, extra={"event": event, **fields})
    except Exception:  # pragma: no cover - logging must never crash a caller
        pass


# ── startup diagnostics (Phase 1) ─────────────────────────────────────────────
# Confirms the ACTUAL resources the container is given — not the host's. On
# Render/containers `os.cpu_count()` returns the host core count, which is
# misleading; the real limit is the cgroup CPU quota. Logged once at boot, to
# stdout only (never exposed via an HTTP endpoint).
def _cgroup_cpu_limit() -> float | None:
    """Effective CPU limit from cgroup (v2 then v1). None if unlimited/unknown."""
    try:  # cgroup v2
        with open("/sys/fs/cgroup/cpu.max") as fh:
            quota, period = fh.read().split()
        if quota != "max":
            return round(int(quota) / int(period), 2)
    except Exception:
        pass
    try:  # cgroup v1
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as fh:
            quota = int(fh.read().strip())
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as fh:
            period = int(fh.read().strip())
        if quota > 0 and period > 0:
            return round(quota / period, 2)
    except Exception:
        pass
    return None


def _cgroup_mem_limit_bytes() -> int | None:
    """Effective memory limit from cgroup (v2 then v1). None if unlimited."""
    for path in ("/sys/fs/cgroup/memory.max",
                 "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(path) as fh:
                raw = fh.read().strip()
            if raw and raw != "max":
                v = int(raw)
                # v1 uses a huge sentinel for "unlimited"
                if v < (1 << 62):
                    return v
        except Exception:
            continue
    return None


_startup_logged = False


def log_startup_diagnostics(component: str, extra: dict | None = None) -> None:
    """Emit ONE structured `startup` line with the real runtime shape. Best-effort.
    Idempotent — only the first call per process logs (Streamlit reruns call it
    repeatedly)."""
    global _startup_logged
    if _startup_logged:
        return
    _startup_logged = True
    try:
        import os
        import platform
        info: dict = {
            "component": component,
            "python": platform.python_version(),
            "commit": (os.getenv("RENDER_GIT_COMMIT") or "")[:12] or None,
            "env": os.getenv("RENDER_SERVICE_NAME") or os.getenv("ENV") or "local",
            "host_cpu_count": os.cpu_count(),
            "cgroup_cpu_limit": _cgroup_cpu_limit(),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            # BLAS thread caps (should be "1" on a single-core box)
            "omp_threads": os.getenv("OMP_NUM_THREADS"),
            "openblas_threads": os.getenv("OPENBLAS_NUM_THREADS"),
            "mkl_threads": os.getenv("MKL_NUM_THREADS"),
            "numexpr_threads": os.getenv("NUMEXPR_NUM_THREADS"),
            # app tuning knobs
            "signal_score_workers": os.getenv("SIGNAL_SCORE_WORKERS", "8"),
            "recommender_workers": os.getenv("RECOMMENDER_WORKERS", "5"),
            "malloc_arena_max": os.getenv("MALLOC_ARENA_MAX"),
        }
        mem = _cgroup_mem_limit_bytes()
        if mem:
            info["cgroup_mem_limit_mb"] = round(mem / (1024 * 1024))
        # rate-limiter backend, if importable
        try:
            from utils.ratelimit import backend as _rl_backend
            info["cache_backend"] = _rl_backend()
        except Exception:
            pass
        if extra:
            info.update(extra)
        log_event("startup", **info)
    except Exception:
        pass
