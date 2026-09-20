"""Decision Queue ranking, honesty, reopening, and account-isolation tests."""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import delete

from utils import db
from utils.decision_queue import (
    apply_queue_states,
    build_decision_queue,
    list_queue_states,
    load_score_changes,
    set_queue_state,
)


USER_A = 9701
USER_B = 9702


def _evidence(ticker: str, score: float | None, weight: float = 10) -> dict:
    snapshot = None if score is None else {
        "score": score,
        "case": "BULL" if score >= 65 else ("BEAR" if score <= 35 else "NEUTRAL"),
        "snapshot_date": "2026-07-22",
    }
    return {
        "ticker": ticker,
        "snapshot": snapshot,
        "weight_pct": weight,
        "source": "portfolio",
    }


@pytest.fixture(autouse=True)
def _state():
    db.init_db()
    now = datetime.now(timezone.utc).isoformat()
    with db.engine.begin() as conn:
        conn.execute(delete(db.decision_queue_states).where(
            db.decision_queue_states.c.user_id.in_((USER_A, USER_B))
        ))
        conn.execute(delete(db.score_snapshots).where(
            db.score_snapshots.c.ticker.in_(("DQAAA", "DQMISS"))
        ))
        conn.execute(delete(db.users).where(db.users.c.id.in_((USER_A, USER_B))))
        conn.execute(db.users.insert(), [
            {
                "id": USER_A,
                "email": "queue-a@example.com",
                "password_hash": "test",
                "created_at": now,
                "email_verified": True,
                "subscription_tier": "pro",
            },
            {
                "id": USER_B,
                "email": "queue-b@example.com",
                "password_hash": "test",
                "created_at": now,
                "email_verified": True,
                "subscription_tier": "pro",
            },
        ])
    yield
    with db.engine.begin() as conn:
        conn.execute(delete(db.decision_queue_states).where(
            db.decision_queue_states.c.user_id.in_((USER_A, USER_B))
        ))
        conn.execute(delete(db.score_snapshots).where(
            db.score_snapshots.c.ticker.in_(("DQAAA", "DQMISS"))
        ))
        conn.execute(delete(db.users).where(db.users.c.id.in_((USER_A, USER_B))))


def test_imminent_earnings_and_thesis_conflict_rank_above_concentration():
    evidence = [
        _evidence("EARN", 70, 10),
        _evidence("CONC", 52, 30),
    ]
    theses = [{
        "ticker": "EARN",
        "status": "active",
        "stance": "Bearish",
        "horizon_weeks": 12,
        "created_at": "2026-07-01T00:00:00+00:00",
    }]
    earnings = {"EARN": {"days_until": 2, "is_estimate": True}}

    queue = build_decision_queue(
        evidence, theses=theses, earnings=earnings, today=date(2026, 7, 22)
    )

    assert [row["ticker"] for row in queue] == ["EARN", "CONC"]
    assert queue[0]["severity"] == "urgent"
    assert {t["kind"] for t in queue[0]["triggers"]} == {"earnings", "thesis_conflict"}
    assert "provisional" in queue[0]["why_now"]


def test_missing_score_is_disclosed_as_a_gap_and_never_estimated():
    queue = build_decision_queue([_evidence("DQMISS", None, 8)])

    assert len(queue) == 1
    assert queue[0]["score"] is None
    assert queue[0]["case"] == "UNAVAILABLE"
    assert queue[0]["triggers"][0]["kind"] == "coverage_gap"


def test_macro_rank_is_not_misrepresented_as_a_full_confluence_score():
    evidence = _evidence("RANK", 71, 8)
    evidence["snapshot"]["score_kind"] = "macro_momentum"

    queue = build_decision_queue([evidence], today=date(2026, 7, 22))

    assert queue[0]["score"] is None
    assert queue[0]["triggers"][0]["kind"] == "coverage_gap"


def test_completed_item_reopens_when_its_evidence_changes():
    original = build_decision_queue(
        [_evidence("MOVE", 70)],
        score_changes={"MOVE": {"delta": 10, "from_date": "2026-07-15", "to_date": "2026-07-22"}},
    )[0]
    state = {
        "MOVE": {
            "evidence_hash": original["evidence_hash"],
            "status": "done",
            "snoozed_until": None,
        }
    }
    assert apply_queue_states([original], state)[0]["status"] == "done"

    changed = build_decision_queue(
        [_evidence("MOVE", 58)],
        score_changes={"MOVE": {"delta": -12, "from_date": "2026-07-15", "to_date": "2026-07-22"}},
    )[0]
    assert changed["evidence_hash"] != original["evidence_hash"]
    assert apply_queue_states([changed], state)[0]["status"] == "open"


def test_triage_state_is_user_scoped_and_snooze_requires_a_date():
    set_queue_state(USER_A, "AAPL", "hash-a", "watching")

    assert list_queue_states(USER_A)["AAPL"]["status"] == "watching"
    assert list_queue_states(USER_B) == {}
    with pytest.raises(ValueError, match="snooze date"):
        set_queue_state(USER_A, "AAPL", "hash-a", "snoozed")


def test_score_change_uses_persisted_full_scores_only():
    now = datetime.now(timezone.utc).isoformat()
    with db.engine.begin() as conn:
        conn.execute(db.score_snapshots.insert(), [
            {
                "ticker": "DQAAA", "snapshot_date": "2026-07-15", "score": 50,
                "case": "NEUTRAL", "score_kind": "full", "created_at": now,
            },
            {
                "ticker": "DQAAA", "snapshot_date": "2026-07-22", "score": 63,
                "case": "NEUTRAL", "score_kind": "full", "created_at": now,
            },
        ])

    changes = load_score_changes(["DQAAA"], days=7, as_of=date(2026, 7, 22))

    assert changes["DQAAA"]["delta"] == 13.0
    assert changes["DQAAA"]["observations"] == 2


def test_page_is_registered_pro_gated_and_marketed():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    page = (root / "pages" / "49_Decision_Queue.py").read_text(encoding="utf-8")
    app = (root / "app.py").read_text(encoding="utf-8")
    header = (root / "utils" / "header.py").read_text(encoding="utf-8")
    upgrade = (root / "pages" / "29_Upgrade.py").read_text(encoding="utf-8")

    assert 'require_pro(page_name="Decision Queue")' in page
    assert 'url_path="decision-queue"' in app
    # Hidden from the nav in the 2026-09-14 redesign, still routed by URL.
    assert 'href="/decision-queue"' not in header
    assert "Decision Queue — evidence-ranked daily triage" in upgrade
