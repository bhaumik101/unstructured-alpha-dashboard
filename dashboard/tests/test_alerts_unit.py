"""
Unit tests for utils/alerts.py — the evaluation engine that turns deltas
between a watched ticker's current state and its last-seen snapshot into
alert records. compute_full_ticker_score() is mocked throughout since it's
a heavy multi-fetcher integration function tested on its own elsewhere
(live-verified manually); these tests are about the DELTA/threshold logic,
not re-testing the scoring pipeline itself. A single throwaway user_id (1)
is used since per-user isolation itself is covered in
tests/test_auth_and_multitenancy_unit.py.
"""

from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import create_engine

from utils import db, alerts_db, alerts


@pytest.fixture(autouse=True)
def _in_memory_db(monkeypatch):
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db, "engine", test_engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    db.metadata.create_all(test_engine)
    yield


UID = 1
_THRESHOLDS = {"score_bull_threshold": 65.0, "score_bear_threshold": 35.0, "price_move_pct_threshold": 5.0}


def _fake_full(score: float, price: float, insider="no_data", short_interest="no_data", thirteenf="no_data",
                n_prices: int = 5) -> dict:
    prices = pd.Series([price] * n_prices)
    return {
        "confluence": {"overall_score": score},
        "price_series": prices,
        "insider_score": {"status": insider}, "has_insider_signal": insider != "no_data",
        "short_interest_score": {"status": short_interest}, "has_short_interest_signal": short_interest != "no_data",
        "thirteenf_score": {"status": thirteenf}, "has_13f_signal": thirteenf != "no_data",
    }


def test_evaluate_ticker_first_check_creates_no_alerts_but_saves_state():
    """Nothing to compare against on the very first check -- must not alert,
    but must persist a baseline so the NEXT check has something to diff."""
    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(50.0, 100.0)):
        result = alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)
    assert result == []
    state = alerts_db.get_alert_state(UID, "CCJ")
    assert state["last_score"] == 50.0
    assert state["last_price"] == 100.0


def test_evaluate_ticker_score_crossing_into_bullish_fires_once():
    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(60.0, 100.0)):
        alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)  # baseline: 60, below 65 threshold

    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(70.0, 100.0)):
        result = alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)  # crosses above 65

    assert len(result) == 1
    assert result[0]["alert_type"] == "score_threshold"
    assert result[0]["direction"] == "bullish"
    assert "60" in result[0]["message"] and "70" in result[0]["message"]


def test_evaluate_ticker_staying_bullish_does_not_re_alert():
    """A score that was already above threshold and stays above it must not
    fire again on every subsequent check -- that would make the feed noise."""
    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(70.0, 100.0)):
        alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)  # baseline already bullish

    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(72.0, 100.0)):
        result = alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)  # still bullish, didn't cross

    assert result == []


def test_evaluate_ticker_score_crossing_into_bearish():
    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(40.0, 100.0)):
        alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)

    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(30.0, 100.0)):
        result = alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)

    assert len(result) == 1
    assert result[0]["direction"] == "bearish"


def test_profile_change_rebaselines_before_personalized_threshold_alert(monkeypatch):
    profile = {"tolerance": "aggressive", "horizon": "short", "emphasis": "full"}
    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(60.0, 100.0)):
        alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)

    monkeypatch.setattr(
        "utils.risk_profile.compute_personal_score",
        lambda _full, _profile: {"ok": True, "score": 70.0, "profile": profile},
    )
    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(60.0, 100.0)):
        result = alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS, profile=profile)

    assert result == []
    state = alerts_db.get_alert_state(UID, "CCJ")
    assert state["last_score"] == 70.0
    assert state["last_score_basis"] == "personal:aggressive:short:full"

    monkeypatch.setattr(
        "utils.risk_profile.compute_personal_score",
        lambda _full, _profile: {"ok": True, "score": 30.0, "profile": profile},
    )
    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(60.0, 100.0)):
        result = alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS, profile=profile)

    score_alerts = [row for row in result if row["alert_type"] == "score_threshold"]
    assert len(score_alerts) == 1
    assert score_alerts[0]["direction"] == "bearish"
    assert "Your Score" in score_alerts[0]["message"]


