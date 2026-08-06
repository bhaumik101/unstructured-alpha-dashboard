"""Gated tickers must rotate through the queue, not block the head of it.

WHY THIS EXISTS. cron/score_universe.py orders targets stalest-first from the
newest score_snapshots row per ticker. A gated ticker never earns a snapshot
row, so its date stayed "" — and "" sorts ahead of every real date. The
permanently-ungateable tickers were therefore pinned at the front of every
pass. Measured on a live run 2026-08-06: three of eight passes scored ONE
ticker each while re-downloading prices for the same rejects.

utils/db.scoring_gate_log records "examined today, rejected", and
_last_seen_map folds that date in so rejects rotate to the back.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cron import score_universe as su          # noqa: E402
from utils import db                           # noqa: E402
from utils.db import scoring_gate_log          # noqa: E402
from utils.score_history import record_gate_outcome   # noqa: E402

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# The table is brand new, so a test database created before this change has to
# be migrated the same way production is: plain create_all() via init_db().
db.init_db()


def _clear():
    with db.engine.begin() as conn:
        conn.execute(scoring_gate_log.delete())


class TestGateOutcomeWrite:
    def test_records_the_check_and_upserts_within_a_day(self):
        _clear()
        record_gate_outcome("ZZTOP", "sub_dollar_price")
        record_gate_outcome("ZZTOP", "insufficient_history")
        with db.engine.connect() as conn:
            rows = conn.execute(scoring_gate_log.select()).fetchall()
        assert len(rows) == 1, "a second check the same day must overwrite, not duplicate"
        assert rows[0].reason == "insufficient_history"
        assert rows[0].checked_date == TODAY

    def test_a_write_failure_never_propagates(self, monkeypatch):
        # Bookkeeping must not be able to abort a scoring run.
        class Boom:
            def begin(self):
                raise RuntimeError("db gone")
        monkeypatch.setattr(db, "engine", Boom())
        record_gate_outcome("ZZTOP", "no_price_data")      # must not raise


class TestTheCronActuallyRecordsIt:
    """The writer existing is worthless if the gate path never calls it.

    Mutation-testing this file caught exactly that: deleting the
    record_gate_outcome call from cron/score_universe.py left every other test
    green, because they exercise the helper directly. This walks the AST and
    asserts the call lives INSIDE the `if reason != OK:` branch, so the change
    cannot silently become a no-op.
    """

    def _gate_branch(self):
        import ast
        src = (Path(__file__).resolve().parent.parent
               / "cron" / "score_universe.py").read_text()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.If):
                continue
            t = node.test
            if (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                    and t.left.id == "reason"
                    and isinstance(t.ops[0], ast.NotEq)):
                return node
        raise AssertionError("could not find the `if reason != OK:` gate branch")

    def test_the_gate_branch_records_the_outcome(self):
        import ast
        branch = self._gate_branch()
        calls = [n.func.id for n in ast.walk(branch)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        assert "record_gate_outcome" in calls, (
            "the gate branch must record the check, or gated tickers keep their "
            "empty date and stay pinned to the head of the stalest-first queue")

    def test_the_gate_branch_still_skips_scoring(self):
        # Guard the obvious way to "fix" the above wrongly: recording must be
        # an addition to the branch, never a replacement for the `continue`.
        import ast
        branch = self._gate_branch()
        assert any(isinstance(n, ast.Continue) for n in ast.walk(branch)), (
            "a gated ticker must still skip scoring")

    def test_the_writer_is_imported_in_the_cron(self):
        src = (Path(__file__).resolve().parent.parent
               / "cron" / "score_universe.py").read_text()
        assert "record_gate_outcome" in src.split("def main")[1].split("init_db()")[0], (
            "record_gate_outcome must be imported alongside record_score_snapshot")


class TestStalestOrdering:
    def test_a_gated_ticker_stops_sorting_ahead_of_everything(self):
        _clear()
        seen = su._last_seen_map("macro_momentum")
        assert seen is not None
        before = su._stalest_first(["GATED", "SCORED"], "macro_momentum",
                                   {"SCORED": "2026-01-01"})
        assert before[0] == "GATED", "unscored ticker should start at the head"

        record_gate_outcome("GATED", "sub_dollar_price")
        seen = su._last_seen_map("macro_momentum")
        assert seen.get("GATED") == TODAY, "the gate check must reach the staleness map"

        after = su._stalest_first(["GATED", "SCORED"], "macro_momentum", seen)
        assert after[0] == "SCORED", (
            "a ticker checked today must rotate behind one last scored in January")

    def test_gate_date_never_moves_a_ticker_backwards(self):
        # A ticker scored today and gated last week is still fresh today.
        _clear()
        record_gate_outcome("BOTH", "no_price_data")
        seen = su._last_seen_map("macro_momentum")
        merged = max(seen.get("BOTH", ""), "2026-12-31")
        assert merged == "2026-12-31", "the newer of the two dates must win"

    def test_gated_ticker_counts_as_fresh_for_the_supervisor(self):
        # Otherwise a slice of pure rejects reads as "work remaining" forever
        # and the run never reaches its universe_fresh stop.
        _clear()
        record_gate_outcome("REJECT", "insufficient_history")
        seen = su._last_seen_map("macro_momentum")
        assert su._count_fresh(["REJECT"], seen, TODAY) == 1
