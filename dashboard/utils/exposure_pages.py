# utils/exposure_pages.py
# Unstructured Alpha — crawlable exposure pages, one per measured stock
#
# WHY
# ---
# The pages search engines index for this site were /ticker/{SYMBOL}: the
# retired signal product's Confluence Score and bullish/bearish counts -- the
# "stock pick" framing the product now disclaims. These pages are the current
# product instead: how one company has moved with each economic force, with its
# 90% range and evidence label, straight from the stock library.
#
# Served by the SEO service (seo/main.py) as plain server-rendered HTML, because
# the Streamlit app renders over a websocket that crawlers index poorly.
#
# RULES
# -----
#   * Only a stock that has been measured gets a page. Nothing is estimated to
#     fill one in, and an unmeasured ticker is a 404, not a thin page.
#   * Every string from the database is escaped.
#   * No forecast and no advice: the copy describes how the stock has moved.
#   * Pure functions of their inputs, so the whole page is testable without a
#     server or a database.

from __future__ import annotations

import json
import math
import re
from html import escape
from typing import Dict, Iterable, List, Optional

from utils import exposure as ex

SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
STANDS_UP = ("clear", "tentative")
_ORDER = [f.key for f in ex.FACTORS]
_FACTOR = {f.key: f for f in ex.FACTORS}
_EXTRA = {f.key: f for f in ex.EXTRA_FACTORS}


def fmt_pct(x: Optional[float]) -> str:
    """Same output as report_ui.fmt_pct, without importing Streamlit."""
    if x is None or not math.isfinite(x):
        return "—"
    digits = 1 if abs(x) >= 0.95 else 2
    if round(x, digits) == 0:
        return f"{0:.{digits}f}%"
    sign = "+" if x > 0 else "−"
    return f"{sign}{abs(x):.{digits}f}%"


def lead_factor(rec: dict) -> Optional[str]:
    """The force this stock is most exposed to, among readings that held up.

    None when nothing held up: a page must not say a stock is "exposed to" a
    force on a reading that could not be told apart from zero.
    """
    exps = (rec or {}).get("exposures") or {}
    strong = [k for k in _ORDER if k in exps and exps[k].get("evidence") in STANDS_UP]
    return max(strong, key=lambda k: abs(exps[k]["impact"])) if strong else None


def _date(iso: str) -> str:
    from datetime import date

    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return escape(str(iso))
    return f"{d:%b} {d.day}, {d.year}"


