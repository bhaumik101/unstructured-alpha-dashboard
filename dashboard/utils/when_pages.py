# utils/when_pages.py
# Unstructured Alpha — "Which stocks went up when ... ?" — measured, not predicted
#
# People search the question in this shape: "stocks that go up when interest
# rates fall", "what stocks benefit when oil rises". What ranks for it today is
# forecast commentary ("3 stocks poised to win"). This site holds the measured
# answer: three years of weekly returns, the market's own move removed, a 90%
# range and an evidence label on every figure. One page per force and
# direction, titled the way the question is asked, answered on arrival -- no
# click needed (the Nov 2026 data showed visitors leave without using tools).
#
# RULES
#   * Readings are linear: the move "when rates fell" is the measured move per
#     standard rise with its sign turned over, and the page says so. Nothing is
#     re-estimated or invented for the falling case.
#   * "Went up" / "went down" counts only readings that held up (STANDS_UP);
#     the rest are counted as "no clear link", never ranked.
#   * Past tense, always. No "benefit", "poised", "buy": a description of what
#     happened, not a forecast or advice.
#   * Substance guard: a page with fewer than MIN_HELD stocks that held up
#     either way is noindex and left out of the sitemap -- thin templated pages
#     get dropped by search engines and do the site no good.

from __future__ import annotations

import math

from html import escape
from typing import Dict, Iterable, List, Optional, Tuple

from utils import exposure as ex
from utils.exposure_pages import STANDS_UP, _chip, _date, _shell, data_week, fmt_pct, more_html, tool_header_html
from utils.force_pages import FORCE_BY_KEY, method_notice

MIN_HELD = 8
TOP_UP, TOP_DOWN = 25, 12
SHOW_UP, SHOW_DOWN = 10, 5      # shown at once; the rest of the top list folds open

# key -> (noun as people say it, rise verb, fall verb, rise slug, fall slug)
SCENARIOS: Dict[str, Tuple[str, str, str, str, str]] = {
    "rates": ("interest rates", "rose", "fell", "rates-rise", "rates-fall"),
    "inflation": ("inflation expectations", "rose", "fell", "inflation-rises", "inflation-falls"),
    "dollar": ("the dollar", "rose", "fell", "dollar-rises", "dollar-falls"),
    "oil": ("oil prices", "rose", "fell", "oil-rises", "oil-falls"),
    "credit": ("credit spreads", "widened", "narrowed", "credit-spreads-widen", "credit-spreads-narrow"),
    "short_rates": ("short-term rates", "rose", "fell", "short-rates-rise", "short-rates-fall"),
    "mortgage": ("mortgage rates", "rose", "fell", "mortgage-rates-rise", "mortgage-rates-fall"),
    "volatility": ("market volatility", "rose", "fell", "volatility-rises", "volatility-falls"),
    "gold": ("gold", "rose", "fell", "gold-rises", "gold-falls"),
    "copper": ("copper", "rose", "fell", "copper-rises", "copper-falls"),
    "natgas": ("natural gas prices", "rose", "fell", "natural-gas-rises", "natural-gas-falls"),
    "bitcoin": ("bitcoin", "rose", "fell", "bitcoin-rises", "bitcoin-falls"),
    "euro": ("the euro", "rose", "fell", "euro-rises", "euro-falls"),
    "yen": ("the yen", "rose", "fell", "yen-rises", "yen-falls"),
}
# slug -> (force key, +1 for the force rising, -1 for falling)
BY_SLUG: Dict[str, Tuple[str, int]] = {}
for _k, (_n, _rv, _fv, _rs, _fs) in SCENARIOS.items():
    BY_SLUG[_rs] = (_k, 1)
    BY_SLUG[_fs] = (_k, -1)


def shock_phrase(key: str, sign: int) -> str:
    """The standard move, in the direction of the page."""
    p = FORCE_BY_KEY[key].shock_phrase
    return p if sign > 0 else p.replace(" rose ", " fell ").replace(" widened ", " narrowed ").replace(" beat ", " trailed ")


