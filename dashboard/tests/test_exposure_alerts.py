"""Investor Pro exposure alerts.

What must hold:
  * an alert fires when its reading crosses the line, once -- not every week
    it stays past -- and again only after it has come back;
  * a force with no reading this week is skipped and its state kept;
  * the email leads with the alert, gives the reading's range and evidence
    label, and its footer says why the person is getting it;
  * the weekly job emails a Pro user with alerts only when one fires, saves
    states only after a successful send, and never alerts a free user;
  * on the report, a Pro user can add and remove alerts.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, insert

from tests.test_redesign_pages import _page, synthetic_engine  # noqa: F401  (fixture)
from tests.test_exposure import HOLDINGS
from utils import exposure_alerts as xa


def _report(rates=None, oil=-0.2):
    readings = {"oil": {"impact": oil, "low": oil - 0.3, "high": oil + 0.3, "evidence": "indistinct",
                        "label": "Oil and energy"}}
    if rates is not None:
        readings["rates"] = {"impact": rates, "low": rates - 0.4, "high": rates + 0.4, "evidence": "clear",
                             "label": "Interest rates"}
    return {"status": "ok", "as_of": "2026-11-06", "portfolio": {"readings": readings}, "shifts": []}


ALERT = {"id": 1, "user_id": 7, "factor": "rates", "direction": "below", "threshold": -1.0, "last_state": 0}


def test_it_fires_on_the_crossing_not_every_week_it_stays_past():
    fired, states = xa.evaluate([ALERT], _report(rates=-1.3))
    assert [a["id"] for a in fired] == [1] and states == {1: True}
    fired, states = xa.evaluate([dict(ALERT, last_state=1)], _report(rates=-1.5))
    assert fired == [] and states == {1: True}                     # still past: quiet
    fired, states = xa.evaluate([dict(ALERT, last_state=1)], _report(rates=-0.6))
    assert fired == [] and states == {1: False}                    # came back
    fired, _ = xa.evaluate([dict(ALERT, last_state=0)], _report(rates=-1.1))
    assert len(fired) == 1                                          # crossed again
    above = dict(ALERT, direction="above", threshold=0.5)
    assert xa.evaluate([above], _report(rates=0.7))[0] and not xa.evaluate([above], _report(rates=0.5))[0]


def test_a_missing_reading_is_skipped_and_its_state_kept():
    fired, states = xa.evaluate([dict(ALERT, last_state=1)], _report(rates=None))
    assert fired == [] and states == {}


def test_the_alert_email_leads_with_the_alert_and_its_uncertainty():
    from utils.exposure_email import build_weekly_email
    fired, _ = xa.evaluate([ALERT], _report(rates=-1.3))
    mail = build_weekly_email("Your saved portfolio", _report(rates=-1.3), fired=fired, weekly=False)
    assert mail["subject"] == "Alert: Your saved portfolio: interest rates falls below −1.0%"
    html = mail["html"]
    assert html.index("Your alerts") < html.index("What changed")
    assert "the reading is now −1.3% (90% range −1.7% to −0.90%, Clear)" in html
    assert "an exposure alert you set on Investor Pro fired" in html
    assert "turned on the weekly summary" not in html
    plain = build_weekly_email("Your saved portfolio", _report(rates=-1.3))
    assert "Your alerts" not in plain["html"] and not plain["subject"].startswith("Alert")


@pytest.fixture
def alerts_db(monkeypatch, tmp_path):
    from utils import db
    engine = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    db.metadata.create_all(engine, tables=[db.users, db.exposure_alerts])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    return engine


def test_adding_listing_and_removing_alerts(alerts_db):
    assert xa.add_alert(7, "rates", "below", -1.0) == (True, "Alert added.")
    assert xa.add_alert(7, "gold", "below", -1.0)[0] is False            # core five only
    assert xa.add_alert(7, "rates", "sideways", -1.0)[0] is False
    assert xa.add_alert(7, "rates", "below", "x")[0] is False
    for _ in range(xa.MAX_ALERTS - 1):
        assert xa.add_alert(7, "oil", "above", 1.0)[0]
    assert xa.add_alert(7, "oil", "above", 2.0) == (False, f"Up to {xa.MAX_ALERTS} alerts.")
    mine = xa.list_alerts(7)
    assert len(mine) == xa.MAX_ALERTS and xa.list_alerts(8) == []
    assert xa.delete_alert(8, mine[0]["id"]) and len(xa.list_alerts(7)) == xa.MAX_ALERTS   # not yours
    assert xa.delete_alert(7, mine[0]["id"]) and len(xa.list_alerts(7)) == xa.MAX_ALERTS - 1
    assert xa.users_with_alerts() == [7]


def _job(monkeypatch, alerts_db, people, report, status=200):
    import cron.send_exposure_weekly as job
    from utils import db
    with alerts_db.begin() as conn:
        for uid, tier, weekly in people:
            conn.execute(insert(db.users).values(id=uid, email=f"u{uid}@example.com", password_hash="x",
                                                 created_at="2026-01-01", subscription_tier=tier,
                                                 email_verified=True, exposure_email_opted_in=weekly))
    sent = []

    class Resp:
        status_code = status

    import utils.email as email_mod
    monkeypatch.setattr(email_mod, "_post_resend_email", lambda **kw: sent.append(kw) or Resp())
    monkeypatch.setenv("RESEND_API_KEY", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr(job, "init_db", lambda: None)
    monkeypatch.setattr(job, "engine", alerts_db)
    monkeypatch.setattr(job, "get_default_holdings", lambda uid: [{"ticker": "XOM", "weight_pct": 100}])
    monkeypatch.setattr(job.ex, "build_live_report", lambda positions, max_holdings=0: report)
    return job, sent


def test_the_job_emails_a_pro_user_only_when_an_alert_fires(monkeypatch, alerts_db):
    job, sent = _job(monkeypatch, alerts_db, [(7, "pro", False), (8, "free", False)], _report(rates=-1.3))
    xa.add_alert(7, "rates", "below", -1.0)
    xa.add_alert(8, "rates", "below", -1.0)                  # a free user's alert never sends
    assert job.main() == 0
    assert [s["to_email"] for s in sent] == ["u7@example.com"]
    assert sent[0]["subject"].startswith("Alert: ")
    assert xa.list_alerts(7)[0]["last_state"] == 1
    sent.clear()
    assert job.main() == 0 and sent == []                    # still past next week: no email


def test_a_failed_send_does_not_mark_the_alert_as_sent(monkeypatch, alerts_db):
    job, sent = _job(monkeypatch, alerts_db, [(7, "pro", False)], _report(rates=-1.3), status=500)
    xa.add_alert(7, "rates", "below", -1.0)
    job.main()
    assert len(sent) == 1 and xa.list_alerts(7)[0]["last_state"] == 0   # fires again next week


def test_a_pro_user_adds_and_removes_an_alert_on_the_report(monkeypatch, synthetic_engine, alerts_db):  # noqa: F811
    user = {"id": 7, "email": "a@b.c"}
    at = _page(monkeypatch, "pages/60_Exposure_Report.py", user=user,
               state={"uar_holdings": HOLDINGS, "uar_name": "Test", "_tier_7": "pro"})
    assert not at.exception
    at.selectbox(key="uar_alert_dir").select("below").run()
    at.number_input(key="uar_alert_thr").set_value(-1.0).run()
    at.button(key="uar_alert_add").click().run()
    assert not at.exception
    mine = xa.list_alerts(7)
    assert len(mine) == 1 and mine[0]["direction"] == "below" and mine[0]["threshold"] == -1.0
    at.button(key=f"uar_alert_del_{mine[0]['id']}").click().run()
    assert not at.exception and xa.list_alerts(7) == []


def test_a_free_user_sees_what_pro_adds_and_no_controls(monkeypatch, synthetic_engine, alerts_db):  # noqa: F811
    at = _page(monkeypatch, "pages/60_Exposure_Report.py", user={"id": 8, "email": "b@b.c"},
               state={"uar_holdings": HOLDINGS, "uar_name": "Test"})
    assert not at.exception
    assert any("Investor Pro: get an email when an exposure crosses" in c.value for c in at.caption)
    assert not [b for b in at.button if b.key == "uar_alert_add"]
