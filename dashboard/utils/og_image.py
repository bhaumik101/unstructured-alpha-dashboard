# utils/og_image.py
# Unstructured Alpha — the preview image a stock page shows when it is shared
#
# A link to /exposure/XOM pasted into X, LinkedIn, Slack or a message shows a
# 1200x630 card: the ticker, the name, and the five core readings as diverging
# bars. Drawn with Pillow and its bundled font (no system fonts on the
# server), so it renders the same everywhere.
#
# RULES
#   * The same honesty as the page: held-up figures bright, the rest dimmed
#     with faint bars, "not measured" where so, the date, and "the past, not a
#     forecast" on the image itself -- a preview travels without its page.
#   * Pure function of the stored record; the route caches the bytes.

from __future__ import annotations

import io
from functools import lru_cache
from typing import Optional

from utils import exposure as ex
from utils.exposure_pages import STANDS_UP, _date, fmt_pct

W, H = 1200, 630
BG, INK, DIM, LINE, BRAND = "#0d223b", "#e8edf5", "#7f8ca3", "#24405f", "#ffc24b"
UP, DOWN = "#5a8fd4", "#d0893a"
UP_FAINT, DOWN_FAINT = "#2b4466", "#4a3a2b"


@lru_cache(maxsize=8)
def _font(size: int):
    from PIL import ImageFont
    return ImageFont.load_default(size=size)


def _minus(s: str) -> str:
    # The bundled font has no U+2212; an ASCII hyphen reads the same at size.
    return s.replace("−", "-")


def stock_og_png(symbol: str, rec: dict) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    exps = rec.get("exposures") or {}
    name = rec.get("name") or ""

    d.text((64, 48), "UNSTRUCTURED ALPHA", fill=BRAND, font=_font(26))
    d.text((64, 92), symbol, fill=INK, font=_font(88))
    if name and name != symbol:
        nm = name if len(name) <= 38 else name[:37] + "…"
        x = 64 + d.textlength(symbol, font=_font(88)) + 28
        d.text((x, 128), nm, fill=DIM, font=_font(40))
    d.text((64, 200), "Typical weekly move with each economic force, beyond the market",
           fill=DIM, font=_font(28))

    scale = max((abs(exps[f.key]["impact"]) for f in ex.FACTORS if f.key in exps), default=0.0)
    top, row = 262, 58
    bar_l, bar_r = 560, 960
    mid = (bar_l + bar_r) // 2
    for i, f in enumerate(ex.FACTORS):
        y = top + i * row
        e: Optional[dict] = exps.get(f.key)
        d.line([(64, y - 8), (W - 64, y - 8)], fill=LINE, width=1)
        d.text((64, y + 6), f.label, fill=INK, font=_font(34))
        d.rounded_rectangle([bar_l, y + 18, bar_r, y + 34], radius=8, fill="#132c49")
        d.line([(mid, y + 12), (mid, y + 40)], fill=DIM, width=2)
        if not e:
            d.text((W - 64, y + 10), "not measured", fill=DIM, font=_font(28), anchor="ra")
            continue
        strong = e.get("evidence") in STANDS_UP
        half = (bar_r - bar_l) / 2
        w = half * min(1.0, abs(e["impact"]) / scale) if scale > 0 else 0
        up = e["impact"] >= 0
        col = (UP if up else DOWN) if strong else (UP_FAINT if up else DOWN_FAINT)
        x0, x1 = (mid, mid + w) if up else (mid - w, mid)
        if w >= 1:
            d.rounded_rectangle([x0, y + 18, x1, y + 34], radius=8, fill=col)
        d.text((W - 64, y + 6), _minus(fmt_pct(e["impact"])), fill=INK if strong else DIM,
               font=_font(34), anchor="ra")

    d.text((64, H - 62), _minus(f"Bright readings held up; dim ones did not. Data through "
                                f"{_date(rec['as_of'])}. The past, not a forecast."),
           fill=DIM, font=_font(24))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
