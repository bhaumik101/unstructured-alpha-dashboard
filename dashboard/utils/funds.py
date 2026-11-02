# utils/funds.py
# Unstructured Alpha — the ETFs measured alongside the S&P 500
#
# Most retail investors hold funds, not 500 single companies, so the weekly
# library job also measures a fixed list of widely held ETFs (cron/etfs.csv).
# Funds that simply track the S&P 500 (SPY, VOO, IVV, VTI) are deliberately
# not on it: every reading is measured "beyond the stock market's own move",
# and the market control is SPY itself, so for those there is nothing left to
# measure.

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

FUNDS_CSV = Path(__file__).resolve().parent.parent / "cron" / "etfs.csv"
MARKET_TRACKERS = frozenset({"SPY", "VOO", "IVV", "VTI", "ITOT", "SPLG", "SCHX"})


@lru_cache(maxsize=1)
def funds() -> Dict[str, Tuple[str, str]]:
    """{ticker: (name, category)} for every fund on the list."""
    with open(FUNDS_CSV, newline="", encoding="utf-8") as fh:
        return {r["ticker"].strip().upper(): (r["name"].strip(), r["category"].strip())
                for r in csv.DictReader(fh) if r.get("ticker", "").strip()}


def load_funds() -> List[Tuple[str, str]]:
    """(ticker, name) targets for the weekly measurement job."""
    return [(t, n) for t, (n, _) in funds().items()]


def is_fund(ticker: str) -> bool:
    return str(ticker or "").upper() in funds()
