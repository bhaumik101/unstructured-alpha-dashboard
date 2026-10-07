# utils/sector_pages.py
# Unstructured Alpha — economic exposure by sector
#
# The stock and force pages read the library one company or one force at a
# time; these read it one SECTOR at a time: how the energy companies on record
# moved with oil, how the banks moved with rates. Sectors are the S&P 500's
# own GICS sectors, from the checked-in index list (cron/sp500.csv).
#
# RULES
#   * Each cell is the MEDIAN typical move of the sector's stocks on record,
#     with how many of them held up each way beside it -- a median of
#     readings, many of which could not be told apart from zero, says that.
#   * A sector with too few stocks on record shows its count, not a median.
#   * Stocks outside the index (opened by a visitor) have no sector and are
#     left out, never guessed.
#   * Past, not forecast; no advice.

from __future__ import annotations

import csv
import re
from functools import lru_cache
from html import escape
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Optional

from utils import exposure as ex
from utils.exposure_pages import STANDS_UP, _date, _shell, fmt_pct, hub_grid_html

INDEX_CSV = Path(__file__).resolve().parent.parent / "cron" / "sp500.csv"
MIN_FOR_MEDIAN = 3


def slug(sector: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sector.lower()).strip("-")


@lru_cache(maxsize=1)
def sector_by_ticker() -> Dict[str, str]:
    with open(INDEX_CSV, newline="", encoding="utf-8") as fh:
        return {r["ticker"].strip().upper(): r["sector"].strip()
                for r in csv.DictReader(fh) if r.get("sector")}


def sectors() -> List[str]:
    return sorted(set(sector_by_ticker().values()))


def by_slug(s: str) -> Optional[str]:
    return next((x for x in sectors() if slug(x) == s), None)


def sector_cell(members: List[dict], key: str) -> dict:
    """Median typical move on one force among a sector's stocks, with counts."""
    readings = [m["exposures"][key] for m in members if key in (m.get("exposures") or {})]
    held = [e for e in readings if e.get("evidence") in STANDS_UP]
    return {"n": len(readings),
            "median": median(e["impact"] for e in readings) if len(readings) >= MIN_FOR_MEDIAN else None,
            "up": sum(1 for e in held if e["impact"] > 0),
            "down": sum(1 for e in held if e["impact"] < 0)}


def members_of(sector: str, stocks: Iterable[dict]) -> List[dict]:
    m = sector_by_ticker()
    return [s for s in stocks if m.get(s["ticker"]) == sector]


def peer_medians(symbol: str, stocks: Iterable[dict]) -> Optional[dict]:
    """The stock's sector and, per force, the median typical move of its
    sector PEERS on record (the stock itself left out), where at least
    MIN_FOR_MEDIAN peers were measured. None outside the index."""
    sector = sector_by_ticker().get(symbol)
    if not sector:
        return None
    peers = [s for s in members_of(sector, stocks) if s["ticker"] != symbol]
    medians = {}
    for f in tuple(ex.FACTORS) + tuple(ex.EXTRA_FACTORS):
        c = sector_cell(peers, f.key)
        if c["median"] is not None:
            medians[f.key] = c["median"]
    return {"sector": sector, "slug": slug(sector), "medians": medians, "peers": len(peers)}


def _cell_html(c: dict) -> str:
    if c["median"] is None:
        return f'<td class="v-weak">{c["n"]} measured</td>' if c["n"] else '<td class="v-weak">—</td>'
    return (f'<td data-v="{c["median"]:.4f}"><b>{fmt_pct(c["median"])}</b>'
            f'<span class="shock">{c["up"]}↑ {c["down"]}↓ held up, of {c["n"]}</span></td>')


_FOOT = ('Each figure is the median typical weekly move of the sector&#39;s stocks on record when that '
         'force moved by its standard amount, after the stock market&#39;s own move. Beneath it: how '
         'many of those stocks moved up (↑) or down (↓) with the force in a way that held up. The '
         'median includes readings that could not be told apart from zero; the counts say how many '
         'did not. Fewer than three stocks on record shows the count, not a median.')


