"""A cron that scores signals must hold every credential those signals need.

PRODUCTION DIAGNOSIS, 2026-08-21
--------------------------------
"Fed Policy Hawkishness (FOMC AI Score)" was the last signal reporting awaiting
data -- 46 of 47 scored. PR #177 had fixed FOMC calendar discovery and its tests
passed, but the signal still produced nothing on the scheduled path.

Traced against production, step by step, rather than inferred:

  1. calendar discovery      federalreserve.gov/monetarypolicy/fomccalendars.htm
                             HTTP 200, 46 meeting dates found
  2. statement downloads     all 8 dates in the scoring window returned HTTP 200
                             with "Federal Open Market Committee" present
  3. parsed meeting dates    8 past meetings, none in the future
  4. observations            NONE -- fetch_fedspeaks_hawkishness() returns an
                             empty Series on its first statement when
                             ANTHROPIC_API_KEY is unset, before any network call
  5. minimum history (>=3)   never reached; the series was already empty
  6. score calculation       n/a
  7. snapshot persistence    nothing written for this signal
  8. report rendering        correct -- "awaiting data" is the honest output

The failure was step 4 and nothing else: cron/send_digest.py writes
signal_snapshots and did not declare ANTHROPIC_API_KEY. The WEB service does
declare it, so the signal can appear scored in-app while the snapshot the public
report reads has never held a value.

The fix is the credential, not the pipeline. Nothing here weakens the >=3
minimum, invents observations, or lets missing data count as neutral.

WHAT THIS TEST GUARDS
---------------------
Restoring the exact production failure -- removing ANTHROPIC_API_KEY from the
digest cron -- fails test_snapshot_writers_declare_every_credential_they_need.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_BLUEPRINT = yaml.safe_load((_ROOT / "render.yaml").read_text(encoding="utf-8"))
_FETCHERS = (_ROOT / "utils" / "fetchers.py").read_text(encoding="utf-8")


def _services() -> dict[str, dict]:
    return {s["name"]: s for s in _BLUEPRINT.get("services") or []}


def _env_keys(service: dict) -> set[str]:
    return {e.get("key") for e in (service.get("envVars") or [])}


def _credentials_the_fetchers_need() -> set[str]:
    """Env vars that a fetcher reads and treats as required.

    'Required' means the function returns an empty result when it is missing --
    the shape that turns a credential gap into a signal that silently reports no
    data rather than raising.
    """
    needed: set[str] = set()
    tree = ast.parse(_FETCHERS)
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or not fn.name.startswith("fetch_"):
            continue
        src = ast.get_source_segment(_FETCHERS, fn) or ""
        for var in re.findall(r'os\.environ\.get\(\s*"([A-Z][A-Z0-9_]+)"', src):
            # only when absence short-circuits the function
            if re.search(rf'if not \w+:\s*\n\s*return', src):
                needed.add(var)
    return needed


def test_snapshot_writers_declare_every_credential_they_need():
    """The exact production failure, as an assertion.

    cron/send_digest.py calls get_all_signal_scores() and writes
    signal_snapshots. Every credential a signal fetcher treats as required has
    to be present on that service, or the affected signals are unscorable on the
    only path that persists them.
    """
    digest = _services().get("unstructured-alpha-digest")
    assert digest, "the digest cron is gone; this guard needs re-pointing"

    digest_src = (_ROOT / "cron" / "send_digest.py").read_text(encoding="utf-8")
    assert "get_all_signal_scores" in digest_src, (
        "the digest cron no longer scores signals; re-point this test at "
        "whatever writes signal_snapshots now"
    )

    missing = sorted(_credentials_the_fetchers_need() - _env_keys(digest))
    assert not missing, (
        "cron/send_digest.py writes signal_snapshots but does not declare: "
        + ", ".join(missing)
        + ". A fetcher that needs one of these returns an EMPTY SERIES rather "
        "than raising, so the affected signals report 'awaiting data' forever "
        "and nothing in the logs says why. This is exactly how Fed Policy "
        "Hawkishness stayed dark while its own tests passed."
    )


def test_the_anthropic_key_is_specifically_required_here():
    """Named explicitly, because this is the one that was actually missing."""
    digest = _services()["unstructured-alpha-digest"]
    assert "ANTHROPIC_API_KEY" in _env_keys(digest), (
        "the digest cron lost ANTHROPIC_API_KEY; Fed Policy Hawkishness cannot "
        "be scored on the scheduled path without it"
    )


def test_the_fed_fetcher_still_fails_closed_rather_than_guessing():
    """Absence of data must not become a fabricated observation.

    If this ever starts returning a default score instead of an empty series,
    the signal would report a confident reading it does not have.
    """
    fn = next(
        n for n in ast.walk(ast.parse(_FETCHERS))
        if isinstance(n, ast.FunctionDef) and n.name == "fetch_fedspeaks_hawkishness"
    )
    src = ast.get_source_segment(_FETCHERS, fn) or ""
    assert re.search(r"if not api_key:\s*\n\s*return pd\.Series\(dtype=float", src), (
        "the fetcher no longer returns an empty series when the key is missing"
    )
    assert re.search(r"if len\(scored\) < 3:\s*\n\s*return pd\.Series\(dtype=float", src), (
        "the >=3 observation minimum is gone; fewer real data points would now "
        "produce a z-score the history cannot support"
    )
