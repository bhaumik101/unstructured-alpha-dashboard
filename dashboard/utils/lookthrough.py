# utils/lookthrough.py
# Unstructured Alpha — what a fund actually holds, from its SEC Form N-PORT
#
# The report says VXUS carries 78% of a portfolio's dollar exposure. A
# beginner's next question is why. The fund's own filing answers it: about
# 8,900 holdings, almost all priced in currencies other than the dollar. This
# turns each fund's latest N-PORT into a few plain sentences and two bars, and
# links them to the exposure the fund carries in this report.
#
# RULES
#   * Facts from the filing only: counts, shares of net assets, currencies,
#     issuers, countries, the largest positions, and the filing's date. The
#     snapshot is built offline (scripts/build_lookthrough.py) and read
#     locally; a report never waits on the SEC.
#   * A fund with no N-PORT (a commodity trust, a unit investment trust) is
#     said to have no filing; nothing is estimated for it. Single stocks are
#     not looked through: a stock is what it holds.
#   * The "why it matters here" line names a mechanism only where it is a
#     plain matter of arithmetic (prices in another currency; bond prices and
#     yields), and only for a fund that carries that exposure in this report.
#     It describes the past; it is not a forecast.

from __future__ import annotations

import gzip
import json
import time
from html import escape
from pathlib import Path
from typing import Dict, List, Optional

_FILE = Path(__file__).resolve().parent / "data" / "lookthrough.json.gz"
_snap: Optional[dict] = None

# N-PORT's category codes, in words a newcomer reads.
ASSETS = {
    "EC": "Stocks", "EP": "Preferred stock", "DBT": "Bonds", "ABS-MBS": "Mortgage-backed bonds",
    "ABS-CBDO": "Other asset-backed bonds", "ABS-O": "Other asset-backed bonds",
    "ABS-APCP": "Asset-backed commercial paper", "STIV": "Cash and short-term holdings",
    "LON": "Loans", "RE": "Real estate", "COMM": "Commodities", "SN": "Structured notes",
    "DCO": "Commodity derivatives", "DCR": "Credit derivatives", "DE": "Equity derivatives",
    "DFE": "Currency contracts", "DIR": "Interest-rate derivatives", "DO": "Other derivatives",
    "OTHER": "Other", "other": "Other",
}
ISSUERS = {
    "UST": "U.S. Treasury", "USGA": "U.S. government agencies",
    "USGSE": "Government-sponsored agencies (Fannie Mae, Freddie Mac)", "CORP": "Companies",
    "MUN": "U.S. states and cities", "NUSS": "Governments outside the U.S.",
    "RF": "Other funds", "PF": "Private funds", "OTHER": "Other", "other": "Other",
}
CURRENCIES = {
    "USD": "U.S. dollar", "EUR": "euro", "JPY": "Japanese yen", "GBP": "British pound",
    "CAD": "Canadian dollar", "CHF": "Swiss franc", "AUD": "Australian dollar", "HKD": "Hong Kong dollar",
    "TWD": "Taiwan dollar", "KRW": "South Korean won", "INR": "Indian rupee", "CNY": "Chinese yuan",
    "SEK": "Swedish krona", "DKK": "Danish krone", "BRL": "Brazilian real", "ZAR": "South African rand",
    "SGD": "Singapore dollar", "MXN": "Mexican peso", "other": "other currencies",
}
COUNTRIES = {
    "US": "United States", "JP": "Japan", "GB": "United Kingdom", "CA": "Canada", "FR": "France",
    "DE": "Germany", "CH": "Switzerland", "TW": "Taiwan", "KR": "South Korea", "HK": "Hong Kong",
    "CN": "China", "IN": "India", "AU": "Australia", "NL": "Netherlands", "SE": "Sweden",
    "DK": "Denmark", "IT": "Italy", "ES": "Spain", "BR": "Brazil", "MX": "Mexico", "IE": "Ireland",
    "SG": "Singapore", "ZA": "South Africa", "N/A": "Not stated", "other": "Other countries",
}
BOND_ASSETS = ("DBT", "ABS-MBS", "ABS-CBDO", "ABS-O", "ABS-APCP")


_snap_at = 0.0
_TTL = 3600.0


def _bundled() -> dict:
    try:
        return json.loads(gzip.decompress(_FILE.read_bytes()))
    except Exception:
        return {"funds": {}}


def _stored() -> Dict[str, dict]:
    """Rows the weekly refresh wrote; empty when the table is missing or unreachable."""
    try:
        from sqlalchemy import select
        from utils import db
        with db.engine.begin() as conn:
            rows = conn.execute(select(db.fund_lookthrough.c.ticker, db.fund_lookthrough.c.payload)).all()
        return {t: json.loads(p) for t, p in rows}
    except Exception:
        return {}


