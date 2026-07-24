"""
Unit tests for utils/validation_status.py -- the Model Validation
Dashboard's data layer. Per the explicit standard set for this feature
("don't add anything unless it is absolutely perfect and flawless"),
these tests check more than "doesn't crash": they verify the actual
disclosed numbers are word-for-word what the real source docstrings say,
that every signal always gets an entry (even on fetch failure), and that
nothing here silently overstates validation status.
"""

import re

import pandas as pd
import pytest

from utils import analysis
from utils.config import SIGNALS
from utils.validation_status import (
    backtest_all_macro_signals, validate_all_macro_signals, get_static_validation_summary,
)
from tests.test_lead_time_research_unit import _make_signal_and_lagged_price, _make_pure_noise


def _normalize_whitespace(text: str) -> str:
    """Docstrings wrap across lines for readability; collapse any run of
    whitespace (including newlines) to a single space before comparing
    fragments, so a harmless line-wrap doesn't register as a content
    mismatch."""
    return re.sub(r"\s+", " ", text).strip()


# ── get_static_validation_summary() ──────────────────────────────────────────

def test_returns_exactly_five_categories():
    summary = get_static_validation_summary()
    categories = {entry["category"] for entry in summary}
    assert len(summary) == 5
    assert categories == {
        "Confluence Score (per-ticker macro composite)",
        "Power Supercycle Score",
        "Insider Activity (Form 4 open-market buys/sells)",
        "Short Interest (FINRA consolidated)",
        "13F Institutional Positioning",
    }


def test_every_entry_has_required_fields_nonempty():
    for entry in get_static_validation_summary():
        for field in ("category", "status", "detail", "source"):
            assert entry.get(field), f"{entry.get('category')} missing or empty '{field}'"


def test_supercycle_backtest_numbers_match_source_docstring_verbatim():
    """
    The single most important test in this file: the Power Supercycle
    entry's disclosed backtest result must be word-for-word what
    compute_supercycle_score()'s actual docstring says RIGHT NOW, not a
    paraphrase that could quietly drift out of sync if the docstring is
    ever updated after a re-backtest. Reads the live docstring directly
    rather than hard-coding the expected text twice.
    """
    summary = get_static_validation_summary()
    supercycle = next(e for e in summary if e["category"] == "Power Supercycle Score")
    docstring = _normalize_whitespace(analysis.compute_supercycle_score.__doc__)
    detail = _normalize_whitespace(supercycle["detail"])

    # The specific, checkable numbers -- if a future re-backtest changes
    # these, this test should fail until validation_status.py is updated
    # to match, not the other way around.
    for fragment in ("all |r| < 0.07", "p > 0.5 pooled", "CEG, VST, NEE, ETN, VRT, PWR"):
        assert fragment in docstring, f"Expected fragment not found in current docstring: {fragment!r}"
        assert fragment in detail, (
            f"validation_status.py's claim has drifted from the source docstring: {fragment!r}"
        )


def test_confluence_backtest_numbers_match_source_docstring_verbatim():
    summary = get_static_validation_summary()
    confluence = next(e for e in summary if e["category"] == "Confluence Score (per-ticker macro composite)")
    docstring = _normalize_whitespace(analysis.compute_confluence.__doc__)
    detail = _normalize_whitespace(confluence["detail"])

    for fragment in ("pooled across 6 tickers", "it does not yet mean they're right"):
        assert fragment in docstring, f"Expected fragment not found in current docstring: {fragment!r}"
        assert fragment in detail, (
            f"validation_status.py's claim has drifted from the source docstring: {fragment!r}"
        )


def test_status_labels_never_overclaim_validation():
    """
    Confluence and Supercycle must NEVER be labeled as "validated" --
    their own backtests found no significant relationship. Insider/Short
    Interest must be framed as per-ticker/on-demand, never as a single
    blanket "validated" claim (that would overstate what a methodology
    being AVAILABLE means vs. a specific ticker actually having been
    tested and held up).
    """
    summary = get_static_validation_summary()
    for entry in summary:
        if "Confluence" in entry["category"] or "Supercycle" in entry["category"]:
            assert "NOT validated" in entry["status"]
            assert entry["status"] != "Validated"
        if "Insider" in entry["category"] or "Short Interest" in entry["category"]:
            assert "on demand" in entry["status"].lower()
            assert entry["status"] != "Validated"


