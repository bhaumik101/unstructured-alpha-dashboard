"""Tests for utils.risk_profile — validation + personalized ("Your Score") math."""
import copy

from utils import risk_profile as rp
from utils.config import SIGNALS

# Real signal ids grouped by lag, so horizon filtering is exercised against the
# actual signal registry rather than invented ids.
_SHORT_IDS = [s for s, c in SIGNALS.items() if float(c.get("lag_weeks") or 4) <= 3][:3]
_LONG_IDS = [s for s, c in SIGNALS.items() if float(c.get("lag_weeks") or 4) >= 9][:2]


def _full(**over):
    ids = _SHORT_IDS + _LONG_IDS
    base = {
        "confluence": {"overall_score": 70.0, "conviction": "High", "case": "BULLISH"},
        "signal_scores": {s: {"score": 75.0, "status": "bullish"} for s in ids},
        "corr_info": {},
        "momentum_score": 50.0,
        "insider_score": {"score": 80.0, "status": "bullish"},
        "has_insider_signal": True,
        "short_interest_score": {"score": 60.0, "status": "neutral"},
        "has_short_interest_signal": True,
        "thirteenf_score": {"score": 70.0, "status": "bullish"},
        "has_13f_signal": True,
    }
    base.update(over)
    return base


# ── validation ────────────────────────────────────────────────────────────────
def test_normalize_defaults_on_junk():
    for junk in (None, 0, "not json", [], {"tolerance": "wat"}):
        assert rp.normalize(junk) == rp.DEFAULT_PROFILE


def test_normalize_accepts_json_string():
    s = '{"tolerance":"aggressive","horizon":"short","emphasis":"full"}'
    assert rp.normalize(s) == {"tolerance": "aggressive", "horizon": "short", "emphasis": "full"}


def test_normalize_partial_keeps_defaults():
    out = rp.normalize({"tolerance": "conservative"})
    assert out["tolerance"] == "conservative"
    assert out["horizon"] == rp.DEFAULT_PROFILE["horizon"]


def test_is_default():
    assert rp.is_default(None)
    assert not rp.is_default({"tolerance": "aggressive"})


# ── personalized score ────────────────────────────────────────────────────────
def test_balanced_all_matches_canonical_blend_shape():
    out = rp.compute_personal_score(_full(), rp.DEFAULT_PROFILE)
    assert out["ok"] is True
    assert 0 <= out["score"] <= 100
    assert out["macro_share"] == 0.80          # canonical blend
    assert out["n_signals"] == out["n_total"]  # "all" horizon keeps everything


def test_canonical_result_is_never_mutated():
    full = _full()
    snapshot = copy.deepcopy(full)
    rp.compute_personal_score(full, {"tolerance": "aggressive", "horizon": "short", "emphasis": "full"})
    assert full == snapshot, "compute_personal_score must not mutate the input"


def test_horizon_filters_signal_count():
    if not _SHORT_IDS or not _LONG_IDS:
        return  # registry lacks both bands — nothing to assert
    out = rp.compute_personal_score(_full(), {"horizon": "short"})
    assert out["horizon_applied"] is True
    assert out["n_signals"] == len(_SHORT_IDS)
    assert out["n_signals"] < out["n_total"]


def test_horizon_falls_back_when_nothing_matches():
    # Only long-lag signals present, but user asks for short → must fall back,
    # not return an empty/garbage score.
    full = _full(signal_scores={s: {"score": 75.0, "status": "bullish"} for s in _LONG_IDS})
    out = rp.compute_personal_score(full, {"horizon": "short"})
    assert out["ok"] is True
    assert out["n_signals"] == len(_LONG_IDS)


def test_tolerance_shifts_weight_to_momentum():
    full = _full(momentum_score=100.0)  # momentum maxed → aggressive should score higher
    cons = rp.compute_personal_score(full, {"tolerance": "conservative", "emphasis": "macro"})
    aggr = rp.compute_personal_score(full, {"tolerance": "aggressive", "emphasis": "macro"})
    assert aggr["score"] > cons["score"]
    assert aggr["mom_share"] > cons["mom_share"]


def test_emphasis_macro_excludes_alt_data():
    out = rp.compute_personal_score(_full(), {"emphasis": "macro"})
    assert out["alt"] is None and out["alt_share"] == 0.0


def test_emphasis_full_includes_alt_data():
    out = rp.compute_personal_score(_full(), {"emphasis": "full"})
    assert out["alt"] is not None and out["alt_share"] == 0.20


def test_alt_absent_when_no_signals_available():
    full = _full(has_insider_signal=False, has_short_interest_signal=False, has_13f_signal=False)
    out = rp.compute_personal_score(full, {"emphasis": "full"})
    assert out["alt"] is None and out["alt_share"] == 0.0


def test_delta_vs_canonical_reported():
    out = rp.compute_personal_score(_full(), rp.DEFAULT_PROFILE)
    assert out["canonical"] == 70.0
    assert out["delta"] == round(out["score"] - 70.0, 1)


def test_degrades_gracefully_on_empty_signals():
    out = rp.compute_personal_score({"confluence": {"overall_score": 55.0}, "signal_scores": {}}, None)
    assert out["ok"] is False
    assert out["score"] == 55.0          # falls back to canonical
    assert "standard score" in out["explanation"]


def test_never_raises_on_garbage_input():
    for junk in ({}, {"signal_scores": None}, {"confluence": None}):
        out = rp.compute_personal_score(junk, {"tolerance": "aggressive"})
        assert isinstance(out, dict) and "score" in out


def test_score_is_bounded():
    full = _full(momentum_score=1e9)
    out = rp.compute_personal_score(full, {"tolerance": "aggressive"})
    assert 0.0 <= out["score"] <= 100.0


def test_component_snapshot_reuses_personalization_without_live_result():
    signal_ids = _SHORT_IDS + _LONG_IDS
    components = {
        "final_score": 70.0,
        "momentum_score": 90.0,
        "signals": [
            {"id": sid, "score": 65.0, "weight": 0.5, "significant": True}
            for sid in signal_ids
        ],
        "components": [
            {"id": "insider", "kind": "optional", "score": 80.0},
        ],
    }

    out = rp.compute_personal_score_from_components(
        components, {"tolerance": "aggressive", "horizon": "short", "emphasis": "full"}
    )

    assert out["ok"] is True
    assert out["canonical"] == 70.0
    assert out["momentum"] == 90.0
    assert out["alt"] == 80.0
    if _SHORT_IDS and _LONG_IDS:
        assert out["n_signals"] == len(_SHORT_IDS)


def test_component_snapshot_helper_degrades_on_missing_data():
    out = rp.compute_personal_score_from_components(None, rp.DEFAULT_PROFILE)
    assert out["ok"] is False
    assert out["score"] is None
