"""Home's large live-score bundle should use the read-only shared cache path."""

from __future__ import annotations

from pathlib import Path


_DASH = Path(__file__).resolve().parent.parent


def test_shared_signal_cache_reuses_identity_without_recomputing(monkeypatch):
    from utils import signals_cache

    calls: list[int] = []
    sentinel = {"signal": {"score": 73.0, "status": "bullish"}}

    def fake_scores(version: int = 1) -> dict:
        calls.append(version)
        return sentinel

    signals_cache.get_shared_signal_scores.clear()
    monkeypatch.setattr(signals_cache, "get_all_signal_scores", fake_scores)
    try:
        first = signals_cache.get_shared_signal_scores(9)
        second = signals_cache.get_shared_signal_scores(9)
    finally:
        signals_cache.get_shared_signal_scores.clear()

    assert first is sentinel
    assert second is sentinel
    assert calls == [9]


def test_home_uses_shared_scores_but_deeper_pages_keep_copy_isolation():
    home = (_DASH / "pages" / "home_page.py").read_text(encoding="utf-8")
    signal_dashboard = (
        _DASH / "pages" / "1_Signal_Dashboard.py"
    ).read_text(encoding="utf-8")

    assert "get_shared_signal_scores()" in home
    assert "get_all_signal_scores()" not in home
    assert "get_all_signal_scores()" in signal_dashboard
