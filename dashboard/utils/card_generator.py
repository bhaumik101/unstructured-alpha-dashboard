"""
utils/card_generator.py
=======================
Shareable signal card generator — produces a 1200×630 PNG suitable for
Twitter/X cards, Discord embeds, Reddit posts, and general social sharing.

WHY PIL NOT SVG: SVG requires browser or dedicated renderer to convert to a
format that auto-embeds in social platforms. PIL produces a real raster PNG
with no external dependencies beyond Pillow (which is already transitively
available via fpdf2 and is now explicit in requirements.txt).

Font path resolution: Liberation Sans ships with Ubuntu/Debian (Render's host
OS) and covers all the weight/style variants needed. Falls back to PIL's
built-in default font if no system TTF is found, so the generator never raises
even in unusual environments — it just renders less polished text.

Card layout (1200 × 630):
┌─────────────────────────────────────────────────────────┐
│ UNSTRUCTURED ALPHA                  [score_color top bar]│
│                                                         │
│  NVDA · NVIDIA Corporation         ┌──────────────────┐ │
│                                    │   74 / 100       │ │
│  ▲ 5 Bullish  ▼ 2 Bearish         │   BULLISH        │ │
│  ● 1 Neutral                       │   Strong conv.   │ │
│                                    └──────────────────┘ │
│  TOP SIGNALS                                            │
│  ▲ Insider Buy Cluster                                  │
│  ▲ Treasury Yield Spread (10Y–2Y)                      │
│  ▲ ISM Manufacturing PMI                               │
│                                                         │
│ unstructuredalpha.com            Signal Intelligence  │
└─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import io
import os
from datetime import date
from pathlib import Path


# ── Colour constants matching utils/theme.py ──────────────────────────────────
_BG         = (11, 13, 18)        # #0B0D12
_BG_CARD    = (18, 21, 30)        # #12151E
_BG_CARD2   = (22, 26, 38)        # slightly lighter card
_TEXT_PRI   = (232, 238, 255)     # #E8EEFF
_TEXT_SEC   = (136, 146, 170)     # #8892AA
_TEXT_MID   = (184, 192, 212)     # #B8C0D4
_GREEN      = (0, 213, 102)       # #00D566
_RED        = (255, 68, 68)       # #FF4444
_NEUTRAL    = (107, 127, 191)     # #6B7FBF
_CYAN       = (0, 200, 224)       # #00C8E0
_BORDER     = (40, 48, 68)        # subtle border

W, H = 1200, 630


# ── Font loader ───────────────────────────────────────────────────────────────

def _font(size: int, bold: bool = False):
    """Load a TTF font at the given size, falling back to PIL default."""
    try:
        from PIL import ImageFont
        candidates = []
        if bold:
            candidates = [
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/Library/Fonts/Arial Bold.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        else:
            candidates = [
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        for path in candidates:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()
    except Exception:
        from PIL import ImageFont
        return ImageFont.load_default()


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _rounded_rect(draw, xy, radius: int, fill, outline=None, outline_width: int = 2):
    """Draw a filled rounded rectangle. xy = (x1, y1, x2, y2)."""
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill,
                            outline=outline, width=outline_width)


def _text_w(draw, text: str, font) -> int:
    """Return pixel width of text in the given font."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except Exception:
        return len(text) * 10  # rough fallback


def _draw_text(draw, xy, text: str, font, fill, anchor="la"):
    """Draw text with safe anchor handling."""
    try:
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)
    except Exception:
        draw.text(xy, text, font=font, fill=fill)


# ── Gradient fill (top accent bar) ───────────────────────────────────────────

def _horizontal_gradient_bar(img, y: int, height: int, color_left, color_right):
    """Draw a horizontal gradient bar from color_left to color_right."""
    from PIL import ImageDraw as _ID
    draw = _ID.Draw(img)
    for x in range(W):
        t = x / W
        r = int(color_left[0] * (1 - t) + color_right[0] * t)
        g = int(color_left[1] * (1 - t) + color_right[1] * t)
        b = int(color_left[2] * (1 - t) + color_right[2] * t)
        draw.line([(x, y), (x, y + height)], fill=(r, g, b))


# ── Main generator ────────────────────────────────────────────────────────────

