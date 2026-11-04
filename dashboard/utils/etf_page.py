# utils/etf_page.py
# Unstructured Alpha — /etfs: widely held funds against the economy
#
# Most retail investors own funds, not single companies. The weekly library
# job measures the funds in cron/etfs.csv exactly as it measures a stock; this
# page lays them out by kind (bonds, sectors, commodities, ...), each section
# with one takeaway and a table of the five core forces.
#
# RULES
#   * A takeaway names only a reading that held up (Clear or Tentative); a
#     section with none says so rather than lead with noise.
#   * Grey figures could not be told apart from zero; a dash was not measured.
#   * Past, not forecast; no advice.

from __future__ import annotations

from html import escape
from typing import Dict, Iterable, List, Optional

from utils import exposure as ex
from utils.exposure_pages import (STANDS_UP, _shell, data_chips, data_week, fmt_pct,
                                  tool_header_html)
from utils.funds import funds

ORDER = ("Bonds", "Sector", "Broad and style", "Commodities", "International", "Crypto")
HEADINGS = {"Bonds": "Bond funds", "Sector": "Sector funds", "Broad and style": "Broad, style and dividend funds",
            "Commodities": "Commodity funds", "International": "International funds", "Crypto": "Crypto funds"}
_CORE = tuple(ex.FACTORS)

_CSS = """<style>
.etf-sec{margin-top:26px}.etf-sec h2{margin-bottom:4px}
.etf-take{margin:4px 0 10px;color:var(--ink2);max-width:75ch}
.etf-t td{font-variant-numeric:tabular-nums;white-space:nowrap}
.etf-t td.u{background:rgba(47,111,189,.14)}.etf-t td.d{background:rgba(181,101,29,.16)}
.etf-t tbody th span{display:block;font-weight:400;color:var(--ink3);max-width:260px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.etf-jump{display:flex;flex-wrap:wrap;gap:6px 14px;margin:10px 0 0;padding:0;list-style:none}
</style>"""


def takeaway(group: List[dict]) -> Optional[str]:
    """The largest core reading in the group that held up, as one sentence."""
    best = None
    for s in group:
        for f in _CORE:
            e = (s.get("exposures") or {}).get(f.key)
            if e and e.get("evidence") in STANDS_UP and (best is None or abs(e["impact"]) > abs(best[2]["impact"])):
                best = (s, f, e)
    if not best:
        return None
    s, f, e = best
    return (f'The largest clear link here: <a href="/exposure/{escape(s["ticker"])}">{escape(s["ticker"])}</a> '
            f'typically moved <b>{fmt_pct(e["impact"])}</b> in weeks when {escape(f.shock_phrase)}, '
            f'beyond the stock market&#39;s own move.')


def _cell(e: Optional[dict]) -> str:
    if not e:
        return '<td title="Not measured">—</td>'
    v = fmt_pct(e["impact"])
    if e.get("evidence") in STANDS_UP:
        return f'<td class="{"u" if e["impact"] > 0 else "d"}"><b>{v}</b></td>'
    return f'<td><span class="v-weak">{v}</span></td>'


def _table(group: List[dict], label: str) -> str:
    head = "".join(f'<th scope="col" title="In weeks when {escape(f.shock_phrase)}">{escape(f.label)}</th>'
                   for f in _CORE)
    rows = "".join(
        f'<tr><th scope="row"><a href="/exposure/{escape(s["ticker"])}">{escape(s["ticker"])}</a>'
        f'<span>{escape(s.get("name") or "")}</span></th>'
        + "".join(_cell((s.get("exposures") or {}).get(f.key)) for f in _CORE) + "</tr>"
        for s in sorted(group, key=lambda s: s["ticker"]))
    return (f'<div class="card" tabindex="0" role="region" aria-label="{escape(label)}">'
            f'<table class="etf-t"><thead><tr><th scope="col">Fund</th>{head}</tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def etfs_page_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    listed = funds()
    measured = [s for s in stocks if s.get("ticker") in listed]
    canonical = f"{base_url}/etfs"
    title = "ETF exposure to interest rates, inflation, oil, the dollar and credit"
    desc = (f"How {len(measured)} widely held ETFs (bond, sector, dividend, commodity and international "
            "funds) have moved with interest rates, inflation, the dollar, oil and credit spreads.")
    crumb = '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › ETFs</nav>'
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title,
          "description": desc, "url": canonical}
    if not measured:
        body = crumb + tool_header_html("ETFs", [], "No fund has been measured yet. Funds are added each week.")
        return _shell(title, desc, canonical, ld, body, app_url, robots="noindex, follow")

    by_cat: Dict[str, List[dict]] = {}
    for s in measured:
        by_cat.setdefault(listed[s["ticker"]][1], []).append(s)
    cats = [c for c in ORDER if c in by_cat] + sorted(c for c in by_cat if c not in ORDER)
    jump = "".join(f'<li><a href="#{c.lower().replace(" ", "-")}">{escape(HEADINGS.get(c, c))}</a></li>'
                   for c in cats)
    sections = "".join(
        f'<section class="etf-sec" id="{c.lower().replace(" ", "-")}"><h2>{escape(HEADINGS.get(c, c))}</h2>'
        f'<p class="etf-take">{takeaway(by_cat[c]) or "No reading in this group held up."}</p>'
        + _table(by_cat[c], HEADINGS.get(c, c)) + "</section>"
        for c in cats)
    lead = ("Most investors own funds, not single companies. Each fund here is measured the same way as a "
            "stock: its typical weekly move, beyond the stock market&#39;s own move, in weeks when a force "
            "moved by its standard amount. Bold, shaded figures held up; grey ones could not be told apart "
            "from zero. Funds that simply track the S&amp;P 500 are not listed: with the market taken out, "
            "there is nothing left to measure.")
    body = (_CSS + crumb
            + tool_header_html("ETFs", data_chips(len(measured), "widely held funds",
                                                  data_week(s.get("as_of") for s in measured)), lead)
            + f'<ul class="etf-jump" aria-label="Fund groups">{jump}</ul>'
            + sections
            + '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here is a '
              'recommendation to buy, sell or hold any security.</p>'
            + '<div class="actions"><a class="btn btn-primary" href="/exposure">Every stock and fund</a>'
              '<a class="btn btn-secondary" href="/scenario">Build a scenario</a>'
              '<a class="btn btn-secondary" href="/mylist">Measure your own list</a></div>')
    return _shell(title, desc, canonical, ld, body, app_url)