# ── backtest_all_macro_signals() ─────────────────────────────────────────────

def test_backtest_returns_an_entry_for_every_signal(monkeypatch):
    """
    Every signal must get a result dict, even ones whose fetch fails --
    the Model Validation Dashboard's "N of M validated" count depends on
    every signal being represented, not silently dropped on error.
    """
    # Force every fetch to fail, to exercise the except-path for ALL
    # signals deterministically rather than relying on whichever ones
    # happen to fail due to no network access in this environment.
    monkeypatch.setattr(
        "utils.validation_status.fetch_signal_series",
        lambda cfg, start, end, point_in_time=False: (_ for _ in ()).throw(RuntimeError("no network")),
    )
    backtest_all_macro_signals.clear()  # bypass the 24h cache for this test
    results = backtest_all_macro_signals()

    assert set(results.keys()) == set(SIGNALS.keys())
    for sig_id, result in results.items():
        assert result["backtested"] is False, f"{sig_id} should not claim backtested on a forced failure"
        assert result["pcs"] is None


def test_backtest_result_shape_is_consistent_on_failure(monkeypatch):
    monkeypatch.setattr(
        "utils.validation_status.fetch_signal_series",
        lambda cfg, start, end, point_in_time=False: (_ for _ in ()).throw(RuntimeError("no network")),
    )
    backtest_all_macro_signals.clear()
    results = backtest_all_macro_signals()

    first = next(iter(results.values()))
    expected_keys = {"pcs", "backtested", "n_tested", "significance_rate", "avg_abs_r", "details"}
    assert set(first.keys()) == expected_keys


# ── validate_all_macro_signals() -- the universal lag-validation rollout ────
# (2026-06-22: every macro signal now gets the SAME out-of-sample +
# Bonferroni-corrected methodology previously built only for insider
# activity / short interest.) Uses a small, monkeypatched SIGNALS dict and
# the SAME synthetic ground-truth generators already proven for
# lag_scan_with_validation() in test_lead_time_research_unit.py, rather
# than real network fetches -- fast, deterministic, and an actual test of
# whether the wiring recovers a known answer, not just "doesn't crash".

_FAKE_SIGNALS = {
    "fake_strong": {
        "name": "Fake Strong Signal", "category": "macro", "lag_weeks": 6,
        "inverse": False, "pcs": 7, "relevant_tickers": ["AAA", "BBB", "CCC"],
    },
    "fake_noise": {
        "name": "Fake Noise Signal", "category": "macro", "lag_weeks": 4,
        "inverse": False, "pcs": 5, "relevant_tickers": ["DDD", "EEE", "FFF"],
    },
    "fake_no_tickers": {
        "name": "Fake No-Ticker Signal", "category": "macro", "lag_weeks": 0,
        "inverse": False, "pcs": 3, "relevant_tickers": [],
    },
}


