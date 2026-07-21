"""Administrative/scheduled warm-up for frequently searched full scores."""

from __future__ import annotations

import time
from collections.abc import Iterable

from utils.fetchers import fetch_prices_batch
from utils.performance import record_timing
from utils.score_cache import prime_full_score_result
from utils.score_components import build_components
from utils.score_history import record_score_components, record_score_snapshot
from utils.ticker_score import compute_full_ticker_score, price_window


DEFAULT_WARM_TICKERS = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    "SPY", "QQQ", "CCJ", "LEU",
)


def warm_full_scores(
    tickers: Iterable[str] = DEFAULT_WARM_TICKERS,
    *,
    pause_seconds: float = 0.75,
) -> list[dict]:
    """Batch prices, score sequentially, persist only complete results."""
    normalized = tuple(dict.fromkeys(str(t).upper().strip() for t in tickers if str(t).strip()))
    start, end = price_window()
    prices = fetch_prices_batch(normalized, start, end)
    report: list[dict] = []
    for index, ticker in enumerate(normalized):
        started = time.perf_counter()
        success = False
        error = None
        stored = False
        try:
            result = compute_full_ticker_score(
                ticker,
                price_series=prices.get(ticker),
                include_optional=True,
            )
            success = bool(result.get("is_complete", True))
            if success:
                prime_full_score_result(ticker, result, None, include_optional=True)
                confluence = result["confluence"]
                record_score_snapshot(
                    ticker,
                    confluence["overall_score"],
                    confluence["case"],
                    confluence["conviction"],
                    kind="full",
                )
                record_score_components(ticker, build_components(result))
                stored = True
            else:
                error = "unavailable sources: " + ",".join(result.get("source_errors", []))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        duration = time.perf_counter() - started
        event = record_timing(
            "warm_full_score",
            ticker=ticker,
            duration_seconds=duration,
            success=success,
            cache_status="primed" if stored else "not_stored",
            metadata={"error": error},
        )
        event["stored"] = stored
        report.append(event)
        if index + 1 < len(normalized) and pause_seconds > 0:
            time.sleep(float(pause_seconds))
    return report
