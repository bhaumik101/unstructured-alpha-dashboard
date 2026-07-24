"""Real-data-only integrity controls and page coverage."""

from pathlib import Path

import pytest

from utils.header import count_unavailable_signals

DASHBOARD = Path(__file__).resolve().parent.parent
PAGES = DASHBOARD / "pages"


def test_count_mixed_availability():
    signals = {
        "a": {"score": 60, "unavailable": True},
        "b": {"score": 40, "error": True},
        "c": {"score": 55, "unavailable": False},
        "d": {"score": 50},
    }
    assert count_unavailable_signals(signals) == (2, 4)


def test_count_empty_and_malformed_is_safe():
    assert count_unavailable_signals({}) == (0, 0)
    assert count_unavailable_signals(None) == (0, 0)
    assert count_unavailable_signals({"a": "oops", "b": None}) == (0, 2)


def test_banner_suppressed_when_all_sources_available(monkeypatch):
    import utils.header as h
    calls = []
    monkeypatch.setattr(h.st, "markdown", lambda *a, **k: calls.append(a))
    h.render_data_unavailable_banner(0, 47)
    assert calls == []


def test_banner_minor_outage_is_calm_but_still_honest(monkeypatch):
    """A few signals down out of 47 gets the proportionate 'PARTIAL DATA' notice
    — still discloses the exact count, exclusion, and no-synthetic promise, but
    without the full-red alarm that caused disclosure fatigue on every load."""
    import utils.header as h
    calls = []
    monkeypatch.setattr(h.st, "markdown", lambda *a, **k: calls.append(a[0]))
    h.render_data_unavailable_banner(3, 47)
    assert "3 of 47" in calls[0]
    assert "PARTIAL DATA" in calls[0]
    assert "REAL DATA UNAVAILABLE" not in calls[0]     # not alarmist for 94% coverage
    assert "excluded" in calls[0]
    assert "No placeholder" in calls[0]


def test_banner_major_outage_escalates_to_loud_red(monkeypatch):
    """When a material share (>=15%) is unavailable, coverage really is
    compromised, so the loud 'REAL DATA UNAVAILABLE' treatment returns."""
    import utils.header as h
    calls = []
    monkeypatch.setattr(h.st, "markdown", lambda *a, **k: calls.append(a[0]))
    h.render_data_unavailable_banner(20, 47)
    assert "20 of 47" in calls[0]
    assert "REAL DATA UNAVAILABLE" in calls[0]
    assert "No placeholder" in calls[0]


def test_disclose_returns_excluded_count(monkeypatch):
    import utils.header as h
    monkeypatch.setattr(h.st, "markdown", lambda *a, **k: None)
    assert h.disclose_unavailable_signals({"a": {"error": True}, "b": {}}) == 1


SCORE_CONSUMING_PAGES = [
    "1_Signal_Dashboard.py", "2_Today_Digest.py", "3_Ticker_Deep_Dive.py",
    "4_Power_Supercycle.py", "5_Market_Overview.py", "6_Stock_Screener.py",
    "9_AI_Assistant.py", "40_Stock_Recommender.py", "42_Sector_View.py",
    "43_Events_Forecasts.py", "44_Portfolio_Suite.py", "28_Export.py",
    "home_page.py",
]
_MARKERS = ("disclose_unavailable_signals", "render_data_unavailable_banner")


@pytest.mark.parametrize("page", SCORE_CONSUMING_PAGES)
def test_score_consumer_discloses_real_data_availability(page):
    src = (PAGES / page).read_text(encoding="utf-8")
    assert any(marker in src for marker in _MARKERS)


def test_no_active_runtime_synthetic_generators():
    active_sources = [DASHBOARD / "utils" / "fetchers.py", *PAGES.glob("*.py")]
    forbidden = ("_synthetic_signal", "_synthetic_cot", "_synthetic_congress_trades")
    offenders = [p.name for p in active_sources if any(x in p.read_text(encoding="utf-8") for x in forbidden)]
    assert not offenders, f"runtime placeholder generators remain: {offenders}"


def test_export_pdf_embeds_availability_warning():
    src = (PAGES / "28_Export.py").read_text(encoding="utf-8")
    build = src[src.index("def build_pdf"):]
    assert "count_unavailable_signals(all_signals)" in build
    assert "REAL DATA UNAVAILABLE" in build
    assert "No placeholder observations" in build


def test_export_preview_only_contains_live_rows():
    src = (PAGES / "28_Export.py").read_text(encoding="utf-8")
    assert '"Source":   "Live"' in src
    assert 'if sv.get("error")' in src
