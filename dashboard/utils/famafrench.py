# utils/famafrench.py
# Unstructured Alpha — the Fama-French factors, as an independent check
#
# The report removes the stock market's own move using SPY and reads size and
# value tilts from fund-price spreads (IWM/IWB, IWD/IWF), because those are
# current to the day. The academic factors from Kenneth French's data library
# (Mkt-RF: the whole U.S. market over T-bills; SMB: small minus big; HML:
# value minus growth) are built differently and published a month or two
# late. They are the independent yardstick: if the report's market beta and
# style tilts agree with them, the market adjustment is sound.
#
# RULES
#   * The web app reads a bundled weekly snapshot plus the rows the weekly
#     cron stores (cron/refresh_famafrench.py, table ff_weekly); it never
#     downloads the library itself. Newer rows win for their week.
#   * Their two-month lag is stated, not hidden: the check covers only the
#     weeks both have.
#   * The library's data are © Eugene F. Fama and Kenneth R. French and are
#     credited where shown.

from __future__ import annotations

import gzip
import io
import json
import time
import zipfile
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_weekly_CSV.zip"
SOURCE_PAGE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"
COLUMNS = ("Mkt-RF", "SMB", "HML", "RF")
_FILE = Path(__file__).resolve().parent / "data" / "ff_weekly.json.gz"
_cache: Optional[pd.DataFrame] = None
_cache_at = 0.0
_TTL = 3600.0


def parse_zip(data: bytes, since: str = "2014-01-01") -> pd.DataFrame:
    """The weekly 3-factor table (percent), dated by its Friday, from `since` on."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    rows = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 5 and parts[0].isdigit() and len(parts[0]) == 8:
            try:
                rows.append((pd.Timestamp(parts[0]), *map(float, parts[1:])))
            except ValueError:
                continue
    frame = pd.DataFrame(rows, columns=["date", *COLUMNS]).set_index("date").sort_index()
    return frame[frame.index >= pd.Timestamp(since)]


def to_rows(frame: pd.DataFrame) -> Dict[str, list]:
    return {str(d.date()): [round(float(v), 4) for v in row] for d, row in zip(frame.index, frame.to_numpy())}


def _from_rows(rows: Dict[str, list]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(COLUMNS), dtype=float)
    return pd.DataFrame([rows[k] for k in rows], index=pd.to_datetime(list(rows)), columns=list(COLUMNS)).sort_index()


def _bundled() -> Dict[str, list]:
    try:
        return json.loads(gzip.decompress(_FILE.read_bytes())).get("rows", {})
    except Exception:
        return {}


def _stored() -> Dict[str, list]:
    try:
        from sqlalchemy import select
        from utils import db
        t = db.ff_weekly
        with db.engine.begin() as conn:
            got = conn.execute(select(t.c.date, t.c.mkt_rf, t.c.smb, t.c.hml, t.c.rf)).all()
        return {d: [m, s, h, r] for d, m, s, h, r in got}
    except Exception:
        return {}


def weekly() -> pd.DataFrame:
    """Weekly Mkt-RF, SMB, HML, RF in percent; bundled plus stored, re-read hourly."""
    global _cache, _cache_at
    if _cache is None or time.time() - _cache_at > _TTL:
        rows = _bundled()
        rows.update(_stored())
        _cache, _cache_at = _from_rows(rows), time.time()
    return _cache
