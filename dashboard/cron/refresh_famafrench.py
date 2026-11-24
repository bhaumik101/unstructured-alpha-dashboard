"""Weekly: store the latest Fama-French weekly factors (cron/run_group weekly-universe).

Downloads the weekly 3-factor file from Kenneth French's data library (about
40 KB), keeps the last 120 weeks and upserts them into ff_weekly;
utils/famafrench.py merges them over the bundled snapshot. The library is
revised now and then, so recent weeks are re-stored, not only new ones. A
failed download leaves what was stored and fails the job.
"""

from __future__ import annotations

import sys
import urllib.request

from utils import famafrench as ff


def main() -> int:
    try:
        req = urllib.request.Request(ff.URL, headers={"User-Agent": "Mozilla/5.0 (compatible; UnstructuredAlpha/1.0)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            frame = ff.parse_zip(r.read())
    except Exception as e:
        print(f"[famafrench] download or parse failed: {str(e)[:160]}", file=sys.stderr, flush=True)
        return 1
    frame = frame.iloc[-120:]
    if frame.empty:
        print("[famafrench] the file had no weekly rows", file=sys.stderr, flush=True)
        return 1
    from utils import db
    if db.IS_SQLITE:
        from sqlalchemy.dialects.sqlite import insert as _ins
    else:
        from sqlalchemy.dialects.postgresql import insert as _ins
    rows = [{"date": str(d.date()), "mkt_rf": float(m), "smb": float(s), "hml": float(h), "rf": float(r)}
            for d, (m, s, h, r) in zip(frame.index, frame.to_numpy())]
    stmt = _ins(db.ff_weekly).values(rows)
    stmt = stmt.on_conflict_do_update(index_elements=["date"], set_={
        "mkt_rf": stmt.excluded.mkt_rf, "smb": stmt.excluded.smb, "hml": stmt.excluded.hml, "rf": stmt.excluded.rf})
    with db.engine.begin() as conn:
        conn.execute(stmt)
    print(f"[famafrench] stored {len(rows)} weeks through {rows[-1]['date']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