def _newer(a: Optional[dict], b: Optional[dict]) -> bool:
    """Is summary a from a later filing than b?"""
    if not b:
        return True
    return (a.get("filed") or "", a.get("period") or "") > (b.get("filed") or "", b.get("period") or "")


def snapshot() -> dict:
    """The bundled snapshot, with any newer filing the weekly refresh stored on top.
    Re-read at most hourly, so a report never queries per render."""
    global _snap, _snap_at
    if _snap is None or time.time() - _snap_at > _TTL:
        snap = _bundled()
        funds = dict(snap.get("funds", {}))
        for t, s in _stored().items():
            if s.get("holdings") and _newer(s, funds.get(t)):
                funds[t] = s
        _snap, _snap_at = {"built": snap.get("built"), "funds": funds}, time.time()
    return _snap


def fund(ticker: str) -> Optional[dict]:
    """The fund's summary, {"none": why} when it files no N-PORT, None if unknown."""
    return snapshot().get("funds", {}).get(str(ticker or "").upper().strip())


def _date(iso: str) -> str:
    from datetime import date
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f"{d:%b} {d.day}, {d.year}"
    except ValueError:
        return str(iso or "?")


def _pct(v: float) -> str:
    v = min(max(v, 0.0), 100.0)                # cash and collateral can push a sum past 100
    return f"{v:.0f}%" if v >= 1 else ("<1%" if v > 0 else "0%")


def mix(f: dict, key: str) -> List:
    """A breakdown as shares that add to at most 100%. A fund lending its
    securities holds the cash collateral too, so its filing's shares of net
    assets can add to 111%; scaled down, they read as shares of what it holds."""
    rows = [(c, float(v)) for c, v in f.get(key, []) if v > 0]
    total = sum(v for _, v in rows)
    return [(c, v * 100.0 / total) for c, v in rows] if total > 100.0 else rows


def _share(rows: List, keys) -> float:
    return sum(v for k, v in rows if k in keys)


def non_usd(f: dict) -> float:
    return 100.0 - _share(mix(f, "currencies"), ("USD",)) if f.get("currencies") else 0.0


def bonds(f: dict) -> float:
    return _share(mix(f, "assets"), BOND_ASSETS)


def _words(rows: List, names: Dict[str, str], k: int = 3, floor: float = 1.0) -> str:
    parts = [f"{names.get(c, c)} {_pct(v)}" for c, v in rows if c != "other" and v >= floor][:k]
    return ", ".join(parts)


def why_here(ticker: str, f: dict, report: dict) -> str:
    """A plain mechanism, only for an exposure this fund carries in this report."""
    readings = report["portfolio"]["readings"]
    carried = set()
    for key, rows in (report.get("contributions") or {}).items():
        r = readings.get(key, {})
        if r.get("evidence") not in ("clear", "tentative"):
            continue
        for c in rows:
            if c["ticker"] == ticker and c.get("share") is not None and c["share"] >= 0.25:
                carried.add(key)
    if "dollar" in carried and non_usd(f) >= 30:
        return (f"Why it carries the U.S. dollar exposure here: {_pct(non_usd(f))} of it is priced in other "
                "currencies, so when the dollar strengthens those holdings are worth fewer dollars.")
    if "rates" in carried and bonds(f) >= 50:
        return (f"Why it carries the interest-rate exposure here: {_pct(bonds(f))} of it is bonds, and a bond's "
                "price falls when interest rates rise.")
    return ""


