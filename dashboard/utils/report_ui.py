# utils/report_ui.py
# Unstructured Alpha — presentation for the exposure report
#
# The pages stay thin: everything a user reads is built here as escaped HTML or
# plain text by pure functions, so the wording is testable without a browser.
# Numbers come only from utils/exposure.py; nothing here computes a statistic.

from __future__ import annotations

import csv
import io
import math
import re
from datetime import datetime
from html import escape
from typing import Iterable, List, Optional, Tuple

from urllib.parse import quote

import streamlit as st

from utils import exposure as ex

SAMPLE_KEYS = {
    "balanced": "Balanced ETF portfolio",
    "income": "Retirement income",
    "growth": "Concentrated growth stocks",
}
FREE_MAX_HOLDINGS = 15
PRO_MAX_HOLDINGS = ex.MAX_HOLDINGS
FACTOR_BY_KEY = {f.key: f for f in ex.FACTORS}
FACTOR_COLORS = {"rates": "#3b7ddd", "inflation": "#e0664a", "dollar": "#1a9a70",
                 "oil": "#d99018", "credit": "#7c5ce0", "growth": "#1497b0"}

GENERIC_ERROR = ("Something went wrong while measuring this portfolio. Nothing has been "
                 "estimated in its place; please try again.")

REPORT_CSS = """<style>
.uar{--uar-surface:#151922;--uar-subtle:#1b202b;--uar-ink:#e8eaef;--uar-ink-2:#bcc2ce;
  --uar-ink-3:#8f97a7;--uar-line:#2b3240;--uar-accent:#8db4e8;--uar-pos:#79aee9;--uar-neg:#e3a35c;
  font-family:Inter,system-ui,-apple-system,sans-serif;font-variant-numeric:tabular-nums;color:var(--uar-ink);}
html[data-ua-theme="light"] .uar{--uar-surface:#ffffff;--uar-subtle:#f2f3f5;--uar-ink:#14171f;
  --uar-ink-2:#3a4152;--uar-ink-3:#596070;--uar-line:#e2e4e9;--uar-accent:#1f4e8c;--uar-pos:#2563a8;--uar-neg:#b45309;}
.uar-strip{height:5px;background:linear-gradient(90deg,#3b7ddd,#7c5ce0,#e0664a,#d99018,#1a9a70,#1497b0);}
.uar-dot{display:inline-block;width:12px;height:12px;border-radius:4px;margin-right:9px;vertical-align:0;}
.uar-card{background:var(--uar-surface);border:1px solid var(--uar-line);border-radius:12px;overflow:hidden;margin:6px 0 18px;}
.uar-head{padding:16px 20px;border-bottom:1px solid var(--uar-line);display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 20px;}
.uar-title{font-size:1.02rem;font-weight:650;color:var(--uar-ink);}
.uar-sub{font-size:.84rem;color:var(--uar-ink-3);line-height:1.5;}
.uar-lead{font-size:1.02rem;color:var(--uar-ink-2);line-height:1.65;margin:2px 0 10px;}
.uar-body{padding:14px 20px;}
.uar-row{display:grid;grid-template-columns:minmax(150px,1.1fr) minmax(140px,1.2fr) 150px minmax(160px,1fr);
  gap:14px;align-items:center;padding:14px 20px;border-bottom:1px solid var(--uar-line);}
.uar-row:last-child{border-bottom:0;}
.uar-label{font-weight:600;font-size:.95rem;color:var(--uar-ink);}
.uar-shock{font-size:.78rem;color:var(--uar-ink-3);line-height:1.4;}
.uar-val{font-weight:650;font-size:.95rem;color:var(--uar-ink);}
.uar-range{font-size:.78rem;color:var(--uar-ink-3);}
.uar-bar{position:relative;height:22px;}
.uar-axis{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--uar-line);}
.uar-fill{position:absolute;top:7px;height:8px;border-radius:2px;}
.uar-whisker{position:absolute;top:10px;height:2px;background:var(--uar-ink-3);opacity:.6;}
.uar-chip{display:inline-block;align-self:flex-start;font-size:.72rem;font-weight:600;padding:2px 8px;border-radius:999px;
  border:1px solid var(--uar-line);color:var(--uar-ink-2);white-space:nowrap;}
.uar-chip-clear{background:rgba(26,154,112,.16);border-color:rgba(26,154,112,.55);color:#4fcf9f;}
html[data-ua-theme="light"] .uar-chip-clear{background:#dcf3ea;border-color:#9fd8c2;color:#0b6a4e;}
.uar-chip-tentative{background:rgba(217,144,24,.16);border-color:rgba(217,144,24,.5);color:#f0bb62;}
html[data-ua-theme="light"] .uar-chip-tentative{background:#fdefd6;border-color:#f1cf95;color:#8a4f00;}
.uar-driver{font-size:.8rem;color:var(--uar-ink-3);margin-top:4px;}
.uar-foot{padding:12px 20px;background:var(--uar-subtle);font-size:.8rem;color:var(--uar-ink-3);line-height:1.55;}
.uar-legend{display:flex;flex-wrap:wrap;gap:14px;font-size:.78rem;color:var(--uar-ink-3);align-items:center;}
.uar-sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px;}
.uar-scroll{overflow-x:auto;}\n@media (min-width:761px){.uar-tier{min-height:430px;}}
.uar-table{width:100%;border-collapse:collapse;font-size:.88rem;}
.uar-table th{text-align:left;font-weight:600;color:var(--uar-ink-3);font-size:.74rem;padding:8px 12px;border-bottom:1px solid var(--uar-line);white-space:nowrap;}
.uar-table td{padding:9px 12px;border-bottom:1px solid var(--uar-line);color:var(--uar-ink-2);}
.uar-table tr:last-child td{border-bottom:0;}
.uar-note{border-left:3px solid var(--uar-line);padding:8px 14px;color:var(--uar-ink-2);font-size:.88rem;margin:10px 0;line-height:1.55;}
.uar-note-warn{border-left-color:var(--uar-neg);}
.uar-error{border:1px solid var(--uar-neg);border-radius:12px;padding:16px 20px;margin:8px 0 16px;color:var(--uar-ink-2);background:var(--uar-surface);}
.uar-error b{color:var(--uar-ink);}
.uar-kicker{font-size:.8rem;font-weight:600;color:var(--uar-accent);margin-bottom:4px;}
.uar-map{width:100%;max-width:520px;height:auto;display:block;margin:4px auto 10px;}
.uar-map-label{fill:var(--uar-ink);font-size:.88rem;font-weight:600;}
.uar-map-value{fill:var(--uar-ink-3);font-size:.8rem;}
.uar-map-core{fill:var(--uar-ink);font-size:1.02rem;font-weight:700;}
@media print{
  .ua-topnav,.st-key-ua_account_row,[data-testid="stButton"],[data-testid="stRadio"],
  [data-testid="stExpander"],[data-testid="stCode"],.ua-scroll-top,#ua-scroll-top{display:none!important;}
  .uar{--uar-surface:#fff;--uar-subtle:#f6f7f9;--uar-ink:#14171f;--uar-ink-2:#3a4152;
       --uar-ink-3:#596070;--uar-line:#d8dbe2;}
  .uar-card{break-inside:avoid;page-break-inside:avoid;box-shadow:none;}
  .uar-map{max-width:420px;}
  a[href]:after{content:"";}
}
@media (max-width:760px){
  .uar-row{grid-template-columns:1fr auto;gap:6px 12px;}
  .uar-row .uar-bar{grid-column:1/-1;order:3;}
  .uar-row .uar-rowdriver{grid-column:1/-1;order:4;}
}
</style>"""


