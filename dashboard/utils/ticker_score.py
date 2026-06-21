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

from datetime import datetime, timedelta

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
    Universe tickers use their configured signal list; unknown tickers are
    mapped by yfinance sector, falling back to a generic macro set.
    """
    ticker = ticker.upper().strip()
    tkr_meta = TICKERS.get(ticker, {})

    if tkr_meta:
        company_name_hint = tkr_meta.get("name", ticker)
        relevant_sig_ids = tkr_meta.get("signals") or list(SIGNALS.keys())
        return tkr_meta, company_name_hint, relevant_sig_ids

    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        company_name_hint = info.get("longName") or info.get("shortName") or ticker
        sector = info.get("sector", "")
        relevant_sig_ids = SECTOR_SIGNAL_MAP.get(sector, _DEFAULT_SIGNAL_IDS)
    except Exception:
        company_name_hint = ticker
        relevant_sig_ids = _DEFAULT_SIGNAL_IDS

    return tkr_meta, company_name_hint, relevant_sig_ids


def compute_full_ticker_score(ticker: str, signal_ids: list | None = None) -> dict:
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
    relevant_sig_ids = signal_ids if signal_ids else auto_sig_ids

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
    price_start = (datetime.now() - timedelta(days=365 * 15)).strftime("%Y-%m-%d")

    signal_scores, signal_data = {}, {}
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

    price_series = fetch_price(ticker, price_start, end)

    # Per-ticker correlation weighting + significance (mirrors the page exactly)
    corr_info = {}
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

    # Optional signal 1: federal contracts
    contracts_df = fetch_federal_contracts(company_name_hint, years=2)
    contract_vel = score_contract_velocity(contracts_df)
    has_contract_signal = contract_vel.get("status") != "no_data" and contract_vel.get("award_count", 0) >= 3

    # Optional signal 2: insider activity
    insider_tx = fetch_insider_transactions_detail(ticker, days=180)
    insider_score = score_insider_activity(insider_tx)
    has_insider_signal = insider_score.get("status") != "no_data"

    # Optional signal 3: short interest
    short_interest_df = fetch_short_interest(ticker, years=1.5)
    short_interest_score = score_short_interest(short_interest_df)
    has_short_interest_signal = (
        short_interest_score.get("status") != "no_data" and short_interest_score.get("periods", 0) >= 2
    )

    # Optional signal 4: 13F institutional positioning
    ticker_cusips = {c for c, t in THIRTEENF_CUSIP_TO_TICKER.items() if t == ticker}
    fund_rows_13f = []
    if ticker_cusips:
        direction_sign = {"long": 1, "short": -1}
        for fund in CURATED_FUNDS:
            fund_df = fetch_13f_holdings(fund["cik"], fund["name"])
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
    }
