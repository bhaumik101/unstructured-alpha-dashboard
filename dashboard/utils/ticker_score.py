# utils/ticker_score.py
# Unstructured Alpha — Shared Full-Ticker Scoring Orchestration
#
# Extracted from pages/3_Ticker_Deep_Dive.py (2026-06-21) so the alert engine
# can evaluate the exact same Confluence Score the user sees on that page,
# rather than a second, independently-computed approximation that could
# silently drift apart from it. Before this extraction, the full scoring
# pipeline (macro confluence -> momentum blend -> optional differentiator-
# signal blend) lived entirely inline in the page script with no way to call
# it from anywhere else. If the alert engine had reimplemented its own
# version of "the score", a real and likely failure mode would be: the
# dashboard shows GOOGL at 62, an alert fires because some OTHER computation
# said 68 crossed a threshold -- a trust-breaking inconsistency for a
# product whose entire premise is precise, explainable scoring.
#
# This module is intentionally NOT config-agnostic the way utils/fetchers.py
# and utils/analysis.py are kept -- it orchestrates config + fetchers +
# analysis together, the same role the page itself used to play alone.

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from utils.config import SIGNALS, TICKERS, CURATED_FUNDS, THIRTEENF_CUSIP_TO_TICKER
from utils.fetchers import (
    fetch_price, fetch_signal_series,
    fetch_federal_contracts, fetch_insider_transactions_detail,
    fetch_short_interest, fetch_13f_holdings,
)
from utils.analysis import (
    score_signal, compute_confluence, compute_quick_correlation_stats,
    score_insider_activity, score_short_interest, score_13f_positioning,
    score_contract_velocity,
)
from utils.model_version import MODEL_VERSION, signal_registry_version
from utils.performance import notify_progress, timed_stage

# Mirrors pages/3_Ticker_Deep_Dive.py's SECTOR_SIGNAL_MAP exactly -- kept in
# sync by hand since Streamlit pages can't be imported as modules cleanly.
# If this drifts from the page's copy, an unknown ticker could get scored
# differently in an alert than on its own deep-dive page.
SECTOR_SIGNAL_MAP = {
    "Technology":              ["hyperscaler_capex", "semiconductor_etf", "ten_year_yield", "hy_spread", "vix"],
    "Energy":                  ["crude_oil", "crude_inventories", "natural_gas", "gas_storage", "dollar_index"],
    "Financial Services":      ["yield_curve", "hy_spread", "ten_year_yield", "vix", "bank_lending_standards", "credit_card_delinquency"],
    "Healthcare":              ["jobless_claims", "consumer_sentiment", "hy_spread", "ten_year_yield", "fda_approval_velocity"],
    "Consumer Cyclical":       ["retail_sales", "consumer_sentiment", "jobless_claims", "ata_trucking", "retail_job_openings", "ecommerce_share"],
    "Consumer Defensive":      ["retail_sales", "food_cpi", "jobless_claims", "consumer_sentiment", "retail_job_openings"],
    "Industrials":             ["ism_pmi", "ata_trucking", "rail_traffic", "durable_goods", "hy_spread", "construction_spending"],
    "Basic Materials":         ["copper", "dollar_index", "ism_pmi", "crude_oil", "shipping_index"],
    "Utilities":               ["ten_year_yield", "natural_gas", "uranium_proxy", "power_demand_growth", "vix"],
    "Real Estate":             ["ten_year_yield", "housing_starts", "hy_spread", "vix"],
    "Communication Services":  ["hyperscaler_capex", "jobless_claims", "ten_year_yield", "hy_spread"],
}
_DEFAULT_SIGNAL_IDS = ["ata_trucking", "hy_spread", "ten_year_yield", "vix", "yield_curve"]


