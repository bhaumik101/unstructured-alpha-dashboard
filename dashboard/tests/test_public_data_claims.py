"""Public copy must not out-claim the registry.

Two failures motivated this file, and both were the same shape as the
"Hyperscaler CapEx" incident in PR #110 -- a claim that did not match what the
code computes:

  1. The landing page advertised FINRA and Congressional Disclosures as signal
     sources. Both source zero of the 47 macro signals (FINRA is real, but it
     powers per-ticker short interest, not the signal library). It also
     advertised CBOE, which is not a provider anywhere in the codebase -- the
     VIX signals are CBOE-originated data fetched through Yahoo Finance.
  2. Six placements said scores were "updated every ~2 hours". Nothing scores
     every two hours; `0 */2 * * *` is threshold-alert evaluation. Scores are
     recomputed daily (score-core) and Mon/Wed/Fri for the rest of the universe.

The marketing site is a separate Next.js app that cannot import the Python
registry, so nothing structurally prevents the two drifting apart again. These
tests are that guard.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parent.parent
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

LANDING = DASHBOARD / "unstructured-alpha-web" / "app" / "page.tsx"

# Providers advertised in the past that source zero macro signals. Naming any of
# these as a *signal* source is the specific false claim being prevented.
NON_SIGNAL_PROVIDERS = ("FINRA", "CBOE", "Congressional Disclosures")


def _landing_source() -> str:
    return LANDING.read_text(encoding="utf-8")


def _strip_comments(source: str) -> str:
    """Drop // comments so the explanatory note about the old list is allowed."""
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("//")
    )


@pytest.mark.skipif(not LANDING.exists(), reason="landing page not present")
def test_landing_does_not_advertise_non_signal_providers() -> None:
    body = _strip_comments(_landing_source())
    offenders = [name for name in NON_SIGNAL_PROVIDERS if name in body]
    assert not offenders, (
        "The landing page advertises providers that source no macro signals: "
        f"{offenders}. FINRA powers per-ticker short interest only; CBOE is not "
        "a provider at all (VIX comes through Yahoo Finance). Either remove the "
        "claim or wire the provider up to a real signal."
    )


@pytest.mark.skipif(not LANDING.exists(), reason="landing page not present")
def test_landing_does_not_claim_a_two_hourly_scoring_cadence() -> None:
    body = _strip_comments(_landing_source())
    hits = re.findall(r"every\s*~?\s*2\s*h(?:ours?)?\b", body, flags=re.IGNORECASE)
    assert not hits, (
        f"Landing page still claims a ~2 hour scoring cadence ({hits}). Scores "
        "are recomputed daily, with the full universe three times a week. The "
        "two-hour number is threshold-alert evaluation, not scoring."
    )


@pytest.mark.skipif(not LANDING.exists(), reason="landing page not present")
def test_landing_source_list_matches_the_registry() -> None:
    """The advertised source list must equal what actually feeds the signals."""
    from utils.product_metrics import signal_source_labels

    body = _landing_source()
    match = re.search(r"const SOURCES = \[(.*?)\];", body, flags=re.DOTALL)
    assert match, "could not locate the SOURCES array on the landing page"
    advertised = re.findall(r'"([^"]+)"', match.group(1))

    # Compare loosely: the site uses display names like "FRED (Federal Reserve)"
    # while the registry says "FRED". Every advertised entry must correspond to a
    # real signal source, and every real source must be represented.
    real = signal_source_labels()

    def _norm(value: str) -> str:
        return value.split(" (")[0].strip().lower()

    advertised_norm = {_norm(a) for a in advertised}
    real_norm = {_norm(r) for r in real}

    unbacked = advertised_norm - real_norm
    missing = real_norm - advertised_norm
    assert not unbacked, f"advertised but source no signals: {sorted(unbacked)}"
    assert not missing, f"real signal sources not advertised: {sorted(missing)}"


def test_app_does_not_report_the_cache_ttl_as_a_scoring_cadence() -> None:
    """The 6-hour number is a cache TTL. It is not how often scores change."""
    from utils.product_metrics import (
        SCORE_COMPUTE_DESCRIPTION,
        SCORE_COMPUTE_SHORT,
        SCORE_REFRESH_HOURS,
    )

    assert SCORE_REFRESH_HOURS == 6, "cache TTL is consumed by signals_cache"
    assert "daily" in SCORE_COMPUTE_SHORT
    assert "daily" in SCORE_COMPUTE_DESCRIPTION

    offenders: list[str] = []
    banned = re.compile(
        r"(?:scores?|signals?)[^.\n]{0,40}(?:update|recalculate|refresh)[^.\n]{0,20}"
        r"every\s*~?\s*(?:2|6)\s*hours?",
        flags=re.IGNORECASE,
    )
    for path in sorted((DASHBOARD / "pages").glob("*.py")) + [
        DASHBOARD / "utils" / "header.py"
    ]:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if banned.search(line):
                offenders.append(f"{path.relative_to(DASHBOARD)}:{n}")

    assert not offenders, (
        "These surfaces describe the cache TTL as the scoring cadence: "
        + ", ".join(offenders)
    )
