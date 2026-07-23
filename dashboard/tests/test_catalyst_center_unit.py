"""Catalyst calendar integrity, portfolio ranking, and private-plan tests."""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete

from utils import catalyst_center, db
from utils.catalyst_center import (
    build_catalyst_digest_items,
    build_portfolio_catalysts,
    get_catalyst_plan,
    list_catalyst_plans,
    parse_fred_release_calendar,
    save_catalyst_plan,
)


USER_A = 9801
USER_B = 9802


@pytest.fixture(autouse=True)
def _plans():
    db.init_db()
    now = datetime.now(timezone.utc).isoformat()
    with db.engine.begin() as conn:
        conn.execute(delete(db.catalyst_plans).where(db.catalyst_plans.c.user_id.in_((USER_A, USER_B))))
        conn.execute(delete(db.users).where(db.users.c.id.in_((USER_A, USER_B))))
        conn.execute(db.users.insert(), [
            {"id": USER_A, "email": "catalyst-a@example.com", "password_hash": "test", "created_at": now,
             "email_verified": True, "subscription_tier": "pro"},
            {"id": USER_B, "email": "catalyst-b@example.com", "password_hash": "test", "created_at": now,
             "email_verified": True, "subscription_tier": "pro"},
        ])
    yield
    with db.engine.begin() as conn:
        conn.execute(delete(db.catalyst_plans).where(db.catalyst_plans.c.user_id.in_((USER_A, USER_B))))
        conn.execute(delete(db.users).where(db.users.c.id.in_((USER_A, USER_B))))


def test_parser_keeps_only_verified_mapped_dates_and_deduplicates():
    payload = {"release_dates": [
        {"release_id": 10, "release_name": "Consumer Price Index", "date": "2026-08-12"},
        {"release_id": 10, "release_name": "Consumer Price Index", "date": "2026-08-12"},
        {"release_id": 11, "release_name": "Employment Situation", "date": "2026-08-07"},
        {"release_id": 12, "release_name": "Unknown Weekly Feed", "date": "2026-08-10"},
        {"release_id": 13, "release_name": "Gross Domestic Product", "date": "2027-01-01"},
    ]}
    rows = parse_fred_release_calendar(payload, start=date(2026, 8, 1), end=date(2026, 8, 31))
    assert [row["title"] for row in rows] == ["Employment Situation", "Consumer Price Index"]
    assert all(row["source"] == "FRED release calendar" for row in rows)
    assert len({row["event_key"] for row in rows}) == 2


def test_fred_request_explicitly_includes_future_dates(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"release_dates": []}

    def fake_get(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr(catalyst_center, "resilient_get", fake_get)
    fetch = getattr(catalyst_center.fetch_fred_release_calendar, "__wrapped__", catalyst_center.fetch_fred_release_calendar)
    result = fetch("2026-08-01", "2026-09-01", "fred-key")
    assert result["available"] is True
    assert captured["url"] == catalyst_center.FRED_RELEASE_DATES_URL
    assert captured["params"]["include_release_dates_with_no_data"] == "true"
    assert captured["params"]["realtime_start"] == "2026-08-01"
    assert captured["params"]["realtime_end"] == "2026-09-01"


def test_portfolio_catalysts_rank_weighted_near_events_without_inventing_any():
    macro = [{
        "event_key": "macro:10:2026-08-12", "event_type": "macro", "date": date(2026, 8, 12),
        "date_str": "2026-08-12", "title": "Consumer Price Index", "official_name": "CPI",
        "category": "Inflation", "signals": ["ten_year_yield"], "source": "FRED", "source_url": "",
    }]
    rows = build_portfolio_catalysts(
        [{"ticker": "AAA", "weight_pct": 70}, {"ticker": "BBB", "weight_pct": 30}],
        macro,
        {"AAA": {"date": date(2026, 8, 3), "is_estimate": True}, "BBB": None},
        {"AAA": ["ten_year_yield"], "BBB": []},
        today=date(2026, 8, 1),
    )
    assert [row["event_type"] for row in rows] == ["earnings", "macro"]
    assert rows[0]["affected_weight"] == 70
    assert rows[0]["is_estimate"] is True
    assert build_portfolio_catalysts([], [], {}, {}, today=date(2026, 8, 1)) == []


def test_private_plans_are_user_scoped_and_update_in_place():
    save_catalyst_plan(
        user_id=USER_A, event_key="macro:10:2026-08-12", event_date="2026-08-12",
        title="Consumer Price Index", base_case="First line\nSecond line", watch_for="Core CPI",
    )
    assert get_catalyst_plan(USER_B, "macro:10:2026-08-12") is None
    saved = get_catalyst_plan(USER_A, "macro:10:2026-08-12")
    assert saved["base_case"] == "First line\nSecond line"

    save_catalyst_plan(
        user_id=USER_A, event_key="macro:10:2026-08-12", event_date="2026-08-12",
        title="Consumer Price Index", base_case=saved["base_case"], watch_for="Core CPI",
        status="reviewed", outcome_notes="Print reviewed",
    )
    assert len(list_catalyst_plans(USER_A)) == 1
    assert get_catalyst_plan(USER_A, "macro:10:2026-08-12")["status"] == "reviewed"
    assert list_catalyst_plans(USER_B) == []


def test_digest_selects_near_events_and_recent_overdue_reviews():
    catalysts = [
        {
            "event_key": "earnings:AAA:2026-08-03", "event_type": "earnings",
            "date": date(2026, 8, 3), "date_str": "2026-08-03", "title": "AAA Earnings",
            "days_until": 2, "affected_weight": 45.0, "affected_tickers": ["AAA"],
            "is_estimate": True, "priority": 118,
        },
        {
            "event_key": "macro:10:2026-08-20", "event_type": "macro",
            "date": date(2026, 8, 20), "date_str": "2026-08-20", "title": "CPI",
            "days_until": 19, "affected_weight": 80.0, "affected_tickers": ["AAA", "BBB"],
            "is_estimate": False, "priority": 90,
        },
    ]
    plans = [
        {"event_key": "earnings:AAA:2026-08-03", "event_date": "2026-08-03", "title": "AAA Earnings",
         "status": "planned", "watch_for": "Guidance"},
        {"event_key": "macro:9:2026-07-30", "event_date": "2026-07-30", "title": "GDP",
         "status": "planned", "watch_for": "Consumption"},
        {"event_key": "macro:8:2026-07-01", "event_date": "2026-07-01", "title": "Old event",
         "status": "planned", "watch_for": "Too old"},
    ]

    items = build_catalyst_digest_items(catalysts, plans, today=date(2026, 8, 1))

    assert [item["delivery_type"] for item in items] == ["review_due", "upcoming"]
    assert items[0]["days_overdue"] == 2
    assert items[1]["plan_saved"] is True
    assert items[1]["watch_for"] == "Guidance"
    assert all(item["title"] not in {"CPI", "Old event"} for item in items)


def test_page_has_no_hardcoded_event_schedule_and_navigation_is_upgraded():
    root = Path(__file__).resolve().parents[1]
    page = (root / "pages" / "43_Events_Forecasts.py").read_text()
    app = (root / "app.py").read_text()
    header = (root / "utils" / "header.py").read_text()
    assert "EVENTS = [" not in page
    assert "include_release_dates_with_no_data" in (root / "utils" / "catalyst_center.py").read_text()
    assert 'title="Catalyst Command Center"' in app
    assert ">Catalyst Command Center</a>" in header
