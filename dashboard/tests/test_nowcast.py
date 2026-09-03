"""The nowcast harness must not be able to cheat, and must admit when it fails.

This is the evaluation half of the pivot away from predicting equity returns.
The model itself is replaceable; the harness is what makes any result
believable, so these tests attack it rather than the fit.

Three things are being defended:

1. NO LOOK-AHEAD. Month M's features may contain nothing from month M or
   later, and a prediction already made must not change when later data
   arrives. That second property is the strong one: it catches any leak that
   works by fitting on the whole sample, including the standardisation leak
   that is easy to write and invisible in the output.

2. THE BASELINE IS REAL. Skill is measured against "last month's value", which
   for a persistent macro series is a genuinely hard baseline. A harness that
   scores against zero, or against the sample mean, flatters itself.

3. FAILURE IS REPORTABLE. Thin data returns available=False with a reason. A
   model that loses to the naive forecast returns beats_naive=False. Neither is
   allowed to render as a zero or an empty success.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.nowcast import (  # noqa: E402
    MIN_TRAIN_MONTHS,
    NOWCAST_TARGET_SERIES,
    build_design,
    monthly_aggregate,
    run_nowcast_backtest,
    score_predictions,
    walk_forward,
)


def _months(n: int, start: str = "2014-01-01") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="MS")


def _target_driven_by(driver: np.ndarray, beta: float, seed: int, noise: float = 0.6) -> pd.Series:
    """A persistent monthly index whose CHANGE responds to last month's driver.

    Mirrors how a diffusion index actually behaves: strongly autocorrelated in
    level, with the interesting part in the month-over-month change.
    """
    rng = np.random.default_rng(seed)
    n = len(driver)
    level = np.zeros(n)
    level[0] = 50.0
    for t in range(1, n):
        level[t] = level[t - 1] + beta * driver[t - 1] + rng.normal(0, noise)
    return pd.Series(level, index=_months(n))


# ── no look-ahead ───────────────────────────────────────────────────────────

def test_a_feature_cannot_appear_in_its_own_month():
    """The row for month M must carry the feature's change from month M-1."""
    idx = _months(24)
    spike = pd.Series(0.0, index=idx)
    spike.iloc[10] = 100.0                       # a single, unmistakable month
    target = pd.Series(np.arange(24, dtype=float) + 50.0, index=idx)

    X, y = build_design(target, {"spike": spike}, feature_lag_months=1)

    assert X.loc[idx[10], "spike"] == 0.0, (
        "month 10's row saw month 10's own spike — that is look-ahead"
    )
    assert X.loc[idx[11], "spike"] == pytest.approx(100.0), (
        "the spike should surface one month later, as a lagged change"
    )


def test_predictions_do_not_change_when_future_data_arrives():
    """The strongest guard here.

    A prediction for month t was made with rows 0..t-1. Appending months after
    t cannot alter it. Any leak that works by fitting or standardising over the
    whole sample breaks this immediately, and breaks it silently otherwise.
    """
    n = 90
    rng = np.random.default_rng(11)
    driver = rng.normal(0, 1, n)
    target = _target_driven_by(driver, beta=0.9, seed=3)
    feat = pd.Series(np.cumsum(driver), index=_months(n))

    X, y = build_design(target, {"driver": feat}, feature_lag_months=1)

    full = walk_forward(X, y, min_train=MIN_TRAIN_MONTHS)
    truncated = walk_forward(X.iloc[:60], y.iloc[:60], min_train=MIN_TRAIN_MONTHS)

    assert not truncated.empty
    overlap = truncated.index.intersection(full.index)
    assert len(overlap) >= 10, "need a meaningful overlap to compare"

    np.testing.assert_allclose(
        full.loc[overlap, "predicted"].to_numpy(),
        truncated.loc[overlap, "predicted"].to_numpy(),
        rtol=1e-9, atol=1e-9,
        err_msg="a past prediction moved when future rows were appended — the fit "
                "or the standardisation is seeing the whole sample",
    )


def test_lag_zero_is_refused_rather_than_approximated():
    """A true nowcast needs intra-month release cutoffs. Until those exist,
    silently allowing lag 0 would leak days of future data."""
    idx = _months(20)
    with pytest.raises(ValueError, match="feature_lag_months"):
        build_design(
            pd.Series(np.arange(20, dtype=float), index=idx),
            {"f": pd.Series(np.arange(20, dtype=float), index=idx)},
            feature_lag_months=0,
        )


