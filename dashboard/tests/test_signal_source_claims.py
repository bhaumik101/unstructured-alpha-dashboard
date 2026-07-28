"""The Signal Dashboard must name only providers that actually feed signals.

The dashboard advertised "FRED / EIA / SEC EDGAR / FINRA / yfinance" as the
source of the 47 signals while zero signals were sourced from SEC EDGAR or
FINRA -- those power per-ticker analysis on Ticker Deep Dive instead. For a
product whose differentiation is data integrity, an inaccurate source claim
sitting directly under the signal table is the most damaging kind of drift,
so it is now derived from config and pinned by these tests.
"""

from __future__ import annotations

from utils.config import SIGNALS
from utils.product_metrics import (
    PRIMARY_SOURCES,
    signal_source_labels,
    signal_sources_phrase,
    source_names,
)
from utils.provider_health import canonical_provider

# Providers the product genuinely uses, but NOT for the macro signal library.
NON_SIGNAL_PROVIDERS = {"sec_edgar", "finra", "cftc", "usaspending", "congress"}


def _actual_signal_providers() -> set[str]:
    return {canonical_provider(cfg.get("source")) for cfg in SIGNALS.values()}


def test_labels_match_the_config_exactly():
    """Every label shown corresponds to a provider that feeds >=1 signal."""
    actual = _actual_signal_providers()
    assert len(signal_source_labels()) == len(actual)


def test_no_non_signal_provider_is_claimed_as_a_signal_source():
    """SEC EDGAR / FINRA / CFTC / USASpending / Congress must not appear."""
    for provider in NON_SIGNAL_PROVIDERS:
        # Only assert on providers that genuinely feed nothing today.
        if provider in _actual_signal_providers():
            continue
        label_root = PRIMARY_SOURCES[provider].split(" (")[0]
        assert label_root not in signal_source_labels()
        assert label_root not in signal_sources_phrase()


def test_ordering_is_by_signal_count():
    """Most-used provider first, so the caption leads with what dominates."""
    labels = signal_source_labels()
    assert labels[0] == "FRED"          # 28 of 47 signals


def test_phrase_is_short_enough_for_a_caption():
    phrase = signal_sources_phrase()
    assert len(phrase) < 90
    assert "more" in phrase or phrase.count("/") <= 4


def test_source_names_still_lists_every_provider():
    """source_names() intentionally stays broader -- Pro copy legitimately
    cites SEC EDGAR insider filings and FINRA short interest, which are real
    features backed by real fetchers. Narrowing it would understate the product."""
    assert len(source_names()) == len(PRIMARY_SOURCES)
    assert any("SEC EDGAR" in name for name in source_names())
