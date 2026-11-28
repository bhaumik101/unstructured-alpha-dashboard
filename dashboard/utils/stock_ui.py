# utils/stock_ui.py
# Unstructured Alpha — the pieces of the single-stock page
#
# A stock is measured by the same engine as a portfolio (one holding at 100%),
# so the page reuses the report's own map, table and charts. What differs is
# the wording -- the engine's sentences say "this portfolio" -- and the one
# thing only a stock has here: its stored history from the stock library.

from __future__ import annotations

import re
from html import escape
from typing import Dict, List

from utils import report_ui as ui

# Evidence -> the report's own chip classes, so a stored week reads like a live one.
_CHIP = {"clear": "clear", "tentative": "tentative"}

_WORDING = (
    (re.compile(r"\bthis portfolio's\b"), "this stock's"),
    (re.compile(r"\bThis portfolio's\b"), "This stock's"),
    (re.compile(r"\bthis portfolio\b"), "this stock"),
    (re.compile(r"\bThis portfolio\b"), "This stock"),
    (re.compile(r"\bthe portfolio\b"), "the stock"),
    (re.compile(r"\bThe portfolio\b"), "The stock"),
)


def as_stock(html: str, ticker: str = "") -> str:
    """The report's HTML, worded for one company instead of a portfolio."""
    for pattern, repl in _WORDING:
        html = pattern.sub(repl, html)
    if ticker:
        # The map's centre node: "Portfolio / 1 holding" becomes the ticker.
        html = html.replace('class="uar-map-core">Portfolio<',
                            f'class="uar-map-core">{escape(ticker)}<')
        html = re.sub(r'>1 holding<', '>one company<', html)
    return html


def stock_header_html(ticker: str, name: str, report: dict) -> str:
    as_of = report.get("as_of")
    title = escape(ticker) + (f' <span class="uar-sub" style="font-size:var(--p-t-md);font-weight:500">'
                              f'{escape(name)}</span>' if name and name != ticker else "")
    return (f'<div class="uar"><div class="uar-title" style="font-size:var(--p-t-lg)">{title}</div>'
            f'<div class="uar-sub">Measured as a one-company portfolio'
            + (f' · data through {escape(ui.fmt_date(as_of))}' if as_of else "")
            + '</div></div>')


def _cell(e: dict | None) -> str:
    if not e:
        # Not measured that week. Shown as a gap, never as a zero.
        return '<td class="usl-gap" title="Not measured this week">—</td>'
    cls = _CHIP.get(e.get("evidence"), "zero")
    return (f'<td><span class="usl-v usl-{cls}">{ui.fmt_pct(e["impact"])}</span>'
            f'<span class="usl-r">{ui.fmt_pct(e["low"])} to {ui.fmt_pct(e["high"])}</span></td>')


def history_html(history: List[dict], order: List[str]) -> str:
    """Every stored week for this stock, newest first, one column per force.

    Only drawn once there are two weeks to compare; a single week is the report
    above, and a one-row table would suggest a history that does not exist yet.
    """
    if len(history) < 2:
        return ""
    labels: Dict[str, str] = {k: ui.FACTOR_BY_KEY[k].label for k in order if k in ui.FACTOR_BY_KEY}
    head = "".join(f'<th><span class="uar-dot" style="background:{ui.FACTOR_COLORS.get(k, "#3b7ddd")}">'
                   f'</span>{escape(labels[k])}</th>' for k in labels)
    rows = "".join(
        f'<tr><td class="usl-week">{escape(ui.fmt_date(h["as_of"]))}</td>'
        + "".join(_cell(h["exposures"].get(k)) for k in labels) + "</tr>"
        for h in history)
    return (
        '<div class="uar"><div class="uar-card"><div class="uar-body">'
        '<table class="usl-table"><thead><tr><th>Data through</th>' + head + '</tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        '<div class="uar-foot">Each row is this stock measured over the three years to that week. '
        'Bold figures held up (Clear or Tentative); grey ones could not be told apart from zero. '
        'A dash means that force could not be measured that week, not that it was zero.</div>'
        '</div></div></div>')


def library_chips_html(stocks: List[dict], limit: int = 12) -> str:
    """Recently measured stocks, as links to their own pages."""
    chips = "".join(
        f'<a class="usl-chip" href="/stock?t={escape(s["ticker"])}" target="_self">'
        f'<b>{escape(s["ticker"])}</b>'
        + (f'<span>{escape(s["name"])}</span>' if s.get("name") and s["name"] != s["ticker"] else "")
        + '</a>'
        for s in stocks[:limit])
    return f'<div class="usl-chips">{chips}</div>' if chips else ""


LANDSCAPE_FORCES = ("rates", "oil", "dollar", "credit", "inflation", "value", "size", "emerging", "copper",
                    "gold", "volatility")


