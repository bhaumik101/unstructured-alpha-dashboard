"""Memory-budget accounting on the scoring cron.

WHY THIS EXISTS. score-core now reaches 100% coverage with --passes 6, but
score-rest still stops with remaining=525 and stop_reason=memory, and the logs
could not say WHERE the 390MB went. That distinction decides real money: if the
import baseline already consumes most of the budget, extra passes buy almost
nothing (each fresh subprocess re-pays the baseline) and the instance has to
grow instead. So the run must report its own budget breakdown, and -- the part
these tests actually guard -- an UNREADABLE measurement must never be rendered
as a healthy one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cron.score_universe import _headroom, _rss_mb        # noqa: E402


class TestHeadroom:
    def test_reports_working_room_above_startup_cost(self):
        assert _headroom(268.4, 390) == 121.6

    def test_unreadable_rss_is_unknown_not_full_budget(self):
        # The bug this forbids: _rss_mb() fails, returns 0.0, and `limit - 0`
        # reports 390MB of headroom for a process we cannot see -- which would
        # argue against an instance upgrade using a number that is not a
        # measurement at all.
        assert _headroom(0.0, 390) == "unknown"
        assert _headroom(0.0, 390) != 390

    def test_negative_reading_is_also_unknown(self):
        assert _headroom(-1.0, 390) == "unknown"

    def test_already_over_limit_reports_negative_not_unknown(self):
        # A process that starts above its own guard is a real, actionable
        # finding -- it must not be flattened into "unknown".
        assert _headroom(400.0, 390) == -10.0

    def test_headroom_shrinks_as_startup_cost_grows(self):
        room = [_headroom(b, 390) for b in (200.0, 268.0, 340.0)]
        assert room == sorted(room, reverse=True)
        assert len(set(room)) == 3          # strictly decreasing, not a constant


class TestRssProbe:
    def test_rss_is_readable_and_plausible_here(self):
        # Guards the probe itself: on Linux (where the cron runs) /proc/self/statm
        # must yield a positive figure, or every number above becomes "unknown".
        rss = _rss_mb()
        if sys.platform.startswith("linux"):
            assert rss > 0, "/proc/self/statm probe returned nothing on Linux"
            assert rss < 10_000, f"implausible RSS reading: {rss}MB"


class TestRunLogsCarryTheBreakdown:
    """The fields have to reach the log line, not just exist as locals."""

    def test_run_start_and_run_complete_emit_the_budget_fields(self):
        src = (Path(__file__).resolve().parent.parent
               / "cron" / "score_universe.py").read_text()
        start = src.split('_log("run_start"')[1].split(")\n")[0]
        for field in ("rss_interpreter_mb", "rss_imports_mb",
                      "rss_ready_mb", "rss_limit_mb", "rss_headroom_mb"):
            assert field in start, f"run_start lost {field}"

        done = src.split('_log("run_complete"')[1].split("\n\n")[0]
        for field in ("rss_ready_mb", "rss_peak_mb", "rss_work_mb"):
            assert field in done, f"run_complete lost {field}"

    def test_headroom_goes_through_the_helper_not_raw_subtraction(self):
        # Raw `limit - rss_ready` at the call site would reintroduce the
        # 0.0-reads-as-full-budget bug while keeping these tests green.
        src = (Path(__file__).resolve().parent.parent
               / "cron" / "score_universe.py").read_text()
        assert "rss_headroom_mb=_headroom(" in src
        assert "rss_headroom_mb=round(args.max_rss_mb" not in src
