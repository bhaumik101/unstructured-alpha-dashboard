"""Guards for the public marketing-site analytics beacon.

This is an unauthenticated write path into analytics_events reachable by anyone
on the internet. A metrics table that strangers can write arbitrary rows into is
worse than no metrics table, because the numbers still look plausible. Every
test here pins a rejection rule.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from seo.track_api import ALLOWED_EVENTS, ALLOWED_PAGES, MAX_BODY_BYTES, router

TOKEN = "test-ingest-token"
CLIENT_HEADERS = {
    "x-forwarded-for": "203.0.113.7",
    "user-agent": "Mozilla/5.0 (Macintosh)",
    "x-ua-track-token": TOKEN,
}


@pytest.fixture()
def client_and_writes(monkeypatch):
    monkeypatch.setenv("TRACK_INGEST_TOKEN", TOKEN)
    app = FastAPI()
    app.include_router(router)
    writes: list[dict] = []

    def _capture(**kwargs):
        writes.append(kwargs)

    with patch("seo.track_api._write_event", side_effect=_capture):
        yield TestClient(app), writes


def _post(client, payload, headers=None):
    return client.post(
        "/api/track",
        content=json.dumps(payload),
        headers={**CLIENT_HEADERS, **(headers or {})},
    )


def test_valid_landing_page_view_is_recorded(client_and_writes):
    client, writes = client_and_writes
    res = _post(client, {"event": "page_view", "page": "Landing"})

    assert res.status_code == 204
    assert len(writes) == 1
    assert writes[0]["event"] == "page_view"
    assert writes[0]["page"] == "Landing"
    assert writes[0]["visitor_id"]


def test_valid_app_open_records_bounded_action_and_ticker(client_and_writes):
    client, writes = client_and_writes
    res = _post(client, {
        "event": "app_opened", "page": "Landing",
        "action": "hero_ticker", "ticker": "nvda",
    })

    assert res.status_code == 204
    assert len(writes) == 1
    assert writes[0]["event"] == "app_opened"
    assert writes[0]["properties"] == {
        "page": "Landing", "site": "marketing",
        "action": "hero_ticker", "ticker": "NVDA",
    }


def test_app_open_rejects_unknown_action_and_drops_invalid_ticker(client_and_writes):
    client, writes = client_and_writes
    _post(client, {
        "event": "app_opened", "page": "Landing",
        "action": "invented_action", "ticker": "NVDA",
    })
    assert writes == []

    _post(client, {
        "event": "app_opened", "page": "Landing",
        "action": "hero_ticker", "ticker": "<script>",
    })
    assert len(writes) == 1
    assert "ticker" not in writes[0]["properties"]


def test_arbitrary_event_names_are_rejected(client_and_writes):
    """Anyone can call this, so only an allowlist may be written.

    Without it a stranger could inject 'checkout_completed' rows and silently
    corrupt revenue and conversion reporting.
    """
    client, writes = client_and_writes
    for evil in ["checkout_completed", "signup_completed", "'; DROP TABLE", ""]:
        assert _post(client, {"event": evil, "page": "Landing"}).status_code == 204
    assert writes == []


def test_unknown_page_label_is_normalised_not_stored_verbatim(client_and_writes):
    """The page dimension must not become an injection vector into admin views."""
    client, writes = client_and_writes
    _post(client, {"event": "page_view", "page": "<script>alert(1)</script>"})

    assert len(writes) == 1
    assert writes[0]["page"] == "Other"
    assert writes[0]["page"] in ALLOWED_PAGES


def test_bots_are_not_counted_as_visitors(client_and_writes):
    """Bot traffic would inflate the denominator and understate conversion.

    That denominator is the entire reason this endpoint exists, so bots are
    dropped rather than stored-and-filtered-later.
    """
    client, writes = client_and_writes
    res = _post(
        client,
        {"event": "page_view", "page": "Landing"},
        headers={"user-agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"},
    )

    assert res.status_code == 204
    assert writes == []


def test_forged_ip_without_the_token_is_rejected(client_and_writes):
    """The endpoint trusts x-forwarded-for, so that trust must be gated.

    Ungated, anyone could POST a different forged IP in a loop and manufacture
    unlimited unique visitors -- corrupting the precise number this endpoint
    exists to make trustworthy.
    """
    client, writes = client_and_writes
    for bad in [{}, {"x-ua-track-token": "wrong"}, {"x-ua-track-token": ""}]:
        res = client.post(
            "/api/track",
            content=json.dumps({"event": "page_view", "page": "Landing"}),
            headers={
                "x-forwarded-for": "198.51.100.1",
                "user-agent": "Mozilla/5.0 (Macintosh)",
                **bad,
            },
        )
        assert res.status_code == 204
    assert writes == []


def test_unset_token_fails_closed(monkeypatch):
    """No configured secret means accept nothing.

    An open write path that still returns 204 would quietly fill the table with
    forgeable rows; silently-wrong analytics is worse than none.
    """
    monkeypatch.delenv("TRACK_INGEST_TOKEN", raising=False)
    app = FastAPI()
    app.include_router(router)
    writes: list[dict] = []
    with patch("seo.track_api._write_event", side_effect=lambda **kw: writes.append(kw)):
        res = TestClient(app).post(
            "/api/track",
            content=json.dumps({"event": "page_view", "page": "Landing"}),
            headers=CLIENT_HEADERS,
        )
    assert res.status_code == 204
    assert writes == []


def test_request_without_a_client_address_is_not_stored(client_and_writes):
    """No address means no stable identity.

    Storing it anyway would add a page view that can never be attributed to a
    visitor -- exactly what makes ~80% of the historical table unusable.
    """
    client, writes = client_and_writes
    res = client.post(
        "/api/track",
        content=json.dumps({"event": "page_view", "page": "Landing"}),
        # Authenticated relay, but no forwarded address at all.
        headers={"user-agent": "Mozilla/5.0 (Macintosh)", "x-ua-track-token": TOKEN},
    )
    assert res.status_code == 204
    assert writes == []


def test_oversized_body_is_rejected(client_and_writes):
    client, writes = client_and_writes
    res = _post(
        client,
        {"event": "page_view", "page": "Landing", "junk": "x" * (MAX_BODY_BYTES + 100)},
    )
    assert res.status_code == 204
    assert writes == []


def test_malformed_body_never_errors(client_and_writes):
    """The beacon must never change what a visitor sees."""
    client, writes = client_and_writes
    for body in ["not json", "[]", "null", ""]:
        res = client.post("/api/track", content=body, headers=CLIENT_HEADERS)
        assert res.status_code == 204
    assert writes == []


def test_response_is_always_204_and_reveals_nothing(client_and_writes):
    """Identical responses for accepted and rejected events.

    A different status for a rejected event would let an anonymous caller probe
    the allowlist.
    """
    client, _ = client_and_writes
    accepted = _post(client, {"event": "page_view", "page": "Landing"})
    rejected = _post(client, {"event": "made_up_event", "page": "Landing"})

    assert accepted.status_code == rejected.status_code == 204
    assert accepted.content == rejected.content == b""


def test_landing_visitor_id_matches_the_app_for_the_same_person(client_and_writes):
    """The whole point: one person browsing both sites is ONE visitor.

    If the marketing site derived identity differently, the funnel would be two
    disconnected counts and conversion would still be uncomputable.
    """
    from utils.analytics import visitor_context

    client, writes = client_and_writes
    _post(client, {"event": "page_view", "page": "Landing"})

    from_app = visitor_context(
        headers={
            "x-forwarded-for": "203.0.113.7",
            "user-agent": "Mozilla/5.0 (Macintosh)",
        }
    )["visitor_id"]
    assert writes and writes[0]["visitor_id"] == from_app


def test_allowlists_stay_minimal():
    """Widening these is a deliberate decision, not an accident."""
    assert ALLOWED_EVENTS == {"page_view", "app_opened"}
    assert "Landing" in ALLOWED_PAGES and "Other" in ALLOWED_PAGES
