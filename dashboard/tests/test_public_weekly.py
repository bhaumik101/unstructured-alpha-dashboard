"""The weekly public email: sign-up, double opt-in, unsubscribe, the send.

What must hold:
  * nothing but the confirmation goes to an address until its owner confirms;
  * the sign-up endpoint answers the same whatever happened (no probing);
  * a link opened by a mail scanner (GET) never confirms or unsubscribes --
    only the button (POST) does, and one-click unsubscribe works;
  * each confirmed address gets each data week once; a failed send is
    retried; nobody subscribed means the library is not even loaded;
  * every weekly email says why it was sent and carries an unsubscribe link
    and List-Unsubscribe headers;
  * the sign-up box appears only where it fits, and only when sends can go out.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine

from utils import public_weekly as pw
from utils import subscribers as sb

T0 = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)


@pytest.fixture
def db(monkeypatch, tmp_path):
    from utils import db as dbm
    engine = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    dbm.metadata.create_all(engine, tables=[dbm.public_subscribers, dbm.users, dbm.exposure_alerts,
                                            dbm.stock_measurements, dbm.stock_exposures])
    monkeypatch.setattr(dbm, "engine", engine)
    monkeypatch.setattr(dbm, "IS_SQLITE", True)
    return engine


def _token(email):
    from utils import db as dbm
    with dbm.engine.connect() as c:
        return c.execute(dbm.public_subscribers.select().where(dbm.public_subscribers.c.email == email)
                         ).mappings().first()


# ── the list ────────────────────────────────────────────────────────────────

def test_sign_up_confirm_and_the_abuse_limits(db):
    sent = []
    send = lambda e, t: sent.append((e, t)) or True       # noqa: E731
    assert sb.subscribe("  Ann@Example.COM ", "Quiz", send, now=T0) == "sent"
    row = _token("ann@example.com")
    assert row["status"] == "pending" and sent == [("ann@example.com", row["token"])]
    assert sb.subscribe("ann@example.com", "Quiz", send, now=T0 + timedelta(minutes=5)) == "cooldown"
    assert sb.subscribe("ann@example.com", "Quiz", send, now=T0 + timedelta(minutes=11)) == "sent"
    token = _token("ann@example.com")["token"]
    assert token != row["token"]                                     # a fresh link each time
    assert sb.due("2026-11-13") == []                                # pending gets nothing
    assert sb.confirm(token) and sb.confirm(token)                   # idempotent
    assert sb.subscribe("ann@example.com", "Quiz", send, now=T0 + timedelta(hours=1)) == "already"
    assert len(sent) == 2
    for bad in ("", "nope", "a@b", "<x>@example.com", "a" * 250 + "@example.com"):
        assert sb.subscribe(bad, "Quiz", send, now=T0) == "invalid"
    assert sb.confirm("not-a-token") is False and sb.confirm("") is False


def test_a_daily_cap_across_everyone(db, monkeypatch):
    monkeypatch.setattr(sb, "DAILY_CAP", 3)
    outs = [sb.subscribe(f"p{i}@example.com", "", lambda e, t: True, now=T0) for i in range(5)]
    assert outs == ["sent", "sent", "sent", "capped", "capped"]


def test_unsubscribe_is_final_until_signing_up_again(db):
    sb.subscribe("bo@example.com", "", lambda e, t: True, now=T0)
    t = _token("bo@example.com")["token"]
    sb.confirm(t)
    assert sb.due("2026-11-13") == [("bo@example.com", t)]
    assert sb.unsubscribe(t) and sb.due("2026-11-13") == []
    assert sb.confirm(t) is False                                    # an old link cannot re-subscribe
    assert sb.subscribe("bo@example.com", "", lambda e, t: True, now=T0) == "sent"
    assert _token("bo@example.com")["status"] == "pending"


# ── the endpoints ───────────────────────────────────────────────────────────

@pytest.fixture
def client(db, monkeypatch):
    from fastapi.testclient import TestClient
    import seo.main as M
    monkeypatch.setattr(M, "_get_engine", lambda: (db, None, None))
    monkeypatch.setattr(M, "_exposure_cache", {})
    monkeypatch.setenv("RESEND_API_KEY", "test")
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)
    sent = []
    monkeypatch.setattr(pw, "send_confirmation", lambda base, e, t, post=None: sent.append((e, t)) or True)
    return TestClient(M.app), sent


def test_the_endpoint_answers_the_same_whatever_happened(client):
    c, sent = client
    answers = {c.post("/api/subscribe", json={"email": e, "source": "Quiz"}).text
               for e in ("cy@example.com", "cy@example.com", "not-an-email", "")}
    assert answers == {'{"ok":true}'}
    assert [e for e, _ in sent] == ["cy@example.com"]                # one confirmation, after the response
    assert c.post("/api/subscribe", content=b"x" * 5000).text == '{"ok":true}'


def test_a_scanner_opening_the_links_changes_nothing_only_the_button_does(client):
    c, sent = client
    c.post("/api/subscribe", json={"email": "di@example.com", "source": "Quiz"})
    t = sent[0][1]
    page = c.get(f"/subscribe/confirm?t={t}")
    assert page.status_code == 200 and "noindex" in page.text and f'value="{t}"' in page.text
    assert _token("di@example.com")["status"] == "pending"           # GET did not confirm
    assert "You are subscribed" in c.post("/subscribe/confirm", data={"t": t}).text
    assert _token("di@example.com")["status"] == "confirmed"
    c.get(f"/unsubscribe?t={t}")
    assert _token("di@example.com")["status"] == "confirmed"         # GET did not unsubscribe
    assert "You are unsubscribed" in c.post(f"/unsubscribe?t={t}").text   # RFC 8058 one-click
    assert _token("di@example.com")["status"] == "unsubscribed"
    assert "did not work" in c.post("/subscribe/confirm", data={"t": "bogus"}).text


def test_without_a_key_there_is_no_sign_up_at_all(client, monkeypatch):
    c, _ = client
    monkeypatch.delenv("RESEND_API_KEY")
    assert c.post("/api/subscribe", json={"email": "ed@example.com"}).status_code == 503
    assert pw.signup_html("Quiz") == ""


def test_the_box_shows_only_where_it_fits(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test")
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)
    assert 'id="wk-form" data-source="Quiz"' in pw.signup_html("Quiz")
    assert pw.signup_html("Stock page") == "" and pw.signup_html(None) == ""
    monkeypatch.setenv("RESEND_FROM_EMAIL", "X <onboarding@resend.dev>")
    assert pw.signup_html("Quiz") == ""                              # owner-only test sender: off


# ── the emails and the send ─────────────────────────────────────────────────

def _e(impact, ev):
    return {"impact": impact, "low": impact - 0.5, "high": impact + 0.5, "evidence": ev}


CHANGES = {"as_of": "2026-11-13", "compared": 540,
           "gained": [{"ticker": "XOM", "name": "Exxon Mobil", "key": "oil", "now": _e(2.4, "clear"),
                       "before": _e(1.0, "indistinct"), "before_as_of": "2026-11-06"}],
           "lost": [], "shifts": []}


def test_the_weekly_email_says_why_and_carries_an_unsubscribe(monkeypatch):
    mail = pw.weekly_email("https://www.x", CHANGES, "tok123")
    assert mail["subject"] == "This week: 1 links started holding up, 0 stopped (data through Nov 13, 2026)"
    h = mail["html"]
    assert 'href="https://www.x/exposure/XOM"' in h and "90% range" in h and "clear" in h.lower()
    assert "because you confirmed the weekly email" in h and "not a forecast" in h
    assert 'href="https://www.x/unsubscribe?t=tok123"' in h
    for word in ("buy", "sell", "should", "recommend"):
        assert word not in h.lower().replace("not a forecast or investment advice", "")
    posted = []
    monkeypatch.setenv("RESEND_API_KEY", "k")
    pw._post("a@b.co", mail, "public_weekly", "key", post=lambda url, json, timeout, headers:
             posted.append(json) or type("R", (), {"status_code": 200})())
    assert posted[0]["headers"] == {"List-Unsubscribe": "<https://www.x/unsubscribe?t=tok123>",
                                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    assert posted[0]["from"].endswith("@unstructuredalpha.com>")


def test_each_address_gets_each_week_once_and_failures_retry(db, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "k")
    import utils.changes_page as cp
    monkeypatch.setattr(cp, "changes", lambda latest, prev: CHANGES)
    for e in ("ok@example.com", "bad@example.com", "pend@example.com"):
        sb.subscribe(e, "", lambda *_: True, now=T0)
    sb.confirm(_token("ok@example.com")["token"])
    sb.confirm(_token("bad@example.com")["token"])
    to = []

    def post(url, json, timeout, headers):
        to.append(json["to"][0])
        return type("R", (), {"status_code": 500 if json["to"][0] == "bad@example.com" else 200})()
    assert pw.run("https://www.x", lambda: [], lambda: [], post=post) == 1
    assert sorted(to) == ["bad@example.com", "ok@example.com"]       # never the pending address
    to.clear()
    assert pw.run("https://www.x", lambda: [], lambda: [], post=post) == 1
    assert to == ["bad@example.com"]                                  # sent once; the failure retried


def test_nobody_confirmed_means_the_library_is_not_loaded(db, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "k")
    boom = lambda: (_ for _ in ()).throw(AssertionError("library loaded"))   # noqa: E731
    assert pw.run("https://www.x", boom, boom) == 0


def test_the_weekly_job_runs_the_public_email_even_with_no_portfolio_recipients(db, monkeypatch):
    import cron.send_exposure_weekly as job
    calls = []
    monkeypatch.setenv("RESEND_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr(job, "init_db", lambda: None)
    monkeypatch.setattr(job, "engine", db)
    monkeypatch.setattr(pw, "run", lambda *a, **k: calls.append(a) or 0)
    assert job.main() == 0 and len(calls) == 1


def test_a_failed_portfolio_send_does_not_skip_the_public_email(db, monkeypatch):
    import cron.send_exposure_weekly as job
    calls = []
    monkeypatch.setenv("RESEND_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr(job, "init_db", lambda: None)
    monkeypatch.setattr(job, "_portfolio_emails", lambda key: 1)
    monkeypatch.setattr(pw, "run", lambda *a, **k: calls.append(a) or 0)
    assert job.main() == 1 and len(calls) == 1
