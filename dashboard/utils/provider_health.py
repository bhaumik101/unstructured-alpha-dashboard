"""Provider telemetry, freshness classification, and last-known-good live data.

This module is intentionally process-local: it adds no database query to page
loads and survives every user/session inside a running web instance. Render
restarts clear the store, which is the safe failure mode—no observation is ever
invented or restored without having been fetched successfully in this process.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import threading
import time
from typing import Any

from utils.product_metrics import PRIMARY_SOURCES


_PROVIDER_ALIASES = {
    "yfinance": "yahoo",
    "yfinance_multi": "yahoo",
    "yfinance_basket": "yahoo",
    "yfinance_ratio": "yahoo",
    "ny_fed_gscpi": "ny_fed",
    "fda": "openfda",
    "fedspeaks": "federal_reserve",
    "fed_fomc": "federal_reserve",
    "google": "google_trends",
    "sec": "sec_edgar",
    "sec_xbrl_sum": "sec_edgar",
}

_EXPECTED_CADENCE = {
    "fred": "Daily to monthly, by series",
    "eia": "Weekly",
    "ny_fed": "Monthly",
    "yahoo": "Market days; options delayed",
    "sec_edgar": "Event driven",
    "finra": "Twice monthly",
    "cftc": "Weekly",
    "usaspending": "Daily",
    "congress": "Disclosure driven",
    "openfda": "Daily",
    "arxiv": "Daily",
    "google_trends": "Weekly",
    "federal_reserve": "Event driven",
}

_lock = threading.RLock()
_events: dict[str, dict[str, Any]] = {}
_last_known_good: dict[str, dict[str, Any]] = {}
_LKG_LIMIT = 256


def canonical_provider(provider: str | None) -> str:
    raw = str(provider or "unknown").strip().lower()
    return _PROVIDER_ALIASES.get(raw, raw)


def provider_label(provider: str | None) -> str:
    key = canonical_provider(provider)
    return PRIMARY_SOURCES.get(key, key.replace("_", " ").title())


def record_provider_event(
    provider: str,
    *,
    success: bool,
    latency_ms: float | None = None,
    error_type: str | None = None,
    status_code: int | None = None,
) -> None:
    """Record a sanitized provider outcome without URLs, keys, or payloads."""
    key = canonical_provider(provider)
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        row = _events.setdefault(key, {
            "provider": key,
            "requests": 0,
            "successes": 0,
            "failures": 0,
            "consecutive_failures": 0,
            "latency_ms": None,
            "last_success": None,
            "last_failure": None,
            "last_error": None,
            "last_status_code": None,
        })
        row["requests"] += 1
        if latency_ms is not None:
            latency = max(0.0, float(latency_ms))
            prior = row.get("latency_ms")
            row["latency_ms"] = latency if prior is None else round(prior * 0.75 + latency * 0.25, 1)
        row["last_status_code"] = int(status_code) if status_code is not None else None
        if success:
            row["successes"] += 1
            row["consecutive_failures"] = 0
            row["last_success"] = now
            row["last_error"] = None
        else:
            row["failures"] += 1
            row["consecutive_failures"] += 1
            row["last_failure"] = now
            row["last_error"] = str(error_type or "ProviderError")[:80]


def provider_health_snapshot(circuit_states: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Return every canonical provider, including sources not yet called."""
    circuits = {canonical_provider(k): v for k, v in (circuit_states or {}).items()}
    with _lock:
        observed = deepcopy(_events)

    keys = list(PRIMARY_SOURCES)
    keys.extend(k for k in observed if k not in keys)
    output = []
    for key in keys:
        row = observed.get(key, {
            "provider": key, "requests": 0, "successes": 0, "failures": 0,
            "consecutive_failures": 0, "latency_ms": None,
            "last_success": None, "last_failure": None, "last_error": None,
            "last_status_code": None,
        })
        circuit = circuits.get(key, "closed")
        if circuit == "open":
            state = "unavailable"
        elif circuit == "half_open" or row["consecutive_failures"] > 0:
            state = "degraded"
        elif row["last_success"]:
            state = "operational"
        elif row["last_failure"]:
            state = "unavailable"
        else:
            state = "not_checked"
        output.append({
            **row,
            "label": provider_label(key),
            "state": state,
            "circuit": circuit,
            "expected_cadence": _EXPECTED_CADENCE.get(key, "Provider dependent"),
        })
    return output


