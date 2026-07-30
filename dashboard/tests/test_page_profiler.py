"""Unit coverage for privacy-safe sequential page timing."""

from __future__ import annotations

from pathlib import Path

import pytest

from utils.performance import PageProfiler

_DASH = Path(__file__).resolve().parent.parent


def test_page_profiler_returns_serializable_sequential_summary():
    profiler = PageProfiler("home")
    first = profiler.checkpoint("data")
    summary = profiler.finish("render")

    assert first["phase"] == "data"
    assert first["duration_ms"] >= 0
    assert summary["page"] == "home"
    assert summary["total_ms"] >= 0
    assert summary["slowest_phase"] in {"data", "render"}
    assert [phase["phase"] for phase in summary["phases"]] == ["data", "render"]
    assert all(set(phase) == {"phase", "duration_ms", "success"} for phase in summary["phases"])


def test_page_profiler_cannot_be_reused_after_finish():
    profiler = PageProfiler("home")
    profiler.finish()

    with pytest.raises(RuntimeError):
        profiler.checkpoint("late")
    with pytest.raises(RuntimeError):
        profiler.finish()


def test_home_and_admin_share_only_session_local_timing_summary():
    home = (_DASH / "pages" / "home_page.py").read_text(encoding="utf-8")
    admin = (_DASH / "pages" / "38_Admin.py").read_text(encoding="utf-8")

    assert 'PageProfiler("home")' in home
    assert 'st.session_state["_ua_home_perf_last"]' in home
    assert 'st.session_state.get("_ua_home_perf_last")' in admin
    assert "Home render diagnostics (this session)" in admin
