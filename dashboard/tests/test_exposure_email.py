"""The weekly email must be worth receiving, and honest in weeks when nothing happened.

An emailed summary is the product's retention loop, which makes it the place
most likely to drift into manufactured urgency. These tests pin the opposite:
the subject line says plainly when nothing changed, the body never forecasts or
advises, it carries its own opt-out, and it is only ever sent to people who
asked for it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import exposure_email as em  # noqa: E402
from tests.test_exposure import _BANNED, _report  # noqa: E402

CRON = (_ROOT / "cron" / "send_exposure_weekly.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def report():
    r = _report()
    assert r["status"] == "ok"
    return r


def _visible(html: str) -> str:
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    # The required disclaimer is the one sanctioned use of these words: it says
    # the product is NOT these things. Everything else must still be clean.
    for allowed in (r"(?:is|are) not a forecast",
                    r"or a recommendation to buy, sell or hold any security",
                    r"does not guarantee future results"):
        text = re.sub(allowed, "", text)
    return text


def test_a_quiet_week_says_so_in_the_subject(report):
    for shift in report["shifts"]:
        shift["significant"] = False
    subject = em.subject_for("Test portfolio", report)
    assert subject == "Test portfolio: no measurable change this week"


def test_a_real_change_is_named_in_the_subject(report):
    changed = {**report, "shifts": [{"key": "rates", "label": "Interest rates", "significant": True,
                                     "sentence": "Interest rates sensitivity has been stronger."}]}
    assert em.subject_for("Test portfolio", changed) == (
        "Test portfolio: interest rates sensitivity changed"
    )


def test_the_body_leads_with_what_changed_then_shows_every_exposure(report):
    html = em.build_weekly_email("Test portfolio", report)["html"]
    assert html.index("What changed") < html.index("Current exposures")
    for reading in report["portfolio"]["readings"].values():
        assert reading["label"] in html
    assert "not a forecast" in html


def test_a_quiet_week_still_explains_itself_rather_than_inventing_news(report):
    quiet = {**report, "shifts": [{"key": "rates", "label": "Interest rates",
                                   "significant": False, "sentence": "no change"}]}
    html = em.build_weekly_email("Test portfolio", quiet)["html"]
    assert "No measurable change" in html
    assert "Most weeks look like this" in html


def test_every_email_carries_its_own_opt_out_and_disclaimer(report):
    html = em.build_weekly_email("Test portfolio", report)["html"]
    assert "Turn it off" in html
    assert "Nothing here is personalized" in html
    assert "does not guarantee future results" in html


def test_the_email_never_forecasts_or_advises(report):
    built = em.build_weekly_email("Test portfolio", report)
    for text in (built["subject"], _visible(built["html"])):
        match = _BANNED.search(text)
        assert not match, f"forward-looking or advisory language: {match.group(0)!r}"


def test_a_portfolio_name_cannot_inject_markup(report):
    html = em.build_weekly_email('<script>alert(1)</script>', report)["html"]
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ── the cron ────────────────────────────────────────────────────────────────

def test_only_verified_opted_in_accounts_are_emailed():
    assert "exposure_email_opted_in.is_(True)" in CRON
    assert "email_verified.is_(True)" in CRON


def test_one_send_per_user_per_week_however_often_it_runs():
    assert 'idempotency_key=f"exposure-weekly-{uid}-{week}"' in CRON
    assert '%G-W%V' in CRON


def test_an_unmeasurable_portfolio_is_skipped_rather_than_emailed_blank():
    block = CRON[CRON.index('if report.get("status") != "ok"'):]
    assert "skipped += 1" in block[:400]
    assert "continue" in block[:400]


def test_a_missing_mail_key_stops_the_run_instead_of_failing_silently():
    assert 'if not api_key:' in CRON
    assert "Nothing was sent." in CRON
    assert "return 2" in CRON


def test_a_missing_database_url_fails_loudly_instead_of_sending_nothing():
    """Without DATABASE_URL the app falls back to an empty local SQLite file.
    The job would find no opted-in users and exit 0 forever while sending
    nothing, which is the failure mode hardest to notice."""
    assert 'if not os.environ.get("DATABASE_URL")' in CRON
    assert "refusing to run against an" in CRON
    nowcast = (_ROOT / "cron" / "run_nowcast.py").read_text(encoding="utf-8")
    assert 'if not os.environ.get("DATABASE_URL")' in nowcast, (
        "the nowcast writes its write-once record to the same database"
    )