def _clone(value: Any) -> Any:
    try:
        return value.copy(deep=True)
    except Exception:
        return deepcopy(value)


def remember_last_known_good(key: str, value: Any, *, provider: str) -> None:
    """Remember a non-empty real provider result for bounded safe fallback."""
    if value is None or bool(getattr(value, "empty", False)):
        return
    now_epoch = time.time()
    with _lock:
        if len(_last_known_good) >= _LKG_LIMIT and key not in _last_known_good:
            oldest = min(_last_known_good, key=lambda k: _last_known_good[k]["stored_at_epoch"])
            _last_known_good.pop(oldest, None)
        _last_known_good[key] = {
            "value": _clone(value),
            "provider": canonical_provider(provider),
            "stored_at_epoch": now_epoch,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }


def get_last_known_good(key: str, *, max_age_seconds: int = 7 * 86400) -> Any | None:
    """Return a labeled copy of genuine cached data, never a placeholder."""
    with _lock:
        entry = _last_known_good.get(key)
        if not entry:
            return None
        age = max(0.0, time.time() - entry["stored_at_epoch"])
        if age > max(1, int(max_age_seconds)):
            return None
        value = _clone(entry["value"])

    attrs = getattr(value, "attrs", None)
    if isinstance(attrs, dict):
        attrs.pop("fetch_error", None)
        attrs.pop("error_type", None)
        attrs.update({
            "provider": entry["provider"],
            "data_state": "cached_live",
            "retrieved_at": entry["stored_at"],
            "cache_age_seconds": round(age, 1),
            "stale": True,
        })
    return value


def freshness_for_signal(signal: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Classify an already-scored signal using its genuine last observation."""
    data = signal.get("data")
    cfg = signal.get("config") or {}
    source = canonical_provider(cfg.get("source") or signal.get("provider"))
    state = str(signal.get("data_state") or getattr(data, "attrs", {}).get("data_state") or "live")
    cache_age_seconds = signal.get("cache_age_seconds")
    if cache_age_seconds is None:
        cache_age_seconds = getattr(data, "attrs", {}).get("cache_age_seconds")
    if signal.get("unavailable") or signal.get("error") or data is None or bool(getattr(data, "empty", True)):
        return {"state": "unavailable", "provider": source, "last_observation": None,
                "age_days": None, "cache_age_seconds": None}

    try:
        last = data.index.max()
        last_dt = last.to_pydatetime() if hasattr(last, "to_pydatetime") else last
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        age_days = max(0.0, (current - last_dt).total_seconds() / 86400)
        last_text = last_dt.date().isoformat()
    except Exception:
        age_days = None
        last_text = None

    frequency = str(cfg.get("frequency", "daily")).lower()
    threshold = 5 if "daily" in frequency else 14 if "week" in frequency else 45 if "month" in frequency else 120
    if state == "cached_live":
        quality = "cached_live"
    elif age_days is not None and age_days > threshold:
        quality = "delayed"
    else:
        quality = "fresh"
    return {"state": quality, "provider": source, "last_observation": last_text,
            "age_days": age_days, "cache_age_seconds": cache_age_seconds}


def summarize_signal_quality(signals: dict[str, dict]) -> dict[str, int]:
    counts = {"fresh": 0, "cached_live": 0, "delayed": 0, "unavailable": 0, "total": len(signals)}
    for signal in signals.values():
        state = freshness_for_signal(signal)["state"]
        counts[state] = counts.get(state, 0) + 1
    return counts


def _reset_for_tests() -> None:
    with _lock:
        _events.clear()
        _last_known_good.clear()
