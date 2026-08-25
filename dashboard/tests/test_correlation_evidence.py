"""Correlation must earn its weight, and 47 tests are one family.

Two statistical defects in how correlation became a Confluence Score weight:

1. MULTIPLE COMPARISONS. Each ticker is tested against ~47 signals at an
   uncorrected alpha of 0.05, so roughly two signals per ticker clear the bar on
   noise alone. Bonferroni exists in the codebase but only in the validation
   path, which by its own docstring does not feed scoring.

2. SAMPLE SIZE WAS INVISIBLE. `weight = max(0.15, |r|) * pcs/10` treated r=0.30
   over 8 observations exactly like r=0.30 over 100. At n=8 a correlation needs
   |r| > ~0.71 to be distinguishable from zero; at n=100, ~0.20.

Both are fixed at the source: Benjamini-Hochberg over the per-ticker family, and
weighting on the lower confidence bound of |r| rather than |r| itself. The bound
needs no threshold -- a correlation that cannot be told apart from zero shrinks
to zero on its own.

Measured on live data when this landed: across NVDA, CAT and MU the score moved
by at most 0.5 points and 1-2 of 47 weights changed, because no macro signal's
correlation with any of the three survived its own confidence interval.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.analysis import (  # noqa: E402
    WEIGHT_FLOOR,
    benjamini_hochberg,
    correlation_lower_bound,
)


# ── Benjamini-Hochberg ───────────────────────────────────────────────────────

def test_bh_rejects_exactly_the_ranks_the_procedure_allows():
    """p_(k) <= (k/m) * alpha for the largest such k, then everything below."""
    ps = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    rejected, q = benjamini_hochberg(ps, alpha=0.05)
    # 0.001 <= 0.005 and 0.008 <= 0.010; 0.039 > 0.015, and no larger rank
    # qualifies, so exactly the first two are rejected.
    assert rejected == [True, True] + [False] * 8
    assert q[0] == pytest.approx(0.01)
    assert q[1] == pytest.approx(0.04)


def test_bh_adjusted_values_are_monotone_in_rank():
    """A q-value may never fall as the raw p-value rises."""
    ps = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    _, q = benjamini_hochberg(ps, alpha=0.05)
    assert q == sorted(q), f"q-values are not monotone: {q}"


def test_bh_is_less_conservative_than_bonferroni_but_still_corrects():
    """The point of choosing BH: it controls error without destroying power."""
    ps = [0.001, 0.002, 0.003, 0.004] + [0.5] * 46
    rejected, _ = benjamini_hochberg(ps, alpha=0.05)
    n_bh = sum(rejected)
    n_bonferroni = sum(1 for p in ps if p < 0.05 / len(ps))
    n_uncorrected = sum(1 for p in ps if p < 0.05)
    assert n_bonferroni <= n_bh <= n_uncorrected
    assert n_bh == 4, f"BH found {n_bh} of 4 genuine effects"


def test_bh_preserves_input_order():
    """Results are zipped back onto the caller's signal list by position."""
    ps = [0.9, 0.001, 0.5, 0.002]
    rejected, q = benjamini_hochberg(ps, alpha=0.05)
    assert rejected == [False, True, False, True]
    assert q[1] < q[0] and q[3] < q[2]


def test_bh_handles_an_empty_family():
    assert benjamini_hochberg([], 0.05) == ([], [])


def test_bh_treats_unusable_p_values_as_never_rejected():
    """A missing p-value must not shift the ranks of the real ones."""
    rejected, q = benjamini_hochberg([0.001, None, float("nan"), 0.002], alpha=0.05)
    assert rejected[1] is False and rejected[2] is False
    assert q[1] == 1.0 and q[2] == 1.0
    assert rejected[0] is True and rejected[3] is True


def test_a_family_of_pure_noise_yields_no_discoveries():
    """The defect this fixes: 47 uncorrected tests invent ~2 findings."""
    ps = [i / 47 for i in range(1, 48)]          # uniform, i.e. null is true
    uncorrected = sum(1 for p in ps if p < 0.05)
    rejected, _ = benjamini_hochberg(ps, alpha=0.05)
    assert uncorrected >= 2, "fixture should reproduce the uncorrected illusion"
    assert sum(rejected) == 0, "BH accepted a discovery from a uniform null"


# ── Fisher z lower bound ─────────────────────────────────────────────────────