def resolve_ticker_meta(ticker: str) -> tuple[dict, str, list]:
    """
    Resolve (tkr_meta, company_name_hint, relevant_sig_ids) for a ticker.

    FIXED 2026-06-23: tickers with a short manually-configured "signals"
    list (e.g. VRT only had ["hyperscaler_capex", "copper"]) were only
    ever evaluated against those 2 signals -- the per-ticker correlation
    weighting and significance filtering that the rest of the platform
    applies were running on an artificially tiny dataset, hiding many
    signals that are genuinely relevant for that ticker. The manual
    "signals" list was originally intended as a CURATION hint (domain
    knowledge of which signals MATTER for the stock's thesis), not as a
    RESTRICTION on which signals are ever tested.

    Now: the manually-configured signals are ALWAYS INCLUDED (as a
    guaranteed starting set reflecting domain knowledge), and the full
    signal library is appended after them so the significance-based
    scoring, table filtering, and Deep Correlation Scan selectbox all
    have access to every signal in the universe. Signals the manual
    curation already covers stay first in the list so the multiselect
    default shows them prominently.
    """
    ticker = ticker.upper().strip()
    tkr_meta = TICKERS.get(ticker, {})

    if tkr_meta:
        company_name_hint = tkr_meta.get("name", ticker)
        # Priority signals (manually curated for this ticker's thesis),
        # PLUS all remaining signals from the full library.
        priority_sigs = tkr_meta.get("signals") or []
        all_sigs = list(SIGNALS.keys())
        # Union: priority first, then everything else not already in the list.
        relevant_sig_ids = priority_sigs + [s for s in all_sigs if s not in priority_sigs]
        return tkr_meta, company_name_hint, relevant_sig_ids

    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        company_name_hint = info.get("longName") or info.get("shortName") or ticker
        sector = info.get("sector", "")
        # Sector-mapped signals FIRST (most relevant by domain knowledge),
        # then everything else so significance filtering has the full library.
        sector_sigs = SECTOR_SIGNAL_MAP.get(sector, _DEFAULT_SIGNAL_IDS)
        all_sigs = list(SIGNALS.keys())
        relevant_sig_ids = sector_sigs + [s for s in all_sigs if s not in sector_sigs]
    except Exception:
        company_name_hint = ticker
        relevant_sig_ids = list(SIGNALS.keys())

    return tkr_meta, company_name_hint, relevant_sig_ids


def price_window() -> tuple[str, str]:
    """The (start, end) date window compute_full_ticker_score uses for prices.
    Exposed so batch callers can pre-fetch the exact same window."""
    end = datetime.now().strftime("%Y-%m-%d")
    price_start = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    return price_start, end


def _empty_errored_frame() -> "pd.DataFrame":
    """An empty frame flagged as a fetch failure.

    Used when a prefetch task raised. It carries fetch_error=True so the caller
    appends to source_errors, the score is marked incomplete, and the page says
    the provider is unavailable -- the same path a live provider outage takes.
    Deliberately NOT an empty-but-clean frame, which would read as "we looked
    and there is genuinely nothing here" and silently drop the signal instead.
    """
    frame = pd.DataFrame()
    frame.attrs["fetch_error"] = True
    return frame


