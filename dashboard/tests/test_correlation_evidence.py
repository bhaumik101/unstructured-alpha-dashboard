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


# ── the power gate: a sample too small to find anything must not weight ──────
# 2026-08-26. Weighting on the lower confidence bound fixed the case where a
# large |r| over few observations scored like a large |r| over many. It did NOT
# fix the inverse: at very small n the sampling distribution of r is so wide
# that a spuriously huge |r| still clears the bound AND the 0.15 weight floor.
# Measured under the null, P(pure noise produces an above-floor weight):
#     quarterly (n~7)   2.63%      monthly (n~23)  1.04%      weekly (n~103)  0.05%
# So the signals with the LEAST evidence were the likeliest to be handed an
# outsized weight -- exactly backwards. utils/ticker_score.py's raw ">= 20
# observations" gate excludes quarterly signals but lets all 19 monthly ones in.

def _weekly(values, start="2024-01-01"):
    import pandas as pd
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="W"))


def _strongly_related(n_points, seed=11):
    """A signal and price that genuinely move together, at a chosen length."""
    import numpy as np
    rng = np.random.default_rng(seed)
    steps = rng.normal(0, 0.02, n_points)
    sig = np.exp(np.cumsum(steps))
    prc = np.exp(np.cumsum(steps * 1.8 + rng.normal(0, 0.002, n_points)))
    return _weekly(sig), _weekly(prc)


def test_min_detectable_r_is_the_pearson_critical_value():
    from utils.analysis import min_detectable_r
    # Pinned against the t-distribution critical values, so the gate's threshold
    # cannot drift silently.
    assert min_detectable_r(7) == 0.7545
    assert min_detectable_r(23) == 0.4132
    assert min_detectable_r(103) == 0.1937
    assert min_detectable_r(519) == 0.0861
    assert min_detectable_r(3) == 1.0, "undefined below n=4, must not claim power"


def test_an_underpowered_sample_earns_no_weight_however_strong_the_correlation():
    """The headline: same real relationship, two sample sizes, opposite outcome."""
    from utils.analysis import compute_quick_correlation_stats

    thin_sig, thin_prc = _strongly_related(24)
    thin = compute_quick_correlation_stats(thin_sig, thin_prc)

    assert abs(thin["r"]) > 0.8, f"the relationship really is strong: r={thin['r']}"
    assert thin["underpowered"] is True
    assert thin["r_lower"] == 0.0, (
        "a correlation found in ~23 observations cannot be distinguished from "
        "the noise a 23-observation sample generates; it must not earn weight"
    )


def test_the_same_relationship_does_earn_weight_once_the_sample_supports_it():
    from utils.analysis import compute_quick_correlation_stats

    thick_sig, thick_prc = _strongly_related(160)
    thick = compute_quick_correlation_stats(thick_sig, thick_prc)

    assert thick["underpowered"] is False
    assert thick["r_lower"] > 0.15, (
        "a well-sampled strong correlation must still clear the weight floor -- "
        "the gate is there to remove noise, not to mute everything"
    )


def test_the_gate_never_invents_weight_it_only_removes_it():
    """A powered sample's bound must be exactly correlation_lower_bound()."""
    from utils.analysis import compute_quick_correlation_stats, correlation_lower_bound

    sig, prc = _strongly_related(160, seed=3)
    out = compute_quick_correlation_stats(sig, prc)
    assert out["r_lower"] == correlation_lower_bound(out["r"], out["n"]), (
        "when the sample is adequate the gate must be a no-op, not a rescale"
    )


def test_the_gate_boundary_sits_where_the_ceiling_says_it_does():
    from utils.analysis import min_detectable_r, MIN_DETECTABLE_R_CEILING
    assert min_detectable_r(31) > MIN_DETECTABLE_R_CEILING, "n=31 is underpowered"
    assert min_detectable_r(32) <= MIN_DETECTABLE_R_CEILING, "n=32 is the first powered size"