def test_the_bound_matches_the_fisher_transform():
    r, n = 0.5, 40
    z = math.atanh(r) - 1.959963984540054 / math.sqrt(n - 3)
    assert correlation_lower_bound(r, n) == pytest.approx(math.tanh(z), abs=5e-5)


def test_the_same_r_is_worth_more_with_more_data():
    """The whole point: r=0.30 at n=8 is not r=0.30 at n=100."""
    assert correlation_lower_bound(0.30, 8) == 0.0
    assert correlation_lower_bound(0.30, 100) > 0.10


def test_the_bound_is_zero_when_the_interval_reaches_zero():
    """No threshold is chosen anywhere; unconvincing correlations self-shrink."""
    assert correlation_lower_bound(0.05, 500) == 0.0
    assert correlation_lower_bound(0.20, 12) == 0.0


def test_the_bound_is_monotone_in_both_arguments():
    assert (correlation_lower_bound(0.2, 200) < correlation_lower_bound(0.4, 200)
            < correlation_lower_bound(0.6, 200))
    assert (correlation_lower_bound(0.5, 20) < correlation_lower_bound(0.5, 60)
            < correlation_lower_bound(0.5, 300))


def test_sign_is_discarded_because_the_weight_is_a_magnitude():
    assert correlation_lower_bound(-0.6, 80) == correlation_lower_bound(0.6, 80)


def test_degenerate_inputs_return_zero_rather_than_infinity():
    for n in (0, 1, 3):
        assert correlation_lower_bound(0.9, n) == 0.0
    # arctanh(1) diverges. The clip keeps the result finite and inside [0, 1];
    # a perfect sample correlation legitimately bounds near 1, it just must not
    # be an overflow.
    perfect = correlation_lower_bound(1.0, 50)
    assert math.isfinite(perfect) and 0.99 < perfect <= 1.0
    assert correlation_lower_bound(float("nan"), 50) == 0.0
    assert correlation_lower_bound("x", 50) == 0.0


def test_the_bound_never_exceeds_the_point_estimate():
    for r in (0.1, 0.35, 0.7, 0.95):
        for n in (10, 50, 400):
            assert correlation_lower_bound(r, n) <= r + 1e-9


# ── the scoring path ─────────────────────────────────────────────────────────

def test_the_stats_function_reports_the_bound_alongside_r():
    import numpy as np
    import pandas as pd
    from utils.analysis import compute_quick_correlation_stats

    idx = pd.date_range("2024-01-01", periods=200, freq="D")
    rng = np.random.default_rng(7)
    noise = pd.Series(rng.normal(size=200).cumsum() + 100, index=idx)
    other = pd.Series(rng.normal(size=200).cumsum() + 100, index=idx)

    out = compute_quick_correlation_stats(noise, other)
    assert "r_lower" in out and "n" in out
    assert out["r_lower"] <= abs(out["r"]) + 1e-9


def test_every_guard_path_still_carries_r_lower():
    """Callers index r_lower unconditionally; a missing key would KeyError."""
    import pandas as pd
    from utils.analysis import compute_quick_correlation_stats

    tiny = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2024-01-01", periods=3))
    out = compute_quick_correlation_stats(tiny, tiny)
    assert out["r_lower"] == 0.0


def test_the_score_weights_on_evidence_not_raw_correlation():
    source = (_ROOT / "utils" / "ticker_score.py").read_text(encoding="utf-8")
    assert "max(0.15, abs(r))" not in source, (
        "the weight is back on raw |r|, which ignores sample size entirely"
    )
    assert "max(WEIGHT_FLOOR, evidence)" in source


def test_the_family_is_corrected_once_not_per_signal():
    """Correcting inside the loop is the uncorrected alpha wearing a hat."""
    source = (_ROOT / "utils" / "ticker_score.py").read_text(encoding="utf-8")
    assert source.count("benjamini_hochberg(") == 1
    corr_block = source[source.index("corr_info = {}"):source.index("# Momentum blend")]
    assert corr_block.index("benjamini_hochberg(") < corr_block.index("for position, sig_id"), (
        "BH must run over the collected family before weights are assigned"
    )


def test_the_floor_is_a_named_decision():
    assert 0 < WEIGHT_FLOOR < 1
    source = (_ROOT / "utils" / "ticker_score.py").read_text(encoding="utf-8")
    assert "WEIGHT_FLOOR" in source
