# utils/holdings.py
# Unstructured Alpha — how a portfolio's weights are entered and worked out
#
# WHY THIS EXISTS
# ---------------
# The report asked for percentages. Almost nobody holds a portfolio in
# percentages: a statement lists share counts, an adviser thinks in dollars,
# and only the summary line is a percentage. Asking for percentages made
# someone do the arithmetic before they could use the product, and arithmetic
# done in a hurry is how a portfolio gets entered wrong.
#
# So a holding can be given as a percentage, a dollar amount, or a share count,
# and this module turns any of them into the weights the engine measures.
#
# THE RULE: A MISSING PRICE IS NOT A ZERO.
# Share counts need a price to become a weight. When a price cannot be fetched
# the holding is reported as unpriced and left OUT of the weights, rather than
# silently counting as nothing — a holding quietly weighted at zero is a
# portfolio the visitor did not describe, and the report would give no sign.

from __future__ import annotations

import math
from typing import Callable, Dict, Iterable, List, Optional, Tuple

# How a visitor says how much of something they hold.
MODES = ("percent", "amount", "shares")
MODE_LABELS = {
    "percent": "Percent of portfolio",
    "amount": "Dollar value",
    "shares": "Number of shares",
}
MODE_HELP = {
    "percent": "Weights are rescaled to 100%, so rough shares are fine.",
    "amount": "What each position is worth. The percentages are worked out for you.",
    "shares": "How many shares you hold. Multiplied by the last close to get a value.",
}
MODE_COLUMN = {"percent": "Weight %", "amount": "Value $", "shares": "Shares"}


def _finite(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def latest_closes(tickers: Iterable[str],
                  fetcher: Optional[Callable] = None) -> Dict[str, dict]:
    """{ticker: {"close": float, "date": "YYYY-MM-DD"}} for what could be priced.

    A ticker that could not be priced is simply absent — callers must treat
    that as unknown, never as zero. Never raises: a pricing outage degrades the
    share-count entry mode, it does not take the page down.
    """
    wanted = tuple(dict.fromkeys(str(t).upper() for t in tickers if str(t).strip()))
    if not wanted:
        return {}

    if fetcher is None:
        from datetime import date, timedelta

        from utils.fetchers import fetch_prices_batch

        end = date.today() + timedelta(days=1)
        start = end - timedelta(days=14)          # a fortnight covers any holiday run
        try:
            frames = fetch_prices_batch(wanted, str(start), str(end))
        except Exception:
            return {}
    else:
        try:
            frames = fetcher(wanted)
        except Exception:
            return {}

    out: Dict[str, dict] = {}
    for ticker in wanted:
        series = (frames or {}).get(ticker)
        if series is None or len(series) == 0:
            continue
        try:
            series = series.dropna()
            if series.empty:
                continue
            close = _finite(series.iloc[-1])
            if close is None or close <= 0:
                continue
            out[ticker] = {"close": close, "date": str(series.index[-1])[:10]}
        except Exception:
            continue
    return out


def row_value(row: dict, mode: str, prices: Dict[str, dict]) -> Optional[float]:
    """What this holding is worth in the units the mode is entered in.

    None means "not known", which is different from 0.0 and has to stay
    different all the way to the weights.
    """
    if mode == "shares":
        shares = _finite(row.get("shares"))
        quote = prices.get(str(row.get("ticker", "")).upper())
        if shares is None or shares <= 0 or not quote:
            return None
        return shares * float(quote["close"])
    if mode == "amount":
        amount = _finite(row.get("amount"))
        return amount if amount and amount > 0 else None
    weight = _finite(row.get("weight_pct"))
    return weight if weight and weight > 0 else None


def to_weights(draft: List[dict], mode: str,
               prices: Optional[Dict[str, dict]] = None) -> Tuple[List[dict], List[str]]:
    """(holdings for the engine, problems to show). Weights sum to 100.

    Rows the mode cannot price are dropped from the weights AND named in the
    problems, because a portfolio measured without one of its holdings is a
    different portfolio and the page has to say so.
    """
    prices = prices or {}
    mode = mode if mode in MODES else "percent"
    # Two different reasons a row has no value, and they need different
    # sentences. Reporting "no recent price" for a holding that simply has no
    # share count yet sends someone looking for a data problem that is not
    # there -- which is what the first version did the moment anyone switched
    # a percentage portfolio into share counts.
    priced, unpriced, blank = [], [], []
    for row in draft or []:
        ticker = str(row.get("ticker", "")).upper()
        if not ticker:
            continue
        value = row_value(row, mode, prices)
        if value is not None:
            priced.append({"ticker": ticker, "value": float(value)})
        elif mode == "shares" and ticker not in prices:
            unpriced.append(ticker)
        else:
            blank.append(ticker)

    total = sum(r["value"] for r in priced)
    problems: List[str] = []
    if unpriced:
        problems.append(
            f"No recent price for {', '.join(unpriced)}, so {'it has' if len(unpriced) == 1 else 'they have'} "
            f"no value to weight. Enter {'it' if len(unpriced) == 1 else 'them'} as a percentage or a "
            f"dollar value instead, or remove {'it' if len(unpriced) == 1 else 'them'}."
        )
    if blank:
        noun = {"shares": "share count", "amount": "value"}.get(mode, "weight")
        problems.append(
            f"No {noun} yet for {', '.join(blank)}, so {'it is' if len(blank) == 1 else 'they are'} "
            f"left out of the weights."
        )
    if total <= 0:
        return [], problems or ["Nothing has an amount yet."]

    return ([{"ticker": r["ticker"], "weight_pct": 100.0 * r["value"] / total} for r in priced],
            problems)


def portfolio_value(draft: List[dict], mode: str,
                    prices: Optional[Dict[str, dict]] = None) -> Optional[float]:
    """The portfolio's total in dollars, when the mode knows dollars.

    None in percent mode: percentages describe proportions and say nothing
    about size, and inventing a total from them would be a made-up number on a
    page whose whole argument is that its numbers are careful.
    """
    if mode == "percent":
        return None
    values = [row_value(row, mode, prices or {}) for row in draft or []]
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def fmt_money(value: Optional[float]) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    if abs(value) >= 1000:
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def fmt_shares(value) -> str:
    number = _finite(value)
    if number is None:
        return "—"
    return f"{number:,.0f}" if float(number).is_integer() else f"{number:,.4f}".rstrip("0").rstrip(".")