def _join(items: List[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def summary_sentence(symbol: str, rec: dict) -> str:
    """One paragraph from the stored numbers, in the report's own wording."""
    exps: Dict[str, dict] = rec.get("exposures") or {}
    keys = [k for k in _ORDER if k in exps]
    ranked = sorted(keys, key=lambda k: -abs(exps[k]["impact"]))
    clear = [ex.lower_label(_FACTOR[k].label) for k in ranked if exps[k]["evidence"] == "clear"]
    tent = [ex.lower_label(_FACTOR[k].label) for k in ranked if exps[k]["evidence"] == "tentative"]
    none = [ex.lower_label(_FACTOR[k].label) for k in keys if exps[k]["evidence"] not in STANDS_UP]
    weeks = rec.get("n_obs") or rec.get("window_weeks")
    span = (f"Over the {weeks} weeks to {_date(rec['as_of'])}" if weeks
            else f"In the three years to {_date(rec['as_of'])}")
    parts = []
    if clear:
        parts.append(f"clearly sensitive to {_join(clear)}")
    if tent:
        parts.append(f"tentatively sensitive to {_join(tent)}")
    if parts:
        text = f"{span}, {symbol} has been {' and '.join(parts)}."
    else:
        text = (f"{span}, {symbol} shows no clear sensitivity to any of the economic forces "
                f"measured, beyond its movement with the stock market.")
    if none:
        text += f" No measurable link to {_join(none)}."
    beta = rec.get("market_beta")
    if beta is not None and math.isfinite(beta):
        text += (f" It has typically moved {beta:.2f} times as much as the U.S. stock market, "
                 f"which is accounted for separately.")
    return text


def page_title(symbol: str, name: str) -> str:
    who = f"{name} ({symbol})" if name and name != symbol else symbol
    return f"{who}: exposure to interest rates, inflation, oil and the dollar"


# ── the page ────────────────────────────────────────────────────────────────

_CSS = """
:root{--bg:#fafaf8;--surface:#fff;--subtle:#f4f6fa;--ink:#13213a;--ink2:#3a4760;--ink3:#5b6780;
  --line:#dfe5ee;--accent:#1f5fae;--navy:#0d223b;--navy2:#15375d;--bright:#ffc24b;
  --clear-bg:#dcf3ea;--clear-ink:#0b6a4e;--tent-bg:#fdefd6;--tent-ink:#8a4f00;--zero-bg:#eceff4;--zero-ink:#4a5568;}
@media (prefers-color-scheme:dark){:root{--bg:#0b1422;--surface:#121d2f;--subtle:#16233a;--ink:#e8edf5;
  --ink2:#bdc7d8;--ink3:#8f9bb1;--line:#243349;--accent:#8cb8f2;--navy:#081628;--navy2:#10294a;
  --clear-bg:#11392e;--clear-ink:#7fdcb8;--tent-bg:#3a2a0d;--tent-ink:#f5c774;--zero-bg:#1f2a3c;--zero-ink:#b3bfd2;}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:Inter,"SF Pro Text","Segoe UI",system-ui,sans-serif;
  line-height:1.6;font-variant-numeric:tabular-nums}
a{color:var(--accent)}
.skip{position:absolute;left:12px;top:-60px;background:var(--bright);color:#13213a;padding:8px 14px;border-radius:8px;font-weight:700}
.skip:focus{top:8px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.bar{background:linear-gradient(120deg,var(--navy),var(--navy2));background-color:var(--navy)}
.bar-in{max-width:980px;margin:0 auto;padding:14px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.brand{color:#fff;font-weight:800;letter-spacing:-.01em;text-decoration:none}.brand span{color:var(--bright)}
.bar a.cta{background:var(--bright);color:#13213a;font-weight:700;text-decoration:none;padding:8px 14px;border-radius:10px;font-size:.88rem}
main{max-width:980px;margin:0 auto;padding:28px 16px 48px}
.crumb{font-size:.82rem;color:var(--ink3);margin-bottom:10px}.crumb a{color:var(--ink3)}
h1{font-size:1.7rem;line-height:1.25;letter-spacing:-.02em;margin-bottom:6px}
.meta{color:var(--ink3);font-size:.88rem;margin-bottom:16px}
.lead{font-size:1.05rem;color:var(--ink2);max-width:760px;margin-bottom:22px}
h2{font-size:1.2rem;margin:30px 0 10px}
h3{font-size:.8rem;margin:14px 0 8px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink3)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th{text-align:left;font-weight:650;color:var(--ink3);padding:10px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top;color:var(--ink2)}
tr:last-child td{border-bottom:0}
td b{color:var(--ink)}
.shock{display:block;font-size:.82rem;color:var(--ink3)}
.chip{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.78rem;font-weight:650;white-space:nowrap}
.chip-clear{background:var(--clear-bg);color:var(--clear-ink)}.chip-tentative{background:var(--tent-bg);color:var(--tent-ink)}
.chip-zero{background:var(--zero-bg);color:var(--zero-ink)}
.v-weak{color:var(--ink3)}
.foot{font-size:.82rem;color:var(--ink3);padding:10px 12px;background:var(--subtle)}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0 6px}
.btn{display:inline-flex;align-items:center;min-height:44px;padding:0 18px;border-radius:10px;font-weight:650;text-decoration:none}
.btn-primary{background:var(--accent);color:#fff}
@media (prefers-color-scheme:dark){.btn-primary{color:#0b1422}}
.btn-secondary{background:var(--surface);border:1px solid var(--line);color:var(--ink)}
.related{display:flex;flex-wrap:wrap;gap:8px;list-style:none}
.related a{display:inline-block;padding:7px 12px;border:1px solid var(--line);border-radius:10px;background:var(--surface);
  color:var(--ink);text-decoration:none;font-size:.92rem}
.caveat{border-left:3px solid var(--accent);background:var(--subtle);padding:10px 14px;color:var(--ink2);margin:26px 0 10px;font-size:.92rem}
.small{font-size:.82rem;color:var(--ink3)}
.grid{columns:3 220px;column-gap:16px}.grid li{list-style:none;break-inside:avoid;margin:0 0 6px}
.forces{columns:2 280px;column-gap:24px}.forces li{list-style:none;break-inside:avoid;margin:0 0 10px}
.forces a{font-weight:650}
th[scope=row]{font-weight:650;color:var(--ink);white-space:normal}
"""


def _chip(evidence: str) -> str:
    cls = {"clear": "chip-clear", "tentative": "chip-tentative"}.get(evidence, "chip-zero")
    return f'<span class="chip {cls}">{escape(ex.EVIDENCE_LABELS.get(evidence, evidence))}</span>'


def _shell(title: str, description: str, canonical: str, json_ld: dict, body: str,
           app_url: str, robots: str = "") -> str:
    ld = json.dumps(json_ld, separators=(",", ":")).replace("</", "<\\/")
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(title)}</title>'
        + (f'<meta name="robots" content="{escape(robots)}">' if robots else "") +
        f'<meta name="description" content="{escape(description)}">'
        f'<link rel="canonical" href="{escape(canonical)}">'
        f'<meta property="og:type" content="website"><meta property="og:title" content="{escape(title)}">'
        f'<meta property="og:description" content="{escape(description)}">'
        f'<meta property="og:url" content="{escape(canonical)}"><meta property="og:site_name" content="Unstructured Alpha">'
        '<meta name="twitter:card" content="summary">'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap">'
        f'<script type="application/ld+json">{ld}</script>'
        f'<style>{_CSS}</style></head><body>'
        '<a class="skip" href="#main">Skip to content</a>'
        '<header class="bar"><div class="bar-in">'
        '<a class="brand" href="/">UNSTRUCTURED <span>ALPHA</span></a>'
        f'<a class="cta" href="{escape(app_url)}/">Measure a portfolio</a>'
        '</div></header>'
        f'<main id="main">{body}</main></body></html>')


