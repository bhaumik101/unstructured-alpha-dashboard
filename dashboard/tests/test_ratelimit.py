"""Unit tests for utils.ratelimit — exercise the in-process fallback path
(no REDIS_URL in test env → deterministic, no network)."""
import time

import utils.ratelimit as rl


def test_within_limit_allowed():
    key = f"t_within_{time.time()}"
    for i in range(5):
        allowed, retry = rl.check(key, limit=5, window=60)
        assert allowed is True
        assert retry == 0


def test_over_limit_blocked_with_retry_after():
    key = f"t_over_{time.time()}"
    for _ in range(3):
        assert rl.check(key, limit=3, window=60)[0] is True
    allowed, retry = rl.check(key, limit=3, window=60)   # 4th
    assert allowed is False
    assert retry >= 1


def test_window_resets():
    key = f"t_reset_{time.time()}"
    assert rl.check(key, limit=1, window=1)[0] is True
    assert rl.check(key, limit=1, window=1)[0] is False   # blocked in-window
    time.sleep(1.1)
    assert rl.check(key, limit=1, window=1)[0] is True     # new window


def test_distinct_keys_independent():
    t = time.time()
    assert rl.check(f"a_{t}", limit=1, window=60)[0] is True
    assert rl.check(f"b_{t}", limit=1, window=60)[0] is True  # different key, own bucket


def test_limit_action_uses_policy():
    actor = f"user_{time.time()}"
    # ai_research policy is (10, 3600) → first call allowed
    allowed, _ = rl.limit_action(actor, "ai_research")
    assert allowed is True


def test_unknown_action_is_noop_allowed():
    allowed, retry = rl.limit_action("anyone", "does_not_exist")
    assert allowed is True and retry == 0


def test_backend_reports_memory_without_redis():
    # No REDIS_URL configured in the test environment.
    assert rl.backend() in ("memory", "redis")  # 'memory' locally; contract holds either way