# ── the baseline is the real one ────────────────────────────────────────────

def test_the_naive_forecast_is_last_months_level():
    n = 70
    rng = np.random.default_rng(5)
    driver = rng.normal(0, 1, n)
    target = _target_driven_by(driver, beta=0.8, seed=9)
    feat = pd.Series(np.cumsum(driver), index=_months(n))
    X, y = build_design(target, {"driver": feat}, feature_lag_months=1)

    frame = walk_forward(X, y, min_train=MIN_TRAIN_MONTHS)
    assert not frame.empty

    for when in frame.index:
        position = y.index.get_loc(when)
        assert frame.loc[when, "naive"] == pytest.approx(y.iloc[position - 1]), (
            "naive must be the previous observed level, not a mean or a zero"
        )


def test_skill_is_measured_against_naive_not_against_zero():
    frame = pd.DataFrame(
        {"actual": [50.0, 52.0, 51.0], "predicted": [50.0, 52.0, 51.0], "naive": [48.0, 50.0, 52.0]},
        index=_months(3),
    )
    scored = score_predictions(frame)
    assert scored["rmse_model"] == 0.0
    assert scored["rmse_naive"] > 0
    assert scored["skill"] == pytest.approx(1.0)
    assert scored["beats_naive"] is True


# ── it can find signal, and it does not invent it ───────────────────────────

def test_a_genuinely_predictive_feature_beats_the_naive_forecast():
    """Sanity in the other direction: if the harness could never win, its
    failures would mean nothing."""
    n = 140
    rng = np.random.default_rng(21)
    driver = rng.normal(0, 1, n)
    target = _target_driven_by(driver, beta=2.5, seed=4, noise=0.4)
    feat = pd.Series(np.cumsum(driver), index=_months(n))

    result = run_nowcast_backtest(target, {"driver": feat})
    assert result.available is True, result.reason
    assert result.beats_naive is True, (
        f"a strong, correctly-lagged driver should beat persistence; "
        f"skill={result.skill}, rmse_model={result.rmse_model}, rmse_naive={result.rmse_naive}"
    )
    assert result.skill > 0.25


def test_pure_noise_features_do_not_manufacture_skill():
    """Twelve unrelated series against a persistent target. The honest outcome
    is roughly zero skill or worse — never a confident win."""
    n = 140
    rng = np.random.default_rng(77)
    target = _target_driven_by(rng.normal(0, 1, n), beta=0.0, seed=8, noise=1.0)
    features = {
        f"noise_{i}": pd.Series(np.cumsum(rng.normal(0, 1, n)), index=_months(n))
        for i in range(12)
    }

    result = run_nowcast_backtest(target, features)
    assert result.available is True, result.reason
    assert result.skill is not None
    assert result.skill < 0.15, (
        f"noise produced skill={result.skill}; the harness is flattering itself"
    )


def test_losing_to_the_naive_forecast_is_reported_not_hidden():
    n = 120
    rng = np.random.default_rng(31)
    target = _target_driven_by(rng.normal(0, 1, n), beta=0.0, seed=12, noise=1.2)
    features = {f"n{i}": pd.Series(np.cumsum(rng.normal(0, 1, n)), index=_months(n))
                for i in range(15)}

    result = run_nowcast_backtest(target, features)
    assert result.available is True
    assert isinstance(result.beats_naive, bool), (
        "a loss must be a reportable False, never None or an empty success"
    )
    assert result.n_scored > 0


# ── unavailable is not zero ─────────────────────────────────────────────────

def test_thin_history_is_unavailable_with_a_reason():
    idx = _months(10)
    result = run_nowcast_backtest(
        pd.Series(np.arange(10, dtype=float) + 50, index=idx),
        {"f": pd.Series(np.arange(10, dtype=float), index=idx)},
    )
    assert result.available is False
    assert result.rmse_model is None and result.skill is None, (
        "an uncomputable score must stay None; 0.0 would read as a perfect model"
    )
    assert "aligned months" in result.reason


