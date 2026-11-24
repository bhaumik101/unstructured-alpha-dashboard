"""Weekly: refresh the fund look-through from new SEC Form N-PORT filings.

Runs last in the weekly-universe group. For every fund the product names it
reads the fund's EDGAR filing feed (one small request) and downloads and
parses the filing only when it is newer than what is already known (the
database row, else the bundled snapshot). N-PORT becomes public about 60 days
after each quarter, so most weeks nothing changes and the job costs ~80 feed
requests; in the weeks a quarter lands it updates those funds.

A fund that fails keeps its previous summary; nothing is estimated. Exits
non-zero only if every fund failed (the SEC unreachable), so the group's
failure signal means something.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from utils import lookthrough as lt
from utils import nport


def _store(ticker: str, s: dict) -> None:
    from utils import db
    if db.IS_SQLITE:
        from sqlalchemy.dialects.sqlite import insert as _ins
    else:
        from sqlalchemy.dialects.postgresql import insert as _ins
    values = {"ticker": ticker, "source": s.get("source"), "filed": s.get("filed"), "period": s.get("period"),
              "payload": json.dumps(s, separators=(",", ":")), "updated_at": datetime.now(timezone.utc).isoformat()}
    stmt = _ins(db.fund_lookthrough).values(**values).on_conflict_do_update(
        index_elements=["ticker"], set_={k: v for k, v in values.items() if k != "ticker"})
    with db.engine.begin() as conn:
        conn.execute(stmt)


def main() -> int:
    lt._snap = None                                  # read the database fresh, not a cached view
    known = lt.snapshot()["funds"]
    by_ticker = nport.series_map()
    tickers = sorted(set(nport.fund_tickers()) | {t for t, f in known.items() if f.get("holdings")})
    counts = {"same": 0, "new": 0, "none": 0, "failed": 0}
    for t in tickers:
        try:
            status, s = nport.refresh_one(t, by_ticker, (known.get(t) or {}).get("source", ""))
            counts[status] += 1
            if status == "new":
                _store(t, s)
                print(f"[lookthrough] {t} new filing {s['period']} ({s['holdings']} holdings)", flush=True)
        except Exception as e:
            counts["failed"] += 1
            print(f"[lookthrough] {t} failed: {str(e)[:120]}", file=sys.stderr, flush=True)
    print(f"[lookthrough] {counts}", flush=True)
    return 1 if counts["failed"] and not (counts["same"] or counts["new"] or counts["none"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
