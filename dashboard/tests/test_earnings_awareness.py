"""Tests for utils.earnings_awareness — event-risk context on a macro score."""
from datetime import date, timedelta

from utils import earnings_awareness as ea


# ── risk classification ──────────────────────────────────────────────────────
def test_risk_bands():
    assert ea.classify_risk(0) == ea.RISK_TODAY
    assert ea.classify_risk(1) == ea.RISK_IMMINENT
    assert ea.classify_risk(ea.IMMINENT_DAYS) == ea.RISK_IMMINENT
    assert ea.classify_risk(ea.IMMINENT_DAYS + 1) == ea.RISK_NEAR
    assert ea.classify_risk(ea.NEAR_DAYS) == ea.RISK_NEAR
    assert ea.classify_risk(ea.NEAR_DAYS + 1) == ea.RISK_NONE


def test_risk_handles_none_and_past():
    assert ea.classify_risk(None) == ea.RISK_NONE
    assert ea.classify_risk(-5) == ea.RISK_NONE


def test_labels_read_naturally():
    assert ea.risk_label(0) == "Reports today"
    assert ea.risk_label(1) == "Reports tomorrow"
    assert "2d" in ea.risk_label(2)
    assert ea.risk_label(60) == ""


def test_caveat_only_when_relevant():
    assert ea.caveat_text(1)
    assert ea.caveat_text(5)
    assert ea.caveat_text(60) == ""
    assert ea.caveat_text(None) == ""


# ── badge rendering ──────────────────────────────────────────────────────────
def test_badge_empty_when_nothing_to_say():
    assert ea.badge_html(None) == ""
    assert ea.badge_html({"risk": ea.RISK_NONE}) == ""


def test_badge_renders_and_marks_estimate():
    info = {"risk": ea.RISK_IMMINENT, "label": "Reports in 2d",
            "date": date(2026, 8, 1), "is_estimate": True}
    html = ea.badge_html(info)
    assert "Reports in 2d" in html and "⚠" in html
    assert "est." in html, "provisional dates must be marked as estimates"


# ── next_earnings selection logic ────────────────────────────────────────────
def _patch_rows(monkeypatch, rows):
    import utils.fetchers as f
    monkeypatch.setattr(f, "fetch_earnings_dates", lambda t: rows, raising=False)


def test_next_earnings_picks_soonest_unreported(monkeypatch):
    today = ea._today()
    _patch_rows(monkeypatch, [
        {"date": today + timedelta(days=14), "reported": False},
        {"date": today + timedelta(days=3),  "reported": False},   # soonest
        {"date": today - timedelta(days=30), "reported": True},
    ])
    info = ea.next_earnings("AAPL")
    assert info and info["days_until"] == 3
    assert info["risk"] == ea.RISK_IMMINENT


def test_next_earnings_ignores_already_reported(monkeypatch):
    today = ea._today()
    _patch_rows(monkeypatch, [{"date": today + timedelta(days=2), "reported": True}])
    assert ea.next_earnings("AAPL") is None


def test_next_earnings_ignores_beyond_lookahead(monkeypatch):
    today = ea._today()
    _patch_rows(monkeypatch, [{"date": today + timedelta(days=90), "reported": False}])
    assert ea.next_earnings("AAPL") is None


def test_next_earnings_none_when_no_data(monkeypatch):
    _patch_rows(monkeypatch, [])
    assert ea.next_earnings("AAPL") is None


def test_next_earnings_degrades_on_fetch_error(monkeypatch):
    import utils.fetchers as f

    def _boom(_t):
        raise RuntimeError("provider down")

    monkeypatch.setattr(f, "fetch_earnings_dates", _boom, raising=False)
    # A provider failure must produce NO warning, never a wrong warning.
    assert ea.next_earnings("AAPL") is None


def test_next_earnings_skips_malformed_rows(monkeypatch):
    today = ea._today()
    _patch_rows(monkeypatch, [
        {"date": None, "reported": False},
        {"reported": False},
        {"date": "not-a-date", "reported": False},
        {"date": today + timedelta(days=5), "reported": False},
    ])
    info = ea.next_earnings("AAPL")
    assert info and info["days_until"] == 5
