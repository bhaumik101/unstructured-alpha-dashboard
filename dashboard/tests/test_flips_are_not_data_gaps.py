"""A signal that stopped reporting has not flipped.

get_signal_flips() compared raw status strings. cron/send_digest.py snapshots
EVERY signal each day, including ones whose fetch failed -- those land with
status "insufficient_data" from signals_cache._error_result(). So a single
transient outage read as two flips:

    day 1  bullish
    day 2  insufficient_data     -> "bullish flipped to insufficient_data"
    day 3  bullish               -> "insufficient_data flipped to bullish"

This function is not internal. It feeds:

    cron/tweet_signal_flips.py   PUBLIC tweets, weekdays 13:00 UTC
    cron/signal_flip_alerts.py   user alert emails, every 6 hours
    cron/send_digest.py          the daily digest email
    utils/convergence.py         convergence detection -> prediction_log
    Signal Dashboard, Today's Brief

So a dropped API response could announce a market move that never happened, to
the public timeline and to every subscribed user, and seed a prediction from it.

Flips are now computed over readings only. A gap is skipped rather than treated
as a state, so a real flip either side of an outage is still reported.
"""

from __future__ import annotations

import utils.score_history as sh


def _snap(sig, date, status, score=50.0):
    return {"signal_id": sig, "snapshot_date": date, "status": status, "score": score}


def _flips(monkeypatch, rows):
    """Run get_signal_flips against a fixed set of snapshot rows."""
    class _Res:
        def mappings(self): return self
        def all(self): return rows
    class _Conn:
        def execute(self, *a, **k): return _Res()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Engine:
        def connect(self): return _Conn()
        def begin(self): return _Conn()
    monkeypatch.setattr(sh.db, "engine", _Engine())
    return sh.get_signal_flips(days_back=7)


def test_a_fetch_failure_is_not_a_flip(monkeypatch):
    rows = [
        _snap("hy_spread", "2026-08-18", "bullish"),
        _snap("hy_spread", "2026-08-19", "insufficient_data"),
    ]
    assert _flips(monkeypatch, rows) == [], (
        "a signal whose data stopped arriving was reported as having flipped"
    )


def test_recovering_from_a_failure_is_not_a_flip_either(monkeypatch):
    rows = [
        _snap("hy_spread", "2026-08-18", "insufficient_data"),
        _snap("hy_spread", "2026-08-19", "bullish"),
    ]
    assert _flips(monkeypatch, rows) == []


def test_a_real_flip_across_a_gap_is_still_reported(monkeypatch):
    """The gap is skipped, not the signal."""
    rows = [
        _snap("hy_spread", "2026-08-17", "bullish"),
        _snap("hy_spread", "2026-08-18", "insufficient_data"),
        _snap("hy_spread", "2026-08-19", "bearish"),
    ]
    out = _flips(monkeypatch, rows)
    assert len(out) == 1, f"a genuine bullish->bearish flip was lost: {out}"
    assert out[0]["from_status"] == "bullish"
    assert out[0]["to_status"] == "bearish"
    assert out[0]["from_date"] == "2026-08-17", (
        "the flip should be dated from the last real reading, not the gap"
    )


def test_an_ordinary_flip_still_works(monkeypatch):
    rows = [
        _snap("hy_spread", "2026-08-18", "bullish"),
        _snap("hy_spread", "2026-08-19", "bearish"),
    ]
    out = _flips(monkeypatch, rows)
    assert len(out) == 1 and out[0]["to_status"] == "bearish"


def test_a_signal_with_only_gaps_reports_nothing(monkeypatch):
    rows = [
        _snap("dead_signal", "2026-08-18", "insufficient_data"),
        _snap("dead_signal", "2026-08-19", "unavailable"),
    ]
    assert _flips(monkeypatch, rows) == []


def test_only_the_three_readings_count_as_states():
    assert sh._READING_STATUSES == frozenset({"bullish", "bearish", "neutral"}), (
        "the reading set changed; anything added here becomes something a "
        "public tweet can announce as a flip"
    )
