"""
Config integrity checks for utils/config.py — SIGNALS, TICKERS, CATEGORIES.

These exist because this project has twice shipped a dangling reference:
once when oil_rig_count was removed but four tickers still listed it in
their "signals" list, and historically when FRED series IDs were guessed
rather than verified. These tests don't verify the series IDs are REAL
(that requires a live network call against FRED/EIA, which a unit test
shouldn't depend on) — but they do catch every dangling-reference and
missing-required-field class of bug for free, instantly, offline.
"""

from utils.config import SIGNALS, TICKERS, CATEGORIES, POWER_SUPERCYCLE_SIGNALS

REQUIRED_SIGNAL_KEYS = {
    "name", "tier", "pcs", "source", "frequency",
    "lag_weeks", "inverse", "unit", "description", "relevant_tickers",
    "category", "color",
}
# Multi-ticker composite signals (source "yfinance_multi"/"yfinance_basket")
# use "series_ids" (plural) instead of a single "series_id" — both are valid,
# checked separately below rather than folded into REQUIRED_SIGNAL_KEYS.

VALID_SOURCES = {"fred", "eia", "yfinance", "yfinance_basket", "yfinance_multi",
                 "yfinance_ratio", "arxiv", "fda", "google_trends", "fedspeaks",
                 "ny_fed_gscpi", "sec_xbrl_sum"}


def test_every_signal_has_required_keys():
    missing = {}
    for sig_id, cfg in SIGNALS.items():
        gaps = REQUIRED_SIGNAL_KEYS - cfg.keys()
        if gaps:
            missing[sig_id] = gaps
    assert not missing, f"Signals missing required keys: {missing}"


def test_every_signal_source_is_known():
    bad = {sig_id: cfg["source"] for sig_id, cfg in SIGNALS.items() if cfg["source"] not in VALID_SOURCES}
    assert not bad, f"Signals with unrecognized source (not wired into fetch_signal_series): {bad}"


def test_every_signal_has_a_nonempty_series_identifier():
    """Every signal must have either series_id (single) or series_ids (list,
    for multi-ticker composites like hyperscaler_capex) — never neither."""
    bad = []
    for sig_id, cfg in SIGNALS.items():
        has_single = str(cfg.get("series_id", "")).strip()
        has_multi = bool(cfg.get("series_ids"))
        if not has_single and not has_multi:
            bad.append(sig_id)
    assert not bad, f"Signals with no series_id and no series_ids: {bad}"


def test_no_signal_references_a_nonexistent_relevant_ticker():
    """Every ticker a signal claims is "relevant" must actually exist in TICKERS."""
    bad = {}
    for sig_id, cfg in SIGNALS.items():
        unknown = [t for t in cfg.get("relevant_tickers", []) if t not in TICKERS]
        if unknown:
            bad[sig_id] = unknown
    assert not bad, f"Signals referencing tickers not in TICKERS: {bad}"


def test_no_ticker_references_a_nonexistent_signal():
    """
    The inverse of the above — this is exactly the bug class that slipped
    through when oil_rig_count was removed: tickers (XOM, HAL, SLB, BKR)
    kept listing it in their "signals" array after the signal itself was
    deleted from SIGNALS.
    """
    bad = {}
    for ticker, cfg in TICKERS.items():
        unknown = [s for s in cfg.get("signals", []) if s not in SIGNALS]
        if unknown:
            bad[ticker] = unknown
    assert not bad, f"Tickers referencing signals not in SIGNALS: {bad}"


def test_every_signal_category_exists():
    bad = {sig_id: cfg["category"] for sig_id, cfg in SIGNALS.items() if cfg["category"] not in CATEGORIES}
    assert not bad, f"Signals referencing unknown categories: {bad}"


def test_every_ticker_has_a_name():
    bad = [t for t, cfg in TICKERS.items() if not cfg.get("name", "").strip()]
    assert not bad, f"Tickers missing a full company name (breaks ticker_label()): {bad}"


def test_power_supercycle_signals_all_exist():
    bad = {}
    for leg, sig_ids in POWER_SUPERCYCLE_SIGNALS.items():
        unknown = [s for s in sig_ids if s not in SIGNALS]
        if unknown:
            bad[leg] = unknown
    assert not bad, f"Power Supercycle legs reference unknown signals: {bad}"


def test_pcs_scores_are_in_valid_range():
    bad = {sig_id: cfg["pcs"] for sig_id, cfg in SIGNALS.items() if not (1 <= cfg["pcs"] <= 10)}
    assert not bad, f"Signals with out-of-range static PCS (must be 1-10): {bad}"


def test_no_duplicate_signal_names():
    names = [cfg["name"] for cfg in SIGNALS.values()]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"Duplicate signal display names: {dupes}"