# ── formatting ──────────────────────────────────────────────────────────────

def fmt_pct(x: Optional[float]) -> str:
    """Signed percent with a true minus sign; two decimals below 1%."""
    if x is None or not math.isfinite(x):
        return "—"
    digits = 1 if abs(x) >= 0.95 else 2
    if round(x, digits) == 0:
        return f"{0:.{digits}f}%"
    sign = "+" if x > 0 else "−"
    return f"{sign}{abs(x):.{digits}f}%"


def fmt_date(iso: Optional[str]) -> str:
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return str(iso or "")
    return f"{d:%b} {d.day}, {d.year}"


def _join(items: List[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def evidence_chip(evidence: str) -> str:
    label = ex.EVIDENCE_LABELS.get(evidence, evidence)
    cls = {"clear": " uar-chip-clear", "tentative": " uar-chip-tentative"}.get(evidence, "")
    return f'<span class="uar-chip{cls}">{escape(label)}</span>'


def _nice_scale(values: Iterable[float]) -> float:
    peak = max((abs(v) for v in values if v is not None and math.isfinite(v)), default=0.25)
    for step in (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0):
        if peak <= step:
            return step
    return math.ceil(peak / 10.0) * 10.0


def exposure_bar(impact: float, low: float, high: float, scale: float) -> str:
    def pos(v: float) -> float:
        return 50.0 + max(-scale, min(scale, v)) / scale * 50.0
    left = min(pos(0.0), pos(impact))
    width = abs(pos(impact) - pos(0.0))
    colour = "var(--uar-pos)" if impact >= 0 else "var(--uar-neg)"
    return (f'<div class="uar-bar" aria-hidden="true"><div class="uar-axis"></div>'
            f'<div class="uar-fill" style="left:{left:.2f}%;width:{width:.2f}%;background:{colour};"></div>'
            f'<div class="uar-whisker" style="left:{pos(low):.2f}%;width:{pos(high) - pos(low):.2f}%;"></div></div>')


# ── holdings input ──────────────────────────────────────────────────────────

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
_TICKER_COLS = {"ticker", "symbol", "tickers", "symbols", "holding", "security id"}
_WEIGHT_COLS = {"weight", "weight_pct", "weight %", "weight (%)", "allocation", "allocation %",
                "percent", "percentage", "% of account", "% of portfolio", "portfolio %", "pct"}
_VALUE_COLS = {"market value", "value", "amount", "position value", "current value",
               "market_value", "marketvalue", "mkt val (market value)", "mkt val"}
_NOT_HOLDINGS = {"CASH", "TOTAL", "ACCOUNT", "PENDING", "--"}


def _number(value: object) -> Optional[float]:
    s = str(value or "").strip().replace("$", "").replace(",", "").rstrip("%").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        x = float(s)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def parse_holdings_text(text: str) -> Tuple[List[dict], List[str]]:
    """'VTI 40' / 'VTI, 40%' / 'VTI' per line. Returns (rows, rejected lines)."""
    rows, rejected = [], []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p for p in re.split(r"[,\t ]+", line) if p]
        ticker = parts[0].upper().lstrip("$")
        weight = _number(parts[1]) if len(parts) > 1 else None
        if not _TICKER_RE.match(ticker) or (len(parts) > 1 and weight is None):
            rejected.append(line)
            continue
        rows.append({"ticker": ticker, "weight_pct": weight})
    return rows, rejected


def parse_holdings_csv(data: bytes) -> Tuple[List[dict], List[str]]:
    """A CSV with a ticker/symbol column and an optional weight or value column.

    Brokerage exports often put account details above the real header, so the
    header is the first row (within the first 15) that names a ticker column.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    table = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not table:
        return [], ["The file is empty."]

    header_at = next((i for i, r in enumerate(table[:15])
                      if any(c.strip().lower() in _TICKER_COLS for c in r)), None)
    if header_at is None:
        return [], ["No ticker column found. Add a header row with a column named Ticker or Symbol."]
    header = [c.strip().lower() for c in table[header_at]]

    def find(names: set) -> Optional[int]:
        return next((i for i, h in enumerate(header) if h in names), None)

    t_col = find(_TICKER_COLS)
    w_col = find(_WEIGHT_COLS)
    v_col = find(_VALUE_COLS) if w_col is None else None
    amount_col = w_col if w_col is not None else v_col

    rows, rejected = [], []
    for line_no, r in enumerate(table[header_at + 1:], start=header_at + 2):
        raw = r[t_col].strip().upper().lstrip("$") if t_col < len(r) else ""
        if not raw or any(raw.startswith(x) for x in _NOT_HOLDINGS):
            continue
        if not _TICKER_RE.match(raw):
            rejected.append(f"Row {line_no}: {raw[:24]}")
            continue
        amount = _number(r[amount_col]) if amount_col is not None and amount_col < len(r) else None
        if amount is not None and amount <= 0:
            rejected.append(f"Row {line_no}: {raw} has no positive weight or value")
            continue
        rows.append({"ticker": raw, "weight_pct": amount})
    return rows, rejected


HOLDINGS_PARAM = "h"
APP_BASE = "https://app.unstructuredalpha.com"


def holdings_param(rows: Iterable[dict]) -> str:
    """'VTI:40,BND:30' — a portfolio small enough to live in a link.

    Outreach and sharing both need one URL that opens a finished report, with
    no account and no upload. Weights are rounded to one decimal: the extra
    precision changes nothing a reader sees and makes links unreadable.
    """
    parts = []
    for r in rows or []:
        weight = r.get("weight_pct")
        parts.append(f"{r['ticker']}:{round(float(weight), 1):g}" if weight else str(r["ticker"]))
    return ",".join(parts)


def parse_holdings_param(value: str) -> List[dict]:
    """The inverse. Anything malformed is dropped, never guessed at."""
    rows: List[dict] = []
    for chunk in str(value or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        ticker, _, weight = chunk.partition(":")
        ticker = ticker.strip().upper().lstrip("$")
        if not _TICKER_RE.match(ticker):
            continue
        rows.append({"ticker": ticker, "weight_pct": _number(weight) if weight else None})
    return rows


def share_url(rows: Iterable[dict], app_base: str = APP_BASE) -> str:
    return f"{app_base}/?{HOLDINGS_PARAM}={quote(holdings_param(rows))}"


def holdings_to_text(rows: Iterable[dict]) -> str:
    out = []
    for r in rows or []:
        w = r.get("weight_pct")
        out.append(f"{r['ticker']} {round(float(w), 2):g}" if w else str(r["ticker"]))
    return "\n".join(out)


def prepare_holdings(rows: Iterable[dict], max_holdings: int):
    """(cache key, cleaning notes). The key is the normalized, sorted portfolio."""
    positions, notes = ex.normalize_positions(rows, max_holdings)
    key = tuple(sorted((p["ticker"], round(p["weight_pct"], 4)) for p in positions))
    return key, notes


# ── data (cached; errors are never cached) ──────────────────────────────────

class _NotCacheable(Exception):
    def __init__(self, payload: dict):
        super().__init__(payload.get("message", ""))
        self.payload = payload


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=200)
def _cached_ok_report(key: tuple, max_holdings: int) -> dict:
    report = ex.build_live_report([{"ticker": t, "weight_pct": w} for t, w in key],
                                  max_holdings=max_holdings)
    if report.get("status") != "ok":
        # Raised, not returned: Streamlit does not cache exceptions, so a
        # provider outage is retried on the next request instead of being
        # served from cache for six hours.
        raise _NotCacheable(report)
    return report


def get_report(key: tuple, max_holdings: int) -> dict:
    """Shared cache, then this process's cache, then the engine.

    The database lookup comes first because it survives deploys and is shared
    across instances: without it every restart makes the next visitor wait ~25
    seconds for a measurement someone else already paid for.
    """
    if not key:
        return {"status": "error", "message": "Add at least one holding with a ticker symbol."}

    from utils import report_cache

    stored = report_cache.get(key, max_holdings)
    if stored is not None:
        return stored

    try:
        report = _cached_ok_report(key, max_holdings)
    except _NotCacheable as exc:
        return exc.payload
    except Exception:
        return {"status": "error", "message": GENERIC_ERROR, "retryable": True}

    report_cache.put(key, max_holdings, report)
    return report


# ── report sections ─────────────────────────────────────────────────────────

def ordered_keys(report: dict) -> List[str]:
    readings = report["portfolio"]["readings"]
    top = [k for k in report.get("top_exposures", []) if k in readings]
    return top + [f.key for f in ex.FACTORS if f.key in readings and f.key not in top]


def summary_text(report: dict) -> str:
    p = report["portfolio"]
    readings = p["readings"]
    clear = [ex.lower_label(readings[k]["label"]) for k in report["top_exposures"]
             if readings[k]["evidence"] == "clear"]
    tentative = [ex.lower_label(readings[k]["label"]) for k in report["top_exposures"]
                 if readings[k]["evidence"] == "tentative"]
    none = [ex.lower_label(r["label"]) for r in readings.values()
            if r["evidence"] in ("indistinct", "not_enough_data")]
    span = f"Over the {p['n_obs']} weeks to {fmt_date(p['end'])}"
    parts = []
    if clear:
        parts.append(f"clearly sensitive to {_join(clear)}")
    if tentative:
        parts.append(f"tentatively sensitive to {_join(tentative)}")
    if parts:
        text = f"{span}, this portfolio has been {' and '.join(parts)}."
    else:
        text = (f"{span}, this portfolio shows no clear sensitivity to any of the economic forces "
                f"measured, beyond its movement with the stock market.")
    if none:
        text += f" No measurable link to {_join(none)}."
    beta = p.get("market_beta")
    if beta is not None and math.isfinite(beta):
        text += (f" It has typically moved {beta:.2f} times as much as the U.S. stock market, "
                 f"which is accounted for separately.")
    return text


def _driver_text(report: dict, key: str) -> str:
    reading = report["portfolio"]["readings"][key]
    rows = report["contributions"].get(key, [])
    if reading["evidence"] not in ("clear", "tentative") or not rows:
        return "No measurable link"
    top = rows[0]
    if top.get("share") is not None and top["share"] >= 0.5:
        return f"Mostly {top['ticker']}"
    return "Largest: " + ", ".join(r["ticker"] for r in rows[:2])


_MAP_NODES = {"rates": (260, 92), "dollar": (446, 152), "inflation": (414, 356),
              "oil": (106, 356), "credit": (74, 152)}


def exposure_map_html(report: dict) -> str:
    """The portfolio at the centre, each force around it.

    Line weight follows the measured size; a force with no clear link is a faint
    dashed line. It carries no information the table below does not — it is the
    shape of the answer, for a reader who takes in a picture faster than a table.
    """
    readings = report.get("portfolio", {}).get("readings") or {}
    drawable = [k for k in _MAP_NODES if k in readings]
    if len(drawable) < 3:
        return ""
    cx, cy = 260, 218
    peak = max((abs(readings[k]["impact"]) for k in drawable), default=1.0) or 1.0

    lines, nodes = [], []
    for key in drawable:
        x, y = _MAP_NODES[key]
        r = readings[key]
        clear = r["evidence"] in ("clear", "tentative")
        colour = FACTOR_COLORS.get(key, "#3b7ddd")
        width = 2 + 8 * min(1.0, abs(r["impact"]) / peak) if clear else 1.5
        lines.append(
            f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" stroke="{colour if clear else "var(--uar-ink-3)"}" '
            f'stroke-width="{width:.1f}" stroke-linecap="round"'
            + ('' if clear else ' stroke-dasharray="5 6" opacity="0.5"') + '></line>')
        above = y < cy - 80
        label_y = y - 56 if above else y + 48
        value_y = y - 38 if above else y + 66
        value = fmt_pct(r["impact"]) if clear else "no clear link"
        nodes.append(
            f'<g opacity="{1 if clear else 0.65}">'
            f'<circle cx="{x}" cy="{y}" r="26" fill="{colour}"></circle>'
            f'<text x="{x}" y="{label_y}" text-anchor="middle" class="uar-map-label">'
            f'{escape(r["label"])}</text>'
            f'<text x="{x}" y="{value_y}" text-anchor="middle" class="uar-map-value">{value}</text>'
            f'</g>')

    holdings = len(report.get("positions") or [])
    return (
        f'<div class="uar"><svg class="uar-map" viewBox="0 0 520 430" role="img" '
        f'aria-label="Diagram of this portfolio and the economic forces it is exposed to. '
        f'The table below gives the same figures.">'
        f'<circle cx="{cx}" cy="{cy}" r="150" fill="none" stroke="var(--uar-line)"></circle>'
        + "".join(lines)
        + f'<circle cx="{cx}" cy="{cy}" r="64" fill="var(--uar-subtle)" stroke="var(--uar-line)"></circle>'
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" class="uar-map-core">Portfolio</text>'
        f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" class="uar-map-value">'
        f'{holdings} holding{"" if holdings == 1 else "s"}</text>'
        + "".join(nodes)
        + '</svg></div>')


def exposure_table_html(report: dict) -> str:
    p = report["portfolio"]
    readings = p["readings"]
    keys = ordered_keys(report)
    scale = _nice_scale([v for k in keys for v in (readings[k]["low"], readings[k]["high"])])
    rows = []
    for key in keys:
        r = readings[key]
        rows.append(
            f'<div class="uar-row">'
            f'<div><div class="uar-label"><span class="uar-dot" style="background:{FACTOR_COLORS[key]}"></span>{escape(r["label"])}</div>'
            f'<div class="uar-shock">In weeks when {escape(r["shock_phrase"])}</div></div>'
            f'{exposure_bar(r["impact"], r["low"], r["high"], scale)}'
            f'<div><div class="uar-val">{fmt_pct(r["impact"])}</div>'
            f'<div class="uar-range">range {fmt_pct(r["low"])} to {fmt_pct(r["high"])}</div></div>'
            f'<div class="uar-rowdriver">{evidence_chip(r["evidence"])}'
            f'<div class="uar-driver">{escape(_driver_text(report, key))}</div></div>'
            f'</div>'
        )
    return (
        '<div class="uar"><div class="uar-card"><div class="uar-strip"></div>'
        '<div class="uar-head"><div class="uar-title">Exposure to economic forces</div>'
        '<div class="uar-legend">'
        '<span><span class="uar-sw" style="background:var(--uar-pos)"></span>Moves up with the factor</span>'
        '<span><span class="uar-sw" style="background:var(--uar-neg)"></span>Moves down with the factor</span>'
        f'<span>Thin line: 90% range · bar scale ±{scale:g}%</span></div></div>'
        + "".join(rows) +
        f'<div class="uar-foot">Each figure is the portfolio&#39;s typical same-week move when that force '
        f'moved by the stated amount, after accounting for the stock market. Measured over '
        f'{p["n_obs"]} weeks, {escape(fmt_date(p["start"]))} to {escape(fmt_date(p["end"]))}. '
        f'It describes the past; it is not a forecast.</div>'
        '</div></div>'
    )


def factor_detail_html(report: dict, key: str) -> str:
    readings = report["portfolio"]["readings"]
    if key not in readings:
        return ""
    r = readings[key]
    parts = [
        f'<div class="uar"><div class="uar-card" style="border-top:4px solid {FACTOR_COLORS.get(key, "#3b7ddd")}"><div class="uar-head"><div>'
        f'<div class="uar-title"><span class="uar-dot" style="background:{FACTOR_COLORS.get(key, "#3b7ddd")}"></span>{escape(r["label"])}</div>'
        f'<div class="uar-sub">{escape(r["why"])}</div></div>{evidence_chip(r["evidence"])}</div>'
        f'<div class="uar-body"><p class="uar-lead">{escape(r["sentence"])}</p>'
        f'<div class="uar-sub">{escape(ex.EVIDENCE_EXPLAINED[r["evidence"]])} '
        f'Based on {r["n_obs"]} weeks of data.</div>'
    ]
    if r.get("hard_to_separate_from"):
        parts.append(
            f'<div class="uar-note uar-note-warn">Over this period {escape(ex.lower_label(r["label"]))} moved '
            f'closely with {escape(ex.lower_label(r["hard_to_separate_from"]))}, so the two are hard to separate. '
            f'Read them together.</div>')

    rows = report["contributions"].get(key, [])
    if rows:
        body = "".join(
            f'<tr><td><b>{escape(c["ticker"])}</b></td><td>{c["weight_pct"]:.1f}%</td>'
            f'<td>{fmt_pct(c["impact"])} {evidence_chip(c["evidence"])}</td>'
            f'<td>{fmt_pct(c["contribution"])}</td>'
            f'<td>{"—" if c["share"] is None else f"{100 * c["share"]:.0f}%"}</td></tr>'
            for c in rows
        )
        parts.append(
            '<div class="uar-scroll" style="margin-top:12px"><table class="uar-table">'
            '<thead><tr><th>Holding</th><th>Weight</th><th>Its own sensitivity</th>'
            '<th>Contribution</th><th>Share of total</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>'
            '<div class="uar-sub" style="margin-top:8px">A holding&#39;s contribution is its weight times '
            'its own sensitivity, and contributions add up to the portfolio figure. Holdings can offset '
            'each other, so a share can be above 100% or negative.</div>'
        )
    parts.append('</div></div></div>')
    return "".join(parts)


def shifts_html(report: dict) -> str:
    shifts = report.get("shifts") or []
    if not shifts:
        return ('<div class="uar"><div class="uar-note">A before-and-after comparison needs a full '
                'three years of history, so it isn&#39;t available for this portfolio.</div></div>')
    flagged = [s for s in shifts if s["significant"]]
    if not flagged:
        body = ('<div class="uar-note">No measurable change in any exposure between the past year and '
                'the two years before it.</div>')
    else:
        body = "".join(f'<div class="uar-note uar-note-warn">{escape(s["sentence"])}</div>' for s in flagged)
    return (f'<div class="uar">{body}<div class="uar-sub">The past 52 weeks are compared with the '
            f'104 weeks before them. A change is only shown when it is larger than the combined '
            f'uncertainty of both periods.</div></div>')


def recent_moves_html(report: dict) -> str:
    rm = report.get("recent_moves") or {}
    if not rm.get("available"):
        return ""
    counted = [m for m in rm["moves"] if m["counts"]]
    head = (f'<p class="uar-lead">In the {rm["weeks"]} weeks to {escape(fmt_date(rm["end"]))}, the '
            f'portfolio returned {fmt_pct(rm["portfolio_return"])}.</p>')
    if not counted:
        return (f'<div class="uar">{head}<div class="uar-note">None of this portfolio&#39;s exposures is '
                f'strong enough to connect its recent moves to these economic forces.</div></div>')
    rows = "".join(
        f'<tr><td><b>{escape(m["label"])}</b></td><td>{escape(m["move_text"])}</td>'
        f'<td>{fmt_pct(m["attributed"])}</td>'
        f'<td>{fmt_pct(m["attributed"] - ex.Z90 * m["attributed_se"])} to '
        f'{fmt_pct(m["attributed"] + ex.Z90 * m["attributed_se"])}</td></tr>'
        for m in counted
    )
    return (
        f'<div class="uar">{head}<div class="uar-scroll"><table class="uar-table"><thead><tr>'
        f'<th>Economic force</th><th>How it moved</th><th>Portfolio move that lines up with it</th>'
        f'<th>90% range</th></tr></thead><tbody>{rows}</tbody></table></div>'
        f'<div class="uar-sub" style="margin-top:8px">These apply the measured sensitivities to what '
        f'actually happened. They explain the recent past; they are not a forecast. Only exposures '
        f'labelled Clear or Tentative are shown.</div></div>'
    )


def growth_html(report: dict) -> str:
    g = report.get("growth") or {}
    if not g.get("available"):
        reason = g.get("reason") or "monthly data was unavailable"
        return (f'<div class="uar"><div class="uar-note">Economic growth couldn&#39;t be measured: '
                f'{escape(reason)}.</div></div>')
    r = g["readings"].get("growth")
    if not r:
        return ""
    return (f'<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
            f'<div class="uar-title">Economic growth · limited evidence</div>'
            f'<div class="uar-sub">{escape(r["why"])}</div></div>{evidence_chip(r["evidence"])}</div>'
            f'<div class="uar-body"><p class="uar-lead">{escape(r["sentence"])}</p>'
            f'<div class="uar-sub">{escape(g["note"])}</div></div></div></div>')


def notes_html(report: dict, cleaning_notes: Iterable[str] = ()) -> str:
    items = list(cleaning_notes) + list(report.get("notes") or [])
    for x in report.get("excluded") or []:
        items.append(f"{x['ticker']} ({x['weight_pct']:.0f}%): {x['reason']}.")
    if not items:
        return ""
    body = "".join(f"<li>{escape(i)}</li>" for i in dict.fromkeys(items))
    return (f'<div class="uar"><div class="uar-note"><b>About the data</b>'
            f'<ul style="margin:6px 0 0 18px;padding:0">{body}</ul></div></div>')


def error_html(report: dict) -> str:
    excluded = report.get("excluded") or []
    detail = ""
    if excluded:
        items = "".join(f"<li>{escape(x['ticker'])}: {escape(x['reason'])}</li>" for x in excluded)
        detail = f'<ul style="margin:8px 0 0 18px;padding:0">{items}</ul>'
    return (f'<div class="uar"><div class="uar-error"><b>We couldn&#39;t measure this portfolio.</b>'
            f'<div style="margin-top:6px">{escape(report.get("message") or GENERIC_ERROR)}</div>'
            f'{detail}</div></div>')


def portfolio_header_html(name: str, report: dict) -> str:
    positions = report.get("positions") or []
    listing = " · ".join(f"{p['weight_pct']:.0f}% {p['ticker']}"
                         for p in sorted(positions, key=lambda p: -p["weight_pct"])[:8])
    more = f" · +{len(positions) - 8} more" if len(positions) > 8 else ""
    as_of = report.get("as_of")
    return (f'<div class="uar">'
            f'<div class="uar-title" style="font-size:1.35rem">{escape(name)}</div>'
            f'<div class="uar-sub">{escape(listing + more)}'
            + (f' · data through {escape(fmt_date(as_of))}' if as_of else "")
            + '</div></div>')


FOOTER_LINKS = (("Methodology", "/methodology"), ("Research record", "/research"),
                ("Pricing", "/pricing"), ("Privacy &amp; Terms", "/privacy-terms"))


def render_report_footer() -> None:
    """Footer for the redesigned pages. The shared footer still describes the
    old signal product and its data providers, which these pages do not use."""
    links = " · ".join(f'<a href="{href}" target="_self">{label}</a>' for label, href in FOOTER_LINKS)
    st.markdown(
        REPORT_CSS
        + '<div class="uar" style="margin-top:40px;padding-top:16px;border-top:1px solid var(--uar-line)">'
        f'<div class="uar-sub">{links}</div>'
        '<div class="uar-sub" style="margin-top:8px">Unstructured Alpha is an educational and informational '
        'tool. Nothing here is personalized financial, investment, tax or legal advice, or a recommendation '
        'to buy, sell or hold any security. Exposure figures describe how portfolios have moved in the past; '
        'relationships change and past behaviour does not guarantee future results. Prices from Yahoo '
        'Finance; economic series from the Federal Reserve Bank of St. Louis (FRED).</div></div>',
        unsafe_allow_html=True,
    )


HOW_TO_READ = """
**What each number means.** Take "Interest rates −0.66%". In weeks when the 10-year Treasury yield rose 0.25 percentage points, this portfolio typically moved 0.66% lower in the same week. The stock market's own movement is removed first.

**The range.** The 90% range shows how precisely the relationship was measured. A wide range means it is uncertain. A range that crosses zero means the result could be noise.

**The labels.**
- *Clear*: strong enough to hold up even after allowing for testing five factors at once.
- *Tentative*: suggestive, but could be noise.
- *Not distinguishable from zero*: no measurable relationship.
- *Not enough data*: too little history to say.

**Why the market is taken out.** Rates, oil and the dollar often move on the same days as stocks. Without removing that, nearly every stock portfolio would look sensitive to everything.

**What this is not.** It describes the past three years. Relationships change. It is not a forecast, and it is not advice.
"""
