"""
utils/guards.py — resource guards / input caps.

WHY: on the Standard (2 GB / 1 CPU) box the real stability risk is a single
request driving unbounded work — e.g. a user adding 100 portfolio holdings (each
a full ticker score with a 3yr price fetch), a huge export, or a chart with tens
of thousands of points. Widget min/max already bound most inputs; these caps
protect the paths where a list/upload/multiselect could grow without limit.

All caps are overridable via env so they can be tuned without a code change.
Pure standard library — safe to import anywhere.
"""
from __future__ import annotations

import os


def _cap(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


# ── Caps (env-overridable) ────────────────────────────────────────────────────
MAX_PORTFOLIO_HOLDINGS = _cap("MAX_PORTFOLIO_HOLDINGS", 25)   # each = 1 full score
# The exposure report has its own cap, deliberately separate and much higher.
# The comment above is the reason: a holding used to mean a full ticker score
# with its own three-year price fetch. In the exposure engine a holding is one
# OLS fit on 156 weekly returns, sharing a single batched price request with
# every other holding. Timed on this machine with synthetic data: 15 holdings
# 0.06s, 60 holdings 0.13s. The old cap was sized for work this product does
# not do, and it was the only thing Investor Pro had to sell.
MAX_EXPOSURE_HOLDINGS  = _cap("MAX_EXPOSURE_HOLDINGS", 60)
MAX_SAVED_PORTFOLIOS   = _cap("MAX_SAVED_PORTFOLIOS", 5)      # per Pro account
MAX_BASKET_TICKERS     = _cap("MAX_BASKET_TICKERS", 25)
MAX_TICKERS_PER_REQUEST = _cap("MAX_TICKERS_PER_REQUEST", 40)  # ad-hoc multi-ticker scans
MAX_EXPORT_ROWS        = _cap("MAX_EXPORT_ROWS", 5000)
MAX_CHART_POINTS       = _cap("MAX_CHART_POINTS", 1500)        # per series sent to browser
MAX_LOOKBACK_YEARS     = _cap("MAX_LOOKBACK_YEARS", 10)


def clamp(n, lo, hi):
    """Clamp n into [lo, hi]."""
    return max(lo, min(hi, n))


def cap_list(items, limit: int):
    """Return (capped_items, was_truncated). Preserves order."""
    items = list(items)
    if len(items) > limit:
        return items[:limit], True
    return items, False


def downsample_for_chart(x, y=None, max_points: int = MAX_CHART_POINTS):
    """
    Reduce a series to at most `max_points` for *screen rendering* — keeps the
    first/last points and strides the middle so the shape is preserved. This is
    for the on-screen chart only; full-resolution data should be used for any
    download/export. Returns the same type it was given.

    - If given a pandas Series: returns a downsampled Series.
    - If given (x, y) arrays: returns (x2, y2).
    - Never raises; returns the input unchanged on any problem.
    """
    try:
        # pandas Series path
        if y is None and hasattr(x, "iloc") and hasattr(x, "__len__"):
            n = len(x)
            if n <= max_points:
                return x
            step = max(1, n // max_points)
            idx = list(range(0, n, step))
            if idx[-1] != n - 1:      # always keep the final (latest) point
                idx.append(n - 1)
            return x.iloc[idx]
        # (x, y) path
        if y is not None:
            n = len(x)
            if n <= max_points:
                return x, y
            step = max(1, n // max_points)
            x2 = list(x[::step])
            y2 = list(y[::step])
            if x2 and x[-1] != x2[-1]:
                x2.append(x[-1]); y2.append(y[-1])
            return x2, y2
    except Exception:
        pass
    return (x if y is None else (x, y))
