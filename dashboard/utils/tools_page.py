# utils/tools_page.py
# Unstructured Alpha — every free tool on one page
#
# The public site grew one tool at a time; this is the one place that lists
# them all with what each answers, so the landing page and the site header
# have somewhere to send "what else is here?".

from __future__ import annotations

from html import escape
from typing import Iterable

from utils.exposure_pages import _shell

TOOLS = (
    ("/exposure", "Stocks", "Every stock on record against rates, inflation, the dollar, oil and credit. "
     "Sort by any force, filter by name."),
    ("/sectors", "Sectors", "How each S&P 500 sector has moved with each force: the median move and "
     "how many stocks held up each way."),
    ("/forces", "Economic forces", "Nineteen forces, from oil and gold to the yen and bitcoin, and the "
     "stocks that moved up and down with each."),
    ("/explore", "What if?", "Pick a force, drag the size of the move, and see which stocks rose and "
     "fell most in weeks like it. Follow your own tickers too."),
    ("/compare", "Compare two stocks", "Two stocks side by side, force by force, and where they clearly "
     "differ."),
    ("/quiz", "Daily quiz", "Ten questions a day: when a force moved, did a stock rise, fall, or show "
     "no clear link?"),
    ("/changes", "What changed this week", "Readings that started or stopped holding up in the latest "
     "week, and the largest shifts."),
    ("/evidence", "Track record", "How readings measured this way held up over the following year, out "
     "of sample, published whatever it shows."),
)


def tools_page_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    n = len(list(stocks))
    canonical = f"{base_url}/tools"
    title = "Free tools: how stocks move with rates, oil, the dollar and more"
    desc = (f"Free, no sign-up: {n:,} U.S. stocks measured weekly against economic forces, with "
            "tools to explore, compare and test what you think you know." if n else
            "Free, no sign-up tools for how U.S. stocks move with economic forces.")
    cards = "".join(
        f'<li><a href="{h}"><b>{escape(t)}</b><span>{escape(d)}</span></a></li>' for h, t, d in TOOLS)
    body = (
        '<style>.tools{list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}'
        '.tools a{display:block;height:100%;padding:16px;border:1px solid var(--line);border-radius:12px;'
        'background:var(--surface);color:var(--ink);text-decoration:none}'
        '.tools a:hover{border-color:var(--accent)}.tools b{display:block;font-size:1.05rem;margin-bottom:4px}'
        '.tools span{color:var(--ink2);font-size:.92rem}</style>'
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Free tools</nav>'
        '<h1>Free tools</h1>'
        f'<p class="lead">{escape(desc)}</p>'
        f'<ul class="tools">{cards}</ul>'
        '<h2>For your own portfolio</h2>'
        '<p class="lead">Everything above reads one stock or one force at a time. The app measures a '
        'whole portfolio the same way, stress-tests it, and explains its past returns.</p>'
        f'<div class="actions"><a class="btn btn-primary" href="{escape(app_url)}/">Measure a portfolio</a>'
        f'<a class="btn btn-secondary" href="{escape(app_url)}/methodology">Methodology</a></div>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here is a '
        'recommendation to buy, sell or hold any security.</p>')
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title,
          "description": desc, "url": canonical}
    return _shell(title, desc, canonical, ld, body, app_url)