def card_html(ticker: str, f: dict, report: dict, name: str = "") -> str:
    held = f.get("holdings", 0)
    assets = [(c, v) for c, v in mix(f, "assets") if v >= 0.5]
    lines = [f'<p class="ult-line">Holds: {escape(_words(assets, ASSETS).lower())}.</p>']
    if bonds(f) >= 30:
        lines.append(f'<p class="ult-line">Who issued the bonds: {escape(_words(mix(f, "issuers"), ISSUERS))}.</p>')
    nu = non_usd(f)
    if nu >= 10:
        cur = [(c, v) for c, v in mix(f, "currencies") if c != "USD"]
        lines.append(f'<p class="ult-line">{_pct(nu)} is priced in currencies other than the dollar: '
                     f'{escape(_words(cur, CURRENCIES))}.</p>')
        lines.append(f'<p class="ult-line">Largest countries: {escape(_words(mix(f, "countries"), COUNTRIES))}.</p>')
    why = why_here(ticker, f, report)
    bar = "".join(
        f'<i style="width:{min(max(v, 0), 100):.2f}%" class="ult-seg ult-{"bond" if c in BOND_ASSETS else "eq" if c in ("EC", "EP") else "cash" if c == "STIV" else "oth"}" '
        f'title="{escape(ASSETS.get(c, c))} {_pct(v)}"></i>' for c, v in assets)
    top = "".join(
        f'<li><span>{escape(t[0])}</span><b>{_pct(t[1]) if t[1] >= 1 else f"{t[1]:.1f}%"}</b></li>'
        for t in [t for t in f.get("top", []) if t[2] != "STIV"][:5])      # cash and collateral are not "holdings" to a reader
    return (
        '<div class="ult-card">'
        f'<div class="ult-head"><b>{escape(ticker)}</b><span>{escape(name)}</span></div>'
        f'<div class="ult-meta">{held:,} holdings · as of {escape(_date(f.get("period")))} · '
        f'<a href="{escape(f.get("source") or "#")}" target="_blank" rel="noopener">SEC Form N-PORT</a></div>'
        f'<div class="ult-bar" role="img" aria-label="{escape("What it holds: " + _words(assets, ASSETS, k=6, floor=0.5))}">{bar}</div>'
        + "".join(lines)
        + (f'<p class="ult-why">{escape(why)}</p>' if why else "")
        + (f'<div class="ult-top-k">Largest holdings</div><ol class="ult-top">{top}</ol>' if top else "")
        + '</div>')


def lookthrough_html(report: dict, names=None) -> str:
    """'What your funds hold' for the funds in this report; empty if none filed."""
    from utils import holding_names as hn
    names = names or hn.full_name
    positions = sorted(report.get("positions") or [], key=lambda p: -p["weight_pct"])
    cards, none = [], []
    for p in positions:
        f = fund(p["ticker"])
        if not f:
            continue
        if f.get("none"):
            none.append(p["ticker"])
        elif f.get("holdings"):
            cards.append(card_html(p["ticker"], f, report, names(p["ticker"])))
    if not cards:
        return ""
    note = (f'<p class="ult-none">No holdings filing for {escape(", ".join(none))}: '
            'not every fund files Form N-PORT (a commodity trust, for one, does not).</p>' if none else "")
    return (f'<div class="ult"><div class="ult-grid">{"".join(cards)}</div>{note}'
            '<p class="ult-foot">From each fund\'s latest public Form N-PORT filing with the SEC, which funds file '
            'monthly and the SEC publishes about 60 days after each quarter, so these are a few months old. '
            'Shares are of what the fund holds; cash and securities-lending collateral are counted in the '
            'mix but left out of the largest holdings.</p></div>')


LOOKTHROUGH_CSS = """<style>
.ult-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,420px),1fr));gap:14px;}
.ult-card{border:1px solid var(--p-line);border-radius:16px;padding:16px 18px;
  background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.01)),var(--p-surface);}
.ult-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;}
.ult-head b{font-family:ui-monospace,Menlo,monospace;font-size:var(--p-t-md);color:var(--p-ink);}
.ult-head span{font-size:var(--p-t-sm);color:var(--p-ink2);}
.ult-meta{font-size:var(--p-t-xs);color:var(--p-ink3);margin:2px 0 10px;}
.ult-meta a{color:var(--p-accent)!important;}
.ult-bar{display:flex;height:10px;border-radius:999px;overflow:hidden;background:var(--p-subtle);margin-bottom:10px;}
.ult-seg{display:block;height:100%;}
.ult-eq{background:#3b7ddd;}.ult-bond{background:#1a9a70;}.ult-cash{background:#8a96a8;}.ult-oth{background:#d99018;}
.stApp .ult-line{margin:0 0 4px!important;font-size:var(--p-t-sm)!important;color:var(--p-ink2)!important;line-height:1.5!important;}
.stApp .ult-why{margin:8px 0 4px!important;padding:8px 10px;border-radius:10px;font-size:var(--p-t-sm)!important;
  color:var(--p-ink)!important;background:rgba(108,229,210,.08);border:1px solid rgba(108,229,210,.3);line-height:1.5!important;}
.ult-top-k{margin-top:10px;font-size:var(--p-t-xs);letter-spacing:.06em;text-transform:uppercase;color:var(--p-ink3);font-weight:700;}
.ult-top{list-style:none;margin:4px 0 0;padding:0;}
.ult-top li{display:flex;justify-content:space-between;gap:12px;padding:4px 0;border-bottom:1px solid var(--p-line);font-size:var(--p-t-sm);color:var(--p-ink2);}
.ult-top li:last-child{border-bottom:0;}
.ult-top li span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.ult-top li b{color:var(--p-ink);font-variant-numeric:tabular-nums;}
.stApp .ult-none,.stApp .ult-foot{margin:10px 0 0!important;font-size:var(--p-t-xs)!important;color:var(--p-ink3)!important;}
</style>"""
