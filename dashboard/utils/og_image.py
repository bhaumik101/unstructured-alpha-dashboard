# utils/og_image.py
# Unstructured Alpha — the preview image a page shows when it is shared
#
# A link to /exposure/XOM pasted into X, LinkedIn, Slack or a message shows a
# 1200x630 card: the ticker, the name, and the five core readings as bars on
# one shared axis. Drawn with Pillow in the site's own typeface (Inter, bundled
# in static/fonts; the server has no system fonts), in the 2026-11 brand: a
# near-black ground with a faint grid and one teal light, gold only in ALPHA.
#
# RULES
#   * The same honesty as the page: the bar's fill says how strong the
#     evidence is (solid Clear, lighter Tentative, outline not distinguishable
#     from zero), the 90% range is drawn, "not measured" where so, the date,
#     and "the past, not a forecast" on the image -- a preview travels alone.
#   * Direction is the side of zero plus the signed figure, never colour;
#     each force keeps its identity colour for its dot only.
#   * Pure function of the stored record; the route caches the bytes.

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

from utils import exposure as ex
from utils.exposure_pages import STANDS_UP, _date, fmt_pct

W, H = 1200, 630
BG, INK, DIM, LINE, BRAND = "#080d14", "#f3f6fa", "#8794a8", "#1c2738", "#d8b66a"
ACCENT = "#6ce5d2"
FIELD = "#101824"
# Bar fills by evidence. UP/DOWN keep their names for callers: a held-up bar
# is the same bright fill whichever way it points.
UP = DOWN = "#c9d6e8"
UP_FAINT = DOWN_FAINT = "#5d6d84"          # Tentative: lighter
OUTLINE = "#7b8aa0"                        # not distinguishable from zero: outline only
FORCE_HUES = {"rates": "#6fa4ec", "inflation": "#ef9179", "dollar": "#4fc79b",
              "oil": "#eab54f", "credit": "#a893f0", "growth": "#55c3d8"}

_FONTS = Path(__file__).resolve().parent.parent / "static" / "fonts"


@lru_cache(maxsize=16)
def _font(size: int, weight: str = "Regular"):
    from PIL import ImageFont
    path = _FONTS / f"Inter-{weight}.otf"
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:                                    # fonts missing: still draw
        return ImageFont.load_default(size=size)


def _bold(size: int):
    return _font(size, "Bold")


def _semi(size: int):
    return _font(size, "SemiBold")


def _minus(s: str) -> str:
    # Inter has a true minus (U+2212); only the fallback font needs a hyphen.
    return s if (_FONTS / "Inter-Regular.otf").exists() else s.replace("−", "-")


