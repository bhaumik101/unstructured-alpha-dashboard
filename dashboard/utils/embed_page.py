# utils/embed_page.py
# Unstructured Alpha — a small card any site can embed for one stock
#
# One line of HTML (an iframe) puts a stock's five core readings on someone
# else's page, with a link back to the full page. The card is its own complete
# document: no site header, no scripts, its own light and dark styles, so it
# sits cleanly inside a blog post or a newsletter archive.
#
# RULES
#   * The same numbers and the same honesty as the stock page: held-up figures
#     bold, the rest grey, a dash where not measured, the date, and "not a
#     forecast" on the card itself -- an embed must not lose the caveat.
#   * noindex, with the stock page as canonical: the card must never compete
#     with the page it summarises in search.

from __future__ import annotations

from html import escape
from typing import Optional

from utils import exposure as ex
from utils.exposure_pages import STANDS_UP, _date, fmt_pct

EMBED_HEIGHT = 360

_CSS = """<style>
:root{--bg:#fff;--ink:#13213a;--ink3:#5b6780;--line:#dfe5ee;--accent:#1f5fae;--track:#eef2f7;--up:#2f6fbd;--down:#b5651d}
@media (prefers-color-scheme:dark){:root{--bg:#121d2f;--ink:#e8edf5;--ink3:#8f9bb1;--line:#243349;--accent:#8cb8f2;
  --track:#16233a;--up:#5a8fd4;--down:#c9822f}}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.c{border:1px solid var(--line);border-radius:12px;padding:14px 16px;max-width:480px}
.h{display:flex;justify-content:space-between;gap:10px;align-items:baseline;margin-bottom:8px}
.t{font-weight:750;font-size:18px;margin:0}.n{color:var(--ink3);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
table{width:100%;border-collapse:collapse}
td{padding:5px 0;border-top:1px solid var(--line);font-size:13px;vertical-align:middle}
td.v{text-align:right;font-variant-numeric:tabular-nums;width:72px}
td.b{width:38%;padding:0 10px}
.w{color:var(--ink3)}
.tr{display:block;position:relative;height:8px;background:var(--track);border-radius:4px}
.tr::after{content:"";position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--ink3)}
.br{position:absolute;top:0;bottom:0;border-radius:4px}.u{background:var(--up)}.d{background:var(--down)}.f{opacity:.35}
@media (max-width:320px){td.b{display:none}.c{padding:12px}}
.ft{margin-top:8px;font-size:12px;color:var(--ink3);display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
a{color:var(--accent)}
</style>"""


def embed_code(symbol: str, base_url: str) -> str:
    """The one line a site owner pastes."""
    return (f'<iframe src="{base_url}/embed/{symbol}" width="100%" height="{EMBED_HEIGHT}" '
            f'style="border:0;max-width:480px" loading="lazy" '
            f'title="{symbol}: exposure to economic forces, from Unstructured Alpha"></iframe>')


def embed_card_html(symbol: str, rec: dict, base_url: str) -> str:
    exps = rec.get("exposures") or {}
    name = rec.get("name") or ""
    shown = [f for f in ex.FACTORS]
    scale = max((abs(exps[f.key]["impact"]) for f in shown if f.key in exps), default=0.0)
    rows = []
    for f in shown:
        e: Optional[dict] = exps.get(f.key)
        if not e:
            rows.append(f'<tr><td>{escape(f.label)}</td><td class="b"></td><td class="v w">—</td></tr>')
            continue
        strong = e.get("evidence") in STANDS_UP
        w = 50 * min(1.0, abs(e["impact"]) / scale) if scale > 0 else 0
        side = "left:50%" if e["impact"] >= 0 else "right:50%"
        cls = ("u" if e["impact"] >= 0 else "d") + ("" if strong else " f")
        v = fmt_pct(e["impact"])
        rows.append(
            f'<tr><td title="In weeks when {escape(f.shock_phrase)}">{escape(f.label)}</td>'
            f'<td class="b"><span class="tr" aria-hidden="true"><span class="br {cls}" '
            f'style="{side};width:{w:.1f}%"></span></span></td>'
            f'<td class="v">{"<b>" + v + "</b>" if strong else f"<span class=w>{v}</span>"}</td></tr>')
    page = f"{base_url}/exposure/{symbol}"
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(symbol)}: economic exposure</title>'
        '<meta name="robots" content="noindex, follow">'
        f'<link rel="canonical" href="{escape(page)}">{_CSS}</head><body>'
        '<main class="c">'
        f'<div class="h"><h1 class="t">{escape(symbol)}</h1>'
        + (f'<span class="n">{escape(name)}</span>' if name and name != symbol else "") + '</div>'
        f'<table aria-label="{escape(symbol)}: typical weekly move with each economic force">'
        f'{"".join(rows)}</table>'
        '<div class="ft"><span>Typical weekly move beyond the market; bold held up, grey did not. '
        f'Data through {_date(rec["as_of"])}. The past, not a forecast.</span>'
        f'<a href="{escape(page)}" target="_blank" rel="noopener">Full exposure on Unstructured Alpha →</a>'
        '</div></main></body></html>')


def embed_box_html(symbol: str, base_url: str) -> str:
    """The collapsible "Embed this card" box on the stock page, with a copy button."""
    code = embed_code(symbol, base_url)
    return (
        '<details class="embed"><summary>Embed this card on your site</summary>'
        f'<p class="small">Paste this where you want {escape(symbol)}&#39;s card to appear. It updates '
        'when the stock is re-measured each week.</p>'
        f'<textarea readonly rows="3" aria-label="Embed code for {escape(symbol)}" '
        f'style="width:100%;font:13px ui-monospace,monospace">{escape(code)}</textarea>'
        '<button type="button" class="btn btn-secondary" id="embed-copy">Copy the code</button>'
        '<span class="small" id="embed-said" aria-live="polite"></span>'
        '<script>(function(){var b=document.getElementById("embed-copy"),t=b.previousElementSibling,'
        's=document.getElementById("embed-said");b.addEventListener("click",function(){t.select();'
        'function ok(){s.textContent=" Copied.";}'
        'if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t.value).then(ok,function(){'
        's.textContent=" Selected: press Ctrl+C or Cmd+C.";});}else{s.textContent=" Selected: press Ctrl+C or Cmd+C.";}});})();'
        '</script></details>')
