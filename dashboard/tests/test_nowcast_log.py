"""The forward record's only value is that it cannot be edited into looking good.

Ten configurations were searched against 2011-2026 (docs/NOWCAST_RESULTS.md),
so the best backtest result there is the best of ten tries. The forward record
is the uncontaminated test: an estimate written down before the number exists,
scored against what printed.

That is worth exactly nothing if a prediction can be revised after the fact, so
these tests attack the write path rather than the arithmetic:

1. A month's prediction is written ONCE. A second call does not overwrite it,
   whatever it would have predicted the second time.
2. Scoring may fill `actual` and `scored_at` and nothing else.
3. A skill score is WITHHELD until enough months exist. The backtest already
   produced a confident +0.280 off three crisis months; a record that starts at
   n=1 must not be able to repeat that.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.nowcast_log import next_target_month  # noqa: E402


# ── the month being nowcast ─────────────────────────────────────────────────

def test_the_nowcast_month_is_the_one_that_has_not_published():
    """IP for month M prints mid-M+1, so when the series ends at M-1 the open
    question is M — ended, inputs complete, official number not yet out."""
    assert next_target_month("2026-07") == "2026-08"
    assert next_target_month("2026-11") == "2026-12"


def test_the_month_rolls_over_the_year():
    assert next_target_month("2026-12") == "2027-01"


# ── the write path, with a fake engine ──────────────────────────────────────

class _FakeResult:
    def __init__(self, rowcount=1, rows=None):
        self.rowcount = rowcount
        self._rows = rows or []
    def mappings(self): return self
    def all(self): return self._rows


class _FakeConn:
    def __init__(self, store): self.store = store
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, stmt, *a, **k):
        name = type(stmt).__name__
        if "Insert" in name:
            values = dict(stmt.compile().params)
            key = (values.get("target_series"), values.get("target_month"))
            if key in self.store["rows"]:
                return _FakeResult(rowcount=0)          # ON CONFLICT DO NOTHING
            values["id"] = len(self.store["rows"]) + 1
            values.setdefault("actual", None)
            self.store["rows"][key] = values
            return _FakeResult(rowcount=1)
        if "Update" in name:
            self.store["updates"].append(dict(stmt.compile().params))
            return _FakeResult(rowcount=1)
        return _FakeResult(rows=list(self.store["rows"].values()))


class _FakeEngine:
    def __init__(self, store): self.store = store
    def begin(self): return _FakeConn(self.store)


@pytest.fixture
def store(monkeypatch):
    from utils import db
    import utils.nowcast_log as nl
    data = {"rows": {}, "updates": []}
    monkeypatch.setattr(db, "engine", _FakeEngine(data))
    monkeypatch.setattr(nl.db, "engine", _FakeEngine(data), raising=False)
    monkeypatch.setattr(db, "IS_SQLITE", True, raising=False)
    return data


def test_a_month_is_written_once_and_never_overwritten(store):
    from utils.nowcast_log import log_nowcast

    first = log_nowcast("IPMANSICS", "2026-08", predicted=101.5, naive=100.0,
                        estimator="factor", n_features=12)
    assert first is True

    # A second run — perhaps after the number printed — must change nothing.
    second = log_nowcast("IPMANSICS", "2026-08", predicted=99.9, naive=100.0,
                         estimator="factor", n_features=12)
    assert second is False, (
        "a nowcast that can be rewritten after the fact is not a forecast"
    )
    assert store["rows"][("IPMANSICS", "2026-08")]["predicted"] == 101.5


def test_a_missing_prediction_is_refused_rather_than_stored_as_zero(store):
    from utils.nowcast_log import log_nowcast
    assert log_nowcast("IPMANSICS", "2026-08", predicted=None, naive=100.0,
                       estimator="factor") is False
    assert not store["rows"]


def test_scoring_touches_only_the_outcome_columns(store):
    from utils.nowcast_log import log_nowcast, resolve_nowcasts

    log_nowcast("IPMANSICS", "2026-08", predicted=101.5, naive=100.0,
                estimator="factor", n_features=12)
    resolve_nowcasts(lambda _series, _month: 100.8)

    assert store["updates"], "the published month should have been scored"
    written = set(store["updates"][0])
    assert written <= {"actual", "scored_at", "id_1", "id"}, (
        f"scoring wrote {written} — it may only fill actual and scored_at, never "
        f"the prediction"
    )


def test_an_unpublished_month_is_left_alone(store):
    from utils.nowcast_log import log_nowcast, resolve_nowcasts

    log_nowcast("IPMANSICS", "2026-08", predicted=101.5, naive=100.0, estimator="factor")
    assert resolve_nowcasts(lambda _s, _m: None) == 0
    assert not store["updates"]


# ── the record refuses to flatter itself early ──────────────────────────────

def test_skill_is_withheld_until_enough_months_exist(store):
    """The backtest produced a confident +0.280 off three crisis months. A
    record that starts at n=1 must not be able to do that."""
    from utils.nowcast_log import get_forward_record, log_nowcast, resolve_nowcasts

    for i, month in enumerate(["2026-08", "2026-09", "2026-10"]):
        log_nowcast("IPMANSICS", month, predicted=100.0 + i, naive=100.0, estimator="factor")
    for key in store["rows"]:
        store["rows"][key]["actual"] = 100.0 + store["rows"][key]["predicted"] * 0

    record = get_forward_record("IPMANSICS")
    assert record["n_scored"] == 3
    assert record["skill"] is None, (
        "three months cannot support a skill score; the backtest already showed "
        "what a ratio of two RMSEs does on a handful of observations"
    )
    assert record["enough_to_judge"] is False
    assert "months needed" in record["note"]
    assert record["months_model_closer"] is not None, (
        "the hit-rate is still reportable — it is the number that does not "
        "explode on small samples"
    )


def test_an_empty_record_says_so_rather_than_scoring_zero(store):
    from utils.nowcast_log import get_forward_record
    record = get_forward_record("IPMANSICS")
    assert record["n_logged"] == 0 and record["n_scored"] == 0
    assert record["skill"] is None and record["rmse_model"] is None
    assert record["note"]


# ── the specification must not drift while the record accumulates ───────────

def test_the_cron_does_not_expose_the_model_as_a_flag():
    """A cron flag that changes the estimator is a tuning surface. The record is
    only worth keeping if the specification cannot drift mid-flight."""
    source = (_ROOT / "cron" / "run_nowcast.py").read_text(encoding="utf-8")
    assert 'ESTIMATOR = "factor"' in source
    for banned in ("--estimator", "--n-factors", "--alpha", "argparse"):
        assert banned not in source, (
            f"{banned!r} in the cron lets the locked specification change between "
            f"months, which restarts the record without anyone noticing"
        )


def test_the_cron_scores_before_it_publishes():
    """Publishing and scoring the same month in one pass would make the
    timestamps meaningless."""
    source = (_ROOT / "cron" / "run_nowcast.py").read_text(encoding="utf-8")
    assert source.index("resolve_nowcasts(") < source.index("log_nowcast("), (
        "scoring must run before publishing, the same way the resolver cron "
        "repairs before it resolves"
    )