def landscape_html(stocks: List[dict]) -> str:
    """What the library's stocks moved with: per force, how many are Clear in
    each direction, as a diverging bar on one shared scale. Built from the
    stored readings only; empty when the library is."""
    from utils import exposure as ex

    labels = {f.key: f.label for f in ex.FACTORS + ex.EXTRA_FACTORS}
    stocks = [x for x in stocks if x.get("exposures")]
    if len(stocks) < 20:
        return ""
    rows, top = [], 1
    for k in LANDSCAPE_FORCES:
        up = down = 0
        for x in stocks:
            r = x["exposures"].get(k) or {}
            if r.get("evidence") == "clear" and r.get("impact") is not None:
                up += r["impact"] > 0
                down += r["impact"] < 0
        if up + down:
            rows.append((k, up, down))
            top = max(top, up, down)
    if not rows:
        return ""
    with_any = sum(1 for x in stocks if any((r or {}).get("evidence") == "clear" for r in x["exposures"].values()))
    bars = "".join(
        f'<div class="usl-lrow" title="{escape(labels.get(k, k))}: {up} stocks rose with it, {down} fell, Clear only">'
        f'<span class="usl-ldown"><i style="width:{100 * down / top:.1f}%"></i><b>{down or ""}</b></span>'
        f'<span class="usl-lname">{escape(labels.get(k, k))}</span>'
        f'<span class="usl-lup"><i style="width:{100 * up / top:.1f}%"></i><b>{up or ""}</b></span></div>'
        for k, up, down in sorted(rows, key=lambda r: -(r[1] + r[2])))
    return (f'<div class="usl-land"><div class="usl-lhead"><span class="usl-lk">What {len(stocks):,} stocks moved with</span>'
            f'<span class="usl-lstat"><b>{100 * with_any / len(stocks):.0f}%</b> have at least one Clear link</span></div>'
            '<div class="usl-laxis"><span>fell when it rose</span><span></span><span>rose when it rose</span></div>'
            f'{bars}<p class="usl-lnote">Stocks with a Clear reading in each direction, after accounting for the stock '
            'market, over the last three years of weekly data. Hover a row for the counts. It describes the past; it '
            'is not a forecast.</p></div>')


STOCK_CSS = """<style>
.usl-table{width:100%;border-collapse:collapse;font-size:var(--p-t-sm,.82rem);font-variant-numeric:tabular-nums;}
.usl-table th{text-align:left;font-weight:650;color:var(--p-ink3);padding:6px 8px;border-bottom:1px solid var(--p-line);white-space:nowrap;}
.usl-table td{padding:7px 8px;border-bottom:1px solid var(--p-line);vertical-align:top;color:var(--p-ink2);}
.usl-table .usl-week{font-weight:600;color:var(--p-ink);white-space:nowrap;}
.usl-v{display:block;font-weight:500;color:var(--p-ink3);}
.usl-v.usl-clear,.usl-v.usl-tentative{font-weight:750;color:var(--p-ink);}
.usl-r{display:block;font-size:var(--p-t-xs,.75rem);color:var(--p-ink3);}
.usl-gap{color:var(--p-ink3);}
.usl-chips{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 12px;}
.usl-chip{display:inline-flex;align-items:baseline;gap:6px;padding:7px 12px;min-height:36px;box-sizing:border-box;
  border:1px solid var(--p-line);border-radius:var(--p-r-btn,10px);background:var(--p-surface);
  color:var(--p-ink)!important;text-decoration:none!important;font-size:var(--p-t-sm,.82rem);}
.usl-chip span{color:var(--p-ink3);}
.usl-chip:hover{border-color:var(--p-accent);background:var(--p-sky);}
@media (max-width:700px){.usl-table{display:block;overflow-x:auto;}}

.usl-land{margin:4px 0 16px;padding:14px 16px 12px;border-radius:16px;border:1px solid rgba(148,180,210,.18);
  background:radial-gradient(100% 140% at 50% 0%,rgba(108,229,210,.07),transparent 60%),rgba(255,255,255,.025);
  -webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);box-shadow:inset 0 1px 0 rgba(255,255,255,.06);}
.usl-lhead{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:6px 12px;margin-bottom:8px;}
.usl-lk{font-size:var(--uar-t-micro,.74rem);font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--ux-teal,#6ce5d2);}
.usl-lstat{font-size:var(--uar-t-sm,.82rem);color:var(--uar-ink-2,#b7c3d4);}
.usl-lstat b{font-size:var(--uar-t-val,1.02rem);color:var(--uar-ink,#e8edf5);}
.usl-laxis,.usl-lrow{display:grid;grid-template-columns:1fr minmax(120px,170px) 1fr;gap:10px;align-items:center;}
.usl-laxis{font-size:var(--uar-t-micro,.74rem);color:var(--uar-ink-3,#8394ab);margin-bottom:4px;}
.usl-laxis span:first-child{text-align:right;}
.usl-lrow{padding:3px 0;font-size:var(--uar-t-sm,.82rem);}
.usl-lname{text-align:center;color:var(--uar-ink,#e8edf5);font-weight:600;}
.usl-ldown,.usl-lup{position:relative;display:flex;align-items:center;gap:6px;height:14px;}
.usl-ldown{flex-direction:row-reverse;}
.usl-ldown i,.usl-lup i{display:block;height:12px;min-width:2px;}
.usl-ldown i{border-radius:4px 0 0 4px;background:linear-gradient(270deg,#b97d1a,#e0a43a);}
.usl-lup i{border-radius:0 4px 4px 0;background:linear-gradient(90deg,#4a8ae6,#6cb4f0);}
.usl-ldown b,.usl-lup b{font-size:var(--uar-t-micro,.74rem);color:var(--uar-ink-2,#b7c3d4);font-variant-numeric:tabular-nums;}
.usl-lnote{margin:8px 0 0;font-size:var(--uar-t-micro,.74rem);color:var(--uar-ink-3,#8394ab);}
html[data-ua-theme="light"] .usl-land{background:#fff;border-color:rgba(15,23,42,.1);}
html[data-ua-theme="light"] .usl-ldown i{background:#b9770e;}html[data-ua-theme="light"] .usl-lup i{background:#2f6fd0;}
@media (max-width:640px){.usl-laxis,.usl-lrow{grid-template-columns:1fr 96px 1fr;gap:6px;}}
</style>"""
