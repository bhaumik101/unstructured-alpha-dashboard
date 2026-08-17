"""A poisoned pip cache must not be permanent.

Diagnosed from Render build logs. Four cron services failed to build for three
days straight, every attempt identical:

  ERROR: THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE.
  unknown package:
  Expected sha256 d8a47c11...
  Got             1868eaa8...   (score-rest, on both Aug 13 and Aug 16)
  Got             308a2279...   (lifecycle)

The *expected* hash is the same package on every service; the *got* bytes
differ per service and are stable within a service across days. So each one
cached its own corrupt copy of the same package and has replayed it ever since.

Two things this rules out, both of which were guessed before the logs were
read: it is not dependency resolution (#148), and it is not the interpreter
(#149) — the failures continued byte-identically after Python moved 3.14 -> 3.12,
because pip's HTTP cache is keyed by URL, not by interpreter.

A cached install that fails now retries with --no-cache-dir, so a corrupt entry
costs one slow build instead of an outage that only a manual "Clear build cache"
can end. Normal builds still use the cache.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_RENDER = Path(__file__).resolve().parent.parent / "render.yaml"
_SPEC = yaml.safe_load(_RENDER.read_text(encoding="utf-8"))
_SERVICES = [s for s in _SPEC.get("services", []) if "buildCommand" in s]


def test_services_are_parsed():
    assert len(_SERVICES) >= 15, f"only {len(_SERVICES)} build commands found"


def test_every_build_retries_without_the_cache():
    missing = [s["name"] for s in _SERVICES if "--no-cache-dir" not in s["buildCommand"]]
    assert not missing, (
        "a poisoned cache entry is permanent for these services — every build "
        f"replays it until someone clears the cache by hand: {missing}"
    )


def test_the_retry_is_a_fallback_not_the_default():
    """Always skipping the cache would slow all 16 services on every build."""
    for s in _SERVICES:
        cmd = s["buildCommand"]
        assert "||" in cmd, (
            f"{s['name']}: the no-cache install must be a fallback after `||`, "
            f"not the primary command"
        )
        first = cmd.split("||")[0]
        assert "--no-cache-dir" not in first, (
            f"{s['name']}: the FIRST install should use the cache; only the "
            f"retry bypasses it"
        )


def test_the_web_service_still_runs_the_injector_after_a_retry():
    """`a || b && c` binds left to right — without parentheses the injector
    would be skipped whenever the first install succeeded."""
    web = [s for s in _SERVICES if "inject_boot_splash" in s["buildCommand"]]
    assert web, "no service runs the boot-splash injector"
    for s in web:
        cmd = s["buildCommand"]
        assert cmd.strip().startswith("("), (
            f"{s['name']}: group the install alternatives in parentheses, or "
            f"the injector's execution depends on which install ran"
        )
        assert re.search(r"\)\s*&&\s*python scripts/inject_boot_splash\.py", cmd), (
            f"{s['name']}: the injector must run after the grouped install"
        )