def sectors_hub_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    stocks = list(stocks)
    rows, newest = [], ""
    for sec in sectors():
        mem = members_of(sec, stocks)
        newest = max([newest] + [str(m.get("as_of") or "")[:10] for m in mem])
        cells = "".join(_cell_html(sector_cell(mem, f.key)) for f in ex.FACTORS)
        rows.append(f'<tr><th scope="row"><a href="/sectors/{slug(sec)}">{escape(sec)}</a>'
                    f'<span class="shock">{len(mem)} stocks on record</span></th>{cells}</tr>')
    head = "".join(f'<th scope="col" title="In weeks when {escape(f.shock_phrase)}">{escape(f.label)}</th>'
                   for f in ex.FACTORS)
    title = "Which sectors move with interest rates, oil, the dollar and credit"
    desc = ("How each S&P 500 sector's stocks have moved with interest rates, inflation expectations, "
            "the dollar, oil and credit spreads: the median move, and how many held up each way.")
    body = (
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Sectors</nav>'
        '<h1>Economic exposure by sector</h1>'
        + (f'<p class="meta">Data through {_date(newest)}</p>' if newest else "")
        + f'<p class="lead">{escape(desc)}</p>'
        '<div class="card" tabindex="0" role="region" aria-label="Each sector against the five core forces">'
        f'<table><thead><tr><th scope="col">Sector</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
        f'<div class="foot">{_FOOT}</div></div>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here is a '
        'recommendation to buy, sell or hold any security.</p>'
        '<div class="actions"><a class="btn btn-primary" href="/exposure">Every stock on record</a>'
        '<a class="btn btn-secondary" href="/forces">Every economic force</a></div>')
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title,
          "description": desc, "url": f"{base_url}/sectors"}
    any_measured = any(members_of(s, stocks) for s in sectors())
    return _shell(title, desc, f"{base_url}/sectors", ld, body, app_url,
                  robots="" if any_measured else "noindex, follow")


def sector_page_html(sector: str, stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    stocks = list(stocks)
    mem = members_of(sector, stocks)
    total = sum(1 for v in sector_by_ticker().values() if v == sector)
    canonical = f"{base_url}/sectors/{slug(sector)}"
    title = f"{sector} stocks: exposure to interest rates, oil, the dollar and more"
    newest = max((str(m.get("as_of") or "")[:10] for m in mem), default="")
    if not mem:
        desc = f"How {sector} stocks have moved with economic forces."
        body = ('<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › '
                f'<a href="/sectors">Sectors</a> › {escape(sector)}</nav><h1>{escape(sector)}</h1>'
                f'<p class="lead">None of the {total} {escape(sector)} companies in the S&amp;P 500 has '
                'been measured yet. Readings are added each week.</p>')
        return _shell(title, desc, canonical, {"@context": "https://schema.org", "@type": "WebPage",
                                               "name": title, "url": canonical},
                      body, app_url, robots="noindex, follow")
    summary = "".join(
        f'<tr><th scope="row"><a href="/forces/{f.key}">{escape(f.label)}</a>'
        f'<span class="shock">In weeks when {escape(f.shock_phrase)}</span></th>'
        f'{_cell_html(sector_cell(mem, f.key))}</tr>'
        for f in tuple(ex.FACTORS) + tuple(ex.EXTRA_FACTORS) if sector_cell(mem, f.key)["n"])
    desc = (f"How {len(mem)} of the {total} {sector} companies in the S&P 500 have moved with interest "
            "rates, oil, the dollar and more: the sector's median move and every stock's own reading.")
    others = "".join(f'<li><a href="/sectors/{slug(s)}">{escape(s)}</a></li>' for s in sectors() if s != sector)
    body = (
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › '
        f'<a href="/sectors">Sectors</a> › {escape(sector)}</nav>'
        f'<h1>{escape(sector)}</h1>'
        f'<p class="meta">{len(mem)} of {total} companies on record'
        + (f' · data through {_date(newest)}' if newest else "") + '</p>'
        f'<p class="lead">{escape(desc)}</p>'
        f'<h2>The sector as a whole</h2>'
        f'<div class="card" tabindex="0" role="region" aria-label="{escape(sector)}: median move on each force">'
        f'<table><thead><tr><th scope="col">Economic force</th><th scope="col">Median move</th></tr></thead>'
        f'<tbody>{summary}</tbody></table><div class="foot">{_FOOT}</div></div>'
        f'<h2>Every {escape(sector)} stock on record</h2>'
        + hub_grid_html(mem, f"{sector} stocks against the five core forces")
        + '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here is a '
          'recommendation to buy, sell or hold any security.</p>'
        f'<h2>Other sectors</h2><ul class="related">{others}</ul>')
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title,
          "description": desc, "url": canonical}
    if newest:
        ld["dateModified"] = newest
    return _shell(title, desc, canonical, ld, body, app_url)