def title_for(key: str, sign: int) -> str:
    noun, rv, fv, *_ = SCENARIOS[key]
    return f"Stocks that went up when {noun} {rv if sign > 0 else fv}"


def slug_for(key: str, sign: int) -> str:
    return SCENARIOS[key][3 if sign > 0 else 4]


def scenario(key: str, sign: int, stocks: Iterable[dict]) -> dict:
    """Every stock measured on the force, with its move in this direction:
    went up / went down (held up) and how many showed no clear link."""
    from utils.funds import is_fund
    from utils.sector_pages import sector_by_ticker
    secs = sector_by_ticker()
    up, down, dates, measured = [], [], [], 0
    sectors: Dict[str, List[float]] = {}
    for s in stocks:
        e = (s.get("exposures") or {}).get(key)
        if not e:
            continue
        measured += 1
        dates.append(str(e.get("as_of") or s.get("as_of") or "")[:10])
        move, low, high = sign * e["impact"], sign * e["low"], sign * e["high"]
        if low > high:
            low, high = high, low
        row = {"ticker": s["ticker"], "name": s.get("name") or "", "move": move, "low": low, "high": high,
               "evidence": e.get("evidence"),
               "sector": secs.get(s["ticker"]) or ("ETF" if is_fund(s["ticker"]) else "")}
        held = e.get("evidence") in STANDS_UP
        if held:
            (up if move > 0 else down).append(row)
        if row["sector"] and row["sector"] != "ETF":          # the sector table is companies only
            sectors.setdefault(row["sector"], []).append(move)
    up.sort(key=lambda r: (-r["move"], r["ticker"]))
    down.sort(key=lambda r: (r["move"], r["ticker"]))
    by_sector = []
    for name, moves in sectors.items():
        rows = [r for r in up + down if r["sector"] == name]
        n_up = sum(1 for r in rows if r["move"] > 0)
        moves = sorted(moves)
        median = moves[len(moves) // 2] if len(moves) % 2 else (moves[len(moves) // 2 - 1] + moves[len(moves) // 2]) / 2
        by_sector.append({"sector": name, "measured": len(moves), "up": n_up, "down": len(rows) - n_up, "median": median})
    by_sector.sort(key=lambda r: (-r["median"], r["sector"]))
    return {"key": key, "sign": sign, "measured": measured, "up": up, "down": down,
            "none": measured - len(up) - len(down), "sectors": by_sector, "as_of": data_week(dates)}


def split_html(sc: dict, phrase: str) -> str:
    """Every stock measured, in one strip: went up (held up), no clear link,
    went down (held up). The middle is usually the biggest, and it is drawn
    as such: that is the most common honest answer."""
    n_up, n_down, n_none, total = len(sc["up"]), len(sc["down"]), sc["none"], sc["measured"]
    if total <= 0:
        return ""
    seg = []
    for cls, n, label in (("wp-up", n_up, "went up"), ("wp-none", n_none, "no clear link"), ("wp-down", n_down, "went down")):
        if n:
            seg.append(f'<span class="{cls}" style="flex-grow:{n}" title="{n:,} {label}"><b>{n:,}</b> <i>{label}</i></span>')
    return ('<figure class="wp-split" aria-label="'
            + escape(f"Of {total:,} stocks measured: {n_up:,} went up, {n_none:,} showed no clear link, "
                     f"{n_down:,} went down, in weeks when {phrase}.") + '">'
            f'<div class="wp-bar" aria-hidden="true">{"".join(seg)}</div>'
            '<div class="wp-key" aria-hidden="true"><span class="k-up">went up</span><span class="k-none">no clear link</span>'
            '<span class="k-down">went down</span></div>'
            f'<figcaption>All {total:,} stocks and ETFs measured. Up and down count only readings that held up.</figcaption>'
            '</figure>')


def ranked_svg(sc: dict, n_up: int = 10, n_down: int = 5) -> str:
    """The largest moves either way on one shared axis: bar from zero to the
    typical move, the 90% range as a capped line, solid for Clear and lighter
    for Tentative. The same figures as the tables below."""
    rows = sc["up"][:n_up] + sc["down"][:n_down][::-1]
    if len(rows) < 3:
        return ""
    span = max(max(abs(r["low"]), abs(r["high"])) for r in rows)
    span = max(0.5, math.ceil(span * 2) / 2)
    W, ROW, TOP, LX, RX = 760, 30, 34, 150, 660
    split_gap = 18 if sc["up"][:n_up] and sc["down"][:n_down] else 0
    H = TOP + ROW * len(rows) + split_gap + 26
    mid = (LX + RX) / 2

    def X(v):
        return mid + max(-1.0, min(1.0, v / span)) * (RX - LX) / 2
    out, n_first = [], len(sc["up"][:n_up])
    for i, r in enumerate(rows):
        y = TOP + i * ROW + (split_gap if i >= n_first else 0)
        x0, x1 = sorted((mid, X(r["move"])))
        tone = "wp-clear" if r["evidence"] == "clear" else "wp-tent"
        title = (f'{r["ticker"]}{" · " + r["name"] if r["name"] else ""}: {fmt_pct(r["move"])} '
                 f'(90% range {fmt_pct(r["low"])} to {fmt_pct(r["high"])}), {r["evidence"]}')
        out.append(
            f'<a href="/exposure/{escape(r["ticker"])}" aria-label="{escape(title)}"><g class="wp-row"><title>{escape(title)}</title>'
            f'<rect x="0" y="{y - 4}" width="{W}" height="{ROW}" class="wp-hit"/>'
            f'<text x="{LX - 14}" y="{y + 15}" text-anchor="end" class="wp-t">{escape(r["ticker"])}</text>'
            f'<line x1="{X(r["low"]):.1f}" y1="{y + 11}" x2="{X(r["high"]):.1f}" y2="{y + 11}" class="wp-ci"/>'
            f'<line x1="{X(r["low"]):.1f}" y1="{y + 5}" x2="{X(r["low"]):.1f}" y2="{y + 17}" class="wp-ci"/>'
            f'<line x1="{X(r["high"]):.1f}" y1="{y + 5}" x2="{X(r["high"]):.1f}" y2="{y + 17}" class="wp-ci"/>'
            f'<rect x="{x0:.1f}" y="{y + 4}" width="{max(1.5, x1 - x0):.1f}" height="14" rx="3" class="{tone}"/>'
            f'<text x="{W - 6}" y="{y + 15}" text-anchor="end" class="wp-v">{fmt_pct(r["move"])}</text>'
            '</g></a>')
    axis_y = H - 14
    return (
        f'<figure class="card wp-rank"><svg viewBox="0 0 {W} {H}" role="group" aria-label="'
        + escape("Largest moves: " + "; ".join(f'{r["ticker"]} {fmt_pct(r["move"])}' for r in rows)) + '">'
        f'<text x="{LX}" y="16" class="wp-h">Largest moves up</text>'
        + (f'<text x="{LX}" y="{TOP + n_first * ROW + split_gap - 8}" class="wp-h">Largest moves down</text>'
           if split_gap else "")
        + f'<line x1="{mid}" y1="{TOP - 8}" x2="{mid}" y2="{axis_y - 8}" class="wp-zero"/>'
        + "".join(out)
        + f'<text x="{LX}" y="{axis_y + 6}" class="wp-ax">{fmt_pct(-span)}</text>'
        f'<text x="{mid}" y="{axis_y + 6}" text-anchor="middle" class="wp-ax">0</text>'
        f'<text x="{RX}" y="{axis_y + 6}" text-anchor="end" class="wp-ax">{fmt_pct(span)}</text>'
        '</svg><figcaption class="foot">Bar: the typical weekly move beyond the market; line: its 90% range; '
        'solid Clear, lighter Tentative. One shared scale. Click a name to open it.</figcaption></figure>')


_WP_CSS = """<style>
.wp-split{margin:22px 0 8px}
.wp-bar{display:flex;gap:3px;height:44px;border-radius:10px;overflow:hidden}
.wp-bar span{display:flex;align-items:center;gap:6px;padding:0 14px;min-width:0;white-space:nowrap;overflow:hidden;
  font-size:var(--fs-sm);color:var(--ink2)}
.wp-bar b{font-size:var(--fs-lead);color:var(--ink);font-variant-numeric:tabular-nums}
.wp-up{background:color-mix(in srgb,var(--accent) 28%,var(--surface))}
.wp-none{background:var(--subtle)}
.wp-down{background:color-mix(in srgb,var(--ink3) 30%,var(--surface));justify-content:flex-end}
.wp-split figcaption{margin-top:8px;font-size:var(--fs-xs);color:var(--ink3)}
.wp-rank{padding:16px 16px 0;margin:18px 0}
.wp-rank svg{width:100%;height:auto;display:block}
.wp-h{fill:var(--ink3);font-size:var(--fs-xs);font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.wp-t{fill:var(--accent);font:700 var(--fs-sm) ui-monospace,"SF Mono",Menlo,monospace}
.wp-v{fill:var(--ink);font-size:var(--fs-sm);font-weight:700;font-variant-numeric:tabular-nums}
.wp-ci{stroke:var(--ink3);stroke-width:1.3}
.wp-clear{fill:var(--ink2)}.wp-tent{fill:var(--ink3);opacity:.55}
.wp-zero{stroke:var(--ink3);stroke-dasharray:3 4;opacity:.7}
.wp-ax{fill:var(--ink3);font-size:var(--fs-xs);font-family:ui-monospace,"SF Mono",Menlo,monospace}
.wp-hit{fill:transparent}.wp-row:hover .wp-hit{fill:var(--subtle)}
.wp-rank .foot{margin:10px -16px 0}
.wp-bar i{font-style:normal}
.wp-key{display:none}
@media (max-width:640px){
  .wp-bar{height:40px}.wp-bar span{padding:0 10px}.wp-bar i{display:none}
  .wp-key{display:flex;flex-wrap:wrap;gap:4px 14px;margin-top:8px;font-size:var(--fs-xs);color:var(--ink2)}
  .wp-key span::before{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
  .wp-key .k-up::before{background:color-mix(in srgb,var(--accent) 28%,var(--surface))}
  .wp-key .k-none::before{background:var(--subtle)}
  .wp-key .k-down::before{background:color-mix(in srgb,var(--ink3) 30%,var(--surface))}
  .wp-rank{padding:12px 8px 0}.wp-rank .foot{margin:10px -8px 0}
  .wp-rank .wp-t,.wp-rank .wp-v{font-size:26px}.wp-rank .wp-h,.wp-rank .wp-ax{font-size:20px}
}
</style>"""


def substantive(sc: dict) -> bool:
    from utils.force_pages import method_notice
    return len(sc["up"]) + len(sc["down"]) >= MIN_HELD and not method_notice(sc["key"], sc["as_of"])


def _table(rows: List[dict], label: str) -> str:
    body = "".join(
        f'<tr><th scope="row"><a href="/exposure/{escape(r["ticker"])}">{escape(r["ticker"])}</a>'
        + (f'<span class="shock">{escape(r["name"])}</span>' if r["name"] else "")
        + f'</th><td><b>{fmt_pct(r["move"])}</b></td><td>{fmt_pct(r["low"])} to {fmt_pct(r["high"])}</td>'
        f'<td>{_chip(r["evidence"])}</td><td class="small">{escape(r["sector"])}</td></tr>'
        for r in rows)
    return (f'<div class="card" tabindex="0" role="region" aria-label="{escape(label)}"><table><thead><tr>'
            '<th scope="col">Stock</th><th scope="col">Typical weekly move</th><th scope="col">90% range</th>'
            f'<th scope="col">Evidence</th><th scope="col">Sector</th></tr></thead><tbody>{body}</tbody></table></div>')


def _folded_table(rows: List[dict], label: str, show: int, total: int) -> str:
    """The first `show` rows at once; the rest of the list one click away."""
    html = _table(rows[:show], label)
    if len(rows) > show:
        rest = len(rows) - show
        html += more_html("", f"Show {rest} more", "", _table(rows[show:], f"{label}, continued")
                          + (f'<p class="small">Showing the {len(rows)} largest of {total}.</p>'
                             if total > len(rows) else ""), quiet=True)
    return html


def _sector_table(sc: dict) -> str:
    rows = [r for r in sc["sectors"] if r["measured"] >= 5]
    if not rows:
        return ""
    body = "".join(
        f'<tr><th scope="row">{escape(r["sector"])}</th><td>{r["up"]}↑ {r["down"]}↓ held up, of {r["measured"]}</td>'
        f'<td><b>{fmt_pct(r["median"])}</b></td></tr>' for r in rows)
    # Same pick as the lead sentence, so the page never names two "top" sectors.
    best = next((r for r in rows if r["up"]), None)
    hint = f"{len(rows)} sectors" + (f" · most often up: {escape(best['sector'])}" if best else "")
    return more_html("sectors", "By sector", hint, (
            '<div class="card" tabindex="0" role="region" aria-label="By sector"><table><thead><tr>'
            '<th scope="col">Sector</th><th scope="col">Readings that held up</th><th scope="col">Median move</th>'
            f'</tr></thead><tbody>{body}</tbody></table></div>'
            '<p class="small">Median of every stock measured in the sector, held up or not.</p>'))


def when_page_html(slug: str, stocks: Iterable[dict], base_url: str, app_url: str) -> Optional[str]:
    if slug not in BY_SLUG:
        return None
    key, sign = BY_SLUG[slug]
    f = FORCE_BY_KEY[key]
    stocks = list(stocks)
    sc = scenario(key, sign, stocks)
    noun, rv, fv, *_ = SCENARIOS[key]
    verb = rv if sign > 0 else fv
    other = slug_for(key, -sign)
    title = title_for(key, sign)
    phrase = shock_phrase(key, sign)
    canonical = f"{base_url}/when/{slug}"
    n_up, n_down = len(sc["up"]), len(sc["down"])
    desc = (f"Measured, not predicted: of {sc['measured']:,} U.S. stocks and ETFs, {n_up} went up and {n_down} went "
            f"down beyond the market in weeks when {noun} {verb}, in a way that held up. Three years of weekly "
            "returns, with a 90% range on every figure.")
    top_sector = next((r for r in sc["sectors"] if r["measured"] >= 5 and r["up"]), None)
    lead = (f"Of {sc['measured']:,} stocks and ETFs measured, <b>{n_up}</b> went up beyond the market in weeks when "
            f"{escape(phrase)}, in a way that held up, and <b>{n_down}</b> went down. The other {sc['none']:,} "
            "showed no link that could be told apart from noise &mdash; the most common answer."
            + (f" The sector that most often went up: <b>{escape(top_sector['sector'])}</b> "
               f"({top_sector['up']} of {top_sector['measured']}, median {fmt_pct(top_sector['median'])})."
               if top_sector else ""))
    body = (
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › <a href="/when">What moved when</a> › '
        f'{escape(noun.capitalize())} {escape(verb)}</nav>'
        + tool_header_html(title, ["Measured, not predicted", f"{sc['measured']:,} stocks and ETFs",
                                   f"Data through {_date(sc['as_of'])}" if sc["as_of"] else "",
                                   "Market move removed first"],
                           f"In weeks when {escape(phrase)}: what each stock typically did, beyond the stock "
                           "market&#39;s own move, over three years of weekly returns.")
        + method_notice(key, sc["as_of"])
        + f'<p class="lead">{lead}</p>'
        + _WP_CSS + split_html(sc, phrase) + ranked_svg(sc)
        + (f'<h2>Went up when {escape(noun)} {escape(verb)} ({n_up})</h2>' + _folded_table(sc["up"][:TOP_UP], "Went up", SHOW_UP, n_up)
           if n_up else f'<h2>Went up when {escape(noun)} {escape(verb)}</h2><p>None held up.</p>')
        + (f'<h2>Went down when {escape(noun)} {escape(verb)} ({n_down})</h2>' + _folded_table(sc["down"][:TOP_DOWN], "Went down", SHOW_DOWN, n_down)
           if n_down else "")
        + _sector_table(sc)
        + '<div class="actions">'
        f'<a class="btn btn-primary" href="/xray">How did your portfolio move? X-ray it</a>'
        f'<a class="btn btn-secondary" href="/when/{other}">When {escape(noun)} {escape(fv if sign > 0 else rv)}</a>'
        f'<a class="btn btn-secondary" href="/forces/{key}">Every stock on {escape(ex.lower_label(f.label))}</a></div>'
        + more_html("method", "How this is measured", "", (
        f'<p>Each figure is a stock&#39;s typical same-week move when {escape(phrase.replace(" fell ", " moved ").replace(" rose ", " moved "))} '
        'by that standard amount, after removing the stock market&#39;s own move, from three years of weekly returns. '
        'The readings are linear: the move in a week when it fell is the measured move for a rise with its sign turned '
        'over. "Held up" means the 90% range excludes zero (Tentative) or the figure clears a stricter bar (Clear). '
        '<a href="/learn">How to read these figures</a>.</p>'), quiet=True)
        + '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Relationships change; '
        '<a href="/evidence">the track record</a> shows how often readings held their direction a year later. '
        'Nothing here is a recommendation to buy, sell or hold any security.</p>')
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": title, "description": desc,
          "url": canonical, "dateModified": sc["as_of"] or None,
          "publisher": {"@type": "Organization", "name": "Unstructured Alpha"},
          "about": {"@type": "Thing", "name": f"{noun} {verb}"}}
    return _shell(f"{title}: measured, not predicted", desc, canonical, ld, body, app_url,
                  robots="" if substantive(sc) else "noindex, follow")


