# utils/holding_names.py
# Unstructured Alpha — a holding's full name, wherever its ticker is shown
#
# "VTI 40%" means nothing to someone who has never looked up a ticker, and
# the report's readers range from advisers to a first-time 401(k) holder.
# Every place the report prints a ticker can ask for the name behind it.
#
# RULES
#   * Local only. Rendering a report never waits on the network for a label:
#     the names come from what the visitor's own holdings carried (a search
#     result includes the fund's name), the bundled table of common funds,
#     the curated names of the scored universe, and the stock library.
#   * Unknown is honest: no name means the ticker is shown alone, never a
#     guessed name.
#   * Names are display text only; they never feed a calculation.

from __future__ import annotations

import time
from typing import Dict, Iterable, Optional

_remembered: Dict[str, str] = {}
_library: Dict[str, str] = {}
_library_at = 0.0
_LIBRARY_TTL = 600.0
KINDS: Dict[str, str] = {}      # ticker -> "ETF" | "Stock" | "Mutual fund", where known


def _clean(t: str) -> str:
    return str(t or "").strip().upper()


def _static() -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        from utils.config import TICKERS
        for t, m in TICKERS.items():
            if m.get("name"):
                out[_clean(t)] = str(m["name"])
    except Exception:
        pass
    try:
        from utils.symbol_search import common_symbols
        for t, n, kind in common_symbols():
            out[_clean(t)] = n          # the bundled table is the most carefully written
            if kind:
                KINDS[_clean(t)] = kind
    except Exception:
        pass
    return out


_STATIC = _static()


def remember(holdings: Optional[Iterable[dict]]) -> None:
    """Keep the names a visitor's holdings carried (from the search box)."""
    for h in holdings or []:
        t, n = _clean(h.get("ticker")), str(h.get("name") or "").strip()
        if t and n and n.upper() != t:
            _remembered[t] = n


def _library_names() -> Dict[str, str]:
    global _library, _library_at
    if time.time() - _library_at > _LIBRARY_TTL:
        try:
            from utils import stock_library as lib
            _library = {_clean(s.get("ticker")): str(s.get("name")) for s in lib.latest() if s.get("name")}
        except Exception:
            _library = {}
        _library_at = time.time()
    return _library


def full_name(ticker: str) -> str:
    """The holding's full name, or "" when it is not known locally."""
    t = _clean(ticker)
    if not t:
        return ""
    name = _remembered.get(t) or _STATIC.get(t) or _library_names().get(t) or ""
    return "" if name.upper() == t else name


def short(name: str, n: int = 34) -> str:
    """A name trimmed for a tight label; the full one goes in a tooltip."""
    return name if len(name) <= n else name[: n - 1].rstrip(" ,.-") + "…"


def with_name(ticker: str) -> str:
    """'BND (Vanguard Total Bond Market ETF)' for prose; the ticker alone if unknown."""
    n = full_name(ticker)
    return f"{_clean(ticker)} ({n})" if n else _clean(ticker)
