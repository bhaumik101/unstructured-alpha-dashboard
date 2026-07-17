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
