"""A report's FRED series are fetched together, not one after another.

With the extra forces a report asks for ~15 series. Fetched in turn, a cold
cache costs the sum of their latencies, and a FRED outage the sum of their
timeouts (12s API + 30s public fallback each): minutes for one report. This
pins that they are fetched at once, and that a failure still reaches exactly
the caller that asked for that series, so the engine excludes and names it.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import exposure as ex  # noqa: E402


def test_every_series_a_report_can_ask_for_is_prefetched():
    ids = set(ex.REPORT_SERIES_IDS)
    assert {f.series_id for f in ex.FACTORS} <= ids
    assert ex.GROWTH_FACTOR.series_id in ids
    assert {f.series_id for f in ex.EXTRA_FACTORS if f.source == "fred"} <= ids
    assert not ids & set(ex.EXTRA_PRICE_TICKERS), "fund prices are not FRED series"


def test_series_are_fetched_at_once_not_in_turn():
    active = {"now": 0, "peak": 0}
    lock = threading.Lock()

    def slow(sid, s, e):
        with lock:
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
        time.sleep(0.2)
        with lock:
            active["now"] -= 1
        return sid

    ids = [f"S{i}" for i in range(12)]
    f = ex.prefetching(slow, ids, workers=8)
    t0 = time.monotonic()
    assert [f(i, "a", "b") for i in ids] == ids
    assert time.monotonic() - t0 < 1.0, "12 x 0.2s fetched in turn would take 2.4s"
    assert active["peak"] > 1


def test_each_series_is_fetched_once():
    calls = []
    f = ex.prefetching(lambda sid, s, e: calls.append(sid) or sid, ["A", "B"])
    for _ in range(3):
        f("A", "x", "y"), f("B", "x", "y")
    assert sorted(calls) == ["A", "B"]


def test_a_failure_reaches_only_the_caller_that_asked_for_it():
    def fetch(sid, s, e):
        if sid == "BAD":
            raise ConnectionError("down")
        return sid

    f = ex.prefetching(fetch, ["GOOD", "BAD"])
    assert f("GOOD", "x", "y") == "GOOD"
    with pytest.raises(ConnectionError):
        f("BAD", "x", "y")


def test_a_series_not_on_the_list_is_still_fetched():
    f = ex.prefetching(lambda sid, s, e: sid.lower(), ["A"])
    assert f("OTHER", "x", "y") == "other"


def test_the_report_is_identical_with_and_without_prefetch():
    from tests.test_extra_forces import END, _world

    pf, sf = _world()
    h = [{"ticker": "BANK", "weight_pct": 100}]
    plain = ex.build_exposure_report(h, pf, sf, end=END)
    fast = ex.build_exposure_report(h, pf, ex.prefetching(sf, ex.REPORT_SERIES_IDS), end=END)
    assert plain["portfolio"]["readings"] == fast["portfolio"]["readings"]
    assert plain["extras"] == fast["extras"]


def test_the_live_adapter_prefetches():
    src = (_ROOT / "utils" / "exposure.py").read_text(encoding="utf-8")
    body = src[src.index("def build_live_report"):]
    assert "prefetching(_series, REPORT_SERIES_IDS)" in body
    assert body.index("key = _get_fred_key()") < body.index("def _series"), (
        "the FRED key must be resolved on the calling thread, not inside the workers")
