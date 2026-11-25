# utils/gdpnow.py
# Unstructured Alpha — the Atlanta Fed's GDPNow estimate, as context only
#
# GDPNow is the Federal Reserve Bank of Atlanta's running model estimate of
# this quarter's real GDP growth (seasonally adjusted, annualized), updated
# several times a month as new data come in. The "What changed" page shows it
# beside the portfolio's own movements so a reader knows what the economy is
# doing right now.
#
# RULES
#   * Context, never a signal: nothing here feeds a reading, a score or an
#     alert, and it is labelled as the Atlanta Fed's estimate, not ours.
#   * Its record is shown with it: each past quarter's final estimate next to
#     the BEA's figure for that quarter, and the average miss.
#   * ALFRED (FRED's archive of past vintages) gives what the estimate said on
#     each date, so the path of this quarter's estimate and the date of the
#     latest update are read, not guessed. A failed download shows nothing.

from __future__ import annotations

import datetime as dt
import io
import time
from typing import Callable, Dict, List, Optional

import pandas as pd

SERIES = "GDPNOW"
BEA_SERIES = "A191RL1Q225SBEA"      # BEA real GDP, % change at an annual rate
ALFRED_CSV = "https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={ids}&vintage_date={dates}"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=2011-01-01"
SOURCE_PAGE = "https://www.atlantafed.org/cqer/research/gdpnow"
MAX_VINTAGES = 12                   # ALFRED returns at most this many vintages per request
RECENT_DAYS = 12                    # daily vintages: finds the latest update day exactly
PATH_WEEKS = 12                     # weekly vintages before that: the estimate's path
TRACK_QUARTERS = 8
_TTL_OK, _TTL_FAIL = 6 * 3600.0, 600.0
_cache: Optional[dict] = None
_cache_at = 0.0


def quarter_label(q: pd.Timestamp) -> str:
    """'Oct–Dec 2026' for the quarter starting 2026-10-01."""
    end = q + pd.offsets.QuarterEnd(0)
    return f"{q:%b}–{end:%b} {q.year}"


def quarter_short(q: pd.Timestamp) -> str:
    return f"Q{(q.month - 1) // 3 + 1} {q.year}"


def parse_alfred(text: str) -> pd.DataFrame:
    """ALFRED's vintage CSV: rows are quarters, columns are vintage dates."""
    frame = pd.read_csv(io.StringIO(text or ""))
    if frame.shape[1] < 2 or frame.empty:
        return pd.DataFrame()
    frame.index = pd.to_datetime(frame.iloc[:, 0], errors="coerce")
    frame = frame.iloc[:, 1:]
    frame.columns = [pd.Timestamp(str(c).rsplit("_", 1)[-1]) for c in frame.columns]
    return frame.apply(pd.to_numeric, errors="coerce").loc[frame.index.notna()].sort_index()


def parse_fred(text: str) -> pd.Series:
    frame = pd.read_csv(io.StringIO(text or ""))
    if frame.shape[1] < 2 or frame.empty:
        return pd.Series(dtype=float)
    s = pd.to_numeric(frame.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(frame.iloc[:, 0], errors="coerce")
    return s[s.index.notna()].dropna().sort_index()


def vintage_dates(today: dt.date) -> List[List[dt.date]]:
    """Two requests' worth: the last RECENT_DAYS days, then weekly before them."""
    recent = [today - dt.timedelta(days=i) for i in range(RECENT_DAYS - 1, -1, -1)]
    first = recent[0]
    weekly = [first - dt.timedelta(weeks=w) for w in range(PATH_WEEKS, 0, -1)]
    return [weekly, recent]


def estimate_path(vintages: pd.DataFrame) -> dict:
    """The quarter the newest vintage estimates, its path and its latest update.

    `vintages` columns are vintage dates in order. The current quarter is the
    newest vintage's last row with a value. A vintage that does not change the
    value is not an update; the first one that does is.
    """
    vintages = vintages.dropna(axis=1, how="all")   # a vintage ALFRED does not have yet is blank
    if vintages.empty:
        return {}
    cols = sorted(vintages.columns)
    newest = vintages[cols[-1]].dropna()
    if newest.empty:
        return {}
    q = newest.index[-1]
    row = vintages.loc[q, cols]
    points, prev = [], None
    for d in cols:
        v = row[d]
        if pd.isna(v):
            continue
        v = float(v)
        if prev is None or abs(v - prev) > 1e-9:
            points.append({"date": str(d.date()), "value": round(v, 2)})
        prev = v
    if not points:
        return {}
    # The latest update's date is exact only when the vintage before it is the
    # day before; with a gap the change happened somewhere inside the gap.
    last = points[-1]
    at = cols.index(pd.Timestamp(last["date"]))
    exact = len(points) > 1 and at > 0 and (cols[at] - cols[at - 1]).days == 1
    return {"quarter": str(q.date()), "label": quarter_label(q), "short": quarter_short(q),
            "value": last["value"], "updated": last["date"] if exact else None,
            "checked": str(cols[-1].date()), "path": points}


def track_record(final: pd.Series, bea: pd.Series, before: str, n: int = TRACK_QUARTERS) -> dict:
    """Each completed quarter's final GDPNow estimate beside the BEA figure."""
    both = pd.concat({"now": final, "bea": bea}, axis=1).dropna()
    both = both[both.index < pd.Timestamp(before)].tail(n)
    if both.empty:
        return {}
    rows = [{"quarter": str(q.date()), "short": quarter_short(q),
             "gdpnow": round(float(r["now"]), 2), "bea": round(float(r["bea"]), 2)}
            for q, r in both.iterrows()]
    miss = (both["now"] - both["bea"]).abs()
    return {"rows": rows, "mean_miss": round(float(miss.mean()), 2), "n": len(rows)}


def _get(url: str) -> str:
    import requests
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text


def build_context(get: Callable[[str], str] = _get, today: Optional[dt.date] = None) -> dict:
    """Everything the panel needs, or {"available": False, "reason": ...}."""
    today = today or dt.date.today()
    try:
        frames = []
        for dates in vintage_dates(today):
            ids = ",".join([SERIES] * len(dates))
            frames.append(parse_alfred(get(ALFRED_CSV.format(ids=ids, dates=",".join(map(str, dates))))))
        vintages = pd.concat([f for f in frames if not f.empty], axis=1)
        vintages = vintages.loc[:, ~vintages.columns.duplicated()].sort_index(axis=1)
        est = estimate_path(vintages)
        if not est:
            return {"available": False, "reason": "the Atlanta Fed's estimate could not be read"}
        final = parse_fred(get(FRED_CSV.format(sid=SERIES)))
        try:
            bea = parse_fred(get(FRED_CSV.format(sid=BEA_SERIES)))
        except Exception:
            bea = pd.Series(dtype=float)                 # the record is left out, never guessed
        return {"available": True, **est, "track": track_record(final, bea, est["quarter"])}
    except Exception as exc:
        return {"available": False, "reason": f"the download failed ({type(exc).__name__})"}


def context() -> dict:
    """build_context, kept 6 hours (10 minutes after a failure)."""
    global _cache, _cache_at
    ttl = _TTL_OK if (_cache or {}).get("available") else _TTL_FAIL
    if _cache is None or time.time() - _cache_at > ttl:
        _cache, _cache_at = build_context(), time.time()
    return _cache
