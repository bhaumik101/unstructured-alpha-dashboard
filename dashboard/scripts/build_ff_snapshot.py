"""Build the bundled Fama-French weekly snapshot used by utils/famafrench.py.

    python scripts/build_ff_snapshot.py

Downloads the weekly 3-factor file from Kenneth French's data library and
writes utils/data/ff_weekly.json.gz (2014 on). cron/refresh_famafrench.py
keeps the database current each week.
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

from utils import famafrench as ff  # noqa: E402


def main() -> int:
    req = urllib.request.Request(ff.URL, headers={"User-Agent": "Mozilla/5.0 (compatible; UnstructuredAlpha/1.0)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        frame = ff.parse_zip(r.read())
    if len(frame) < 400:
        print(f"refusing to write a suspiciously small snapshot ({len(frame)} weeks)", file=sys.stderr)
        return 1
    out = Path(ff._FILE)
    out.write_bytes(gzip.compress(json.dumps({"built": time.strftime("%Y-%m-%d"), "rows": ff.to_rows(frame)},
                                             separators=(",", ":")).encode(), mtime=0))
    print(f"wrote {len(frame)} weeks ({frame.index[0].date()} to {frame.index[-1].date()}) to {out} "
          f"({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
