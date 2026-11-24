"""Build the fund look-through snapshot from SEC Form N-PORT filings.

    python scripts/build_lookthrough.py            # every fund the product names
    python scripts/build_lookthrough.py VXUS BND   # just these

For each fund ticker: the SEC's company_tickers_mf.json gives its series ID;
EDGAR's filing feed for that series gives the latest NPORT-P; its
primary_doc.xml lists every holding (name, value, share of net assets,
currency, asset and issuer category, country). This keeps a compact summary,
not the holdings: the count, asset mix, bond issuer mix, currency mix,
country mix and the ten largest positions. Written to
utils/data/lookthrough.json.gz for utils/lookthrough.py.

N-PORT is filed monthly but made public quarterly, about 60 days after the
quarter's last month, so the newest public filing is typically 2-4 months
old. The report states the date. Run this after each quarter's filings land.

Funds that do not file N-PORT (a commodity trust such as GLD, a unit
investment trust such as SPY) are recorded as having no filing; nothing is
estimated for them.
"""

from __future__ import annotations

import gzip
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.nport import (  # noqa: E402  (shared with cron/refresh_lookthrough.py)
    fund_tickers, refresh_one, series_map, summarize,
)

OUT = ROOT / "utils" / "data" / "lookthrough.json.gz"


def main(argv: list[str]) -> int:
    by_ticker = series_map()
    tickers = [t.upper() for t in argv] or fund_tickers()
    existing = {}
    if OUT.exists():
        try:
            existing = json.loads(gzip.decompress(OUT.read_bytes()))
        except Exception:
            existing = {}
    funds = dict(existing.get("funds", {}))
    for t in tickers:
        try:
            status, s = refresh_one(t, by_ticker)
            funds[t] = s
            print(f"{t:6} {status:4} " + (f"{s['period']} {s['holdings']:>6} holdings  filed {s['filed']}" if status == "new" else s.get("none", "")))
        except Exception as e:                        # a failed fund is left out, never estimated
            print(f"{t:6} FAILED: {e}", file=sys.stderr)
            if t in existing.get("funds", {}):
                funds[t] = existing["funds"][t]
    snap = {"built": time.strftime("%Y-%m-%d"), "funds": funds}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(gzip.compress(json.dumps(snap, separators=(",", ":"), sort_keys=True).encode(), mtime=0))
    print(f"wrote {sum(1 for v in funds.values() if 'holdings' in v)} funds to {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
