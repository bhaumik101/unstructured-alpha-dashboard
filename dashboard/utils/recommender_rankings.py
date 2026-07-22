"""Shared, provider-bounded macro ranking used by the page and alert cron."""

from __future__ import annotations

from utils.config import SIGNALS, TICKERS
from utils.conviction import get_signal_alignment


HORIZON_WEEKS = {
    "Short-term (1–2 wks)": (0, 3),
    "Medium-term (1–2 mo)": (3, 9),
    "Long-term (3+ mo)": (9, 999),
    "All": (0, 999),
}


def macro_rank_all(
    min_lag: int,
    max_lag: int,
    *,
    all_scores: dict | None = None,
) -> list[dict]:
    """Rank the configured universe from one shared real-signal snapshot."""
    from utils.analysis import compute_confluence
    from utils.signals_cache import get_all_signal_scores

    scores = all_scores if all_scores is not None else get_all_signal_scores()
    rows: list[dict] = []
    for ticker, meta in TICKERS.items():
        signal_ids = meta.get("signals", [])
        if min_lag > 0 or max_lag < 999:
            signal_ids = [
                signal_id for signal_id in signal_ids
                if min_lag <= SIGNALS.get(signal_id, {}).get("lag_weeks", 4) <= max_lag
            ]
        ticker_scores = {
            signal_id: scores[signal_id]
            for signal_id in signal_ids
            if signal_id in scores and not scores[signal_id].get("error")
        }
        if not ticker_scores:
            continue
        weights = {
            signal_id: SIGNALS[signal_id].get("pcs", 5) / 10.0
            for signal_id in ticker_scores if signal_id in SIGNALS
        }
        confluence = compute_confluence(ticker_scores, weights=weights)
        bull_signals = [
            {
                "id": signal_id,
                "name": SIGNALS.get(signal_id, {}).get("name", signal_id),
                "lag": SIGNALS.get(signal_id, {}).get("lag_weeks", "?"),
                "score": ticker_scores[signal_id].get("score", 50),
            }
            for signal_id in ticker_scores
            if ticker_scores[signal_id].get("status") == "bullish"
        ]
        bear_signals = [
            {
                "id": signal_id,
                "name": SIGNALS.get(signal_id, {}).get("name", signal_id),
                "lag": SIGNALS.get(signal_id, {}).get("lag_weeks", "?"),
                "score": ticker_scores[signal_id].get("score", 50),
            }
            for signal_id in ticker_scores
            if ticker_scores[signal_id].get("status") == "bearish"
        ]
        aligned, total = get_signal_alignment(
            ticker, confluence["overall_score"], scores
        )
        rows.append({
            "ticker": ticker,
            "name": meta.get("name", ticker),
            "sector": meta.get("sector", "Other"),
            "score": round(confluence["overall_score"], 1),
            "case": confluence["case"],
            "conviction": confluence["conviction"],
            "bull_count": confluence["bull_count"],
            "bear_count": confluence["bear_count"],
            "n_signals": len(ticker_scores),
            "bull_signals": sorted(bull_signals, key=lambda item: -item["score"]),
            "bear_signals": sorted(bear_signals, key=lambda item: item["score"]),
            "enriched": False,
            "has_insider": False,
            "has_13f": False,
            "has_short_int": False,
            "has_contracts": False,
            "momentum_score": 50.0,
            "aligned": aligned,
            "total_relevant": total,
        })
    rows.sort(key=lambda row: -row["score"])
    return rows


def screen_candidates(rows: list[dict], config: dict) -> dict[str, list[dict]]:
    """Apply a saved screen and return its displayed macro-ranked candidates."""
    sectors = set(config.get("sectors") or [])
    filtered = [
        row for row in rows
        if (not sectors or row["sector"] in sectors)
        and row["n_signals"] >= int(config["min_signals"])
    ]
    limit = int(config["n_show"])
    longs = [row for row in filtered if row["score"] >= 65][:limit]
    shorts = [
        row for row in sorted(filtered, key=lambda item: item["score"])
        if row["score"] <= 35
    ][:limit]
    return {"longs": longs, "shorts": shorts}
