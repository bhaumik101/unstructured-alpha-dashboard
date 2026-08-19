"""
Unit tests for the second-audit foundation layer:
  utils/taxonomy.py       — canonical macro-factor taxonomy (Phase 6)
  utils/coverage.py       — coverage tiers + confidence methodology (Phases 4/5)
  utils/product_metrics.py — product-metric single source of truth (Phase 7)

taxonomy and coverage are import-clean (no config); product_metrics needs a
stubbed config (it computes counts from the registry).
"""

import sys
import types

import pytest

_stub = types.ModuleType("utils.config")
# These sizes must mirror the REAL registry, because sys.modules.setdefault()
# below only applies when utils.config has not been imported yet -- so whether
# product_metrics derives its counts from the stub or from the real module
# depends purely on collection order. With TICKERS at a stale 193 this file
# passed inside the full suite and failed on its own, which is the signature of
# a test that is measuring the order it ran in.
_stub.SIGNALS = {f"s{i}": {"source": "fred"} for i in range(47)}    # ACTIVE_SIGNAL_COUNT
_stub.TICKERS = {f"T{i}": {} for i in range(280)}                   # SUPPORTED_TICKER_COUNT
_stub.CATEGORIES = {"ai_infrastructure": {"name": "AI Infrastructure"}}
import utils as _utils_pkg
_real_cfg_mod  = sys.modules.get("utils.config")
_real_cfg_attr = getattr(_utils_pkg, "config", None)
sys.modules.setdefault("utils.config", _stub)

from utils import taxonomy as tx          # noqa: E402
from utils import coverage as cov          # noqa: E402
from utils import product_metrics as pm    # noqa: E402

# Put the real utils.config back. The modules imported just above keep whatever
# they bound from the stub -- that is the isolation this file wants -- but
# leaving the stub in sys.modules replaces utils.config PROCESS-WIDE for the
# rest of this xdist worker. Measured: a probe run after this file saw
# utils.config with __file__ = None, i.e. the stub, reporting fake SIGNALS and
# TICKERS; after the 6-signal variant in test_score_explainer_unit.py it could
# not import from utils.product_metrics at all.
if _real_cfg_mod is not None:
    sys.modules["utils.config"] = _real_cfg_mod
else:
    sys.modules.pop("utils.config", None)
if _real_cfg_attr is not None:
    _utils_pkg.config = _real_cfg_attr
else:
    try:
        del _utils_pkg.config
    except AttributeError:
        pass



# ── Taxonomy ─────────────────────────────────────────────────────────────────
def test_taxonomy_internal_consistency():
    assert len(tx.FACTOR_FAMILIES) == 11
    assert len(tx.SIGNAL_FACTOR) == 47
    # every mapped family is a known family — no orphan pointers
    assert all(v in tx.FACTOR_FAMILIES for v in tx.SIGNAL_FACTOR.values())
    assert tx.factor_family_of("ten_year_yield") == "rates"
    assert tx.factor_family_name("rates") == "Rates"
    assert tx.factor_family_name_of("hy_spread") == "Credit"


def test_category_display_fixes_raw_enum_bug():
    # the exact "Ai_Infrastructure" embarrassment
    assert tx.category_display("ai_infrastructure") == "AI Infrastructure"
    assert "_" not in tx.category_display("some_new_enum")
    assert tx.category_display("ai_something").startswith("AI ")
    # a passed CATEGORIES dict is authoritative
    assert tx.category_display("x", {"x": {"name": "Custom"}}) == "Custom"


# ── Coverage tiers ───────────────────────────────────────────────────────────
def test_coverage_tiers():
    assert cov.coverage_tier(12)["id"] == "full" and cov.coverage_tier(12)["generates_score"]
    assert cov.coverage_tier(7)["id"] == "moderate"
    assert cov.coverage_tier(3)["id"] == "limited"
    t1 = cov.coverage_tier(1)
    assert t1["id"] == "insufficient" and t1["generates_score"] is False
    assert cov.coverage_tier(0)["id"] == "insufficient"


# ── Confidence: coverage-dominated, hard-capped ──────────────────────────────
def test_confidence_hard_caps():
    # 1 significant → Insufficient, no score at all
    c1 = cov.assess_confidence(1, 1, 12, 0, 1.0)
    assert c1["level"] == "Insufficient" and c1["score"] is None
    # 3 fresh, perfectly-agreeing signals STILL cap at Limited — the key rule
    assert cov.assess_confidence(3, 3, 12, 0, 1.0)["level"] == "Limited"
    # 5 caps at Moderate even when fresh + agreeing
    assert cov.assess_confidence(5, 5, 12, 0, 1.0)["level"] == "Moderate"
    # 10 fresh, agreeing → High
    assert cov.assess_confidence(10, 10, 12, 0, 0.9)["level"] == "High"


def test_confidence_freshness_and_shape():
    fresh = cov.assess_confidence(10, 10, 12, 0, 0.9)
    stale = cov.assess_confidence(10, 10, 12, 8, 0.9)
    assert stale["score"] < fresh["score"]
    assert any("stale" in r for r in stale["reasons"])
    assert set(fresh["components"]) == {"coverage", "freshness", "agreement", "validation"}


# ── Product metrics SSOT ─────────────────────────────────────────────────────
def test_product_metrics():
    assert pm.ACTIVE_SOURCE_COUNT == len(pm.PRIMARY_SOURCES) == 13
    assert pm.ACTIVE_SIGNAL_COUNT == 47          # computed from the (stubbed) registry
    assert pm.SUPPORTED_TICKER_COUNT == 280
    assert len(pm.source_names()) == 13
    assert pm.signals_phrase() == "47 registered signals"
