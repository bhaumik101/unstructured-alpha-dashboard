"""Privacy and regression coverage for cross-session visitor analytics."""

from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from utils import analytics, db


DESKTOP_CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
)
DESKTOP_SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15"
)
MOBILE_SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
)


def test_visitor_id_is_stable_across_sessions_and_browsers(monkeypatch):
    monkeypatch.setenv("ANALYTICS_HASH_SALT", "test-only-secret")
    chrome = analytics.visitor_context(headers={
        "X-Forwarded-For": "203.0.113.18, 10.0.0.4",
        "User-Agent": DESKTOP_CHROME,
    })
    safari = analytics.visitor_context(headers={
        "x-forwarded-for": "203.0.113.18",
        "user-agent": DESKTOP_SAFARI,
    })

    assert chrome["visitor_id"] == safari["visitor_id"]
    assert chrome["device_type"] == "desktop"
    assert len(chrome["visitor_id"]) == 32
    assert "203.0.113.18" not in repr(chrome)


def test_same_network_different_device_class_is_distinct(monkeypatch):
    monkeypatch.setenv("ANALYTICS_HASH_SALT", "test-only-secret")
    desktop = analytics.visitor_context(headers={
        "x-forwarded-for": "203.0.113.18",
        "user-agent": DESKTOP_CHROME,
    })
    mobile = analytics.visitor_context(headers={
        "x-forwarded-for": "203.0.113.18",
        "user-agent": MOBILE_SAFARI,
    })

    assert desktop["visitor_id"] != mobile["visitor_id"]
    assert mobile["device_type"] == "mobile"


def test_anonymous_without_network_address_remains_unidentified(monkeypatch):
    monkeypatch.setenv("ANALYTICS_HASH_SALT", "test-only-secret")
    context = analytics.visitor_context(headers={"user-agent": DESKTOP_CHROME})
    assert context == {"visitor_id": None, "device_type": "desktop"}


def test_signed_in_fallback_is_stable_without_network_address(monkeypatch):
    monkeypatch.setenv("ANALYTICS_HASH_SALT", "test-only-secret")
    first = analytics.visitor_context(
        user_id=42, headers={"user-agent": DESKTOP_CHROME}
    )
    second = analytics.visitor_context(
        user_id=42, headers={"user-agent": DESKTOP_SAFARI}
    )
    assert first["visitor_id"] == second["visitor_id"]


def test_analytics_migration_adds_visitor_columns_and_indexes(tmp_path, monkeypatch):
    old_db = Path(tmp_path) / "old-analytics.db"
    old_engine = create_engine(f"sqlite:///{old_db}")
    with old_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE analytics_events ("
            "id INTEGER PRIMARY KEY, event_name TEXT NOT NULL, user_id INTEGER, "
            "session_id TEXT, properties TEXT, created_at TEXT NOT NULL)"
        ))

    monkeypatch.setattr(db, "engine", old_engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    db._migrate_analytics_events_table()
    db._migrate_analytics_events_table()  # idempotent on every app boot

    inspector = inspect(old_engine)
    columns = {column["name"] for column in inspector.get_columns("analytics_events")}
    indexes = {index["name"] for index in inspector.get_indexes("analytics_events")}
    assert {"visitor_id", "device_type"} <= columns
    assert {
        "ix_analytics_events_visitor_id",
        "ix_analytics_events_event_created",
    } <= indexes


def test_admin_uses_visitor_identity_not_sessions_for_uniques():
    admin_source = Path("pages/38_Admin.py").read_text(encoding="utf-8")
    assert "COUNT(DISTINCT session_id)" not in admin_source
    assert "SELECT visitor_id, session_id" in admin_source
    assert "Identity Coverage (30d)" in admin_source
    assert "Page Performance (30d)" in admin_source
