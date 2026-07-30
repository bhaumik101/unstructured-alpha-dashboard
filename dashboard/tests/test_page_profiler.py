"""Unit coverage for privacy-safe sequential page timing."""

from __future__ import annotations

from pathlib import Path

import pytest

from utils.performance import PageProfiler, get_latest_page_profile

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


def test_latest_process_profile_is_bounded_and_returned_as_a_copy():
    profiler = PageProfiler("copy-check")
    profiler.checkpoint("data")
    expected = profiler.finish("render")

    first = get_latest_page_profile("copy-check")
    assert first == expected
    first["phases"][0]["phase"] = "mutated"
    assert get_latest_page_profile("copy-check") == expected
    assert get_latest_page_profile("missing-page") is None


def test_home_and_admin_share_anonymous_timing_summary():
    home = (_DASH / "pages" / "home_page.py").read_text(encoding="utf-8")
    admin = (_DASH / "pages" / "38_Admin.py").read_text(encoding="utf-8")

    assert 'PageProfiler("home")' in home
    assert 'st.session_state["_ua_home_perf_last"]' in home
    assert 'st.session_state.get("_ua_home_perf_last")' in admin
    assert 'get_latest_page_profile("home")' in admin
    assert 'st.expander("Home render diagnostics"' in admin


def test_home_profiles_page_shell_components_separately():
    home = (_DASH / "pages" / "home_page.py").read_text(encoding="utf-8")

    header = home.index('render_header(')
    header_checkpoint = home.index('_home_perf.checkpoint("header")')
    theme = home.index('inject_all_css()', header_checkpoint)
    theme_checkpoint = home.index('_home_perf.checkpoint("theme_css")')
    sidebar = home.index('render_sidebar_base()', theme_checkpoint)
    sidebar_checkpoint = home.index('_home_perf.checkpoint("sidebar_base")')

    assert header < header_checkpoint < theme < theme_checkpoint < sidebar < sidebar_checkpoint
    assert '_home_perf.checkpoint("page_shell")' not in home
