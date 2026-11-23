#!/usr/bin/env python3
"""Build unstructured-alpha-web/public/og-image.png, the homepage's share card.

Drawn from real data only: the balanced sample's readings (the same stored
report the landing's hero panel shows; keep SAMPLE in step with page.tsx) and,
behind them, every measured stock from the live /xray.json feed plotted on
rates and oil. Run when the landing's sample is refreshed:

    python scripts/build_landing_og.py [path-or-url-to-xray.json]
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.og_image import ACCENT, DIM, INK, W, H, _bold, _font, _semi, bars, canvas  # noqa: E402

AS_OF = "Nov 13, 2026"
SAMPLE = [  # page.tsx SAMPLE.rows: the stored balanced report, data through 2026-11-13
    ("dollar", "U.S. dollar", -0.71, -0.83, -0.58, "clear"),
    ("rates", "Interest rates", -0.62, -0.70, -0.54, "clear"),
    ("inflation", "Inflation expectations", 0.32, 0.08, 0.56, "tentative"),
    ("credit", "Credit spreads", -0.17, -0.37, 0.04, "indistinct"),
    ("oil", "Oil and energy", -0.10, -0.17, -0.03, "tentative"),
]
OUT = Path(__file__).resolve().parent.parent / "unstructured-alpha-web" / "public" / "og-image.png"


def load_feed(src: str) -> dict:
    if src.startswith("http"):
        with urllib.request.urlopen(src, timeout=30) as r:
            return json.load(r)
    return json.loads(Path(src).read_text())


def main() -> None:
    from PIL import Image, ImageDraw, ImageFilter

    feed = load_feed(sys.argv[1] if len(sys.argv) > 1 else "https://www.unstructuredalpha.com/xray.json")
    img, d = canvas("")

    # Starfield: every stock on rates (x) and oil (y), faint, right half.
    stars = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stars)
    for _, (_, _, r) in feed["s"].items():
        a, b = r[0], r[3]
        if not a or not b:
            continue
        x = 890 + max(-1, min(1, a[0] / 4)) * 300
        y = 315 - max(-1, min(1, b[0] / 4)) * 300
        held = a[1] or b[1]
        sd.ellipse([x - 2.6, y - 2.6, x + 2.6, y + 2.6], fill=(169, 199, 238, 110 if held else 50))
    img.paste(stars, (0, 0), stars)
    d = ImageDraw.Draw(img)

    # Headline, with the gradient word.
    d.text((64, 104), "See the", fill=INK, font=_bold(76))
    word = "forces"
    wx, wy = 64, 190
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).text((wx, wy), word, fill=255, font=_bold(76))
    grad = Image.new("RGB", (W, H))
    gd = ImageDraw.Draw(grad)
    x0, x1 = wx, wx + d.textlength(word, font=_bold(76))
    for x in range(int(x0), int(x1) + 1):
        t = (x - x0) / max(1, x1 - x0)
        c0, c1 = (108, 229, 210), (201, 163, 240)
        gd.line([(x, 0), (x, H)], fill=tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3)))
    img.paste(grad, (0, 0), mask)
    d.text((x1 + 22, wy), "inside", fill=INK, font=_bold(76))
    d.text((64, 276), "your portfolio.", fill=INK, font=_bold(76))
    d.text((64, 384), "Rates, inflation, the dollar, oil and credit,", fill=DIM, font=_font(28))
    d.text((64, 420), "with the uncertainty shown.", fill=DIM, font=_font(28))

    # A compact report panel: the sample, drawn as the product draws it.
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    px, py, pw, ph = 640, 96, 500, 400
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([px, py + 24, px + pw, py + ph + 24], radius=18, fill=(0, 0, 0, 170))
    img.paste(shadow.filter(ImageFilter.GaussianBlur(28)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(28)))
    pd.rounded_rectangle([px, py, px + pw, py + ph], radius=18, fill=(16, 24, 36, 238), outline=(47, 127, 117, 255), width=2)
    img.paste(panel, (0, 0), panel)
    d = ImageDraw.Draw(img)
    d.text((px + 28, py + 24), f"SAMPLE REPORT · DATA THROUGH {AS_OF.upper()}", fill=DIM, font=_semi(14))
    d.text((px + 28, py + 48), "Balanced ETF portfolio", fill=INK, font=_semi(26))
    # The five rows at full size: dot, label, bar on one shared ±1% axis with
    # its 90% range, figure. Same encoding as the site and bars().
    from utils.og_image import FORCE_HUES, OUTLINE, UP, UP_FAINT
    tl, tr = px + 236, px + pw - 104
    mid, half = (tl + tr) / 2, (tr - tl) / 2
    X = lambda v: mid + max(-1, min(1, v)) * half  # noqa: E731
    d.line([(mid, py + 104), (mid, py + 104 + 5 * 50 - 14)], fill="#3a4a60", width=2)
    for i, (k, label, v, lo, hi, ev) in enumerate(SAMPLE):
        y = py + 112 + i * 50
        if i:
            d.line([(px + 28, y - 14), (px + pw - 28, y - 14)], fill="#1c2738", width=1)
        d.ellipse([px + 28, y + 6, px + 38, y + 16], fill=FORCE_HUES[k])
        d.text((px + 48, y), label if len(label) < 20 else "Inflation exp.", fill=INK, font=_semi(19))
        d.line([(X(lo), y + 11), (X(hi), y + 11)], fill="#8b9bb2", width=2)
        for e in (lo, hi):
            d.line([(X(e), y + 5), (X(e), y + 17)], fill="#8b9bb2", width=2)
        x0, x1 = sorted((mid, X(v)))
        if ev == "clear":
            d.rounded_rectangle([x0, y + 5, x1, y + 17], radius=3, fill=UP)
        elif ev == "tentative":
            d.rounded_rectangle([x0, y + 5, x1, y + 17], radius=3, fill=UP_FAINT)
        else:
            d.rounded_rectangle([x0, y + 5, x1, y + 17], radius=3, outline=OUTLINE, width=2)
        d.text((px + pw - 28, y - 1), ("+" if v > 0 else "−") + f"{abs(v):.2f}%",
               fill=INK if ev != "indistinct" else DIM, font=_bold(21), anchor="ra")
    d.text((px + 28, py + ph - 40), "Solid: Clear · lighter: Tentative · outline: not distinguishable", fill=DIM, font=_font(14))

    d.text((64, H - 66), "Free · no account for your first report", fill=ACCENT, font=_semi(22))
    d.text((64, H - 36), "Describes the past; not a forecast, not investment advice.", fill=DIM, font=_font(18))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
