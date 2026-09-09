"""Exploration must be cumulative, not corrosive.

"Keep trying new data until something works" is p-hacking: with enough
candidates one clears p < 0.05 by chance. docs/NOWCAST_RESULTS.md already
records ten configurations searched against 2011-2026, and the best of them
(skill +0.348, p = 0.131) is worth exactly "best of ten tries".

The ledger makes further exploration honest by construction:

1. Candidates are registered IN CODE with a mechanism written before the test.
2. Each is evaluated once. Write-once, so nothing can be re-run until it behaves.
3. The Bonferroni threshold is recomputed FROM THE LEDGER SIZE at read time, so
   the bar tightens on its own and no early result keeps a stale threshold.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.candidate_ledger import CANDIDATES, corrected_alpha  # noqa: E402


# ── registration discipline ────────────────────────────────────────────────

def test_every_candidate_states_a_mechanism_before_it_is_tested():
    for c in CANDIDATES:
        assert len(c.hypothesis) > 60, (
            f"{c.key} has no real hypothesis. A mechanism invented after seeing "
            f"a result explains anything; this must be written first."
        )
        assert c.fred, f"{c.key} names no series"


def test_candidate_keys_are_unique():
    keys = [c.key for c in CANDIDATES]
    assert len(keys) == len(set(keys))


def test_candidates_that_publish_late_are_marked_unsafe_at_lag_zero():
    """rail_carloads shares RAILFRTINTERMODAL's ~2-month publication lag. That
    exact trap inflated the first factor-model result."""
    rail = next((c for c in CANDIDATES if "rail" in c.key), None)
    assert rail is not None
    assert rail.safe_at_lag0 is False, (
        "rail freight publishes ~2 months late; testing it at lag 0 would be "
        "look-ahead, the same bug corrected on 2026-09-03"
    )


def test_no_candidate_duplicates_a_predictor_already_in_the_spec():
    from utils.nowcast import NOWCAST_PREDICTORS
    in_spec = {p.fred for p in NOWCAST_PREDICTORS if p.fred}
    for c in CANDIDATES:
        assert c.fred not in in_spec, (
            f"{c.key} ({c.fred}) is already in the locked specification; testing "
            f"it as a candidate would spend search budget on a known quantity"
        )


# ── the correction is the mechanism ────────────────────────────────────────

def test_the_threshold_tightens_as_the_ledger_grows():
    assert corrected_alpha(1) == pytest.approx(0.05)
    assert corrected_alpha(5) == pytest.approx(0.01)
    assert corrected_alpha(10) == pytest.approx(0.005)
    assert corrected_alpha(20) < corrected_alpha(10) < corrected_alpha(1), (
        "more exploration must demand stronger evidence, automatically"
    )


def test_an_empty_ledger_does_not_divide_by_zero():
    assert corrected_alpha(0) == pytest.approx(0.05)


def test_survival_is_never_persisted_so_it_cannot_go_stale():
    """A candidate tested when the ledger held 3 rows must not keep that
    threshold once 12 have been tested.

    Asserted against the SCHEMA rather than the source text: the property is
    that the verdict is not storable, which a column list states exactly and a
    string search only approximates.
    """
    from utils.db import candidate_evaluations

    columns = {c.name for c in candidate_evaluations.columns}
    assert "survives_correction" not in columns, (
        "a stored verdict freezes the threshold it was computed against"
    )
    assert "corrected_alpha" not in columns
    assert {"dm_p_value", "skill", "evaluated_at"} <= columns

    source = (_ROOT / "utils" / "candidate_ledger.py").read_text(encoding="utf-8")
    ledger_fn = source[source.index("def get_ledger"):]
    assert "corrected_alpha(n)" in ledger_fn, (
        "get_ledger must recompute the threshold from the CURRENT row count"
    )


def test_a_survivor_must_be_both_significant_and_better():
    source = (_ROOT / "utils" / "candidate_ledger.py").read_text(encoding="utf-8")
    ledger_fn = source[source.index("def get_ledger"):]
    assert "skill > 0" in ledger_fn, (
        "a significantly WORSE candidate is not a survivor"
    )


# ── the cron must not promote anything on its own ──────────────────────────

def test_the_cron_evaluates_but_never_promotes():
    """A survivor joining the spec automatically would change the model mid-
    record and silently restart the forward clock."""
    source = (_ROOT / "cron" / "run_nowcast.py").read_text(encoding="utf-8")
    assert "record_evaluation" in source
    assert "NOWCAST_PREDICTORS.append" not in source
    assert "NOWCAST_PREDICTORS +" not in source
    # Comment markers stripped, then whitespace-normalised: the rule is written
    # as a wrapped comment, so a contiguous-substring search would fail on the
    # "#" that begins the continuation line rather than on the rule's absence.
    flat = " ".join(
        " ".join(l.lstrip().lstrip("#").strip() for l in source.splitlines()).split()
    )
    assert "does NOT join the locked specification" in flat, (
        "the no-promotion rule must be stated where the evaluation happens"
    )


def test_only_one_candidate_is_tested_per_run():
    """Testing the whole registry at once would demand p < 0.008 of all of them
    and produce nothing interpretable."""
    source = (_ROOT / "cron" / "run_nowcast.py").read_text(encoding="utf-8")
    block = source[source.index("evaluate one candidate"):source.index("_led = get_ledger()")]
    assert "pending[0]" in block, "exactly one candidate per run"
    assert "for cand in" not in block, "a loop here would spend the whole budget at once"
