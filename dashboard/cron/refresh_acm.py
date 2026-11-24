"""Weekly: store the NY Fed's latest ACM term-premium days (cron/run_group weekly-universe).

Downloads ACMTermPremium.xls (about 10 MB; parsed here, never in the web app),
keeps the last 400 days of the 10-year columns and upserts them into
acm_daily. utils/acm.py merges them over the bundled snapshot. A failed
download leaves what was stored; nothing is filled in. Exits non-zero only
when the download or parse fails outright.
"""

from __future__ import annotations

import sys
import urllib.request

from utils import acm


def main() -> int:
    try:
        req = urllib.request.Request(acm.URL, headers={"User-Agent": "Mozilla/5.0 (compatible; UnstructuredAlpha/1.0)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            frame = acm.parse_xls(r.read())
    except Exception as e:
        print(f"[acm] download or parse failed: {str(e)[:160]}", file=sys.stderr, flush=True)
        return 1
    frame = frame.iloc[-400:]
    if frame.empty:
        print("[acm] the sheet had no 10-year rows", file=sys.stderr, flush=True)
        return 1
    from utils import db
    if db.IS_SQLITE:
        from sqlalchemy.dialects.sqlite import insert as _ins
    else:
        from sqlalchemy.dialects.postgresql import insert as _ins
    rows = [{"date": str(d.date()), "y10": float(y), "tp10": float(tp), "rny10": float(r)}
            for d, (y, tp, r) in zip(frame.index, frame.to_numpy())]
    stmt = _ins(db.acm_daily).values(rows)
    stmt = stmt.on_conflict_do_update(index_elements=["date"],
                                      set_={"y10": stmt.excluded.y10, "tp10": stmt.excluded.tp10,
                                            "rny10": stmt.excluded.rny10})
    with db.engine.begin() as conn:
        conn.execute(stmt)
    print(f"[acm] stored {len(rows)} days through {rows[-1]['date']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