def when_hub_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    stocks = list(stocks)
    canonical = f"{base_url}/when"
    title = "What moved when: stocks that went up when rates, oil, the dollar or gold moved"
    desc = ("Which U.S. stocks actually went up or down when interest rates, inflation, oil, the dollar, gold or "
            "bitcoin moved -- measured from three years of weekly returns, not predicted.")
    items = []
    for key, (noun, rv, fv, rs, fs) in SCENARIOS.items():
        cells = []
        for sign, verb, slug in ((1, rv, rs), (-1, fv, fs)):
            sc = scenario(key, sign, stocks)
            cells.append(f'<a href="/when/{slug}"><b>When {escape(noun)} {escape(verb)}</b>'
                         f'<span class="small">{len(sc["up"])} went up · {len(sc["down"])} went down</span></a>')
        items.append(f'<li>{"".join(cells)}</li>')
    body = (
        '<style>.wh{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}'
        '.wh li{display:grid;grid-template-columns:1fr 1fr;gap:8px}'
        '.wh a{display:grid;gap:2px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:var(--surface);'
        'text-decoration:none;color:var(--ink);box-shadow:var(--shadow)}.wh a:hover{border-color:var(--accent)}</style>'
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › What moved when</nav>'
        + tool_header_html("What moved when", ["Measured, not predicted", f"{len(SCENARIOS) * 2} questions answered"],
                           escape(desc))
        + f'<ul class="wh">{"".join(items)}</ul>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here is a '
        'recommendation to buy, sell or hold any security.</p>')
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title, "description": desc, "url": canonical}
    return _shell(title, desc, canonical, ld, body, app_url)


def when_sitemap_urls(stocks: Iterable[dict], base_url: str) -> List[str]:
    stocks = list(stocks)
    urls = [f"  <url><loc>{base_url}/when</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>"]
    for slug, (key, sign) in BY_SLUG.items():
        sc = scenario(key, sign, stocks)
        if substantive(sc):
            urls.append(f"  <url><loc>{base_url}/when/{slug}</loc>"
                        + (f"<lastmod>{sc['as_of']}</lastmod>" if sc["as_of"] else "")
                        + "<changefreq>weekly</changefreq><priority>0.8</priority></url>")
    return urls