def test_pure_noise_at_monthly_cadence_no_longer_buys_an_above_floor_weight():
    """The defect, reproduced: 40k null draws at n=23 used to clear the floor ~1%
    of the time. With the gate it must be exactly zero, not merely rarer."""
    import numpy as np
    from utils.analysis import compute_quick_correlation_stats, WEIGHT_FLOOR

    rng = np.random.default_rng(2026)
    cleared = 0
    for _ in range(400):
        sig = _weekly(np.exp(np.cumsum(rng.normal(0, 0.02, 24))))
        prc = _weekly(np.exp(np.cumsum(rng.normal(0, 0.02, 24))))
        out = compute_quick_correlation_stats(sig, prc)
        if out["r_lower"] > WEIGHT_FLOOR:
            cleared += 1
    assert cleared == 0, f"{cleared}/400 noise draws still bought a weight"


def test_every_corr_info_site_reports_what_the_sample_could_have_detected():
    """An underpowered signal must read as underpowered, not as 'tested, nothing found'.

    Checked per construction site rather than as a file-wide grep: ticker_score
    builds corr_info in more than one branch, and a whole-file search passes
    while a branch is silently missing the keys.
    """
    source = (_ROOT / "utils" / "ticker_score.py").read_text(encoding="utf-8")

    sites, cursor = [], 0
    while (i := source.find("corr_info[sig_id] = {", cursor)) != -1:
        depth, j = 0, source.index("{", i)
        for j in range(j, len(source)):
            if source[j] == "{": depth += 1
            elif source[j] == "}":
                depth -= 1
                if depth == 0: break
        sites.append(source[i:j + 1])
        cursor = j

    assert len(sites) >= 2, f"expected several corr_info branches, found {len(sites)}"
    for k, block in enumerate(sites):
        assert '"min_detectable_r"' in block and '"underpowered"' in block, (
            f"corr_info branch {k} omits the power numbers; the UI cannot then "
            f"distinguish a signal that was tested and failed from one that "
            f"could never have passed:\n{block}"
        )


def test_the_research_window_is_long_enough_to_find_anything():
    """730 days leaves a weekly signal able to detect only |r| >= 0.194."""
    from utils.validation_status import RESEARCH_WINDOW_DAYS
    from utils.analysis import min_detectable_r
    weekly_n = RESEARCH_WINDOW_DAYS / 7
    assert RESEARCH_WINDOW_DAYS >= 365 * 5, "discovery needs more than a couple of years"
    assert min_detectable_r(int(weekly_n)) < 0.10, (
        f"a {RESEARCH_WINDOW_DAYS}-day window only reaches "
        f"|r| >= {min_detectable_r(int(weekly_n))}"
    )


# ── forward-return, market-adjusted scanning ────────────────────────────────
# 2026-08-26. Two changes aimed at effect size rather than sample size: test
# against forward CUMULATIVE returns over the product's own 4/8/12w horizons,
# and regress out the market first so a macro signal is not largely being
# tested against SPY.
#
# The trap is that overlapping forward windows are autocorrelated. Measured over
# 1200 trials on an AR(0.6) signal, a p-value computed on the raw row count
# rejects a true null at 19.9% / 26.4% / 27.7% for H=4/8/12 -- four to five times
# the nominal 5%. Bartlett's effective n brings that to 4.6% / 5.1% / 4.2%.
#
# n // H was tried first and rejected by measurement: overlap inflates a
# correlation's variance only when BOTH series are autocorrelated, so against a
# white-noise signal n // H gave 0% false positives AND 0% power -- a dead test.

def _ar1_signal(n, rho, seed, scale=0.02):
    import numpy as np, pandas as pd
    rng = np.random.default_rng(seed)
    steps = np.zeros(n)
    for i in range(1, n):
        steps[i] = rho * steps[i - 1] + rng.normal(0, scale)
    idx = pd.date_range("2016-01-01", periods=n, freq="W")
    return pd.Series(np.exp(np.cumsum(steps)), index=idx), steps, idx


