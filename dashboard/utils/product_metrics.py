# utils/product_metrics.py
# Unstructured Alpha — Product Metrics single source of truth (Phase 7)
#
# The website used to claim "43 signals" while another surface said "46 other
# data sources". That kind of drift is a credibility own-goal. This module is
# the ONE place product-fact numbers live. Every surface — landing page, app,
# SEO templates, methodology, emails — should import these rather than hardcode
# a number that will silently rot. Where a number can be COMPUTED from the real
# registry (signal count, ticker count) it is, so it can never disagree with the
# model. A test asserts the computed ones match the registry.

from __future__ import annotations

from utils.config import SIGNALS, TICKERS

# ── Computed from the live registry (cannot drift from the model) ────────────
ACTIVE_SIGNAL_COUNT: int = len(SIGNALS)
SUPPORTED_TICKER_COUNT: int = len(TICKERS)

# ── Canonical primary data providers ─────────────────────────────────────────
# The precise, honest expansion of the "7+ sources" claim. Ordered.
PRIMARY_SOURCES: dict[str, str] = {
    "fred":          "FRED (Federal Reserve economic data)",
    "eia":           "EIA (energy inventories)",
    "ny_fed":        "New York Fed (supply-chain pressure)",
    "yahoo":         "Yahoo Finance (prices and options)",
    "sec_edgar":     "SEC EDGAR (insider, 8-K, and 13F filings)",
    "finra":         "FINRA (short interest)",
    "cftc":          "CFTC (commitments of traders)",
    "usaspending":   "USASpending.gov (federal awards)",
    "congress":      "Congressional disclosure feeds",
    "openfda":       "openFDA (approval activity)",
    "arxiv":         "arXiv (research velocity)",
    "google_trends": "Google Trends (search interest)",
    "federal_reserve":"Federal Reserve communications",
}
ACTIVE_SOURCE_COUNT: int = len(PRIMARY_SOURCES)

# ── Refresh / recency copy ────────────────────────────────────────────────────
# Two different things were being conflated, and every public surface picked a
# different one. They are not the same number and never were:
#
#   SCORE_REFRESH_*  how long the app caches provider data. A real TTL, consumed
#                    by utils/signals_cache.py. Says nothing about scoring.
#   SCORE_COMPUTE_*  how often the Confluence Scores are actually recomputed, by
#                    the scoring crons in render.yaml.
#
# The landing page claimed scores were "updated every ~2 hours" in six places.
# Nothing scores every two hours -- `0 */2 * * *` is threshold-alert evaluation.
# Scores are recomputed daily for the core tier (score-core, "10 4 * * *") and
# Mon/Wed/Fri for the rest of the universe (score-rest, "40 5 * * 1,3,5").
# Keep these phrased in plain English; the exact cron expressions live in
# render.yaml and on the methodology page, not in customer-facing copy.
SCORE_REFRESH_HOURS: int = 6
SCORE_REFRESH_DESCRIPTION: str = "refreshed at most every 6 hours"
SCORE_COMPUTE_DESCRIPTION: str = (
    "scored daily, with the full universe refreshed three times a week"
)
SCORE_COMPUTE_SHORT: str = "scored daily"
LAST_MODEL_UPDATE: str = "2026-07-13"

# ── Pricing (kept here so copy never disagrees with billing) ─────────────────
FREE_PRICE: int = 0
PRO_PRICE_MONTHLY: int = 20
PRO_PRICE_ANNUAL_PER_MONTH: int = 16


def source_names() -> list[str]:
    """Display names of the primary data providers, in canonical order.

    NOTE: this is every provider the product touches ANYWHERE, including ones
    that power per-ticker analysis (SEC EDGAR insider filings, FINRA short
    interest) rather than the macro signal library. Do not use it to describe
    where the signals come from -- use signal_source_labels() for that.
    """
    return list(PRIMARY_SOURCES.values())


def signal_source_labels(*, short: bool = True) -> list[str]:
    """Providers that actually feed the macro signal library, most-used first.

    Derived from the SIGNALS config rather than hand-listed, because the two
    drifted: the Signal Dashboard advertised "FRED / EIA / SEC EDGAR / FINRA /
    yfinance" as the signal sources while zero signals were sourced from SEC
    EDGAR or FINRA (those power Ticker Deep Dive instead). Reading the config
    means the claim cannot go stale again.
    """
    from collections import Counter

    from utils.config import SIGNALS
    from utils.provider_health import canonical_provider, provider_label

    counts = Counter(canonical_provider(cfg.get("source")) for cfg in SIGNALS.values())
    labels = []
    for provider, _n in counts.most_common():
        label = provider_label(provider)
        labels.append(label.split(" (")[0] if short else label)
    return labels


def signal_sources_phrase(*, limit: int = 5) -> str:
    """Short 'A / B / C' string naming the real signal sources for UI captions."""
    labels = signal_source_labels()
    if len(labels) <= limit:
        return " / ".join(labels)
    return " / ".join(labels[:limit]) + f" +{len(labels) - limit} more"


def signals_phrase() -> str:
    """A ready-to-use, always-correct phrase for marketing/UI copy."""
    return f"{ACTIVE_SIGNAL_COUNT} registered signals"


def sources_phrase() -> str:
    return f"{ACTIVE_SOURCE_COUNT} real-data source families"
