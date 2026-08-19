"""A signal with no usable data must be flagged, not just badly-statused.

Several modules decide what is real by filtering on the error flag alone:

    utils/narrative_engine.py  valid = {... if not v.get("error")}
    utils/regime.py            _ok(v) = not v.get("error")

Both then bucket what survives. narrative_engine uses a catch-all --
`status not in ("bullish", "bearish")` counts as neutral -- which is the exact
shape that made the public SEO report publish signals with no data as neutral
market readings. Here it is SAFE, and only for one reason: signals_cache's
_error_result() sets error=True and unavailable=True alongside its
non-reading status, so nothing unreadable ever reaches the catch-all.

That invariant is load-bearing and was written down nowhere. If a future fetch
path ever returns status="insufficient_data" without the flags, the weekly brief
starts counting dead signals as neutral, feeding both the AI prompt and the
bull/bear counts stored in macro_narratives -- silently, because the arithmetic
still adds up.

The score makes it worse: _error_result() carries score=50.0, dead centre. A
consumer that averages without filtering does not get an obvious wrong answer,
it gets a composite quietly dragged toward neutral.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_READINGS = ("bullish", "bearish", "neutral")


def _error_row() -> dict:
    from utils.signals_cache import _error_result
    return _error_result({"name": "Fixture Signal", "category": "macro"})


def test_the_error_row_is_flagged_both_ways():
    """error= is what most consumers filter on; unavailable= is what the UI counts."""
    row = _error_row()
    assert row.get("error") is True, "an unreadable signal must set error=True"
    assert row.get("unavailable") is True, (
        "an unreadable signal must set unavailable=True -- "
        "utils/header.py::count_unavailable_signals filters on it"
    )


def test_the_error_row_never_claims_a_reading():
    row = _error_row()
    assert row.get("status") not in _READINGS, (
        f"an unreadable signal reports status={row.get('status')!r}, which is a "
        "market reading. Nothing downstream can then tell it apart from real data."
    )


def test_a_non_reading_status_always_travels_with_the_error_flag():
    """The invariant narrative_engine's catch-all depends on.

    If this breaks, `status not in ("bullish", "bearish")` starts counting
    unreadable signals as neutral in the weekly brief.
    """
    row = _error_row()
    if row.get("status") not in _READINGS:
        assert row.get("error") is True, (
            "a non-reading status reached a consumer without error=True; "
            "utils/narrative_engine.py would count it as neutral"
        )


def test_narrative_engine_still_filters_on_the_flag():
    """Guards the other half: the filter that makes the catch-all safe."""
    src = (_ROOT / "utils" / "narrative_engine.py").read_text(encoding="utf-8")
    code = "\n".join(line.split("#")[0] for line in src.splitlines())
    assert 'if not v.get("error")' in code, (
        "narrative_engine no longer filters out error rows before bucketing, so "
        "its `status not in (\"bullish\", \"bearish\")` catch-all now counts "
        "unreadable signals as neutral"
    )
