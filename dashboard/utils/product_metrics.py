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
SCORE_REFRESH_HOURS: int = 2
SCORE_REFRESH_DESCRIPTION: str = "updated every ~2 hours"
LAST_MODEL_UPDATE: str = "2026-07-13"

# ── Pricing (kept here so copy never disagrees with billing) ─────────────────
FREE_PRICE: int = 0
PRO_PRICE_MONTHLY: int = 20
PRO_PRICE_ANNUAL_PER_MONTH: int = 16


def source_names() -> list[str]:
    """Display names of the primary data providers, in canonical order."""
    return list(PRIMARY_SOURCES.values())


def signals_phrase() -> str:
    """A ready-to-use, always-correct phrase for marketing/UI copy."""
    return f"{ACTIVE_SIGNAL_COUNT} registered signals"


def sources_phrase() -> str:
    return f"{ACTIVE_SOURCE_COUNT} real-data source families"