def canvas(kicker: str):
    """The shared ground: near-black, a faint grid fading out, one teal light
    top right, the wordmark and a kicker. Returns (image, draw)."""
    from PIL import Image, ImageDraw, ImageFilter

    img = Image.new("RGB", (W, H), BG)
    glow = Image.new("RGB", (W, H), BG)
    g = ImageDraw.Draw(glow)
    g.ellipse([W - 520, -380, W + 260, 300], fill="#123a3a")
    g.ellipse([-300, H - 140, 420, H + 380], fill="#121d33")
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    img = Image.blend(img, glow, 0.85)
    grid = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(grid)
    for x in range(0, W, 48):
        gd.line([(x, 0), (x, H)], fill=255)
    for y in range(0, H, 48):
        gd.line([(0, y), (W, y)], fill=255)
    fade = Image.radial_gradient("L").resize((W * 2, H * 2)).crop((W // 2, 0, W // 2 + W, H))
    fade = fade.point(lambda v: max(0, 34 - v // 6))
    from PIL import ImageChops
    img.paste((168, 181, 199), mask=ImageChops.multiply(grid, fade))
    d = ImageDraw.Draw(img)
    d.text((64, 46), "UNSTRUCTURED", fill=INK, font=_bold(22))
    x = 64 + d.textlength("UNSTRUCTURED ", font=_bold(22))
    d.text((x, 46), "ALPHA", fill=BRAND, font=_bold(22))
    if kicker:
        x2 = x + d.textlength("ALPHA", font=_bold(22)) + 18
        d.text((x2, 48), kicker, fill=ACCENT, font=_semi(18))
    return img, d


def bars(d, rows: Sequence[dict], top: int, row: int = 60, scale: Optional[float] = None) -> None:
    """One row per force: identity dot, label, a bar on a shared axis with its
    90% range, the signed figure. rows: key, label, value (or None), low, high,
    evidence ('clear'|'tentative'|other)."""
    vals = [abs(v) for r in rows for v in (r.get("value"), r.get("low"), r.get("high")) if v is not None]
    scale = scale or max(vals + [0.25])
    bar_l, bar_r = 520, 980
    mid = (bar_l + bar_r) / 2
    half = (bar_r - bar_l) / 2

    def X(v):
        return mid + max(-1.0, min(1.0, v / scale)) * half
    d.line([(mid, top - 14), (mid, top + row * len(rows) - 22)], fill="#3a4a60", width=2)
    for i, r in enumerate(rows):
        y = top + i * row
        if i:
            d.line([(64, y - 18), (W - 64, y - 18)], fill=LINE, width=1)
        d.ellipse([64, y + 7, 78, y + 21], fill=FORCE_HUES.get(r["key"], DIM))
        d.text((94, y - 2), r["label"], fill=INK, font=_semi(30))
        v = r.get("value")
        if v is None:
            d.text((W - 64, y), "not measured", fill=DIM, font=_font(26), anchor="ra")
            continue
        ev = r.get("evidence")
        if r.get("low") is not None and r.get("high") is not None:
            lo, hi = X(r["low"]), X(r["high"])
            d.line([(lo, y + 14), (hi, y + 14)], fill="#8b9bb2", width=2)
            d.line([(lo, y + 6), (lo, y + 22)], fill="#8b9bb2", width=2)
            d.line([(hi, y + 6), (hi, y + 22)], fill="#8b9bb2", width=2)
        x0, x1 = sorted((mid, X(v)))
        if x1 - x0 >= 1:
            if ev == "clear":
                d.rounded_rectangle([x0, y + 6, x1, y + 22], radius=4, fill=UP)
            elif ev == "tentative":
                d.rounded_rectangle([x0, y + 6, x1, y + 22], radius=4, fill=UP_FAINT)
            else:
                d.rounded_rectangle([x0, y + 6, x1, y + 22], radius=4, outline=OUTLINE, width=2)
        d.text((W - 64, y - 2), _minus(fmt_pct(v)), fill=INK if ev in ("clear", "tentative") else DIM,
               font=_bold(32), anchor="ra")


def stock_og_png(symbol: str, rec: dict) -> bytes:
    exps = rec.get("exposures") or {}
    name = rec.get("name") or ""
    img, d = canvas("STOCK EXPOSURE")
    tw = d.textlength(symbol, font=_bold(84))
    d.rounded_rectangle([56, 92, 56 + tw + 32, 196], radius=16, fill="#0f2a2b", outline="#2f7f75", width=2)
    d.text((72, 98), symbol, fill="#bff4ec", font=_bold(84))
    if name and name != symbol:
        nm = name if len(name) <= 34 else name[:33] + "…"
        d.text((56 + tw + 56, 126), nm, fill=INK, font=_semi(40))
    d.text((64, 214), "Typical weekly move with each economic force, beyond the market",
           fill=DIM, font=_font(24))
    rows = []
    for f in ex.FACTORS:
        e = exps.get(f.key)
        rows.append({"key": f.key, "label": f.label, "value": e["impact"] if e else None,
                     "low": e.get("low") if e else None, "high": e.get("high") if e else None,
                     "evidence": (e or {}).get("evidence") if e and e.get("evidence") in STANDS_UP else
                     ("indistinct" if e else None)})
    bars(d, rows, top=276, row=56)
    d.text((64, H - 62), "Bar: solid Clear · lighter Tentative · outline not distinguishable from zero · line 90% range",
           fill=DIM, font=_font(18))
    d.text((64, H - 36), _minus(f"Data through {_date(rec['as_of'])} · three years of weekly returns · the past, not a forecast"),
           fill=DIM, font=_font(18))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