def test_evaluate_ticker_price_move_above_threshold_fires():
    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(50.0, 100.0)):
        alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)

    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(50.0, 110.0)):  # +10%
        result = alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)

    price_alerts = [a for a in result if a["alert_type"] == "price_move"]
    assert len(price_alerts) >= 1
    assert any(a["direction"] == "bullish" for a in price_alerts)


def test_evaluate_ticker_price_move_below_threshold_does_not_fire():
    # Price history establishes a real prior high (120) well above the
    # "current" price throughout, so a small +1% uptick from 100 isn't
    # trivially also a new-52-week-high alert -- isolates the pct-move check.
    prices_with_real_high = pd.Series([100.0, 110.0, 120.0, 105.0, 100.0])
    with patch("utils.alerts.compute_full_ticker_score",
               return_value={**_fake_full(50.0, 100.0), "price_series": prices_with_real_high}):
        alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)

    prices_after = pd.Series([100.0, 110.0, 120.0, 105.0, 101.0])  # +1%, below 5% threshold, still under the 120 high
    with patch("utils.alerts.compute_full_ticker_score",
               return_value={**_fake_full(50.0, 101.0), "price_series": prices_after}):
        result = alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)

    assert result == []


def test_evaluate_ticker_differentiator_signal_change_fires():
    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(50.0, 100.0, insider="neutral")):
        alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)

    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(50.0, 100.0, insider="bullish")):
        result = alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)

    insider_alerts = [a for a in result if a["alert_type"] == "insider"]
    assert len(insider_alerts) == 1
    assert insider_alerts[0]["direction"] == "bullish"


def test_evaluate_ticker_differentiator_no_data_does_not_fire():
    """Going from having real data to genuinely no_data (e.g. a fetch hiccup)
    should not be treated as a meaningful signal change."""
    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(50.0, 100.0, short_interest="bullish")):
        alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)

    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(50.0, 100.0, short_interest="no_data")):
        result = alerts.evaluate_ticker(UID, "CCJ", _THRESHOLDS)

    assert [a for a in result if a["alert_type"] == "short_interest"] == []


def test_evaluate_watchlist_evaluates_every_watched_ticker():
    alerts_db.add_to_watchlist(UID, "CCJ")
    alerts_db.add_to_watchlist(UID, "MSFT")
    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(50.0, 100.0)):
        result = alerts.evaluate_watchlist(UID)
    assert result == []  # first check for both, no alerts, but...
    assert alerts_db.get_alert_state(UID, "CCJ") is not None
    assert alerts_db.get_alert_state(UID, "MSFT") is not None


def test_evaluate_watchlist_skips_tickers_that_error():
    alerts_db.add_to_watchlist(UID, "GOOD")
    alerts_db.add_to_watchlist(UID, "BAD")

    def _side_effect(ticker):
        if ticker == "BAD":
            raise ConnectionError("network down")
        return _fake_full(70.0, 100.0)

    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(60.0, 100.0)):
        alerts.evaluate_ticker(UID, "GOOD", _THRESHOLDS)  # baseline

    with patch("utils.alerts.compute_full_ticker_score", side_effect=_side_effect):
        result = alerts.evaluate_watchlist(UID)

    # GOOD crosses 60->70 and fires; BAD's exception must not block GOOD's alert
    assert any(a["ticker"] == "GOOD" for a in result)
    assert alerts_db.get_alert_state(UID, "BAD") is None  # never successfully evaluated


def test_evaluate_watchlist_only_evaluates_calling_users_tickers():
    """A second user's watchlist must not be touched by evaluate_watchlist(user1)."""
    alerts_db.add_to_watchlist(UID, "CCJ")
    other_uid = 2
    alerts_db.add_to_watchlist(other_uid, "MSFT")

    with patch("utils.alerts.compute_full_ticker_score", return_value=_fake_full(50.0, 100.0)):
        alerts.evaluate_watchlist(UID)

    assert alerts_db.get_alert_state(UID, "CCJ") is not None
    assert alerts_db.get_alert_state(other_uid, "MSFT") is None
