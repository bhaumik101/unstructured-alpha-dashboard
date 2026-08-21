"""The category chip must be coloured by category, in both card variants.

The Pro card painted a chip carrying the category's name and icon with the
bull/bear colour instead. Two problems in one:

  1. It is the wrong fact. The chip says "Supply Chain & Logistics" and looked
     green or red depending on which way the signal was pointing.
  2. It was the FOURTH encoding of bull/bear on a single card, alongside the
     top border, the status symbol and the score colour.

The Simple card already did this correctly, so the two variants disagreed about
what the same chip means. The colour source is now computed once, above the
mode branch, and both read it — which is also what stops them drifting apart
again.

This deliberately removes no information. Reducing the card's 15 metadata
elements is a product decision and is not attempted here.

UPDATE (professional-mode cleanup): the PRO chip is now deliberately UNTINTED.
The Pro card colours the score semantically, and a per-category tint beside it
was a second colour axis competing with the one that carries meaning. The
category is still stated, in text, in the card's metadata row.

The original protection is unchanged and now applies to both variants: no chip
may be painted by the signal's direction. What changed is that "category chip"
no longer implies "category-coloured" for Pro -- Simple keeps its tint, because
Simple is not carrying a semantic score colour next to it.
"""

from __future__ import annotations

import re
from pathlib import Path

_PAGE = Path(__file__).resolve().parent.parent / "pages" / "1_Signal_Dashboard.py"
_SRC = _PAGE.read_text(encoding="utf-8")

# The bull/bear-derived RGB triple, and the category-derived one.
STATE_RGB = re.compile(r"\{_bc_r\},\{_bc_g\},\{_bc_b\}")
CAT_RGB = re.compile(r"\{_cat_cr\},\{_cat_cg\},\{_cat_cb\}")


def _chip_blocks() -> list[str]:
    """Every span that renders the category name.

    Matched on {_cat_name} alone: the Pro chip no longer carries {_cat_icon},
    because the emoji set was the loudest thing on a card built from geometric
    marks. Matching the old icon+name pair would silently find one chip instead
    of two and assert nothing about Pro.
    """
    blocks = []
    for m in re.finditer(r"\{_cat_name\}", _SRC):
        start = _SRC.rfind("<span", 0, m.start())
        assert start != -1, "category chip is not inside a span"
        blocks.append(_SRC[start : m.end()])
    return blocks


def test_both_card_variants_render_a_category_chip():
    blocks = _chip_blocks()
    assert len(blocks) == 2, (
        f"expected the Simple and Pro category chips, found {len(blocks)}"
    )


def test_no_category_chip_is_coloured_by_bull_bear():
    offenders = [b for b in _chip_blocks() if STATE_RGB.search(b)]
    assert not offenders, (
        "a chip labelled with the category name and icon is painted by the "
        "signal's direction. That is the wrong fact, and it is the 4th "
        "bull/bear encoding on one card:\n" + "\n".join(b[:180] for b in offenders)
    )


def test_the_simple_chip_keeps_its_category_colour():
    """Simple mode has no semantic score colour beside it, so the tint is free."""
    simple = [b for b in _chip_blocks() if CAT_RGB.search(b)]
    assert len(simple) == 1, (
        f"expected exactly one category-tinted chip (Simple), found {len(simple)}"
    )


def test_the_pro_chip_is_not_tinted_at_all():
    """The Pro card's one meaningful colour is the score. Nothing competes."""
    untinted = [
        b for b in _chip_blocks()
        if not CAT_RGB.search(b) and not STATE_RGB.search(b)
    ]
    assert len(untinted) == 1, (
        "expected exactly one untinted category chip (Pro). A tint here is a "
        "second colour axis on a card that already colours the score "
        f"semantically. Found {len(untinted)}."
    )


def test_the_pro_chip_carries_no_emoji():
    pro = [b for b in _chip_blocks() if "_cat_icon" not in b]
    assert pro, "every category chip still renders {_cat_icon}"


def test_the_category_colour_is_computed_once_for_both_variants():
    """Two local copies is how the variants disagreed in the first place."""
    assigns = re.findall(r"^\s*_cat_color\s*=", _SRC, flags=re.M)
    assert len(assigns) == 1, (
        f"_cat_color is assigned {len(assigns)} times; compute it once above "
        f"the mode branch so both cards cannot drift apart again"
    )
