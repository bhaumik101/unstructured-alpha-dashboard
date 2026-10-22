# utils/tools_page.py
# Unstructured Alpha — every free tool on one page
#
# The public site grew one tool at a time; this is the one place that lists
# them all with what each answers, so the landing page and the site header
# have somewhere to send "what else is here?".

from __future__ import annotations

from html import escape
from typing import Iterable

from utils.exposure_pages import _shell, tool_header_html

from utils.force_pages import ALL_FORCES

# (href, title, what it answers, group). The groups are the page's sections.
_TOOLS = (
    ("/exposure", "Stocks", "Every stock on record against rates, inflation, the dollar, oil and credit. "
     "Sort by any force, filter by sector or by what held up.", "look"),
    ("/sectors", "Sectors", "A heatmap of how each S&P 500 sector has moved with each force. Pick "
     "a cell to see the stocks behind it.", "look"),
    ("/forces", "Economic forces", f"{len(ALL_FORCES)} forces, from oil and gold to the yen and bitcoin, "
     "and every stock on record laid out on each.", "look"),
    ("/heatmap", "Market heatmap", "Every stock as a tile in its sector, coloured by how it moved with "
     "the force you pick.", "look"),
    ("/map", "Stock map", "Every stock placed on two forces at once: rates against oil, the dollar "
     "against credit, any pair. Light up a sector, find a ticker.", "look"),
    ("/explore", "What if?", "Pick a force, drag the size of the move, and see which stocks rose and "
     "fell most in weeks like it.", "try"),
    ("/scenario", "Build a scenario", "Move rates, inflation, the dollar, oil and credit at once, or pick "
     "a scenario like an inflation scare.", "try"),
    ("/compare", "Compare two stocks", "Two stocks on one scale, force by force, and where they clearly "
     "differ.", "try"),
    ("/mylist", "My list", "Save stocks as you browse, see them side by side, and measure them as one "
     "portfolio. Kept in your browser.", "try"),
    ("/quiz", "Daily quiz", "Ten questions a day: when a force moved, did a stock rise, fall, or show "
     "no clear link?", "play"),
    ("/guess", "Whose fingerprint?", "Five rounds a day: see a mystery stock's profile against the "
     "economy and pick it out of four.", "play"),
    ("/learn", "How to read these pages", "The typical move, the 90% range and the evidence labels, "
     "with a playground to try them.", "learn"),
    ("/changes", "What changed this week", "Readings that started or stopped holding up in the latest "
     "week, and the largest shifts.", "learn"),
    ("/evidence", "Track record", "How readings measured this way held up over the following year, out "
     "of sample, published whatever it shows.", "learn"),
)
TOOLS = tuple((h, t, d) for h, t, d, _ in _TOOLS)
GROUPS = (("look", "Look it up", "Every reading on record, by stock, by sector, by force."),
          ("try", "Try a move", "Ask what happened in weeks like the one you have in mind."),
          ("play", "Play", "Test what you think you know. New rounds every day."),
          ("learn", "Learn and check", "How the numbers are made, and how well they have held up."))

# One small line icon per tool, drawn in currentColor.
_ICON = {
    "/exposure": '<path d="M4 6h16M4 12h16M4 18h10"/>',
    "/sectors": '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/>'
                '<rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>',
    "/forces": '<path d="M3 17l5-6 4 4 8-9"/>',
    "/heatmap": '<rect x="3" y="4" width="8" height="7" rx="1"/><rect x="13" y="4" width="8" height="4" rx="1"/>'
                '<rect x="13" y="10" width="8" height="10" rx="1"/><rect x="3" y="13" width="8" height="7" rx="1"/>',
    "/map": '<circle cx="8" cy="15" r="2"/><circle cx="15" cy="8" r="2"/><circle cx="17" cy="16" r="2"/><path d="M4 4v16h16"/>',
    "/explore": '<path d="M4 12h16"/><circle cx="14" cy="12" r="3"/>',
    "/scenario": '<path d="M5 6h14M5 12h14M5 18h14"/><circle cx="9" cy="6" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="11" cy="18" r="2"/>',
    "/compare": '<path d="M8 4v16M16 4v16"/><circle cx="8" cy="9" r="2"/><circle cx="16" cy="15" r="2"/>',
    "/mylist": '<path d="M12 4l2.4 5 5.6.8-4 3.9.9 5.5L12 16.6 7.1 19.2l.9-5.5-4-3.9 5.6-.8z"/>',
    "/quiz": '<circle cx="12" cy="12" r="8"/><path d="M10 9.5a2 2 0 1 1 3 1.7c-.7.4-1 1-1 1.8M12 16h.01"/>',
    "/guess": '<path d="M7 11a5 5 0 0 1 10 0v2a5 5 0 0 1-10 0z"/><path d="M10 11v2M14 11v2"/>',
    "/learn": '<path d="M4 6l8-3 8 3-8 3z"/><path d="M8 8v5c0 1.5 2 3 4 3s4-1.5 4-3V8"/>',
    "/changes": '<path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"/><path d="M18 3v4h-4M6 21v-4h4"/>',
    "/evidence": '<path d="M5 13l4 4L19 7"/>',
}


def _icon(href: str) -> str:
    return ('<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_ICON.get(href, "")}</svg>')


def tools_page_html(stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    n = len(list(stocks))
    canonical = f"{base_url}/tools"
    title = "Free tools: how stocks move with rates, oil, the dollar and more"
    desc = (f"Free, no sign-up: {n:,} U.S. stocks measured weekly against economic forces, with "
            "tools to explore, compare and test what you think you know." if n else
            "Free, no sign-up tools for how U.S. stocks move with economic forces.")
    sections = "".join(
        f'<section class="tg"><h2>{escape(gl)}</h2><p class="small">{escape(gd)}</p><ul class="tools">'
        + "".join(f'<li><a href="{h}"><span class="ti">{_icon(h)}</span><b>{escape(t)}</b>'
                  f'<span class="td">{escape(d)}</span></a></li>' for h, t, d, g2 in _TOOLS if g2 == g)
        + '</ul></section>' for g, gl, gd in GROUPS)
    body = (
        '<style>.tools{list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(205px,1fr));gap:12px;margin:8px 0 0;padding:0}'
        '.tools a{display:grid;grid-template-columns:40px 1fr;grid-template-rows:40px auto;gap:8px 12px;align-items:center;height:100%;padding:16px;border:1px solid var(--line);'
        'border-radius:12px;background:var(--surface);color:var(--ink);text-decoration:none;transition:border-color .15s,transform .15s}'
        '.tools a:hover{border-color:var(--accent);transform:translateY(-1px)}'
        '.ti{display:grid;place-items:center;width:40px;height:40px;border-radius:10px;background:var(--subtle);color:var(--accent)}'
        '.td{grid-column:1/-1;color:var(--ink2);align-self:start}.tg{margin-top:22px}.tg h2{margin-bottom:2px}'
        '@media (prefers-reduced-motion:reduce){.tools a{transition:none}.tools a:hover{transform:none}}</style>'
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Free tools</nav>'
        + tool_header_html("Free tools", [f"{len(_TOOLS)} tools", f"{n:,} U.S. stocks",
                                          f"{len(ALL_FORCES)} economic forces", "No account needed"],
                           escape(desc))
        + f'{sections}'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here is a '
        'recommendation to buy, sell or hold any security.</p>')
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title,
          "description": desc, "url": canonical}
    return _shell(title, desc, canonical, ld, body, app_url)