def _patch_fake_universe(monkeypatch, strong_seed=7, noise_seed=11):
    """
    Wires validate_all_macro_signals() to a tiny, fully synthetic universe:
    "fake_strong" gets the SAME injected lag-6 relationship already proven
    to be recoverable by lag_scan_with_validation() directly; "fake_noise"
    gets pure noise; "fake_no_tickers" exercises the zero-relevant-tickers
    fallback path. One shared signal series + per-ticker price series so
    every "ticker" in a signal's relevant_tickers sees a consistent
    relationship, the way a real macro signal's tickers would.
    """
    strong_signal, strong_price = _make_signal_and_lagged_price(seed=strong_seed, true_lag=6)
    noise_signal, noise_price = _make_pure_noise(seed=noise_seed)

    # A second, independent noise price series per extra ticker so pooling
    # doesn't just compare the exact same series to itself three times.
    _, strong_price_b = _make_signal_and_lagged_price(seed=strong_seed + 1, true_lag=6)
    _, noise_price_b = _make_pure_noise(seed=noise_seed + 1)

    price_lookup = {
        "AAA": strong_price, "BBB": strong_price_b, "CCC": strong_price,
        "DDD": noise_price, "EEE": noise_price_b, "FFF": noise_price,
    }
    signal_lookup = {"fake_strong": strong_signal, "fake_noise": noise_signal}

    monkeypatch.setattr("utils.validation_status.SIGNALS", _FAKE_SIGNALS)
    monkeypatch.setattr(
        "utils.validation_status.fetch_signal_series",
        lambda cfg, start, end, point_in_time=False: signal_lookup.get(
            next(k for k, v in _FAKE_SIGNALS.items() if v is cfg), pd.Series(dtype=float)
        ),
    )
    monkeypatch.setattr(
        "utils.validation_status.fetch_price",
        lambda ticker, start, end: price_lookup.get(ticker, pd.Series(dtype=float)),
    )
    validate_all_macro_signals.clear()


def test_validate_all_macro_signals_returns_entry_for_every_signal(monkeypatch):
    _patch_fake_universe(monkeypatch)
    results = validate_all_macro_signals()
    assert set(results.keys()) == set(_FAKE_SIGNALS.keys())
    for sig_id, r in results.items():
        assert set(r.keys()) == {"validation", "pooled", "reliability"}


def test_validate_all_macro_signals_handles_no_relevant_tickers_gracefully():
    """fake_no_tickers has an empty relevant_tickers list -- must get a
    clean "insufficient data" entry, never raise on an empty test_tickers
    list (e.g. test_tickers[0] on an empty list)."""
    # No fetch monkeypatching needed -- this path returns before any fetch.
    import utils.validation_status as vstatus
    from unittest.mock import patch

    with patch.object(vstatus, "SIGNALS", _FAKE_SIGNALS):
        vstatus.validate_all_macro_signals.clear()
        results = vstatus.validate_all_macro_signals()

    entry = results["fake_no_tickers"]
    assert entry["validation"]["error"] is not None
    assert entry["pooled"] is None
    assert entry["reliability"]["score"] == 0


def test_validate_all_macro_signals_recovers_strong_injected_relationship(monkeypatch):
    _patch_fake_universe(monkeypatch)
    results = validate_all_macro_signals()

    strong = results["fake_strong"]
    assert strong["validation"]["error"] is None
    assert strong["validation"]["best_lag"] == 6
    assert strong["validation"]["survives_correction"] is True
    assert strong["validation"]["holds_out_of_sample"] is True
    assert strong["pooled"] is not None
    assert strong["pooled"]["n_tickers"] == 2  # BBB, CCC (AAA is the primary, not pooled)
    assert strong["reliability"]["score"] >= 70
    assert strong["reliability"]["label"] == "Reasonably well-supported"


def test_validate_all_macro_signals_rejects_pure_noise(monkeypatch):
    _patch_fake_universe(monkeypatch)
    results = validate_all_macro_signals()

    noise = results["fake_noise"]
    assert noise["validation"]["error"] is None  # enough data to TEST -- just shouldn't pass
    assert noise["validation"]["holds_out_of_sample"] is False
    assert noise["reliability"]["score"] < 40
    assert noise["reliability"]["label"] == "Weak — likely noise"


def test_validate_all_macro_signals_reliability_score_has_full_component_breakdown(monkeypatch):
    """Same transparency requirement as compute_signal_reliability_score()
    itself: the rollout to macro signals must not start hiding the
    component breakdown just because it's now running at scale."""
    _patch_fake_universe(monkeypatch)
    results = validate_all_macro_signals()
    components = results["fake_strong"]["reliability"]["components"]
    assert set(components.keys()) == {
        "corrected_significance", "out_of_sample_validation", "sample_size", "pooled_confirmation",
    }
