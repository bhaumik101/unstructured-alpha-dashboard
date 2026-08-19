"""The audit harness must not throw away results from pages that did render.

Two defects in scripts/a11y_audit.mjs, both found by pointing it at all 32
routes for the first time rather than the seven it had always been given.

1. IT DIED ON THE FOURTH URL
   Streamlit is an SPA and can re-navigate mid-evaluate; puppeteer then rejects
   with "Execution context was destroyed". Unhandled, that ended the whole run.
   A destroyed context is a retry -- the next poll runs in the new context.

2. IT DISQUALIFIED 13 PAGES THAT HAD RENDERED
   The rendered check demanded 3,000 chars. On the full sweep that marked every
   Pro gate and auth wall (~1,700 chars: chrome plus an upgrade panel) and four
   real content pages (2,383-2,988) as "NO DATA", discarding their axe results
   -- including four genuine contrast failures on /sector-view.

   A gate is not a failure to render. It is what an anonymous visitor actually
   sees, which makes it one of the more important surfaces to audit rather than
   one to throw away.

The harness now reports a STATE -- full / gate / empty -- against the ~1,200
char chrome-only baseline, and only "empty" invalidates the numbers.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = (
    Path(__file__).resolve().parent.parent / "scripts" / "a11y_audit.mjs"
).read_text(encoding="utf-8")


def test_a_destroyed_execution_context_is_a_retry_not_a_crash():
    assert "Execution context was destroyed" in _SRC, (
        "the harness no longer tolerates Streamlit re-navigating mid-evaluate; "
        "one such page ends the entire sweep"
    )
    assert re.search(r"const settle = async", _SRC), (
        "the guarded evaluate wrapper is gone"
    )


def test_one_unmeasurable_page_does_not_end_the_sweep():
    assert "failed.push(" in _SRC, "per-URL failures are no longer collected"
    assert "NOT MEASURED" in _SRC, (
        "a page that cannot be measured must be named, not silently skipped"
    )
    assert "} finally {" in _SRC, "the page is no longer closed on the error path"


def test_the_verdict_is_a_state_not_a_boolean():
    for token in ("CHROME_BASELINE", "MIN_CHARS", "FULL_PAGE_CHARS"):
        assert token in _SRC, f"{token} is gone; the verdict is back to pass/fail"
    assert 'state = diag.chars >= FULL_PAGE_CHARS ? "full"' in _SRC, (
        "the three-state classification is gone"
    )


def test_only_an_empty_page_invalidates_its_results():
    """The whole point: a gate's violations are real violations."""
    assert 'state !== "empty"' in _SRC, (
        "results are being discarded for states other than empty again"
    )
    assert re.search(r'state === "empty"[\s\S]{0,200}NO DATA', _SRC), (
        "the NO DATA warning should attach to empty pages only"
    )
    assert "results count" in _SRC, (
        "a gate should be labelled as a real surface whose results count"
    )


def test_the_threshold_sits_above_the_chrome_baseline():
    """Below it, a page showing only nav would look like content."""
    base = int(re.search(r"const CHROME_BASELINE = (\d+)", _SRC).group(1))
    minc = int(re.search(r"const MIN_CHARS = (\d+)", _SRC).group(1))
    full = int(re.search(r"const FULL_PAGE_CHARS = (\d+)", _SRC).group(1))
    assert base < minc < full, (
        f"thresholds are not ordered: baseline={base} min={minc} full={full}"
    )
