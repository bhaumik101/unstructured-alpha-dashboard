"""Lightweight, privacy-safe performance timing for core product paths."""

from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Lock
from typing import Callable, Iterator


_LOGGER = logging.getLogger("unstructured_alpha.performance")
_LATEST_PAGE_PROFILES: dict[str, dict] = {}
_LATEST_PAGE_PROFILES_LOCK = Lock()


def record_timing(
    stage: str,
    *,
    ticker: str = "",
    duration_seconds: float,
    success: bool,
    cache_status: str = "not_applicable",
    metadata: dict | None = None,
) -> dict:
    """Emit one structured timing record without user or session identifiers."""
    event = {
        "event": "performance_timing",
        "stage": str(stage),
        "ticker": str(ticker).upper().strip(),
        "cache_status": str(cache_status),
        "duration_seconds": round(float(duration_seconds), 6),
        "success": bool(success),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if metadata:
        event["metadata"] = {
            str(k): v for k, v in metadata.items()
            if isinstance(v, (str, int, float, bool)) or v is None
        }
    _LOGGER.info("PERF %s", json.dumps(event, sort_keys=True, default=str))
    return event


@contextmanager
def timed_stage(
    stage: str,
    *,
    ticker: str,
    events: list[dict] | None = None,
    cache_status: str = "not_applicable",
    metadata: dict | None = None,
    outcome: dict | None = None,
) -> Iterator[None]:
    """Measure a block, log failures, and preserve the original exception."""
    started = time.perf_counter()
    ok = False
    try:
        yield
        ok = True
    finally:
        measured_success = ok and bool((outcome or {}).get("success", True))
        event = record_timing(
            stage,
            ticker=ticker,
            duration_seconds=time.perf_counter() - started,
            success=measured_success,
            cache_status=cache_status,
            metadata=metadata,
        )
        if events is not None:
            events.append(event)


def notify_progress(
    callback: Callable[[str, str], None] | None,
    stage: str,
    message: str,
) -> None:
    """Progress callbacks are best-effort and must never break scoring."""
    if callback is None:
        return
    try:
        callback(stage, message)
    except Exception:
        pass


class PageProfiler:
    """Sequential, privacy-safe page timing checkpoints.

    This utility intentionally knows nothing about users, sessions, request
    headers, or network identity. Pages may retain the returned summary for an
    admin-only diagnostic while aggregate checkpoints also reach app logs.
    """

    def __init__(self, page: str) -> None:
        self.page = str(page).strip() or "unknown"
        self._started = time.perf_counter()
        self._checkpoint_started = self._started
        self._phases: list[dict] = []
        self._finished = False

    def checkpoint(self, phase: str, *, success: bool = True) -> dict:
        """Close the current sequential phase and start the next one."""
        if self._finished:
            raise RuntimeError("PageProfiler has already been finished")

        now = time.perf_counter()
        duration = max(0.0, now - self._checkpoint_started)
        clean_phase = str(phase).strip() or "unnamed"
        record_timing(
            f"page.{self.page}.{clean_phase}",
            duration_seconds=duration,
            success=success,
            metadata={"page": self.page, "phase": clean_phase},
        )
        result = {
            "phase": clean_phase,
            "duration_ms": round(duration * 1000, 1),
            "success": bool(success),
        }
        self._phases.append(result)
        self._checkpoint_started = now
        return result

    def finish(self, final_phase: str | None = None) -> dict:
        """Finish profiling and return a JSON-serializable admin summary."""
        if self._finished:
            raise RuntimeError("PageProfiler has already been finished")
        if final_phase:
            self.checkpoint(final_phase)

        total_seconds = max(0.0, time.perf_counter() - self._started)
        total_event = record_timing(
            f"page.{self.page}.total",
            duration_seconds=total_seconds,
            success=all(p["success"] for p in self._phases),
            metadata={"page": self.page, "phase_count": len(self._phases)},
        )
        self._finished = True
        slowest = max(self._phases, key=lambda p: p["duration_ms"], default=None)
        summary = {
            "page": self.page,
            "total_ms": round(total_seconds * 1000, 1),
            "captured_at": total_event["timestamp"],
            "slowest_phase": slowest["phase"] if slowest else None,
            "phases": [dict(p) for p in self._phases],
        }
        with _LATEST_PAGE_PROFILES_LOCK:
            _LATEST_PAGE_PROFILES[self.page] = deepcopy(summary)
        return summary


def get_latest_page_profile(page: str) -> dict | None:
    """Return the latest anonymous in-process profile for an admin diagnostic.

    Streamlit's top navigation starts a fresh session when moving between pages,
    so session state alone cannot carry Home timing into Admin. This bounded
    process-local slot stores one summary per page, contains no request or user
    identity, and disappears whenever the app process restarts.
    """
    clean_page = str(page).strip() or "unknown"
    with _LATEST_PAGE_PROFILES_LOCK:
        summary = _LATEST_PAGE_PROFILES.get(clean_page)
        return deepcopy(summary) if summary is not None else None
