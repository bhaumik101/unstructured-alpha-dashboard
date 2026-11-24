# utils/acm.py
# Unstructured Alpha — the 10-year Treasury yield, split in two (NY Fed ACM)
#
# The New York Fed's Adrian-Crump-Moench model splits the 10-year yield into
#   * the expected path of short-term rates (ACMRNY10, the "risk-neutral"
#     yield): where markets think the Fed's rate is heading, and
#   * the term premium (ACMTP10): the extra yield investors demand to hold a
#     ten-year bond instead of rolling short ones.
# The two add up to the yield exactly (ACMY10 = ACMTP10 + ACMRNY10). A
# portfolio can move with one and not the other: a long-bond fund with both,
# a bank stock mostly with the expected path.
#
# RULES
#   * The web app never parses the NY Fed's 10 MB spreadsheet. A bundled
#     daily snapshot (scripts/build_acm_snapshot.py) and the rows the weekly
#     cron stores (cron/refresh_acm.py, table acm_daily) are merged here; the
#     newer row for a date wins.
#   * A gap is a gap: no day is interpolated, and with too little data the
#     split is simply not shown.
#   * Estimates from a model, labelled as the NY Fed's; it describes the past.

from __future__ import annotations

import gzip
import io
import json
import time
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

URL = "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls"
SOURCE_PAGE = "https://www.newyorkfed.org/research/data_indicators/term-premia-tabs"
COLUMNS = ("ACMY10", "ACMTP10", "ACMRNY10")
_FILE = Path(__file__).resolve().parent / "data" / "acm_daily.json.gz"
_cache: Optional[pd.DataFrame] = None
_cache_at = 0.0
_TTL = 3600.0


def parse_xls(data: bytes, since: str = "2014-01-01") -> pd.DataFrame:
    """The 'ACM Daily' sheet's 10-year columns, from `since` on."""
    frame = pd.read_excel(io.BytesIO(data), sheet_name="ACM Daily", usecols=["DATE", *COLUMNS])
    frame["DATE"] = pd.to_datetime(frame["DATE"], format="mixed", errors="coerce")
    frame = frame.dropna().set_index("DATE").sort_index()
    return frame[frame.index >= pd.Timestamp(since)][list(COLUMNS)].astype(float)


def to_rows(frame: pd.DataFrame) -> Dict[str, list]:
    return {str(d.date()): [round(float(v), 6) for v in row] for d, row in zip(frame.index, frame.to_numpy())}


def _from_rows(rows: Dict[str, list]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(COLUMNS), dtype=float)
    idx = pd.to_datetime(list(rows))
    return pd.DataFrame([rows[k] for k in rows], index=idx, columns=list(COLUMNS)).sort_index()


def _bundled() -> Dict[str, list]:
    try:
        return json.loads(gzip.decompress(_FILE.read_bytes())).get("rows", {})
    except Exception:
        return {}


def _stored() -> Dict[str, list]:
    try:
        from sqlalchemy import select
        from utils import db
        t = db.acm_daily
        with db.engine.begin() as conn:
            got = conn.execute(select(t.c.date, t.c.y10, t.c.tp10, t.c.rny10)).all()
        return {d: [y, tp, r] for d, y, tp, r in got}
    except Exception:
        return {}


def daily() -> pd.DataFrame:
    """Daily ACMY10 / ACMTP10 / ACMRNY10, bundled plus stored; re-read hourly."""
    global _cache, _cache_at
    if _cache is None or time.time() - _cache_at > _TTL:
        rows = _bundled()
        rows.update(_stored())                       # the weekly refresh's rows win for their dates
        _cache, _cache_at = _from_rows(rows), time.time()
    return _cache


def series(column: str) -> Optional[pd.Series]:
    """One column as a daily level series (percent), or None when unavailable."""
    frame = daily()
    if frame.empty or column not in frame:
        return None
    s = frame[column].dropna()
    return s if not s.empty else None
