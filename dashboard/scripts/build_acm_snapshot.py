"""Build the bundled NY Fed ACM daily snapshot (10-year yield, term premium,
expected path) used by utils/acm.py.

    python scripts/build_acm_snapshot.py

Downloads the NY Fed's ACMTermPremium.xls, keeps the daily 10-year columns
from 2014 on, and writes utils/data/acm_daily.json.gz. cron/refresh_acm.py
keeps the database current each week; this file is the starting point.
"""

from __future__ import annotations

import gzip
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils import acm  # noqa: E402


def main() -> int:
    req = urllib.request.Request(acm.URL, headers={"User-Agent": "Mozilla/5.0 (compatible; UnstructuredAlpha/1.0)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        frame = acm.parse_xls(r.read())
    if len(frame) < 2000:
        print(f"refusing to write a suspiciously small snapshot ({len(frame)} days)", file=sys.stderr)
        return 1
    out = Path(acm._FILE)
    out.write_bytes(gzip.compress(json.dumps({"built": time.strftime("%Y-%m-%d"), "rows": acm.to_rows(frame)},
                                             separators=(",", ":")).encode(), mtime=0))
    print(f"wrote {len(frame)} days ({frame.index[0].date()} to {frame.index[-1].date()}) to {out} "
          f"({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
