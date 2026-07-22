"""Unit tests for private, per-user investment thesis storage."""

import pytest
from sqlalchemy import delete

from utils import db
from utils.thesis import get_thesis, list_user_theses, save_thesis


@pytest.fixture(autouse=True)
def _clean_theses():
    db.init_db()
    with db.engine.begin() as conn:
        conn.execute(delete(db.investment_theses).where(db.investment_theses.c.user_id.in_([9001, 9002])))
    yield
    with db.engine.begin() as conn:
        conn.execute(delete(db.investment_theses).where(db.investment_theses.c.user_id.in_([9001, 9002])))


def test_thesis_is_private_and_round_trips():
    save_thesis(
        user_id=9001,
        ticker="aapl",
        stance="Bullish",
        status="active",
        horizon_weeks=16,
        entry_price=210.25,
        entry_score=67.0,
        thesis="Services growth is underestimated.",
        catalysts="Product cycle",
        risks="Multiple compression",
        invalidation="Services growth falls below plan",
    )

    saved = get_thesis(9001, "AAPL")
    assert saved["ticker"] == "AAPL"
    assert saved["stance"] == "Bullish"
    assert saved["entry_price"] == pytest.approx(210.25)
    assert get_thesis(9002, "AAPL") is None


def test_saving_again_updates_one_decision_record():
    common = dict(
        user_id=9001,
        ticker="MSFT",
        stance="Neutral",
        horizon_weeks=12,
        thesis="Initial thesis",
    )
    save_thesis(status="active", **common)
    save_thesis(
        **{**common, "stance": "Bearish", "thesis": "Updated thesis"},
        status="invalidated",
        outcome_notes="The original catalyst did not materialize.",
    )

    rows = list_user_theses(9001)
    assert len(rows) == 1
    assert rows[0]["stance"] == "Bearish"
    assert rows[0]["status"] == "invalidated"
    assert list_user_theses(9001, status="active") == []
    assert len(list_user_theses(9001, status="invalidated")) == 1


def test_thesis_requires_valid_decision_inputs():
    with pytest.raises(ValueError):
        save_thesis(
            user_id=9001,
            ticker="NVDA",
            stance="Bullish",
            status="active",
            horizon_weeks=12,
            thesis="",
        )
