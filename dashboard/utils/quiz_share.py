# utils/quiz_share.py
# Unstructured Alpha — a shared quiz result that previews as itself
#
# "Copy your result" used to share text and the bare /quiz link, which every
# chat app previews as the same generic card. The link now carries the result
# as ?g=1101001110&d=2026-11-19 (right/wrong per question, and the day); the
# server titles the page with the score and points og:image at a card of the
# squares (/quiz/og.png?...), so a friend sees "7/10" before they click.
#
# RULES
#   * No spoilers: only right/wrong per question travels, never the answers.
#   * Only a well-formed result is read (0/1 only, a sane length, a real date
#     not in the future); anything else is the ordinary quiz page.
#   * The canonical stays /quiz: a shared result is a view, not a new page.

from __future__ import annotations

import io
import re
from datetime import date, timedelta
from typing import List, Optional, Tuple

_BITS = re.compile(r"[01]{3,20}")


def parse(g: str, d: str, today: Optional[date] = None) -> Optional[Tuple[List[int], date]]:
    if not _BITS.fullmatch(g or ""):
        return None
    try:
        day = date.fromisoformat(d or "")
    except ValueError:
        return None
    today = today or date.today()
    if day > today + timedelta(days=1) or day < date(2026, 1, 1):
        return None
    return [int(c) for c in g], day


def _label(day: date) -> str:
    return f"{day.strftime('%b')} {day.day}, {day.year}"


# The two daily games share the card; each brings its name and its question.
GAMES = {
    "quiz": ("Which way did it move?", "DAILY QUIZ",
             "When oil, rates or the dollar moved, did each stock rise with it, fall with it, or show no clear link?",
             "the same questions for everyone"),
    "guess": ("Whose fingerprint?", "DAILY GAME",
              "Five mystery stocks, each shown by how it moved with rates, inflation, the dollar, oil and credit. "
              "Pick each out of four.", "the same rounds for everyone"),
}


def share_title(bits: List[int], day: date, game: str = "quiz") -> str:
    return f"{sum(bits)}/{len(bits)} on today's “{GAMES[game][0]}” ({_label(day)}) — can you beat it?"


def share_description(bits: List[int], game: str = "quiz") -> str:
    return f"{sum(bits)} of {len(bits)} right. {GAMES[game][2]} {GAMES[game][3].capitalize()} today."


def quiz_og_png(bits: List[int], day: date, game: str = "quiz") -> bytes:
    from utils.og_image import DIM, INK, W, H, _bold, _font, _semi, canvas

    name, kicker, _q, same = GAMES[game]
    img, d = canvas(kicker)
    d.text((64, 100), name, fill=INK, font=_semi(54))
    score = f"{sum(bits)}"
    d.text((64, 180), score, fill=INK, font=_bold(160))
    x = 64 + d.textlength(score, font=_bold(160)) + 14
    d.text((x, 280), f"/ {len(bits)}", fill=DIM, font=_semi(64))
    gap = 14
    size = min(64, int((W - 128 - (len(bits) - 1) * gap) / len(bits)))   # up to 20 squares fit
    for i, b in enumerate(bits):
        x = 64 + i * (size + gap)
        d.rounded_rectangle([x, 400, x + size, 400 + size], radius=max(6, size // 5),
                            fill="#2fbfa8" if b else "#24324a")
    d.text((64, H - 96), f"{_label(day)} · {same}", fill=DIM, font=_font(28))
    d.text((64, H - 56), "Measured from three years of weekly returns. The past, not a forecast.", fill=DIM, font=_font(22))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