def stock_page_html(symbol: str, rec: dict, history: List[dict], related: List[dict],
                    base_url: str, app_url: str, held: Optional[dict] = None) -> str:
    """The page for one measured stock. `rec` is its newest stored week.

    held: utils.track_record.persistence() of the published study, or None.
    """
    from utils import track_record as tr
    from utils.explore_page import stock_whatif_html

    held = held or {}
    name = rec.get("name") or ""
    who = f"{escape(name)} ({escape(symbol)})" if name and name != symbol else escape(symbol)
    exps = rec.get("exposures") or {}
    keys = sorted((k for k in _ORDER if k in exps), key=lambda k: -abs(exps[k]["impact"]))
    summary = summary_sentence(symbol, rec)
    title = page_title(symbol, name)
    canonical = f"{base_url}/exposure/{symbol}"

    rows = "".join(
        f'<tr><td><b><a href="/forces/{k}">{escape(_FACTOR[k].label)}</a></b>'
        f'<span class="shock">In weeks when {escape(_FACTOR[k].shock_phrase)}</span></td>'
        f'<td><b{"" if exps[k]["evidence"] in STANDS_UP else " class=v-weak"}>{fmt_pct(exps[k]["impact"])}</b></td>'
        f'<td>{fmt_pct(exps[k]["low"])} to {fmt_pct(exps[k]["high"])}</td>'
        f'<td>{_chip(exps[k]["evidence"])}'
        + (f'<span class="shock">{escape(line)}</span>'
           if (line := tr.persistence_short(k, exps[k]["evidence"], held)) else "")
        + '</td></tr>'
        for k in keys)
    table = (
        # Focusable and labelled: on a phone the table scrolls sideways inside
        # its card, and a keyboard user has to be able to reach that scroll.
        '<div class="card" tabindex="0" role="region" aria-label="Exposure to each economic force">'
        '<table><thead><tr><th scope="col">Economic force</th>'
        '<th scope="col">Typical weekly move</th><th scope="col">90% range</th>'
        f'<th scope="col">Evidence</th></tr></thead><tbody>{rows}</tbody></table>'
        '<div class="foot">Each figure is the stock\'s typical same-week move when that force moved by '
        'the stated amount, after accounting for the stock market. It describes the past; it is not '
        'a forecast.'
        + (' How often each force&#39;s Clear and Tentative readings held their direction a year '
           'later comes from the <a href="/evidence">published track record</a>.' if held else "")
        + '</div></div>')

    extra_html = ""
    xkeys = [k for k in _EXTRA if k in exps]
    if xkeys:
        xrows = "".join(
            f'<tr><td><b><a href="/forces/{k}">{escape(_EXTRA[k].label)}</a></b>'
            f'<span class="shock">In weeks when {escape(_EXTRA[k].shock_phrase)}</span></td>'
            f'<td><b{"" if exps[k]["evidence"] in STANDS_UP else " class=v-weak"}>{fmt_pct(exps[k]["impact"])}</b></td>'
            f'<td>{fmt_pct(exps[k]["low"])} to {fmt_pct(exps[k]["high"])}</td>'
            f'<td>{_chip(exps[k]["evidence"])}</td></tr>'
            for k in xkeys)
        extra_html = (
            '<h2>More forces, beyond the core five</h2>'
            '<div class="card" tabindex="0" role="region" aria-label="More forces, beyond the core five">'
            '<table><thead><tr><th scope="col">Force</th>'
            '<th scope="col">Typical weekly move</th><th scope="col">90% range</th>'
            f'<th scope="col">Evidence</th></tr></thead><tbody>{xrows}</tbody></table>'
            '<div class="foot">Each is measured with the stock market and the five forces above held '
            'fixed, so it shows only what they don\'t already explain. The evidence bar is stricter '
            f'than for the core five (Clear needs |t| ≥ {ex.EXTRA_CLEAR_T:.2f}, shared across every '
            'force tested). It describes the past; it is not a forecast.</div></div>')

    hist_html = ""
    if len(history) >= 2:
        cols = [k for k in _ORDER if any(k in h["exposures"] for h in history)]
        head = "".join(f'<th scope="col">{escape(_FACTOR[k].label)}</th>' for k in cols)

        def cell(h, k):
            e = h["exposures"].get(k)
            if not e:
                return '<td title="Not measured that week">—</td>'
            strong = e["evidence"] in STANDS_UP
            return f'<td>{"<b>" if strong else "<span class=v-weak>"}{fmt_pct(e["impact"])}{"</b>" if strong else "</span>"}</td>'
        body_rows = "".join(
            f'<tr><th scope="row">{_date(h["as_of"])}</th>{"".join(cell(h, k) for k in cols)}</tr>'
            for h in history[:12])
        hist_html = (
            f'<h2>{escape(symbol)} week by week</h2>'
            f'<div class="card" tabindex="0" role="region" aria-label="{escape(symbol)} week by week">'
            f'<table><thead><tr><th scope="col">Data through</th>{head}</tr></thead>'
            f'<tbody>{body_rows}</tbody></table>'
            '<div class="foot">Each row is the stock measured over the three years to that week. Bold '
            'figures held up; grey ones could not be told apart from zero. A dash means that force '
            'could not be measured that week, not that it was zero.</div></div>')

    rel_html = ""
    lead = lead_factor(rec)
    if related and lead:
        # Up and down listed apart: under one heading, a stock that fell when oil
        # rose would read as one that rose with it.
        force = escape(ex.lower_label(_FACTOR[lead].label))
        for label, side in (("Moved up with", [r for r in related if r["impact"] > 0]),
                            ("Moved down with", [r for r in related if r["impact"] < 0])):
            if not side:
                continue
            items = "".join(
                f'<li><a href="/exposure/{escape(r["ticker"])}">{escape(r["ticker"])}'
                + (f' · {escape(r["name"])}' if r.get("name") else "") + '</a></li>'
                for r in side)
            rel_html += (f'<h3>{label} {force}</h3>'
                         f'<ul class="related" aria-label="Other stocks that {label.lower()} {force}">'
                         f'{items}</ul>')
        rel_html = f'<h2>Other stocks exposed to {force}</h2>{rel_html}'

    body = (
        f'<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › '
        f'<a href="/exposure">Stock exposures</a> › {escape(symbol)}</nav>'
        f'<h1>{who}: economic exposure</h1>'
        f'<p class="meta">Data through {_date(rec["as_of"])} · weekly returns, the stock market\'s own '
        f'movement removed first</p>'
        f'<p class="lead">{escape(summary)}</p>'
        f'<h2>Exposure to each economic force</h2>{table}'
        '<div class="actions">'
        f'<a class="btn btn-primary" href="{escape(app_url)}/stock?t={escape(symbol)}">'
        f'Open the interactive report for {escape(symbol)}</a>'
        f'<a class="btn btn-secondary" href="{escape(app_url)}/">Measure a whole portfolio</a>'
        f'<a class="btn btn-secondary" href="/compare?a={escape(symbol)}">Compare {escape(symbol)} with another stock</a></div>'
        f'{stock_whatif_html(symbol, rec)}{extra_html}{hist_html}{rel_html}'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> It shows how the '
        'stock has moved alongside five economic forces. Relationships change, and nothing here is a '
        'recommendation to buy, sell or hold any security.</p>'
        f'<p class="small">Method: weekly returns over three years, regressed on weekly changes in the '
        f'10-year Treasury yield, 10-year inflation expectations, the trade-weighted dollar, oil and '
        f'corporate credit spreads, controlling for the S&amp;P 500. Newey-West standard errors; the 90% '
        f'range and evidence label show how precisely each figure is measured. Prices from Yahoo '
        f'Finance; economic series from FRED. <a href="{escape(app_url)}/methodology">Full methodology</a>.</p>')

    json_ld = {
        "@context": "https://schema.org", "@type": "WebPage", "name": title,
        "description": summary, "url": canonical, "dateModified": str(rec["as_of"])[:10],
        "about": {"@type": "Corporation", "name": name or symbol, "tickerSymbol": symbol},
        "isPartOf": {"@type": "WebSite", "name": "Unstructured Alpha", "url": base_url},
    }
    return _shell(title, summary[:300], canonical, json_ld, body, app_url)


