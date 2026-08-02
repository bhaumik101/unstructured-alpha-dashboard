"""Cross-process header cache.

Guards the behaviour that makes this worth having: a stale value must be
served INSTANTLY rather than blocking a visitor, and only one caller may do
the slow refresh. Production PERF logs put page.home.header at 72-77% of total
render (max 2607ms) purely because of the blocking yf.download this fronts.
"""

from __future__ import annotations

import json
import time

import pytest

from utils import shared_cache as sc


class FakeRedis:
    """Minimal Redis: get/set with nx+ex semantics, and delete."""
    def __init__(self): self.d = {}
    def ping(self): return True
    def get(self, k): return self.d.get(k)
    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.d:
            return False
        self.d[k] = v
        return True
    def delete(self, k): self.d.pop(k, None)


@pytest.fixture
def redis(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(sc, "_init_client", lambda: r)
    return r


def _seed(r, key, value, age_s):
    r.d[sc._PREFIX + key] = json.dumps({"v": value, "t": time.time() - age_s})


def test_fresh_value_skips_the_producer(redis):
    calls = []
    _seed(redis, "k", [["SPY", "S&P 500", 1.0, 2.0]], age_s=10)
    out = sc.get_or_refresh("k", lambda: calls.append(1) or "NEW", fresh_seconds=900)
    assert out == [["SPY", "S&P 500", 1.0, 2.0]]
    assert calls == []


def test_stale_value_is_served_without_blocking_when_another_caller_refreshes(redis):
    """The whole point: a visitor must never wait behind someone else's refresh."""
    _seed(redis, "k", "STALE", age_s=5000)
    redis.d[sc._PREFIX + "k:lock"] = "1"          # someone else is already refreshing
    calls = []
    out = sc.get_or_refresh("k", lambda: calls.append(1) or "NEW", fresh_seconds=900)
    assert out == "STALE"
    assert calls == [], "served stale but still paid for the producer"


def test_lock_winner_refreshes_and_releases(redis):
    _seed(redis, "k", "STALE", age_s=5000)
    out = sc.get_or_refresh("k", lambda: "NEW", fresh_seconds=900)
    assert out == "NEW"
    assert json.loads(redis.d[sc._PREFIX + "k"])["v"] == "NEW"
    assert sc._PREFIX + "k:lock" not in redis.d, "lock leaked; key wedged until TTL"


def test_no_redis_falls_back_to_calling_the_producer(monkeypatch):
    monkeypatch.setattr(sc, "_init_client", lambda: None)
    assert sc.get_or_refresh("k", lambda: "DIRECT") == "DIRECT"


def test_producer_failure_serves_stale_and_frees_the_lock(redis):
    """A Yahoo outage must degrade to an old strip, not an empty one."""
    _seed(redis, "k", "STALE", age_s=5000)
    def boom(): raise RuntimeError("yahoo down")
    assert sc.get_or_refresh("k", boom, fresh_seconds=900) == "STALE"
    assert sc._PREFIX + "k:lock" not in redis.d


def test_corrupt_entry_does_not_raise(redis):
    redis.d[sc._PREFIX + "k"] = "{not json"
    assert sc.get_or_refresh("k", lambda: "NEW") == "NEW"


def test_strip_survives_json_roundtrip_for_the_renderer(redis):
    """The producer yields tuples; JSON returns lists.

    _render_live_ticker_strip unpacks `for sym, label, price, chg in items`,
    which is why this is safe — but it is only safe by accident unless pinned.
    """
    produced = [("SPY", "S&P 500", 512.34, -1.25)]
    out = sc.get_or_refresh("strip", lambda: produced, fresh_seconds=900)
    again = sc.get_or_refresh("strip", lambda: [], fresh_seconds=900)
    for sym, label, price, chg in again:
        assert sym == "SPY" and label == "S&P 500"
        assert isinstance(price, float) and isinstance(chg, float)
        assert f"${price:,.2f}" == "$512.34"
        assert (chg >= 0) is False