def test_no_features_is_unavailable_not_a_silent_success():
    idx = _months(60)
    result = run_nowcast_backtest(pd.Series(np.arange(60, dtype=float), index=idx), {})
    assert result.available is False
    assert result.skill is None
    assert result.reason


def test_monthly_aggregate_never_invents_a_missing_month():
    """A month with no observations stays missing. Interpolating would make an
    invented input indistinguishable from a measured one."""
    days = pd.date_range("2020-01-01", "2020-05-31", freq="D")
    s = pd.Series(1.0, index=days)
    s.loc["2020-03-01":"2020-03-31"] = np.nan

    monthly = monthly_aggregate(s)
    assert pd.Timestamp("2020-03-01") not in monthly.index
    assert len(monthly) == 4


def test_the_target_is_named_for_the_series_it_actually_uses():
    """utils/config.py keys the Philadelphia Fed index as "ism_pmi". ISM's PMI
    is licensed and is not on FRED. This module must not inherit that."""
    from utils import nowcast

    assert NOWCAST_TARGET_SERIES == "GACDFSA066MSFRBPHI"
    assert "Philadelphia" in nowcast.NOWCAST_TARGET_NAME
    assert "ISM" not in nowcast.NOWCAST_TARGET_NAME


def test_the_ridge_penalty_is_not_tuned_against_the_evaluation_window():
    """Selecting alpha on the scored months is the fastest way to a result that
    does not replicate. It must be a stated constant."""
    source = (_ROOT / "utils" / "nowcast.py").read_text(encoding="utf-8")
    assert "RIDGE_ALPHA" in source
    for banned in ("best_alpha", "for alpha in", "grid_search", "argmin(scores"):
        assert banned not in source, (
            f"{banned!r} suggests alpha is being searched; if that is added it must "
            f"search INSIDE each training window, never across the scored months"
        )


# ── the predictors are pre-specified, not discovered ────────────────────────

def test_the_feature_set_is_pre_specified_and_documented():
    """Choosing predictors because they scored well is how the Confluence Score
    ended up with 47 signals and no mechanism. Each entry must be named in the
    module with a reason beside it."""
    from utils.nowcast import NOWCAST_FEATURE_SIGNALS

    source = (_ROOT / "utils" / "nowcast.py").read_text(encoding="utf-8")
    spec = source[source.index("PRE-SPECIFIED PREDICTORS"):source.index("NOWCAST_FEATURE_SIGNALS: tuple")]

    assert 5 <= len(NOWCAST_FEATURE_SIGNALS) <= 12, (
        f"{len(NOWCAST_FEATURE_SIGNALS)} predictors against ~120 monthly observations "
        f"is either too few to be useful or enough to fit anything"
    )
    for sig_id in NOWCAST_FEATURE_SIGNALS:
        assert sig_id in spec, (
            f"{sig_id} is used as a predictor but has no stated mechanism in the "
            f"pre-specification comment"
        )


def test_every_predictor_actually_exists_in_the_signal_config():
    """A typo here fetches nothing and quietly shrinks the model."""
    from utils.config import SIGNALS
    from utils.nowcast import NOWCAST_FEATURE_SIGNALS

    unknown = [s for s in NOWCAST_FEATURE_SIGNALS if s not in SIGNALS]
    assert not unknown, f"predictors not present in SIGNALS: {unknown}"


def test_the_target_is_not_also_a_predictor():
    """Regressing the index on itself would produce a spectacular, meaningless
    skill score."""
    from utils.config import SIGNALS
    from utils.nowcast import NOWCAST_FEATURE_SIGNALS, NOWCAST_TARGET_SERIES

    for sig_id in NOWCAST_FEATURE_SIGNALS:
        assert SIGNALS[sig_id].get("series_id") != NOWCAST_TARGET_SERIES, (
            f"{sig_id} carries the target series — that is the target leaking in "
            f"as a feature"
        )


def test_the_backtest_script_refuses_to_run_without_a_key():
    """It must not fall back to synthetic data and present the result as real."""
    source = (_ROOT / "scripts" / "backtest_nowcast.py").read_text(encoding="utf-8")
    assert "FRED_API_KEY" in source
    assert "point_in_time=True" in source, (
        "the backtest must read first-print history; revised values would score "
        "the model against numbers nobody could have known at the time"
    )