def _compute_full_ticker_score(
    ticker: str,
    signal_ids: list | None = None,
    price_series: "pd.Series | None" = None,
    include_optional: bool = True,
    progress_callback=None,
    _timing_events: list[dict] | None = None,
) -> dict:
    """
    Compute the exact same full Confluence Score shown on Ticker Deep Dive:
    macro signal confluence (weighted by each signal's real correlation with
    THIS ticker's price) blended with price momentum (20%) and, when present,
    up to four optional differentiator signals (federal contracts, insider
    buy/sell clustering, FINRA short interest trend, curated-fund 13F
    positioning) at a fixed 12%-each slice.

    `signal_ids`: override the auto-derived signal set (used by the page's
    "customize which signals to include" multiselect). Background callers
    (e.g. the alert engine) should leave this as None to get the same
    default set the page would show on first load.

    Returns a dict with the final blended score/case/conviction plus every
    intermediate component, so callers can both display detail (the page)
    and detect deltas against a prior snapshot (the alert engine) without
    re-deriving anything.
    """
    ticker = ticker.upper().strip()
    tkr_meta, company_name_hint, auto_sig_ids = resolve_ticker_meta(ticker)
    # None means "resolve the automatic set"; [] means "explicitly no macro
    # signals". Keeping those semantics distinct is also required by the shared
    # full-result cache key.
    relevant_sig_ids = signal_ids if signal_ids is not None else auto_sig_ids

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
    price_start = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")

    signal_scores, signal_data = {}, {}
    notify_progress(progress_callback, "macro_signals", "Loading macro signals…")
    # Warm every signal's fetch cache concurrently before the scoring loop below
    # walks them one at a time. The loop is deliberately left as it was: it still
    # calls fetch_signal_series with the same (cfg, start, end) key and keeps its
    # own error semantics, so the score it produces is unchanged -- the fetches
    # have simply already happened. Best-effort; a failed prewarm just restores
    # the original serial cost. See signals_cache.prewarm_signal_series.
    with timed_stage("signal_series_prewarm", ticker=ticker, events=_timing_events,
                     metadata={"signal_count": len(relevant_sig_ids)}):
        try:
            from utils.signals_cache import prewarm_signal_series
            prewarm_signal_series(relevant_sig_ids, start, end)
        except Exception:
            pass
    with timed_stage("signal_series_retrieval", ticker=ticker, events=_timing_events,
                     metadata={"signal_count": len(relevant_sig_ids)}):
        for sig_id in relevant_sig_ids:
            cfg = SIGNALS.get(sig_id)
            if not cfg:
                continue
            try:
                s = fetch_signal_series(cfg, start, end)
                signal_scores[sig_id] = score_signal(s, inverse=cfg.get("inverse", False))
                signal_data[sig_id] = s
            except Exception:
                signal_scores[sig_id] = {"score": 50, "status": "neutral"}
                signal_data[sig_id] = pd.Series(dtype=float)

    # Use a caller-supplied price series when given (batch pre-fetch); otherwise
    # fetch this ticker on its own. Byte-identical either way.
    notify_progress(progress_callback, "price_history", "Loading price history…")
    _price_outcome = {}
    with timed_stage("price_retrieval", ticker=ticker, events=_timing_events,
                     cache_status="caller_supplied" if price_series is not None else "unknown",
                     outcome=_price_outcome):
        if price_series is None:
            price_series = fetch_price(ticker, price_start, end)
        _price_outcome["success"] = not getattr(price_series, "attrs", {}).get("fetch_error", False)

    # Per-ticker correlation weighting + significance (mirrors the page exactly)
    corr_info = {}
    with timed_stage("correlation_calculation", ticker=ticker, events=_timing_events,
                     metadata={"signal_count": len(relevant_sig_ids)}):
        if not price_series.empty:
            for sig_id in relevant_sig_ids:
                cfg = SIGNALS.get(sig_id, {})
                lag = cfg.get("lag_weeks", 0)
                raw_series = signal_data.get(sig_id, pd.Series(dtype=float))
                if len(raw_series.dropna()) >= 20:
                    stat = compute_quick_correlation_stats(raw_series, price_series, lag_weeks=lag)
                else:
                    stat = {"r": 0.0, "p_value": 1.0, "significant": False, "n": 0}
                pcs = cfg.get("pcs", 5)
                r = stat["r"]
                weight = max(0.15, abs(r)) * (pcs / 10.0)
                corr_info[sig_id] = {
                    "r": r, "weight": round(weight, 4),
                    "p_value": stat["p_value"], "significant": stat["significant"], "n": stat["n"],
                }
        else:
            for sig_id in relevant_sig_ids:
                cfg = SIGNALS.get(sig_id, {})
                pcs = cfg.get("pcs", 5)
                corr_info[sig_id] = {"r": 0.0, "weight": pcs / 10.0, "p_value": 1.0, "significant": False, "n": 0}

        corr_weights_flat = {sid: ci["weight"] for sid, ci in corr_info.items()}
        confluence = compute_confluence(signal_scores, weights=corr_weights_flat)

    # Momentum blend
    mom_score = 50.0
    if not price_series.empty and len(price_series.dropna()) >= 10:
        ps = price_series.dropna()
        ret_1y = (ps.iloc[-1] / ps.iloc[-252] - 1) if len(ps) >= 252 else 0.0
        ret_1m = (ps.iloc[-1] / ps.iloc[-22] - 1) if len(ps) >= 22 else 0.0
        blended_ret = ret_1y * 0.6 + ret_1m * 0.4
        mom_score = float(np.clip(50.0 + blended_ret * 83.3, 5.0, 95.0))

    # ── Optional differentiator signals ───────────────────────────────────────
    # These four are the expensive part of this function: each is a live network
    # call per ticker (USASpending, SEC EDGAR, FINRA, and a LOOP of 13F filings),
    # together ~6s/ticker. That's the right trade for one Deep Dive view, but it
    # makes bulk scoring of thousands of tickers impossible.
    #
    # `include_optional=False` skips them and returns the macro+momentum score
    # only — the same blend the screener and recommender rank on. Default stays
    # True, so Deep Dive and every existing caller behave EXACTLY as before.
    contracts_df = None
    contract_vel = {"status": "no_data"}
    has_contract_signal = False
    insider_tx = None
    insider_score = {"status": "no_data"}
    has_insider_signal = False
    short_interest_df = None
    short_interest_score = {"status": "no_data"}
    has_short_interest_signal = False
    fund_rows_13f = []
    ticker_cusips = set()
    source_errors: list[str] = []

    if getattr(price_series, "attrs", {}).get("fetch_error"):
        source_errors.append("price_history")

    if include_optional:
        notify_progress(progress_callback, "optional_evidence", "Checking optional evidence…")
        # Federal contracts (USASpending), insider Form 4s (SEC EDGAR) and short
        # interest (FINRA) are three independent providers, and each was being
        # awaited in turn -- measured 0.6-3.4s, 1.8-5.3s and ~0.5s, all serial.
        # They are fetched together here and scored below in the original order.
        # Only the network read moves into the pool: every score_* call, the
        # source_errors ordering and each has_* predicate are unchanged, so the
        # result is identical. yfinance stays out of the pool by design; these
        # three go through utils.resilience (requests + breaker + pooled session).
        with timed_stage("optional_evidence_retrieval", ticker=ticker, events=_timing_events,
                         metadata={"providers": 3}):
            from utils.signals_cache import run_parallel
            _fetched = run_parallel({
                "contracts": lambda: fetch_federal_contracts(company_name_hint, years=2),
                "insider": lambda: fetch_insider_transactions_detail(ticker, days=180),
                "short_interest": lambda: fetch_short_interest(ticker, years=1.5),
            }, max_workers=3)

        def _frame(key):
            """A raising task becomes an empty errored frame -- the same shape the
            fetchers themselves return when a provider is down."""
            value = _fetched.get(key)
            if isinstance(value, BaseException) or value is None:
                return _empty_errored_frame()
            return value

        # Optional signal 1: federal contracts
        _contracts_outcome = {}
        with timed_stage("federal_contract_retrieval", ticker=ticker, events=_timing_events,
                         cache_status="prefetched", outcome=_contracts_outcome):
            contracts_df = _frame("contracts")
            contract_vel = score_contract_velocity(contracts_df)
            _contracts_outcome["success"] = not getattr(contracts_df, "attrs", {}).get("fetch_error", False)
        if getattr(contracts_df, "attrs", {}).get("fetch_error"):
            source_errors.append("federal_contracts")
        has_contract_signal = contract_vel.get("status") != "no_data" and contract_vel.get("award_count", 0) >= 3

        # Optional signal 2: insider activity
        _insider_outcome = {}
        with timed_stage("insider_retrieval", ticker=ticker, events=_timing_events,
                         cache_status="prefetched", outcome=_insider_outcome):
            insider_tx = _frame("insider")
            insider_score = score_insider_activity(insider_tx)
            _insider_outcome["success"] = not getattr(insider_tx, "attrs", {}).get("fetch_error", False)
        if getattr(insider_tx, "attrs", {}).get("fetch_error"):
            source_errors.append("insider_activity")
        has_insider_signal = insider_score.get("status") != "no_data"

        # Optional signal 3: short interest
        _short_outcome = {}
        with timed_stage("short_interest_retrieval", ticker=ticker, events=_timing_events,
                         cache_status="prefetched", outcome=_short_outcome):
            short_interest_df = _frame("short_interest")
            short_interest_score = score_short_interest(short_interest_df)
            _short_outcome["success"] = not getattr(short_interest_df, "attrs", {}).get("fetch_error", False)
        if getattr(short_interest_df, "attrs", {}).get("fetch_error"):
            source_errors.append("short_interest")
        has_short_interest_signal = (
            short_interest_score.get("status") != "no_data" and short_interest_score.get("periods", 0) >= 2
        )

        # Optional signal 4: 13F institutional positioning
        ticker_cusips = {c for c, t in THIRTEENF_CUSIP_TO_TICKER.items() if t == ticker}
    _thirteenf_outcome = {}
    with timed_stage("thirteenf_retrieval", ticker=ticker, events=_timing_events,
                     cache_status="not_requested" if not ticker_cusips else "unknown",
                     outcome=_thirteenf_outcome):
        if ticker_cusips:
            direction_sign = {"long": 1, "short": -1}
            for fund in CURATED_FUNDS:
                fund_df = fetch_13f_holdings(fund["cik"], fund["name"])
                if getattr(fund_df, "attrs", {}).get("fetch_error"):
                    if "thirteenf" not in source_errors:
                        source_errors.append("thirteenf")
                    continue
                if fund_df.empty:
                    continue
                periods = sorted(fund_df["period"].dropna().unique(), reverse=True)
                if not periods:
                    continue
                latest_period = periods[0]
                prior_period = periods[1] if len(periods) > 1 else None

                def _signed_shares(period):
                    rows = fund_df[(fund_df["period"] == period) & (fund_df["cusip"].isin(ticker_cusips))]
                    if rows.empty:
                        return 0.0
                    return float((rows["shares"] * rows["direction"].map(direction_sign)).sum())

                def _source_url(period):
                    # Audit-trail field: the exact information-table XML this
                    # position came from. Picks the first matching row's
                    # source_url -- a fund can hold this ticker via more than
                    # one CUSIP/option-type row in the same filing, but they all
                    # share the same filing, so any one of their source_urls
                    # points to the right document.
                    rows = fund_df[(fund_df["period"] == period) & (fund_df["cusip"].isin(ticker_cusips))]
                    if rows.empty or "source_url" not in rows.columns:
                        return None
                    return rows["source_url"].iloc[0]

                latest_signed = _signed_shares(latest_period)
                prior_signed = _signed_shares(prior_period) if prior_period is not None else None
                if latest_signed == 0.0 and not prior_signed:
                    continue
                fund_rows_13f.append({
                    "fund": fund["name"], "style": fund["style"],
                    "latest_shares": latest_signed, "latest_period": latest_period,
                    "prior_shares": prior_signed, "prior_period": prior_period,
                    "latest_source_url": _source_url(latest_period),
                })
        _thirteenf_outcome["success"] = "thirteenf" not in source_errors

    thirteenf_score = score_13f_positioning(fund_rows_13f)
    has_13f_signal = thirteenf_score.get("status") != "no_data"

    # Generic N-optional-signal blend (see Ticker Deep Dive's original comment
    # for the rationale: fixed 12% slice per active optional signal, with
    # macro+momentum's combined weight shrinking proportionally).
    optional_signals = [
        (has_contract_signal, contract_vel.get("score") if has_contract_signal else None),
        (has_insider_signal, insider_score.get("score") if has_insider_signal else None),
        (has_short_interest_signal, short_interest_score.get("score") if has_short_interest_signal else None),
        (has_13f_signal, thirteenf_score.get("score") if has_13f_signal else None),
    ]
    active_optional = [score for active, score in optional_signals if active]
    n_optional = len(active_optional)
    optional_slice = 0.12
    remaining = 1.0 - optional_slice * n_optional

    macro_score = confluence["overall_score"]
    final_score = macro_score * (remaining * 0.80) + mom_score * (remaining * 0.20)
    for opt_score in active_optional:
        final_score += opt_score * optional_slice
    confluence["overall_score"] = round(final_score, 1)

    if final_score >= 65:
        confluence["case"] = "BULL"
    elif final_score <= 35:
        confluence["case"] = "BEAR"

    notify_progress(progress_callback, "explanation", "Preparing explanation…")
    return {
        "ticker": ticker,
        "company_name_hint": company_name_hint,
        "tkr_meta": tkr_meta,
        "relevant_sig_ids": relevant_sig_ids,
        "signal_scores": signal_scores,
        "signal_data": signal_data,
        "price_series": price_series,
        "corr_info": corr_info,
        "confluence": confluence,
        "momentum_score": mom_score,
        "contract_velocity": contract_vel,
        "has_contract_signal": has_contract_signal,
        "insider_score": insider_score,
        "has_insider_signal": has_insider_signal,
        "insider_tx": insider_tx,
        "short_interest_score": short_interest_score,
        "has_short_interest_signal": has_short_interest_signal,
        "short_interest_df": short_interest_df,
        "thirteenf_score": thirteenf_score,
        "has_13f_signal": has_13f_signal,
        "thirteenf_fund_rows": fund_rows_13f,
        "score_kind": (
            "macro_momentum" if not include_optional
            else "full" if not source_errors
            else "provisional"
        ),
        "is_complete": not source_errors,
        "source_errors": source_errors,
        "model_version": MODEL_VERSION,
        "signal_registry_version": signal_registry_version(),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }


def compute_full_ticker_score(
    ticker: str,
    signal_ids: list | None = None,
    price_series: "pd.Series | None" = None,
    include_optional: bool = True,
    progress_callback=None,
) -> dict:
    """Timed public entrypoint for the canonical ticker score computation."""
    normalized = ticker.upper().strip()
    events: list[dict] = []
    with timed_stage("full_score", ticker=normalized, events=events,
                     metadata={"include_optional": include_optional}):
        result = _compute_full_ticker_score(
            normalized,
            signal_ids=signal_ids,
            price_series=price_series,
            include_optional=include_optional,
            progress_callback=progress_callback,
            _timing_events=events,
        )
    result["_timings"] = events
    return result
