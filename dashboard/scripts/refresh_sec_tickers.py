"""Refresh the bundled SEC ticker-to-company-name snapshot.

    python scripts/refresh_sec_tickers.py

Writes utils/data/sec_company_tickers.json.gz: {"TICKER": "Company name"}
from the SEC's public company_tickers.json (about 10,000 listed companies).
utils/holding_names.py uses it as the last local source for a holding's full
name, so a report never waits on the network to label a stock.

The SEC asks automated clients to identify themselves in the User-Agent; this
uses the same product identity as utils/fetchers.py's EDGAR requests.
"""

from __future__ import annotations

import gzip
import json
import sys
import urllib.request
from pathlib import Path

URL = "https://www.sec.gov/files/company_tickers.json"
UA = "UnstructuredAlpha/1.0 research@unstructuredalpha.com"
OUT = Path(__file__).resolve().parent.parent / "utils" / "data" / "sec_company_tickers.json.gz"


def build(payload: dict) -> dict:
    out = {}
    for row in payload.values():
        t, name = str(row.get("ticker") or "").upper().strip(), str(row.get("title") or "").strip()
        if t and name and t not in out:          # the file lists a company's primary ticker first
            out[t] = name
    return out


def main() -> int:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = build(json.load(r))
    if len(data) < 5000:
        print(f"refusing to write a suspiciously small snapshot ({len(data)} names)", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":"), sort_keys=True).encode(), mtime=0))
    print(f"wrote {len(data)} names to {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