def test_bartlett_keeps_full_n_when_either_series_is_white_noise():
    """The reason n // H was wrong: one-sided persistence costs nothing."""
    import numpy as np
    from utils.analysis import bartlett_effective_n
    rng = np.random.default_rng(0)
    n = 400
    white = rng.normal(size=n)
    persistent = np.zeros(n)
    for i in range(1, n):
        persistent[i] = 0.9 * persistent[i - 1] + rng.normal()

    assert bartlett_effective_n(white, rng.normal(size=n)) > 0.9 * n
    # BOTH argument orders: the formula multiplies the two autocorrelations, so
    # summing only one series' ACF passes one order and fails the other.
    assert bartlett_effective_n(white, persistent) > 0.9 * n, (
        "persistence on only one side must not shrink the effective sample"
    )
    assert bartlett_effective_n(persistent, white) > 0.9 * n, (
        "the correction must use the PRODUCT of both series' autocorrelations, "
        "not either one alone"
    )
    assert bartlett_effective_n(persistent, persistent.copy()) < 0.5 * n, (
        "shared persistence must shrink it substantially"
    )


def test_bartlett_never_claims_more_independence_than_rows():
    """One persistent and one anti-persistent series make the correction sum
    NEGATIVE, which would otherwise report more independent observations than
    there are rows. Two copies of the same series cannot test this: the
    cross-term is then rho(k)^2, which is never negative."""
    import numpy as np
    from utils.analysis import bartlett_effective_n
    rng = np.random.default_rng(4)
    n = 300
    persistent = np.zeros(n)
    for i in range(1, n):
        persistent[i] = 0.85 * persistent[i - 1] + rng.normal()
    alternating = np.array([(-1.0) ** i for i in range(n)]) + rng.normal(0, 0.01, n)

    assert bartlett_effective_n(persistent, alternating) <= n, (
        "effective sample size must never exceed the number of rows"
    )


def test_overlapping_windows_do_not_manufacture_significance():
    """The headline guard: a true null at H=8 must not read as significant.

    Deterministic sweep rather than a single draw -- one seed passing proves
    nothing about a false-positive rate.
    """
    import numpy as np, pandas as pd
    from utils.analysis import compute_forward_return_correlation

    hits = 0
    for seed in range(60):
        sig, _, idx = _ar1_signal(400, 0.6, seed)
        rng = np.random.default_rng(10_000 + seed)
        prc = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.03, 400))), index=idx)
        out = compute_forward_return_correlation(sig, prc, horizon_weeks=8)
        assert out["n_effective"] <= out["n"]
        if out["p_value"] < 0.05:
            hits += 1
    assert hits <= 9, (
        f"{hits}/60 null draws called significant at H=8; the overlap correction "
        f"is not holding (naive row-count inference gives ~26%)"
    )


def test_the_effective_sample_shrinks_once_windows_overlap():
    import numpy as np, pandas as pd
    from utils.analysis import compute_forward_return_correlation
    sig, _, idx = _ar1_signal(400, 0.6, 3)
    rng = np.random.default_rng(77)
    prc = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.03, 400))), index=idx)

    h1 = compute_forward_return_correlation(sig, prc, horizon_weeks=1)
    h12 = compute_forward_return_correlation(sig, prc, horizon_weeks=12)
    assert h12["n_effective"] < h1["n_effective"], (
        "twelve-week overlapping windows carry less independent information "
        "than one-week ones and must report so"
    )
    # ...but the shrink must be adaptive, not a flat n // H division. A
    # WHITE-NOISE signal costs nothing even at a long horizon, which is the
    # whole reason n // H was rejected: it would report n/12 here.
    white_sig = pd.Series(
        np.exp(np.cumsum(np.random.default_rng(5).normal(0, 0.02, 400))), index=idx
    )
    wh12 = compute_forward_return_correlation(white_sig, prc, horizon_weeks=12)
    assert wh12["n_effective"] > wh12["n"] / 3, (
        f"a white-noise signal must keep most of its sample even at H=12; got "
        f"n_eff={wh12['n_effective']} of n={wh12['n']} (n // H would give "
        f"{wh12['n'] // 12})"
    )


