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
.bar-in{flex-wrap:wrap}
.site-nav{display:flex;flex-wrap:wrap;gap:4px 16px;align-items:center;flex:1 1 auto;justify-content:center}
.site-nav a{color:#d6e2f3;text-decoration:none;font-size:.88rem;font-weight:600;padding:6px 0;border-bottom:2px solid transparent}
.site-nav a:hover{color:#fff}.site-nav a[aria-current=page]{color:#fff;border-bottom-color:var(--bright)}
.go{display:flex;gap:6px}.go input{width:118px;min-height:36px;border-radius:9px;border:1px solid #3a5a80;
  background:#0f2440;color:#fff;padding:0 10px;font:inherit;font-size:.88rem;text-transform:uppercase}
.go input::placeholder{color:#9fb3cc;text-transform:none}
.go button{min-height:36px;border-radius:9px;border:0;background:#2a4b74;color:#fff;font:inherit;font-size:.88rem;
  font-weight:650;padding:0 10px;cursor:pointer}
@media (max-width:760px){.bar-in{padding:10px 16px;row-gap:6px}.bar a.cta{display:none}
  .site-nav{order:3;flex-basis:100%;flex-wrap:nowrap;justify-content:flex-start;gap:16px;overflow-x:auto;
    scrollbar-width:none;margin:0 -16px;padding:0 16px}
  .site-nav::-webkit-scrollbar{display:none}.site-nav a{white-space:nowrap}
  .go input{width:96px}}
.site-foot{border-top:1px solid var(--line);background:var(--subtle)}
.site-foot-in{max-width:980px;margin:0 auto;padding:22px 16px 30px;display:grid;
  grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:18px}
.site-foot h2{font-size:.82rem;margin:0 0 6px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink3)}
.site-foot ul{list-style:none}.site-foot li{margin:3px 0}.site-foot a{color:var(--ink2);font-size:.92rem;text-decoration:none}
.site-foot a:hover{text-decoration:underline}.site-foot p{font-size:.82rem;color:var(--ink3)}
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
details.embed{margin:24px 0 8px}details.embed summary{cursor:pointer;font-weight:650}
details.embed textarea{margin:8px 0;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink)}
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
           app_url: str, robots: str = "", og_image: str = "") -> str:
    """og_image: a 1200x630 preview for shares; the site's own image when empty."""
    ld = json.dumps(json_ld, separators=(",", ":")).replace("</", "<\\/")
    if not og_image:
        from urllib.parse import urlsplit
        u = urlsplit(canonical)
        og_image = f"{u.scheme}://{u.netloc}/og-image.png"
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
        f'<meta property="og:image" content="{escape(og_image)}">'
        '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
        '<meta name="twitter:card" content="summary_large_image">'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap">'
        f'<script type="application/ld+json">{ld}</script>'
        f'<style>{_CSS}</style></head><body>'
        '<a class="skip" href="#main">Skip to content</a>'
        '<header class="bar"><div class="bar-in">'
        '<a class="brand" href="/">UNSTRUCTURED <span>ALPHA</span></a>'
        f'{_site_nav(canonical)}'
        '<form class="go" action="/go" method="get" role="search">'
        '<label for="go-t" class="sr-only" style="position:absolute;left:-9999px">Find a stock</label>'
        '<input id="go-t" name="t" placeholder="Ticker" autocomplete="off" spellcheck="false" maxlength="15">'
        '<button type="submit">Go</button></form>'
        f'<a class="cta" href="{escape(app_url)}/">Measure a portfolio</a>'
        '</div></header>'
        f'<main id="main">{body}</main>{_site_footer(app_url)}</body></html>')


# The public tools, in the order the header shows them. Every page carries the
# same header and footer so a visitor can reach any of them from anywhere.
NAV = (("/exposure", "Stocks"), ("/sectors", "Sectors"), ("/forces", "Forces"),
       ("/explore", "What if?"), ("/compare", "Compare"), ("/quiz", "Quiz"))
MORE = (("/tools", "All free tools"), ("/changes", "What changed this week"),
        ("/evidence", "Track record"))


def _site_nav(canonical: str) -> str:
    from urllib.parse import urlsplit
    path = urlsplit(canonical).path or "/"

    def link(href: str, label: str) -> str:
        here = path == href or path.startswith(href + "/")
        return f'<a href="{href}"' + (' aria-current="page"' if here else "") + f'>{escape(label)}</a>'
    return '<nav class="site-nav" aria-label="Site">' + "".join(link(h, t) for h, t in NAV) + '</nav>'


