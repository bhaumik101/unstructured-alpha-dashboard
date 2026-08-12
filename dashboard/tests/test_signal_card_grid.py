"""The signal-card grid must present one bottom edge per row.

Measured on the deployed Signal Dashboard 2026-08-12: 47 cards spanning 175px
to 306px across 11 distinct heights -- a 131px spread. Streamlit stretches the
columns in a row to match the tallest, then leaves the surplus BELOW each
shorter column's content, so the cards end at different heights and the row
reads as ragged.

The fix is CSS-only and depends on three things staying true together: the grid
is wrapped in a keyed container, both card variants carry the hook class, and
the stretch rules stay scoped to that key. Any one of them silently undoes it,
and no rendering test can see the result -- which is why each is pinned here.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_HEADER_SRC = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")
_PAGE = _ROOT / "pages" / "1_Signal_Dashboard.py"
_PAGE_SRC = _PAGE.read_text(encoding="utf-8")

GRID_KEY = "ua_signal_grid"
CARD_CLASS = "ua-signal-card"


def test_the_card_grid_is_wrapped_in_a_keyed_container():
    """Without the key the CSS below has nothing to scope to."""
    assert f'st.container(key="{GRID_KEY}")' in _PAGE_SRC, (
        "the card grid must live in a keyed container so the equal-height CSS "
        "can target only it"
    )
    assert re.search(r"_grid\.columns\(COLS\)", _PAGE_SRC), (
        "the rows must be created from the keyed container, not st.columns -- "
        "bare st.columns lands outside the key and the CSS misses it"
    )


def test_both_card_variants_carry_the_hook_class():
    """Simple and Pro are two separate markup blocks in the same loop.

    They were copy-pasted from each other, so a change applied to one and not
    the other is the likely drift. Only the Pro card would go ragged, on a page
    most users never switch into.
    """
    hooks = _PAGE_SRC.count(f'class="{CARD_CLASS}"')
    assert hooks == 2, (
        f"expected the hook class on both the Simple and Pro card, found "
        f"{hooks}. A card without it will not stretch."
    )


def test_the_stretch_rules_are_scoped_to_the_grid():
    """Unscoped, these rules stretch element containers app-wide.

    "Fill your column" is wrong anywhere a column holds ordinary stacked
    content -- and each column here also holds the "Details & chart" expander,
    which must keep its natural height.
    """
    src = re.sub(r"/\*.*?\*/", "", _HEADER_SRC, flags=re.S)
    rules = [
        ln.strip()
        for ln in src.splitlines()
        if CARD_CLASS in ln and ("{" in ln or ln.rstrip().endswith(","))
    ]
    assert rules, "no CSS rules reference the card hook class"

    unscoped = [
        r
        for r in rules
        # The bare `.ua-signal-card { flex }` rule is intentionally global: it
        # only makes the card grow inside a flex parent it otherwise has none of.
        if f".st-key-{GRID_KEY}" not in r and not r.startswith(f".{CARD_CLASS}")
    ]
    assert not unscoped, (
        f"these rules reach beyond the signal grid: {unscoped}. Prefix each "
        f"with '.st-key-{GRID_KEY} '."
    )


def test_the_expander_is_not_stretched_with_the_card():
    """Only the card absorbs the surplus.

    If the stretch targeted every element container in the column, the
    expander would grow too and the row would still not square up -- it would
    just fail differently, with a tall empty expander header.
    """
    src = re.sub(r"/\*.*?\*/", "", _HEADER_SRC, flags=re.S)
    grow = [
        ln.strip()
        for ln in src.splitlines()
        if f".st-key-{GRID_KEY}" in ln and ".stElementContainer:has(" in ln
    ]
    assert grow, "expected a scoped stElementContainer rule"
    assert all(f":has(.{CARD_CLASS})" in ln for ln in grow), (
        f"the growing container must be selected by the card it holds, not by "
        f"position: {grow}"
    )
    # And nothing may grow a container chosen positionally (:first-child etc),
    # which would catch the card on some rows and the expander on others.
    positional = [
        ln.strip()
        for ln in src.splitlines()
        if f".st-key-{GRID_KEY}" in ln
        and re.search(r":(first|last|nth)-(child|of-type)", ln)
    ]
    assert not positional, f"positional selectors in the grid CSS: {positional}"