def hub_page_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    """Every measured stock, linked. The crawl entry point for the pages above."""
    stocks = sorted(stocks, key=lambda s: s["ticker"])
    items = "".join(
        f'<li><a href="/exposure/{escape(s["ticker"])}">{escape(s["ticker"])}</a>'
        + (f' <span class="small">{escape(s["name"])}</span>' if s.get("name") else "") + '</li>'
        for s in stocks)
    title = "Stock exposure to interest rates, inflation, oil, the dollar and credit"
    desc = (f"How {len(stocks)} U.S. stocks have moved with interest rates, inflation expectations, "
            "the dollar, oil and credit spreads, each with its 90% range and an evidence label.")
    body = (
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Stock exposures</nav>'
        f'<h1>Stock exposures</h1><p class="lead">{escape(desc)} Measured weekly over three years, '
        'with the stock market\'s own movement removed first.</p>'
        + (f'<ul class="grid">{items}</ul>' if items else
           '<p class="lead">No stock has been measured yet.</p>')
        + f'<div class="actions"><a class="btn btn-primary" href="{escape(app_url)}/stock">'
          'Look up any stock</a><a class="btn btn-secondary" href="/forces">Browse by economic '
          'force</a></div>')
    json_ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title,
               "description": desc, "url": f"{base_url}/exposure"}
    return _shell(title, desc, f"{base_url}/exposure", json_ld, body, app_url)


def sitemap_urls(stocks: Iterable[dict], base_url: str) -> List[str]:
    """<url> entries: the hub, then one per measured stock with its real lastmod."""
    stocks = list(stocks)
    newest = max((str(s["as_of"])[:10] for s in stocks), default="")
    urls = [f"  <url><loc>{base_url}/exposure</loc>"
            + (f"<lastmod>{newest}</lastmod>" if newest else "")
            + "<changefreq>weekly</changefreq><priority>0.8</priority></url>"]
    for s in sorted(stocks, key=lambda s: s["ticker"]):
        if not SYMBOL_RE.match(s["ticker"]):
            continue
        urls.append(f"  <url><loc>{base_url}/exposure/{escape(s['ticker'])}</loc>"
                    f"<lastmod>{str(s['as_of'])[:10]}</lastmod>"
                    "<changefreq>weekly</changefreq><priority>0.8</priority></url>")
    return urls
