"""
Unit tests for utils/alerts_db.py — the persistent, per-user watchlist +
alert storage layer. Runs against an in-memory SQLite database (via
utils/db.py) for full isolation between tests. A single throwaway user_id
(1) is used throughout since these tests are about the watchlist/alert CRUD
operations themselves, not cross-user isolation (that's covered separately
in tests/test_auth_and_multitenancy_unit.py).
"""

from sqlalchemy import create_engine

import pytest

from utils import db, alerts_db


@pytest.fixture(autouse=True)
def _in_memory_db(monkeypatch):
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db, "engine", test_engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    db.metadata.create_all(test_engine)
    yield


UID = 1  # throwaway user id; a real row isn't needed since nothing here joins to users


def test_init_db_is_idempotent():
    alerts_db.init_db()
    alerts_db.init_db()  # must not raise on a second call


def test_add_and_get_watchlist():
    alerts_db.add_to_watchlist(UID, "MSFT")
    alerts_db.add_to_watchlist(UID, "ccj", score_bull_threshold=70.0)  # lowercase input
    wl = alerts_db.get_watchlist(UID)
    tickers = {row["ticker"] for row in wl}
    assert tickers == {"MSFT", "CCJ"}
    ccj_row = next(r for r in wl if r["ticker"] == "CCJ")
    assert ccj_row["score_bull_threshold"] == 70.0


def test_add_to_watchlist_upserts_thresholds():
    alerts_db.add_to_watchlist(UID, "GOOGL", score_bull_threshold=65.0)
    alerts_db.add_to_watchlist(UID, "GOOGL", score_bull_threshold=80.0)
    wl = alerts_db.get_watchlist(UID)
    assert len(wl) == 1
    assert wl[0]["score_bull_threshold"] == 80.0


def test_remove_from_watchlist():
    alerts_db.add_to_watchlist(UID, "AAPL")
    assert alerts_db.is_watched(UID, "AAPL")
    alerts_db.remove_from_watchlist(UID, "aapl")  # lowercase input
    assert not alerts_db.is_watched(UID, "AAPL")
    assert alerts_db.get_watchlist(UID) == []


def test_remove_from_watchlist_also_clears_alert_state():
    alerts_db.add_to_watchlist(UID, "NVDA")
    alerts_db.set_alert_state(UID, "NVDA", last_score=72.0)
    alerts_db.remove_from_watchlist(UID, "NVDA")
    assert alerts_db.get_alert_state(UID, "NVDA") is None


def test_is_watched_false_for_unwatched_ticker():
    assert not alerts_db.is_watched(UID, "ZZZZ")


def test_alert_state_roundtrip():
    assert alerts_db.get_alert_state(UID, "AVGO") is None
    alerts_db.set_alert_state(
        UID, "avgo", last_score=55.0, last_score_basis="personal:balanced:long:macro", last_price=410.0
    )
    state = alerts_db.get_alert_state(UID, "AVGO")
    assert state["last_score"] == 55.0
    assert state["last_price"] == 410.0
    assert state["last_score_basis"] == "personal:balanced:long:macro"
    assert state["last_checked_at"]  # populated automatically


def test_set_alert_state_upserts():
    alerts_db.set_alert_state(UID, "HAL", last_score=50.0)
    alerts_db.set_alert_state(UID, "HAL", last_score=60.0)
    state = alerts_db.get_alert_state(UID, "HAL")
    assert state["last_score"] == 60.0


def test_create_and_get_alerts():
    alerts_db.create_alert(UID, "CCJ", "score_threshold", "Score crossed bullish", direction="bullish")
    alerts_db.create_alert(UID, "MSFT", "price_move", "Hit 52-week high", direction="bullish")
    alerts = alerts_db.get_alerts(UID)
    assert len(alerts) == 2
    # most recent first
    assert alerts[0]["ticker"] == "MSFT"
    assert alerts[0]["is_read"] == 0


def test_count_unread_and_mark_all_read():
    alerts_db.create_alert(UID, "CCJ", "score_threshold", "msg1")
    alerts_db.create_alert(UID, "CCJ", "score_threshold", "msg2")
    assert alerts_db.count_unread(UID) == 2
    alerts_db.mark_all_read(UID)
    assert alerts_db.count_unread(UID) == 0
    assert all(a["is_read"] == 1 for a in alerts_db.get_alerts(UID))


def test_mark_read_single_alert():
    id1 = alerts_db.create_alert(UID, "CCJ", "score_threshold", "msg1")
    alerts_db.create_alert(UID, "CCJ", "score_threshold", "msg2")
    alerts_db.mark_read(UID, id1)
    assert alerts_db.count_unread(UID) == 1


def test_get_alerts_unread_only_filter():
    id1 = alerts_db.create_alert(UID, "CCJ", "score_threshold", "msg1")
    alerts_db.create_alert(UID, "CCJ", "score_threshold", "msg2")
    alerts_db.mark_read(UID, id1)
    unread = alerts_db.get_alerts(UID, unread_only=True)
    assert len(unread) == 1
    assert unread[0]["message"] == "msg2"


def test_get_alerts_respects_limit():
    for i in range(5):
        alerts_db.create_alert(UID, "CCJ", "score_threshold", f"msg{i}")
    assert len(alerts_db.get_alerts(UID, limit=3)) == 3


def test_clear_all_alerts():
    alerts_db.create_alert(UID, "CCJ", "score_threshold", "msg1")
    alerts_db.clear_all_alerts(UID)
    assert alerts_db.get_alerts(UID) == []
    assert alerts_db.count_unread(UID) == 0
