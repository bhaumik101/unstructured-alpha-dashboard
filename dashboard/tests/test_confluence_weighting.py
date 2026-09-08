"""The Confluence Score's weights must reflect information, not assertion.

Until 2026-09-03 each signal's weight was `max(0.15, r_lower) * pcs/10`, where
pcs is one of 47 hand-assigned integers. Two measured problems:

1. THE HAND-ASSIGNED PART DID ALMOST NOTHING. pcs ranges 5-9 with 31 of 47 at 7
   or 8, so across 20,000 random score vectors a pcs-weighted mean differed from
   a plain average by 0.49 points on a 0-100 scale (95th pct 1.21, max 2.49). It
   created the appearance of calibration and contributed nothing measurable.

2. THE CROWDING WAS UNCOUNTED. 47 signals carry the information of 9.81, and the
   "macro" block collapses 28 signals into 8.45 effective. Weighting per signal
   handed that block ~3.3x the influence its information supports — up to ±12
   points on the composite when it disagreed with everything else.

The weight is now the independence share: each factor block gets its effective
count of votes, shared among its members. utils/analysis.py already recomputed
the CONVICTION LABEL this way, so the number and the label beside it disagreed
by construction until this landed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.config import SIGNALS  # noqa: E402
from utils.signal_independence import (  # noqa: E402
    effective_signal_count,
    factor_of,
    independence_weights,
)


def _largest_factor() -> list:
    """The most crowded LATENT FACTOR — not the display category.

    utils/config.py's "category" is a UI bucket: it files 28 signals under
    "macro" although they span rates, labour, housing, inflation, credit and
    activity, which are different economic drivers. SIGNAL_FACTOR is the
    economic mapping and is what the correlation prior applies to.
    """
    blocks: dict = {}
    for sid in SIGNALS:
        blocks.setdefault(factor_of(sid), []).append(sid)
    return max(blocks.values(), key=len)


def test_a_crowded_factor_gets_its_effective_count_not_its_headcount():
    """Members of one latent factor must speak with their effective weight."""
    block = _largest_factor()
    assert len(block) >= 4, "expected a genuinely crowded factor to test"

    weights = independence_weights(block)
    total = sum(weights.values())
    effective = effective_signal_count(block)

    assert total == pytest.approx(effective, rel=1e-6), (
        f"the block's total weight ({total:.2f}) must equal its effective count "
        f"({effective:.2f}), not its headcount ({len(block)})"
    )
    assert total < len(block), "a correlated block must lose some of its headcount"


def test_members_of_one_factor_share_equally():
    macro = [s for s in SIGNALS if SIGNALS[s].get("category") == "macro"][:6]
    weights = independence_weights(macro)
    assert len(set(round(w, 9) for w in weights.values())) == 1, (
        "within a block there is no basis for preferring one member over another"
    )


def test_an_uncrowded_signal_keeps_its_full_vote():
    """A factor with one member has nothing to share with; it keeps weight 1."""
    by_factor = {}
    for sid in SIGNALS:
        by_factor.setdefault(factor_of(sid), []).append(sid)
    singletons = [ids[0] for ids in by_factor.values() if len(ids) == 1]
    if not singletons:
        pytest.skip("no single-member factor in the live config")
    weights = independence_weights(SIGNALS.keys())
    assert weights[singletons[0]] == pytest.approx(1.0)


def test_the_hand_assigned_pcs_no_longer_touches_the_weight():
    """PCS may still narrate a signal elsewhere; it must not set its weight."""
    source = (_ROOT / "utils" / "ticker_score.py").read_text(encoding="utf-8")
    body = source[source.index("corr_info = {}"):source.index("# Momentum blend")]
    assert "pcs / 10" not in body and 'get("pcs"' not in body, (
        "the weight is back to a hand-assigned number; 20k simulated score "
        "vectors showed that scheme moves the composite 0.49 points on average "
        "while implying a calibration that was never validated"
    )
    assert "independence_weights" in body


def test_the_score_and_the_conviction_label_use_the_same_crowding_maths():
    """They disagreed by construction: the label was computed on effective
    agreement and the number on raw headcount."""
    score_src = (_ROOT / "utils" / "ticker_score.py").read_text(encoding="utf-8")
    label_src = (_ROOT / "utils" / "analysis.py").read_text(encoding="utf-8")
    assert "signal_independence" in score_src
    assert "signal_independence" in label_src, (
        "if the label stops using it, this test should fail rather than let the "
        "two silently diverge again"
    )


def test_reweighting_actually_moves_a_disagreeing_composite():
    """Guards the premise. If equal and independence weighting agreed, none of
    this would be worth doing."""
    ids = list(SIGNALS.keys())
    indep = independence_weights(ids)

    # The most crowded LATENT FACTOR says one thing, everything else the opposite.
    crowded = set(_largest_factor())
    scores = {s: (20.0 if s in crowded else 80.0) for s in ids}
    arr = np.array([scores[s] for s in ids])
    equal = float(arr.mean())
    weighted = float(np.average(arr, weights=[indep[s] for s in ids]))

    assert weighted > equal, (
        f"down-weighting the crowded bearish factor must pull the composite "
        f"toward the uncrowded majority; equal={equal:.1f} indep={weighted:.1f}"
    )
    assert abs(weighted - equal) > 0.5, (
        f"the correction must be visible, not cosmetic; moved only "
        f"{abs(weighted - equal):.2f} points"
    )


def test_weights_are_positive_and_bounded():
    weights = independence_weights(list(SIGNALS.keys()))
    assert len(weights) == len(SIGNALS)
    assert all(0.0 < w <= 1.0 + 1e-9 for w in weights.values())


def test_unknown_signals_are_not_silently_dropped():
    weights = independence_weights(["not_a_real_signal", "also_fake"])
    assert set(weights) == {"not_a_real_signal", "also_fake"}
    assert all(w > 0 for w in weights.values())