def _site_footer(app_url: str) -> str:
    def ul(items) -> str:
        return "<ul>" + "".join(f'<li><a href="{h}">{escape(t)}</a></li>' for h, t in items) + "</ul>"
    return (
        '<footer class="site-foot"><div class="site-foot-in">'
        f'<div><h2>Explore</h2>{ul(NAV)}</div>'
        f'<div><h2>More</h2>{ul(MORE)}</div>'
        f'<div><h2>Your portfolio</h2>{ul(((escape(app_url) + "/", "Measure a portfolio"), (escape(app_url) + "/scenarios", "Stress-test it"), (escape(app_url) + "/methodology", "Methodology")))}</div>'
        '<div><h2>Unstructured Alpha</h2><p>How U.S. stocks have moved with interest rates, inflation, '
        'the dollar, oil and more, measured weekly. It describes the past and is not a forecast or '
        'investment advice.</p></div>'
        '</div></footer>')


def stock_page_html(symbol: str, rec: dict, history: List[dict], related: List[dict],
                    base_url: str, app_url: str, held: Optional[dict] = None,
                    similar: Optional[List[dict]] = None) -> str:
    """The page for one measured stock. `rec` is its newest stored week.

    held: utils.track_record.persistence() of the published study, or None.
    """
    from utils import track_record as tr
    from utils.embed_page import embed_box_html
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

    from utils.sector_pages import sector_by_ticker, slug as sector_slug
    sector = sector_by_ticker().get(symbol)
    sector_html = (f'<a href="/sectors/{sector_slug(sector)}">{escape(sector)}</a> · ' if sector else "")

    sim_html = ""
    if similar:
        items = "".join(
            f'<li><a href="/exposure/{escape(r["ticker"])}">{escape(r["ticker"])}'
            + (f' · {escape(r["name"])}' if r.get("name") else "") + '</a> '
            f'<a class="small" href="/compare?a={escape(symbol)}&amp;b={escape(r["ticker"])}" '
            f'aria-label="Compare {escape(symbol)} with {escape(r["ticker"])}">compare</a></li>'
            for r in similar)
        sim_html = (f'<h2>Stocks with the most similar profile</h2>'
                    f'<ul class="related" aria-label="Stocks most like {escape(symbol)}">{items}</ul>'
                    '<p class="small">Closest across the five core forces, each scaled by how much '
                    'stocks on record differ on it. Alike in how they moved over three years, not in '
                    'business, size or value.</p>')

    body = (
        f'<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › '
        f'<a href="/exposure">Stock exposures</a> › {escape(symbol)}</nav>'
        f'<h1>{who}: economic exposure</h1>'
        f'<p class="meta">{sector_html}Data through {_date(rec["as_of"])} · weekly returns, the stock '
        f'market\'s own movement removed first</p>'
        f'<p class="lead">{escape(summary)}</p>'
        f'<h2>Exposure to each economic force</h2>{table}'
        '<div class="actions">'
        f'<a class="btn btn-primary" href="{escape(app_url)}/stock?t={escape(symbol)}">'
        f'Open the interactive report for {escape(symbol)}</a>'
        f'<a class="btn btn-secondary" href="{escape(app_url)}/">Measure a whole portfolio</a>'
        f'<a class="btn btn-secondary" href="/compare?a={escape(symbol)}">Compare {escape(symbol)} with another stock</a></div>'
        f'{stock_whatif_html(symbol, rec)}{extra_html}{hist_html}{rel_html}{sim_html}'
        f'{embed_box_html(symbol, base_url)}'
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
    return _shell(title, summary[:300], canonical, json_ld, body, app_url,
                  og_image=f"{base_url}/og/{symbol}.png")


_HUB_SCRIPT = r"""
(function(){
  var t = document.getElementById('hub'), body = t.tBodies[0], q = document.getElementById('hub-q');
  var count = document.getElementById('hub-count'), rows = Array.prototype.slice.call(body.rows);
  function filter(){
    var s = q.value.trim().toUpperCase(), n = 0;
    rows.forEach(function(r){ var hit = !s || r.getAttribute('data-k').indexOf(s) >= 0;
      r.hidden = !hit; if (hit) n++; });
    count.textContent = n + ' of ' + rows.length + ' stocks';
  }
  t.querySelectorAll('thead button').forEach(function(b){
    b.addEventListener('click', function(){
      var col = +b.getAttribute('data-col'), th = b.parentNode;
      var dir = th.getAttribute('aria-sort') === 'descending' ? 1 : -1;
      t.querySelectorAll('thead th').forEach(function(h){ h.removeAttribute('aria-sort'); });
      th.setAttribute('aria-sort', dir < 0 ? 'descending' : 'ascending');
      function key(r){ var v = r.cells[col].getAttribute('data-v');
        return col === 0 ? r.cells[0].textContent : (v === null || v === '' ? null : +v); }
      rows.sort(function(a, z){
        var x = key(a), y = key(z);
        if (col === 0) return dir < 0 ? (x < y ? -1 : 1) : (x < y ? 1 : -1);
        if (x === null) return 1; if (y === null) return -1;   // unmeasured always last
        return dir * (x - y);
      });
      rows.forEach(function(r){ body.appendChild(r); });
    });
  });
  q.addEventListener('input', filter); filter();
})();
"""

_HUB_CSS = """<style>
.hub-bar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:8px 0}
.hub-bar input{min-height:44px;font:inherit;border:1px solid var(--line);border-radius:10px;padding:0 12px;
  background:var(--surface);color:var(--ink);flex:1 1 220px;max-width:360px}
#hub th button{all:unset;cursor:pointer;font-weight:650}
#hub th button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
#hub th[aria-sort=descending] button::after{content:" ↓"}#hub th[aria-sort=ascending] button::after{content:" ↑"}
#hub td{font-variant-numeric:tabular-nums;white-space:nowrap}
#hub tbody th,#hub thead th:first-child{position:sticky;left:0;z-index:1;background:var(--surface)}
@media (max-width:640px){#hub tbody th span{max-width:110px}}
#hub td.h-up{background:rgba(47,111,189,.14)}#hub td.h-down{background:rgba(181,101,29,.16)}
#hub tbody th span{display:block;font-weight:400;font-size:.82rem;color:var(--ink3);max-width:220px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
</style>"""


def hub_grid_html(stocks: Iterable[dict], label: str = "Every stock on record against the five core forces") -> str:
    """The sortable, filterable table of stocks against the core five; works
    in full without script, sorted by ticker."""
    stocks = sorted(stocks, key=lambda s: s["ticker"])

    def cell(e: Optional[dict]) -> str:
        if not e:
            return '<td data-v="" title="Not measured">—</td>'
        strong = e.get("evidence") in STANDS_UP
        cls = (' class="h-up"' if e["impact"] > 0 else ' class="h-down"') if strong else ""
        v = fmt_pct(e["impact"])
        return (f'<td data-v="{e["impact"]:.4f}"{cls}>'
                + (f"<b>{v}</b>" if strong else f'<span class="v-weak">{v}</span>') + '</td>')

    rows = "".join(
        f'<tr data-k="{escape((s["ticker"] + " " + (s.get("name") or "")).upper())}">'
        f'<th scope="row"><a href="/exposure/{escape(s["ticker"])}">{escape(s["ticker"])}</a>'
        + (f'<span>{escape(s["name"])}</span>' if s.get("name") else "") + '</th>'
        + "".join(cell((s.get("exposures") or {}).get(k)) for k in _ORDER) + '</tr>'
        for s in stocks)
    head = ('<th scope="col"><button type="button" data-col="0">Stock</button></th>'
            + "".join(f'<th scope="col"><button type="button" data-col="{i + 1}" '
                      f'title="In weeks when {escape(_FACTOR[k].shock_phrase)}">{escape(_FACTOR[k].label)}</button></th>'
                      for i, k in enumerate(_ORDER)))
    return (
        _HUB_CSS
        + '<div class="hub-bar"><label for="hub-q" class="small">Find a stock</label>'
          '<input id="hub-q" type="search" autocomplete="off" spellcheck="false" placeholder="Ticker or name">'
          '<span class="small" id="hub-count" aria-live="polite"></span></div>'
        + f'<div class="card" tabindex="0" role="region" aria-label="{escape(label)}">'
          f'<table id="hub"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'
          '<div class="foot">Each figure is the stock&#39;s typical move in a week when that force moved '
          'by its standard amount (hover a heading for it), after accounting for the stock market. '
          'Bold, shaded figures held up; grey ones could not be told apart from zero; a dash was not '
          'measured. Click a heading to sort. It describes the past; it is not a forecast.</div></div>'
        + f'<script>{_HUB_SCRIPT}</script>')


def hub_page_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    """Every measured stock against the core five, sortable and filterable.
    The crawl entry point for the pages above: every row links to its page,
    and the table works in full without script, sorted by ticker."""
    stocks = sorted(stocks, key=lambda s: s["ticker"])
    title = "Stock exposure to interest rates, inflation, oil, the dollar and credit"
    desc = (f"How {len(stocks)} U.S. stocks have moved with interest rates, inflation expectations, "
            "the dollar, oil and credit spreads, each with its 90% range and an evidence label.")
    table = hub_grid_html(stocks)
    body = (
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Stock exposures</nav>'
        f'<h1>Stock exposures</h1><p class="lead">{escape(desc)} Measured weekly over three years, '
        'with the stock market\'s own movement removed first.</p>'
        + (table if stocks else '<p class="lead">No stock has been measured yet.</p>')
        + f'<div class="actions"><a class="btn btn-primary" href="{escape(app_url)}/stock">'
          'Look up any stock</a><a class="btn btn-secondary" href="/forces">Browse by economic '
          'force</a><a class="btn btn-secondary" href="/sectors">By sector</a>'
          '<a class="btn btn-secondary" href="/changes">What changed this week</a></div>')
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
