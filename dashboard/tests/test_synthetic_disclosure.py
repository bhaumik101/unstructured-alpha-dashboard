"""Synthetic-data disclosure is a data-correctness control, tested as one.

When no FRED/EIA key is configured or a live fetch fails, signals fall back to
synthetic placeholder series (utils/fetchers._synthetic_signal). Each carries an
`is_synthetic` flag through the signals cache. Any page that ranks, scores,
exports, or reasons over those values while presenting them as real is showing
fabricated data as live — the one failure this product's positioning cannot
survive, and one that is invisible in the output because a synthetic score looks
exactly like a real one.

Audit finding these tests lock in: five pages disclosed synthetic data; eight
score-consuming surfaces did not (Recommender, Today's Digest, Sector View,
Events, Portfolio Suite, home, AI Assistant, Export). The coverage test asserts
every active score-consuming page routes through the shared disclosure, so a new
page cannot quietly reintroduce the gap.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from utils.header import count_synthetic_signals

DASHBOARD = Path(__file__).resolve().parent.parent
PAGES = DASHBOARD / "pages"


# ── The counting helper ───────────────────────────────────────────────────────

def test_count_mixed_signals():
    signals = {
        "a": {"score": 60, "is_synthetic": True},
        "b": {"score": 40, "is_synthetic": False},
        "c": {"score": 55, "is_synthetic": True},
        "d": {"score": 50},  # missing flag == live
    }
    assert count_synthetic_signals(signals) == (2, 4)


def test_count_all_live():
    signals = {"a": {"is_synthetic": False}, "b": {}}
    assert count_synthetic_signals(signals) == (0, 2)


def test_count_all_synthetic():
    signals = {"a": {"is_synthetic": True}, "b": {"is_synthetic": True}}
    assert count_synthetic_signals(signals) == (2, 2)


def test_count_empty_is_safe():
    assert count_synthetic_signals({}) == (0, 0)
    assert count_synthetic_signals(None) == (0, 0)


def test_count_ignores_non_dict_values():
    """A malformed cache entry must not crash the disclosure path."""
    signals = {"a": {"is_synthetic": True}, "b": "oops", "c": None}
    assert count_synthetic_signals(signals) == (1, 3)


def test_banner_suppressed_when_nothing_synthetic(monkeypatch):
    """render_synthetic_data_banner must draw nothing at zero — a false alarm
    on an all-live page teaches users to ignore the real warning."""
    import utils.header as h

    calls = []
    monkeypatch.setattr(h.st, "markdown", lambda *a, **k: calls.append(a))
    h.render_synthetic_data_banner(0, 47)
    assert calls == []


def test_banner_renders_when_synthetic(monkeypatch):
    import utils.header as h

    calls = []
    monkeypatch.setattr(h.st, "markdown", lambda *a, **k: calls.append(a[0]))
    h.render_synthetic_data_banner(3, 47)
    assert calls, "banner should render when signals are synthetic"
    assert "3 of 47" in calls[0]
    assert "DEMO DATA" in calls[0]


def test_disclose_returns_count(monkeypatch):
    import utils.header as h

    monkeypatch.setattr(h.st, "markdown", lambda *a, **k: None)
    n = h.disclose_synthetic_signals({"a": {"is_synthetic": True}, "b": {}})
    assert n == 1


# ── Coverage: the audit finding, locked in ────────────────────────────────────

# Active pages that consume signal scores and therefore MUST disclose synthetic
# data. Retired pages (pages/retired/) are excluded — they are not routable.
SCORE_CONSUMING_PAGES = [
    "1_Signal_Dashboard.py",
    "2_Today_Digest.py",
    "3_Ticker_Deep_Dive.py",
    "4_Power_Supercycle.py",
    "5_Market_Overview.py",
    "6_Stock_Screener.py",
    "9_AI_Assistant.py",
    "40_Stock_Recommender.py",
    "42_Sector_View.py",
    "43_Events_Forecasts.py",
    "44_Portfolio_Suite.py",
    "28_Export.py",
    "home_page.py",
]

_DISCLOSURE_MARKERS = (
    "disclose_synthetic_signals",
    "render_synthetic_data_banner",
)


@pytest.mark.parametrize("page", SCORE_CONSUMING_PAGES)
def test_score_consuming_page_discloses_synthetic_data(page):
    # The invariant is disclosure. Some pages call get_all_signal_scores()
    # directly; a couple source their signal set differently but still surface
    # readings, and those already call render_synthetic_data_banner. Either
    # disclosure marker satisfies the requirement.
    path = PAGES / page
    assert path.exists(), f"{page} not found — update this list if it was renamed"
    src = path.read_text(encoding="utf-8")
    assert any(m in src for m in _DISCLOSURE_MARKERS), (
        f"{page} surfaces signal readings but never discloses synthetic data. "
        "Call disclose_synthetic_signals(get_all_signal_scores()) near the top of "
        "the page, or the page can present fabricated readings as live."
    )


def test_no_new_score_consumer_slips_through():
    """Fail if any active page imports get_all_signal_scores but is neither
    listed nor disclosing — catches a brand-new page reintroducing the gap."""
    listed = set(SCORE_CONSUMING_PAGES)
    offenders = []
    for path in PAGES.glob("*.py"):
        if path.name in listed:
            continue
        src = path.read_text(encoding="utf-8")
        if "get_all_signal_scores" in src and not any(
            m in src for m in _DISCLOSURE_MARKERS
        ):
            offenders.append(path.name)
    assert not offenders, (
        "these active pages consume signal scores without disclosing synthetic "
        f"data (add disclosure and list them): {offenders}"
    )


# ── Export: the flag must travel with the file ────────────────────────────────

def test_export_pdf_embeds_synthetic_warning():
    """A banner on the web page is not enough for Export — the PDF leaves the
    app, so the warning must be written into the document itself."""
    src = (PAGES / "28_Export.py").read_text(encoding="utf-8")
    build = src[src.index("def build_pdf"):]
    assert "count_synthetic_signals(all_signals)" in build, (
        "build_pdf must compute the synthetic count so it can warn in-document"
    )
    assert "DEMO DATA" in build, "the PDF must carry a demo-data warning"


def test_export_preview_table_marks_source_per_row():
    """The on-page table a user can copy out must mark synthetic rows, not just
    show an aggregate banner above it."""
    src = (PAGES / "28_Export.py").read_text(encoding="utf-8")
    assert '"Source"' in src and "is_synthetic" in src, (
        "the export preview rows must include a per-row Source (Live/DEMO) column"
    )
