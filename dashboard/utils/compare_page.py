# utils/compare_page.py
# Unstructured Alpha — two stocks side by side, force by force
#
# Hands-on without a portfolio: type two tickers, see how each has moved with
# every economic force, and which differences are wide enough to stand apart
# from the noise. A plain GET form, so it works with no script at all.
#
# RULES
#   * A force is called a clear difference only when the two 90% ranges do not
#     overlap -- a stricter bar than either reading's own label, and said so.
#   * Readings that did not hold up are shown greyed, never dropped silently
#     and never ranked.
#   * Only the bare /compare page is indexable; every pair is noindex, so the
#     site does not mint a quarter of a million near-duplicate pages.
#   * Past, not forecast; nothing here is advice.

from __future__ import annotations

from html import escape
from typing import Iterable, List, Optional, Tuple

from utils.exposure_pages import STANDS_UP, SYMBOL_RE, _chip, _date, _shell, fmt_pct
from utils.force_pages import ALL_FORCES

# Shown in order, the first three with both stocks on record: the library fills
# in over weeks, so a fixed short list can show nothing at all.
EXAMPLES: Tuple[Tuple[str, str], ...] = (
    ("XOM", "DAL"), ("JPM", "NEE"), ("AAPL", "MSFT"), ("CVX", "DAL"), ("AAPL", "DAL"),
    ("BAC", "AMT"), ("COST", "AMZN"), ("ADBE", "CAT"))


def clean_symbol(raw: Optional[str]) -> str:
    s = (raw or "").strip().upper()
    return s if SYMBOL_RE.match(s) else ""


def compare_rows(a: dict, b: dict) -> List[dict]:
    """One row per force either stock has a reading on, in the site's order."""
    ea, eb = a.get("exposures") or {}, b.get("exposures") or {}
    rows = []
    for f in ALL_FORCES:
        ra, rb = ea.get(f.key), eb.get(f.key)
        if not ra and not rb:
            continue
        apart = bool(ra and rb and (ra["low"] > rb["high"] or rb["low"] > ra["high"]))
        rows.append({"key": f.key, "label": f.label, "phrase": f.shock_phrase,
                     "a": ra, "b": rb, "apart": apart,
                     "gap": abs(ra["impact"] - rb["impact"]) if ra and rb else 0.0})
    return rows


def _cell(r: Optional[dict]) -> str:
    if not r:
        return '<td title="Not measured">—</td>'
    strong = r.get("evidence") in STANDS_UP
    v = fmt_pct(r["impact"])
    return (f'<td><b{"" if strong else " class=v-weak"}>{v}</b>'
            f'<span class="shock">{fmt_pct(r["low"])} to {fmt_pct(r["high"])}</span>'
            f'{_chip(r["evidence"])}</td>')


_CSS = """<style>
.cp-form{display:grid;grid-template-columns:1fr 1fr auto;gap:12px;align-items:end;background:var(--surface);
  border:1px solid var(--line);border-radius:12px;padding:16px;margin:8px 0 6px}
.cp-form label{display:block;font-weight:650;font-size:.92rem;margin-bottom:6px}
.cp-form input{width:100%;min-height:44px;font:inherit;border:1px solid var(--line);border-radius:10px;
  padding:0 10px;background:var(--bg);color:var(--ink);text-transform:uppercase}
.cp-form button{min-height:44px}
tr.cp-apart th,tr.cp-apart td{background:var(--subtle)}
.cp-mark{display:block;font-size:.8rem;font-weight:700;color:var(--accent)}
@media (max-width:640px){.cp-form{grid-template-columns:1fr 1fr}.cp-form button{grid-column:1/-1}
  .cp-tab th[scope=row] .shock,.cp-tab .chip{display:none}.cp-tab th,.cp-tab td{padding-left:8px;padding-right:8px}}
</style>"""


def _form(a: str, b: str, tickers: List[str]) -> str:
    opts = "".join(f'<option value="{escape(t)}">' for t in tickers)
    return (
        '<form class="cp-form" method="get" action="/compare">'
        f'<div><label for="cp-a">First stock</label><input id="cp-a" name="a" value="{escape(a)}" '
        'list="cp-tickers" autocomplete="off" spellcheck="false" required></div>'
        f'<div><label for="cp-b">Second stock</label><input id="cp-b" name="b" value="{escape(b)}" '
        'list="cp-tickers" autocomplete="off" spellcheck="false" required></div>'
        '<button class="btn btn-primary" type="submit">Compare</button>'
        f'<datalist id="cp-tickers">{opts}</datalist></form>')


