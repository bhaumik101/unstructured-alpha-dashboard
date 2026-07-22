"""Security, ownership, rate-limit, and data-integrity tests for the Pro API."""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete

from seo.pro_api import router as pro_api_router
from utils import db
from utils.api_access import (
    authenticate_api_key,
    create_api_key,
    list_api_keys,
    revoke_api_key,
)


PRO_USER = 9601
OTHER_USER = 9602
FREE_USER = 9603
TEST_TICKER = "ZZAPI"

seo_app = FastAPI()
seo_app.include_router(pro_api_router)


@pytest.fixture(autouse=True)
def _api_state():
    db.init_db()
    with db.engine.begin() as conn:
        conn.execute(delete(db.api_keys).where(db.api_keys.c.user_id.in_((PRO_USER, OTHER_USER, FREE_USER))))
        conn.execute(delete(db.score_snapshots).where(db.score_snapshots.c.ticker.in_((TEST_TICKER, "ZZMISS"))))
        conn.execute(delete(db.users).where(db.users.c.id.in_((PRO_USER, OTHER_USER, FREE_USER))))
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(db.users.insert(), [
            {
                "id": PRO_USER,
                "email": "api-pro@example.com",
                "password_hash": "test",
                "created_at": now,
                "email_verified": True,
                "subscription_tier": "pro",
            },
            {
                "id": OTHER_USER,
                "email": "api-other@example.com",
                "password_hash": "test",
                "created_at": now,
                "email_verified": True,
                "subscription_tier": "pro",
            },
            {
                "id": FREE_USER,
                "email": "api-free@example.com",
                "password_hash": "test",
                "created_at": now,
                "email_verified": True,
                "subscription_tier": "free",
            },
        ])
        conn.execute(db.score_snapshots.insert().values(
            ticker=TEST_TICKER,
            snapshot_date="2026-07-22",
            score=72.4,
            case="BULL",
            conviction="high",
            score_kind="full",
            created_at=now,
        ))
    yield
    with db.engine.begin() as conn:
        conn.execute(delete(db.api_keys).where(db.api_keys.c.user_id.in_((PRO_USER, OTHER_USER, FREE_USER))))
        conn.execute(delete(db.score_snapshots).where(db.score_snapshots.c.ticker.in_((TEST_TICKER, "ZZMISS"))))
        conn.execute(delete(db.users).where(db.users.c.id.in_((PRO_USER, OTHER_USER, FREE_USER))))


def test_raw_key_is_returned_once_but_only_safe_metadata_is_listed():
    created = create_api_key(PRO_USER, "Research notebook")

    assert created["raw_key"].startswith("ua_live_")
    assert authenticate_api_key(created["raw_key"])["user_id"] == PRO_USER
    listed = list_api_keys(PRO_USER)
    assert len(listed) == 1
    assert "raw_key" not in listed[0]
    assert "key_hash" not in listed[0]
    assert created["raw_key"] not in repr(listed)


def test_key_ownership_revocation_and_pro_entitlement_are_enforced():
    created = create_api_key(PRO_USER, "Primary")
    assert revoke_api_key(OTHER_USER, created["id"]) is False
    assert authenticate_api_key(created["raw_key"]) is not None
    assert revoke_api_key(PRO_USER, created["id"]) is True
    assert authenticate_api_key(created["raw_key"]) is None
    with pytest.raises(PermissionError):
        create_api_key(FREE_USER, "Not allowed")


def test_active_key_limit_and_unique_names_are_bounded():
    create_api_key(PRO_USER, "Key one")
    with pytest.raises(ValueError, match="unique name"):
        create_api_key(PRO_USER, "key one")
    create_api_key(PRO_USER, "Key two")
    create_api_key(PRO_USER, "Key three")
    with pytest.raises(ValueError, match="up to 3"):
        create_api_key(PRO_USER, "Key four")


def test_score_api_requires_auth_and_returns_persisted_real_snapshot(monkeypatch):
    monkeypatch.setattr("utils.ratelimit.check", lambda key, limit, window: (True, 0))
    client = TestClient(seo_app)
    assert client.get(f"/api/v1/scores/{TEST_TICKER}").status_code == 401

    created = create_api_key(PRO_USER, "API test")
    headers = {"Authorization": f'Bearer {created["raw_key"]}'}
    response = client.get(f"/api/v1/scores/{TEST_TICKER}", headers=headers)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-ratelimit-limit"] == "120"
    assert response.json()["data"] == {
        "ticker": TEST_TICKER,
        "score": 72.4,
        "case": "BULL",
        "conviction": "high",
        "score_kind": "full",
        "as_of": "2026-07-22",
        "source": "persisted_score_snapshot",
    }
    assert "estimation" in response.json()["data_policy"]


def test_batch_api_discloses_missing_and_rate_limit(monkeypatch):
    created = create_api_key(PRO_USER, "Batch test")
    headers = {"Authorization": f'Bearer {created["raw_key"]}'}
    client = TestClient(seo_app)
    monkeypatch.setattr("utils.ratelimit.check", lambda key, limit, window: (True, 0))
    response = client.get(
        f"/api/v1/scores?tickers={TEST_TICKER},ZZMISS", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["missing"] == ["ZZMISS"]

    monkeypatch.setattr("utils.ratelimit.check", lambda key, limit, window: (False, 90))
    limited = client.get(f"/api/v1/scores/{TEST_TICKER}", headers=headers)
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "90"