def generate_signal_card(
    ticker: str,
    company_name: str,
    score: float,
    case: str,          # "BULL" | "BEAR" | "NEUTRAL"
    conviction: str,    # e.g. "Strong · High Conviction"
    bull_count: int,
    bear_count: int,
    neutral_count: int,
    top_signals: list[str],   # list of "<sym> Signal Name" strings, max 4 shown
    date_str: str | None = None,
) -> bytes:
    """
    Generate a 1200×630 shareable PNG card and return the raw PNG bytes.

    Always returns bytes — never raises. On any internal error, returns a
    minimal dark placeholder card so st.download_button always gets valid PNG.
    """
    try:
        return _build_card(
            ticker=ticker.upper().strip(),
            company_name=company_name or "",
            score=float(score),
            case=case.upper() if case else "NEUTRAL",
            conviction=conviction or "",
            bull_count=int(bull_count),
            bear_count=int(bear_count),
            neutral_count=int(neutral_count),
            top_signals=top_signals[:4] if top_signals else [],
            date_str=date_str or date.today().isoformat(),
        )
    except Exception:
        return _error_card()


def _score_color(case: str) -> tuple:
    return _GREEN if case == "BULL" else (_RED if case == "BEAR" else _NEUTRAL)


def _build_card(
    ticker, company_name, score, case, conviction,
    bull_count, bear_count, neutral_count,
    top_signals, date_str,
) -> bytes:
    from PIL import Image, ImageDraw

    img  = Image.new("RGB", (W, H), _BG)
    draw = ImageDraw.Draw(img)

    sc = _score_color(case)

    # ── Top accent gradient bar ──────────────────────────────────────────────
    # Fade from score_color → a darker tint of score_color
    _dim = tuple(max(0, int(c * 0.3)) for c in sc)
    _horizontal_gradient_bar(img, y=0, height=6, color_left=sc, color_right=_dim)

    # ── Background grid lines (subtle depth) ─────────────────────────────────
    for gx in range(0, W, 120):
        draw.line([(gx, 0), (gx, H)], fill=(255, 255, 255, 8) if hasattr(draw, 'alpha_composite') else (20, 24, 34))
    for gy in range(0, H, 120):
        draw.line([(0, gy), (W, gy)], fill=(20, 24, 34))

    # ── Left column: brand + ticker + counts + signals ───────────────────────
    lx = 60
    y  = 42

    # Brand label
    f_brand = _font(14, bold=True)
    _draw_text(draw, (lx, y), "UNSTRUCTURED ALPHA", font=f_brand, fill=_CYAN)
    y += 26

    # Date (right-aligned)
    f_date = _font(13)
    date_display = date_str or date.today().isoformat()
    _draw_text(draw, (W - 60, 50), date_display, font=f_date, fill=_TEXT_SEC, anchor="ra")

    # Ticker (very large)
    f_ticker = _font(96, bold=True)
    _draw_text(draw, (lx, y), ticker, font=f_ticker, fill=_TEXT_PRI)
    y += 108

    # Company name
    f_co = _font(20)
    # Truncate long names
    co_display = company_name if len(company_name) <= 40 else company_name[:38] + "…"
    _draw_text(draw, (lx, y), co_display, font=f_co, fill=_TEXT_SEC)
    y += 44

    # Divider
    draw.line([(lx, y), (560, y)], fill=_BORDER, width=1)
    y += 16

    # Bull / Bear / Neutral counts
    f_count = _font(22, bold=True)
    f_clabel = _font(14)

    items = [
        (f"▲ {bull_count}", _GREEN, "Bullish"),
        (f"▼ {bear_count}", _RED, "Bearish"),
        (f"● {neutral_count}", _NEUTRAL, "Neutral"),
    ]
    cx = lx
    for sym_str, col, lbl in items:
        _draw_text(draw, (cx, y), sym_str, font=f_count, fill=col)
        tw = _text_w(draw, sym_str, f_count)
        _draw_text(draw, (cx + tw + 6, y + 5), lbl, font=f_clabel, fill=_TEXT_SEC)
        cx += tw + _text_w(draw, lbl, f_clabel) + 32

    y += 46

    # Divider
    draw.line([(lx, y), (560, y)], fill=_BORDER, width=1)
    y += 16

    # Top signals header
    f_sig_hdr = _font(12, bold=True)
    _draw_text(draw, (lx, y), "TOP SIGNALS", font=f_sig_hdr, fill=_TEXT_SEC)
    y += 24

    f_sig = _font(18, bold=True)
    f_sign = _font(18)
    max_sig_len = 42
    for sig_line in top_signals[:4]:
        sym = sig_line[:2] if sig_line else "●"
        rest = sig_line[2:].strip() if len(sig_line) > 2 else sig_line
        if len(rest) > max_sig_len:
            rest = rest[:max_sig_len - 1] + "…"

        col = _GREEN if sym.startswith("▲") else (_RED if sym.startswith("▼") else _NEUTRAL)
        _draw_text(draw, (lx, y), sym, font=f_sig, fill=col)
        sym_w = _text_w(draw, sym, f_sig)
        _draw_text(draw, (lx + sym_w + 8, y), rest, font=f_sign, fill=_TEXT_MID)
        y += 30

    # ── Right column: score badge ─────────────────────────────────────────────
    bx1, by1, bx2, by2 = 700, 70, 1060, 500
    bm = 12  # margin inside badge

    # Badge background
    _rounded_rect(draw, (bx1, by1, bx2, by2), radius=20,
                  fill=_BG_CARD2, outline=sc, outline_width=3)

    # Inner glow effect (concentric slightly lighter rect)
    _rounded_rect(draw, (bx1 + 2, by1 + 2, bx2 - 2, by2 - 2), radius=18,
                  fill=_BG_CARD, outline=None)

    badge_cx = (bx1 + bx2) // 2
    badge_y  = by1 + 40

    # Case label (e.g. "BULLISH")
    f_case = _font(26, bold=True)
    case_display = "BULLISH" if case == "BULL" else ("BEARISH" if case == "BEAR" else "NEUTRAL")
    case_w = _text_w(draw, case_display, f_case)
    _draw_text(draw, (badge_cx - case_w // 2, badge_y), case_display, font=f_case, fill=sc)
    badge_y += 44

    # Score number (huge)
    f_score_big = _font(130, bold=True)
    score_str = f"{score:.0f}"
    score_w = _text_w(draw, score_str, f_score_big)
    _draw_text(draw, (badge_cx - score_w // 2, badge_y), score_str,
               font=f_score_big, fill=sc)
    badge_y += 140

    # "/100" label
    f_denom = _font(28)
    denom_str = "out of 100"
    denom_w = _text_w(draw, denom_str, f_denom)
    _draw_text(draw, (badge_cx - denom_w // 2, badge_y), denom_str,
               font=f_denom, fill=_TEXT_SEC)
    badge_y += 46

    # Divider inside badge
    div_pad = 40
    draw.line([(bx1 + div_pad, badge_y), (bx2 - div_pad, badge_y)],
              fill=_BORDER, width=1)
    badge_y += 16

    # Conviction
    f_conv = _font(16)
    conv_short = conviction.split("·")[0].strip() if "·" in conviction else conviction
    if len(conv_short) > 28:
        conv_short = conv_short[:27] + "…"
    conv_w = _text_w(draw, conv_short, f_conv)
    _draw_text(draw, (badge_cx - conv_w // 2, badge_y), conv_short,
               font=f_conv, fill=_TEXT_SEC)

    # ── Bottom footer bar ─────────────────────────────────────────────────────
    fy = H - 52
    draw.line([(0, fy), (W, fy)], fill=_BORDER, width=1)

    f_footer = _font(14, bold=True)
    f_footer_r = _font(14)

    _draw_text(draw, (lx, fy + 16), "unstructuredalpha.com", font=f_footer, fill=_CYAN)
    tagline = "Signal intelligence for serious investors"
    tagline_w = _text_w(draw, tagline, f_footer_r)
    _draw_text(draw, (W - 60 - tagline_w, fy + 16), tagline, font=f_footer_r, fill=_TEXT_SEC)

    # ── Serialize to PNG bytes ────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _error_card() -> bytes:
    """Return a minimal dark PNG if card generation fails."""
    from PIL import Image, ImageDraw
    img  = Image.new("RGB", (W, H), _BG)
    draw = ImageDraw.Draw(img)
    f    = _font(24, bold=True)
    _draw_text(draw, (W // 2, H // 2), "unstructuredalpha.com",
               font=f, fill=_CYAN, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
