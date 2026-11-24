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
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

UA = "UnstructuredAlpha/1.0 research@unstructuredalpha.com"
MF_URL = "https://www.sec.gov/files/company_tickers_mf.json"
FEED = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={series}"
        "&type=NPORT-P&dateb=&owner=include&count=10&output=atom")
OUT = ROOT / "utils" / "data" / "lookthrough.json.gz"
PAUSE = 0.25          # the SEC asks for at most 10 requests a second


def get(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            time.sleep(PAUSE)
            return body
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    return b""


def fund_tickers() -> list[str]:
    from utils.config import TICKERS
    from utils.symbol_search import common_symbols
    out = [t for t, _n, kind in common_symbols() if kind in ("ETF", "Fund")]
    out += [t for t, m in TICKERS.items() if m.get("sector") == "ETF"]
    return sorted(set(out))


def latest_filing(series: str) -> tuple[str, str] | None:
    feed = get(FEED.format(series=series)).decode("utf-8", "replace")
    m = re.search(r"<filing-date>([^<]+)</filing-date>.*?<filing-href>([^<]+)</filing-href>", feed, re.S)
    if not m:
        m2 = re.search(r"<filing-href>([^<]+)</filing-href>.*?<filing-date>([^<]+)</filing-date>", feed, re.S)
        if not m2:
            return None
        return m2.group(2), m2.group(1)
    return m.group(1), m.group(2)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def summarize(xml_bytes: bytes, series: str) -> dict:
    """Stream the filing; keep aggregates and the ten largest positions."""
    assets, issuers, currencies, countries = (defaultdict(float) for _ in range(4))
    # many lines share one issuer (a bond fund holds dozens of Treasury notes),
    # so positions are combined by name before the ten largest are kept
    byname: dict[str, list] = {}
    n = 0
    period = net_assets = None
    name = ""
    for _ev, el in ET.iterparse(__import__("io").BytesIO(xml_bytes), events=("end",)):
        tag = _local(el.tag)
        if tag == "repPdDate":
            period = (el.text or "").strip()
        elif tag == "netAssets" and net_assets is None:
            try:
                net_assets = float(el.text)
            except (TypeError, ValueError):
                pass
        elif tag == "seriesName" and not name:
            name = (el.text or "").strip()
        elif tag == "invstOrSec":
            f = {_local(c.tag): c for c in el}
            try:
                pct = float((f.get("pctVal").text or "0")) if f.get("pctVal") is not None else 0.0
            except ValueError:
                pct = 0.0
            asset = (f.get("assetCat").text if f.get("assetCat") is not None else "") or "OTHER"
            issuer = (f.get("issuerCat").text if f.get("issuerCat") is not None else "") or "OTHER"
            country = (f.get("invCountry").text if f.get("invCountry") is not None else "") or "??"
            cur = "USD"
            cc = f.get("curCd")
            if cc is not None and cc.text:
                cur = cc.text.strip()
            else:
                cond = f.get("currencyConditional")
                if cond is not None and cond.get("curCd"):
                    cur = cond.get("curCd")
            assets[asset] += pct
            issuers[issuer] += pct
            currencies[cur] += pct
            countries[country] += pct
            nm = ((f.get("name").text if f.get("name") is not None else "") or "").strip() or "Unnamed"
            cur_row = byname.setdefault(nm, [0.0, asset, country, 0])
            cur_row[0] += pct
            cur_row[3] += 1
            n += 1
            el.clear()

    def mix(d: dict, k: int, keep: str = "") -> list:
        # `keep` always gets its own line: the dollar share (and the U.S.
        # share) must never be folded into "other", or a fund that is 97%
        # foreign would read as 100% foreign
        rows = sorted(((key, round(v, 2)) for key, v in d.items() if v > 0), key=lambda x: -x[1])
        head = rows[:k]
        if keep and keep in d and d[keep] > 0 and all(key != keep for key, _ in head):
            head = head + [(keep, round(d[keep], 2))]
        rest = sum(v for key, v in rows if (key, v) not in head)
        return head + ([["other", round(rest, 2)]] if rest >= 0.05 else [])

    return {
        "series": series, "series_name": name, "period": period, "net_assets": net_assets,
        "holdings": n,
        "assets": mix(assets, 5), "issuers": mix(issuers, 5),
        "currencies": mix(currencies, 6, keep="USD"), "countries": mix(countries, 8, keep="US"),
        "top": [[nm, round(r[0], 2), r[1], r[2], r[3]]
                for nm, r in sorted(byname.items(), key=lambda kv: (-round(kv[1][0], 6), kv[0]))[:10]],
    }


def main(argv: list[str]) -> int:
    mf = json.loads(get(MF_URL))
    by_ticker = {row[3].upper(): row for row in mf["data"]}
    tickers = [t.upper() for t in argv] or fund_tickers()
    existing = {}
    if OUT.exists():
        try:
            existing = json.loads(gzip.decompress(OUT.read_bytes()))
        except Exception:
            existing = {}
    funds = dict(existing.get("funds", {}))
    for t in tickers:
        row = by_ticker.get(t)
        if not row:
            funds[t] = {"none": "no N-PORT filer"}
            print(f"{t:6} no N-PORT series (not a registered fund)")
            continue
        series = row[1]
        try:
            hit = latest_filing(series)
            if not hit:
                funds[t] = {"none": "no N-PORT filing found", "series": series}
                print(f"{t:6} {series} no NPORT-P filings")
                continue
            filed, href = hit
            folder = href.rsplit("/", 1)[0]
            doc = get(folder + "/primary_doc.xml", timeout=180)
            s = summarize(doc, series)
            s["filed"], s["source"] = filed, href
            funds[t] = s
            print(f"{t:6} {series} {s['period']} {s['holdings']:>6} holdings  filed {filed}")
        except Exception as e:                        # a failed fund is left out, never estimated
            print(f"{t:6} {series} FAILED: {e}", file=sys.stderr)
            if t in existing.get("funds", {}):
                funds[t] = existing["funds"][t]
    snap = {"built": time.strftime("%Y-%m-%d"), "funds": funds}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(gzip.compress(json.dumps(snap, separators=(",", ":"), sort_keys=True).encode(), mtime=0))
    print(f"wrote {sum(1 for v in funds.values() if 'holdings' in v)} funds to {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
