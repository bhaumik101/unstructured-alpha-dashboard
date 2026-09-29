# utils/dashboard_ui.py
# Unstructured Alpha — the main page, as a dashboard
#
# What a first visit sees before choosing a portfolio: a row of headline
# numbers, the stocks most exposed to each force, and what the forces
# themselves did. Every panel reads what is already stored -- the stock
# library and the report cache -- so opening the page never starts a
# measurement, and a panel with nothing stored says so instead of showing a
# placeholder that looks like data.

from __future__ import annotations

from html import escape
from typing import Iterable, List, Optional, Tuple

from utils import report_ui as ui

# (value, label, detail, href or "")
Tile = Tuple[str, str, str, str]


def kpi_tiles_html(tiles: Iterable[Tile]) -> str:
    """Headline numbers. A number with its label and a line of context; no chart."""
    cells = []
    for value, label, detail, href in tiles:
        inner = (f'<div class="udb-v">{escape(value)}</div>'
                 f'<div class="udb-l">{escape(label)}</div>'
                 + (f'<div class="udb-d">{escape(detail)}</div>' if detail else ""))
        cells.append(f'<a class="udb-tile" href="{escape(href)}" target="_self">{inner}</a>' if href
                     else f'<div class="udb-tile">{inner}</div>')
    return f'<div class="udb-tiles">{"".join(cells)}</div>'


def _rank_rows(rows: List[dict], scale: float) -> str:
    return "".join(
        f'<a class="udb-row" href="/stock?t={escape(r["ticker"])}" target="_self">'
        f'<span class="udb-who"><b>{escape(r["ticker"])}</b>'
        + (f'<span>{escape(r["name"])}</span>' if r.get("name") else "")
        + '</span>'
        f'<span class="udb-bar">{ui.exposure_bar(r["impact"], r["low"], r["high"], scale)}</span>'
        f'<span class="udb-num"><b>{ui.fmt_pct(r["impact"])}</b>'
        f'<span>{ui.fmt_pct(r["low"])} to {ui.fmt_pct(r["high"])}</span></span>'
        f'<span class="udb-ev">{ui.evidence_chip(r["evidence"])}</span></a>'
        for r in rows)


def ranked_panel_html(factor_key: str, ranked: dict, n_on_record: int) -> str:
    """The stocks on record most exposed to one force, each way.

    Only readings that held up are ranked (stock_library.ranked filters them),
    so an empty side is an honest "none yet", not a gap in the data.
    """
    f = ui.FACTOR_BY_KEY[factor_key]
    up, down = ranked.get("up") or [], ranked.get("down") or []
    if not up and not down:
        body = (f'<p class="udb-empty">No stock on record has a reading on '
                f'{escape(f.label.lower() if not f.label.startswith("U.S.") else f.label)} that held up '
                f'yet. Every stock viewed on its own page is added, so this fills in as the library '
                f'grows.</p>')
    else:
        scale = ui._nice_scale([v for r in up + down for v in (r["low"], r["high"])])
        body = ""
        if up:
            body += f'<div class="udb-side">Moved up with it</div>{_rank_rows(up, scale)}'
        if down:
            body += f'<div class="udb-side">Moved down with it</div>{_rank_rows(down, scale)}'
    return (
        '<div class="uar"><div class="uar-card udb-card"><div class="uar-body">'
        f'{body}'
        f'<div class="uar-foot">Typical move in a week when {escape(f.shock_phrase)}, after '
        f'accounting for the stock market; the thin line is the 90% range. Among the {n_on_record} '
        f'stock{"" if n_on_record == 1 else "s"} on record, only readings that held up (Clear or '
        f'Tentative) are ranked. It describes the past; it is not a forecast.</div>'
        '</div></div></div>')


def forces_empty_html() -> str:
    return ('<div class="uar"><p class="udb-empty">Shown once any report has been measured in the '
            'last six hours. Open a sample below and it appears here for everyone.</p></div>')


def latest_as_of(stocks: List[dict], report: Optional[dict]) -> str:
    dates = [s["as_of"] for s in stocks if s.get("as_of")]
    if report and report.get("as_of"):
        dates.append(str(report["as_of"])[:10])
    return max(dates) if dates else ""


DASHBOARD_CSS = """<style>
.udb-tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:4px 0 18px;}
.udb-tile{display:block;background:var(--p-surface);border:1px solid var(--p-line);border-radius:var(--p-r,12px);
  padding:14px 16px;color:var(--p-ink)!important;text-decoration:none!important;}
a.udb-tile:hover{border-color:var(--p-accent);background:var(--p-sky);}
.udb-v{font-size:var(--p-t-xl,2.1rem);font-weight:750;letter-spacing:-.02em;line-height:1.1;
  color:var(--p-ink);font-variant-numeric:tabular-nums;}
.udb-l{margin-top:4px;font-size:var(--p-t-sm,.82rem);font-weight:650;color:var(--p-ink2);}
.udb-d{margin-top:2px;font-size:var(--p-t-xs,.75rem);color:var(--p-ink3);}
.udb-card .uar-body{padding-top:10px;}
.udb-side{margin:10px 0 2px;font-size:var(--p-t-xs,.75rem);font-weight:700;letter-spacing:.05em;
  text-transform:uppercase;color:var(--p-ink3);}
.udb-row{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1.3fr) auto auto;gap:12px;align-items:center;
  padding:9px 6px;border-bottom:1px solid var(--p-line);color:var(--p-ink)!important;text-decoration:none!important;
  border-radius:8px;}
.udb-row:hover{background:var(--p-sky);}
.udb-who{display:flex;flex-direction:column;min-width:0;}
.udb-who span{font-size:var(--p-t-xs,.75rem);color:var(--p-ink3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.udb-num{display:flex;flex-direction:column;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
.udb-num span{font-size:var(--p-t-xs,.75rem);color:var(--p-ink3);}
.udb-empty{color:var(--p-ink2);font-size:var(--p-t-sm,.82rem);line-height:1.55;margin:6px 0;}
@media (max-width:900px){.udb-tiles{grid-template-columns:repeat(2,1fr);}}
@media (max-width:560px){.udb-row{grid-template-columns:1fr auto;}.udb-bar,.udb-ev{display:none;}}
</style>"""