def test_removing_the_market_recovers_effect_size_it_was_masking():
    """A macro signal driving only idiosyncratic return, inside a high-beta stock."""
    import numpy as np, pandas as pd
    from utils.analysis import compute_forward_return_correlation

    n, H, beta = 400, 4, 1.3
    sig, steps, idx = _ar1_signal(n, 0.6, 21)
    rng = np.random.default_rng(21)
    mkt_inc = rng.normal(0, 0.02, n)
    bmk = pd.Series(np.exp(np.cumsum(mkt_inc)), index=idx)
    drive = pd.Series(steps).rolling(H).mean().shift(1).fillna(0.0).to_numpy()
    idio = 0.4 * drive + rng.normal(0, 0.015, n)
    prc = pd.Series(np.exp(np.cumsum(beta * mkt_inc + idio)), index=idx)

    raw = compute_forward_return_correlation(sig, prc, horizon_weeks=H)
    adj = compute_forward_return_correlation(sig, prc, bmk, horizon_weeks=H)

    assert adj["beta_adjusted"] is True and raw["beta_adjusted"] is False
    assert abs(adj["r"]) > abs(raw["r"]), (
        f"regressing out the market should expose the idiosyncratic relationship: "
        f"raw |r|={abs(raw['r']):.3f} vs adjusted |r|={abs(adj['r']):.3f}"
    )


def test_market_adjustment_does_not_invent_a_relationship():
    """It must raise real effects, not conjure them out of a null."""
    import numpy as np, pandas as pd
    from utils.analysis import compute_forward_return_correlation
    hits = 0
    for seed in range(40):
        sig, _, idx = _ar1_signal(400, 0.6, seed)
        rng = np.random.default_rng(31_000 + seed)
        mkt_inc = rng.normal(0, 0.02, 400)
        bmk = pd.Series(np.exp(np.cumsum(mkt_inc)), index=idx)
        prc = pd.Series(np.exp(np.cumsum(1.1 * mkt_inc + rng.normal(0, 0.015, 400))), index=idx)
        if compute_forward_return_correlation(sig, prc, bmk, horizon_weeks=4)["p_value"] < 0.05:
            hits += 1
    assert hits <= 6, f"{hits}/40 beta-adjusted null draws called significant"


def test_forward_scan_carries_the_full_contract_on_every_guard_path():
    import pandas as pd
    from utils.analysis import compute_forward_return_correlation
    expected = {"r", "p_value", "significant", "n", "n_effective", "r_lower",
                "min_detectable_r", "underpowered", "horizon_weeks", "beta_adjusted"}
    tiny = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2024-01-01", periods=3, freq="W"))
    assert set(compute_forward_return_correlation(tiny, tiny).keys()) == expected
    empty = pd.Series(dtype=float)
    assert set(compute_forward_return_correlation(empty, empty).keys()) == expected
    assert compute_forward_return_correlation(tiny, tiny, horizon_weeks=0)["underpowered"] is True


def test_the_three_horizons_are_corrected_as_one_family():
    """Best-of-three uncorrected is the same inflation lag scanning guards against."""
    source = (_ROOT / "utils" / "validation_status.py").read_text(encoding="utf-8")
    block = source[source.index("forward = None"):]
    block = block[:block.index('out[sig_id] =')]
    assert "benjamini_hochberg" in block, (
        "the 4/8/12w scans form one family per signal and must be BH-corrected"
    )
    assert "survives_fdr" in block
    # Surviving BH is necessary but not sufficient: a scan whose sample could
    # not have detected a believable correlation must not be promoted to "best"
    # on the strength of a q-value alone.
    assert 'not sc["underpowered"]' in block, (
        "an underpowered scan must be excluded from survivors even if BH rejects"
    )


def test_forward_evidence_distinguishes_not_run_from_nothing_found():
    from utils.model_validation import forward_evidence_label
    assert forward_evidence_label(None) == "Not run"
    assert "Underpowered" in forward_evidence_label(
        {"scans": [{"underpowered": True}, {"underpowered": True}], "best": None})
    assert "no horizon survived" in forward_evidence_label(
        {"scans": [{"underpowered": False}], "best": None})
    label = forward_evidence_label({
        "scans": [{"underpowered": False}],
        "best": {"horizon_weeks": 8, "r": 0.31, "q_value": 0.012, "n_effective": 91},
    })
    assert "8w" in label and "0.31" in label and "91" in label
