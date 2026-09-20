#!/usr/bin/env python3
"""Generate the social link-preview image for the landing page.

WHY THIS EXISTS
---------------
app/layout.tsx has always pointed og:image and twitter:image at
/og-image.png, and that file did not exist: every link shared to X, LinkedIn,
Slack or iMessage rendered a blank card. Link previews are the cheapest
distribution the product has, so this generates the image and commits it.

Run from dashboard/ when the wording or palette changes:

    python scripts/make_og_image.py

Output: unstructured-alpha-web/public/og-image.png (1200x630, the size every
major crawler crops to). tests/test_social_preview.py asserts the file exists,
has those dimensions, and is still the image the page references.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
OUT = Path(__file__).resolve().parent.parent / "unstructured-alpha-web" / "public" / "og-image.png"

NAVY = (13, 34, 59)
NAVY_2 = (21, 55, 93)
WHITE = (255, 255, 255)
MUTED = (186, 202, 222)
GOLD = (255, 194, 75)

# The same identity colours the product uses for each economic force.
FACTORS = [
    ("Rates", (59, 125, 221)),
    ("Inflation", (224, 102, 74)),
    ("Dollar", (26, 154, 112)),
    ("Oil", (217, 144, 24)),
    ("Credit", (124, 92, 224)),
    ("Growth", (20, 151, 176)),
]

_FONT_DIRS = ("/System/Library/Fonts/Supplemental", "/Library/Fonts",
              "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts")
_BOLD = ("Arial Bold.ttf", "DejaVuSans-Bold.ttf", "Helvetica.ttc")
_REGULAR = ("Arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc")


def _font(names: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont:
    for directory in _FONT_DIRS:
        for name in names:
            path = Path(directory) / name
            if path.is_file():
                try:
                    return ImageFont.truetype(str(path), size)
                except OSError:
                    continue
    return ImageFont.load_default()


def build() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)

    # Diagonal wash, the same direction as the site's hero band.
    for y in range(HEIGHT):
        t = y / HEIGHT
        draw.line([(0, y), (WIDTH, y)],
                  fill=tuple(int(a + (b - a) * t) for a, b in zip(NAVY, NAVY_2)))

    # Dot grid, fading out downward, matching the hero's texture.
    for gy in range(0, HEIGHT, 26):
        for gx in range(0, WIDTH, 26):
            fade = max(0.0, 1.0 - gy / (HEIGHT * 0.9))
            if fade > 0.04:
                shade = tuple(int(c + (255 - c) * 0.10 * fade) for c in NAVY_2)
                draw.ellipse([gx, gy, gx + 2, gy + 2], fill=shade)

    draw.text((72, 64), "UNSTRUCTURED ALPHA", font=_font(_BOLD, 26), fill=WHITE)
    draw.text((72, 104), "unstructuredalpha.com", font=_font(_REGULAR, 22), fill=MUTED)

    headline = _font(_BOLD, 62)
    draw.text((72, 186), "See which economic forces", font=headline, fill=WHITE)
    draw.text((72, 258), "your portfolio is", font=headline, fill=WHITE)
    draw.text((72 + draw.textlength("your portfolio is ", font=headline), 258),
              "exposed to.", font=headline, fill=GOLD)

    draw.text((72, 356),
              "Measured from three years of weekly returns, with the",
              font=_font(_REGULAR, 28), fill=MUTED)
    draw.text((72, 394),
              "uncertainty shown on every number. Not a forecast.",
              font=_font(_REGULAR, 28), fill=MUTED)

    # One chip per force: the palette a reader will meet again in the report.
    x = 72
    chip_font = _font(_BOLD, 22)
    for label, colour in FACTORS:
        text_w = draw.textlength(label, font=chip_font)
        draw.rounded_rectangle([x, 492, x + text_w + 54, 542], radius=25, fill=colour)
        draw.ellipse([x + 18, 510, x + 32, 524], fill=WHITE)
        draw.text((x + 40, 503), label, font=chip_font, fill=WHITE)
        x += text_w + 54 + 14

    return image


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    build().save(OUT, "PNG", optimize=True)
    print(f"[og-image] wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