def compare_page_html(stocks: Iterable[dict], a: str, b: str, base_url: str, app_url: str) -> str:
    stocks = list(stocks)
    by = {s["ticker"]: s for s in stocks}
    tickers = sorted(by)
    a, b = clean_symbol(a), clean_symbol(b)
    canonical = f"{base_url}/compare"
    title = "Compare two stocks' exposure to rates, oil, the dollar and more"
    desc = ("Put two U.S. stocks side by side and see how each has moved with interest rates, "
            "oil, the dollar, gold and every other economic force measured here.")
    crumb = '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Compare</nav>'
    head = _CSS + crumb + '<h1>Compare two stocks</h1>'
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "url": canonical,
          "description": desc}

    if not (a or b):
        examples = "".join(
            f'<li><a href="/compare?a={x}&amp;b={y}">{x} vs {y}</a></li>'
            for x, y in [p for p in EXAMPLES if p[0] in by and p[1] in by][:3])
        body = (head + f'<p class="lead">{escape(desc)}</p>' + _form("", "", tickers)
                + (f'<h2>Try</h2><ul class="related">{examples}</ul>' if examples else "")
                + '<p class="small">Any stock on record can be compared: the S&amp;P 500, measured '
                  'weekly, plus any stock a visitor has opened.</p>')
        return _shell(title, desc, canonical, ld, body, app_url,
                      robots="" if stocks else "noindex, follow")

    missing = [t for t in (a, b) if t and t not in by]
    if not (a and b) or a == b or missing:
        why = (f'{" and ".join(escape(m) for m in missing)} {"is" if len(missing) == 1 else "are"} '
               'not on record yet. Opening a stock in the app measures it and adds it here.'
               if missing else f"Pick a second stock to compare with {escape(a or b)}."
               if bool(a) != bool(b) else "Pick two different stocks.")
        body = head + f'<p class="lead">{why}</p>' + _form(a, b, tickers)
        return _shell(title, desc, canonical, ld, body, app_url, robots="noindex, follow")

    sa, sb = by[a], by[b]
    rows = compare_rows(sa, sb)
    apart = sorted((r for r in rows if r["apart"]), key=lambda r: -r["gap"])
    if apart:
        top = apart[0]
        lead = (f"{a} and {b} clearly differ on {len(apart)} of {len(rows)} forces. The widest gap is "
                f"{top['label'].lower()}: in weeks when {top['phrase']}, {a} typically moved "
                f"{fmt_pct(top['a']['impact'])} and {b} {fmt_pct(top['b']['impact'])}.")
    else:
        lead = (f"On none of the {len(rows)} forces measured do {a} and {b} differ by more than the "
                "noise in the readings: their 90% ranges overlap every time.")

    def who(s: dict) -> str:
        n = s.get("name") or ""
        return f'<a href="/exposure/{escape(s["ticker"])}">{escape(s["ticker"])}</a>' + (
            f'<span class="shock">{escape(n)}</span>' if n and n != s["ticker"] else "")

    trs = "".join(
        f'<tr{" class=cp-apart" if r["apart"] else ""}><th scope="row"><a href="/forces/{r["key"]}">'
        f'{escape(r["label"])}</a><span class="shock">In weeks when {escape(r["phrase"])}</span>'
        + ('<span class="cp-mark">Clear difference</span>' if r["apart"] else "") + '</th>'
        f'{_cell(r["a"])}{_cell(r["b"])}</tr>' for r in rows)
    newest = max(str(sa.get("as_of") or "")[:10], str(sb.get("as_of") or "")[:10])
    body = (
        head + f'<p class="meta">{escape(a)} vs {escape(b)}'
        + (f' · data through {_date(newest)}' if newest else "") + '</p>'
        + _form(a, b, tickers)
        + f'<p class="lead">{escape(lead)}</p>'
        f'<div class="card cp-tab" tabindex="0" role="region" aria-label="{escape(a)} and {escape(b)}, force by force">'
        f'<table><thead><tr><th scope="col">Economic force</th><th scope="col">{who(sa)}</th>'
        f'<th scope="col">{who(sb)}</th></tr></thead><tbody>{trs}</tbody></table>'
        '<div class="foot">Each figure is the stock&#39;s typical move in a week when the force moved by '
        'the stated amount, after accounting for the stock market, with its 90% range beneath. Grey '
        'figures could not be told apart from zero. A row is marked a clear difference only when the '
        'two 90% ranges do not overlap.</div></div>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Relationships '
        'change, and nothing here is a recommendation to buy, sell or hold any security.</p>'
        '<div class="actions">'
        f'<a class="btn btn-primary" href="{escape(app_url)}/">Measure a whole portfolio</a>'
        '<a class="btn btn-secondary" href="/explore">What if? Move a force</a></div>')
    return _shell(f"{a} vs {b}: exposure to economic forces", lead[:300], canonical, ld, body,
                  app_url, robots="noindex, follow")
