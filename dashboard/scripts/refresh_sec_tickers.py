"""Refresh the bundled SEC ticker-to-company-name snapshot.

    python scripts/refresh_sec_tickers.py

Writes utils/data/sec_company_tickers.json.gz: {"TICKER": "Company name"}
from the SEC's public company_tickers.json (about 10,000 listed companies),
and utils/data/sec_fund_names.json.gz: {"TICKER": "Fund name (Share class)"}
from the SEC's Investment Company Series and Class data set (mutual funds,
ETFs and their share classes -- the 401(k) funds the company file lacks).
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
FUND_URL = ("https://www.sec.gov/files/investment/data/other/investment-company-series-class-information/"
            "investment-company-series-class-{year}.csv")
FUND_OUT = OUT.parent / "sec_fund_names.json.gz"
_SMALL = {"of", "and", "the", "for", "in", "on", "at", "to", "a", "an", "or"}


def tidy(name: str) -> str:
    """An all-capitals SEC name in ordinary case ('GROWTH FUND OF AMERICA' ->
    'Growth Fund of America'); anything already in mixed case is kept as filed."""
    name = " ".join(name.split())
    if not name or name != name.upper():
        return name
    words = name.title().split(" ")
    return " ".join(w.lower() if i and w.lower() in _SMALL else w for i, w in enumerate(words))


def fund_name(series: str, klass: str) -> str:
    """'Vanguard Total Stock Market Index Fund (Admiral Shares)'; the class is
    left off when it only repeats the fund's name."""
    series, klass = tidy(series), tidy(klass)
    if not klass or klass.lower() in series.lower() or series.lower() in klass.lower():
        return series or klass
    return f"{series} ({klass})"


def build_funds(rows) -> dict:
    out = {}
    for r in rows:
        t = (r.get("Class Ticker") or "").strip().upper()
        if t and t not in out and (r.get("Series Name") or r.get("Class Name")):
            out[t] = fund_name(r.get("Series Name") or "", r.get("Class Name") or "")
    return out


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

    import csv
    import io
    import time
    year = int(time.strftime("%Y"))
    for y in (year, year - 1):                   # the new year's file appears some weeks in
        try:
            req = urllib.request.Request(FUND_URL.format(year=y), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                text = r.read().decode("utf-8-sig", "replace")
            break
        except Exception:
            text = ""
    funds = build_funds(csv.DictReader(io.StringIO(text))) if text else {}
    if len(funds) < 5000:
        print(f"refusing to write a suspiciously small fund snapshot ({len(funds)} names)", file=sys.stderr)
        return 1
    FUND_OUT.write_bytes(gzip.compress(json.dumps(funds, separators=(",", ":"), sort_keys=True).encode(), mtime=0))
    print(f"wrote {len(funds)} fund names to {FUND_OUT} ({FUND_OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
