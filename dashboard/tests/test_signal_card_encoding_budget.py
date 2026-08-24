"""One chromatic state cue, one non-chromatic, and no third framing of the
same statistic.

Both card variants encoded bull/bear four times over: a gradient background
tint, a coloured top border, the status symbol, and the score/pill colour. #144
removed a fifth (the category chip, which was painting the wrong fact
entirely). Four cues for one boolean is what made a 47-card grid read as loud.

The budget kept here is deliberate and cheap to state:

  - exactly one NON-chromatic cue: the arrow/symbol, which survives colour
    blindness and greyscale printing
  - exactly one CHROMATIC cue: the score (Pro) or status pill (Simple)
  - no decorative repeats: no state-derived gradient, no state-derived border

Whoever revisits this should move a cue, not add one.
"""

from __future__ import annotations

import re
from pathlib import Path

_PAGE = Path(__file__).resolve().parent.parent / "pages" / "1_Signal_Dashboard.py"
_SRC = _PAGE.read_text(encoding="utf-8")

# The card markup runs from the first card div to the expander that follows.
_CARDS = _SRC[
    _SRC.index('<div class="ua-signal-card"') : _SRC.index('st.expander("Details & chart")')
]

# Split per variant. Checking the block as a whole is not enough: stripping
# BOTH cues from the Pro score passed every test in this file, because the
# Simple card still contained the strings being looked for.
_PRO_MARKER = "PRO card: full metrics"
_SIMPLE = _CARDS[: _CARDS.index(_PRO_MARKER)]
_PRO = _CARDS[_CARDS.index(_PRO_MARKER) :]
_VARIANTS = (("Simple", _SIMPLE), ("Pro", _PRO))


def test_no_card_paints_a_state_derived_background():
    """The gradient tint was pure repetition of the border and the score.

    Scoped to the CARD container. The status pill's own tinted background is
    the chromatic cue itself, not a repeat of it, so it is allowed.
    """
    offenders = []
    for m in re.finditer(r'<div class="ua-signal-card" style="([^\']*)', _CARDS):
        opening = m.group(1)
        if "linear-gradient" in opening or "_bc_" in opening:
            offenders.append(opening.strip()[:120])
    assert not offenders, (
        "the card container paints a state-derived background, which repeats "
        "the score colour:\n" + "\n".join(offenders)
    )


def test_no_card_paints_a_state_derived_border():
    offenders = [
        ln.strip()
        for ln in _CARDS.splitlines()
        if re.search(r"border[^:]*:\s*[^;]*\{border\}", ln) or "border-top:2px solid" in ln
    ]
    assert not offenders, (
        "a state-derived border is a decorative repeat of the score colour:\n"
        + "\n".join(offenders)
    )


def test_each_variant_keeps_its_non_chromatic_cue():
    """Colour alone must never be the only carrier of direction.

    Asserted per variant. A whole-block check passes while one card has lost
    both cues, which is exactly what happened when this was written.
    """
    for name, block in _VARIANTS:
        assert "{sym}" in block, (
            f"the {name} card lost the status symbol — the only cue that "
            f"survives colour blindness and greyscale"
        )


def test_each_variant_keeps_one_chromatic_cue():
    """One chromatic cue is the budget, not zero.

    The cue is now emitted as `_status_text` rather than `border`. Same hue and
    same single cue: `border` is chosen for a 4px rule, and reusing it for
    10-13px text measured 3.27:1 against the card. `_status_text` is that hue
    lifted to clear WCAG AA (utils.theme.ink) -- a readability derivation, not a
    second colour axis. The border keeps `border` itself.
    """
    for name, block in _VARIANTS:
        assert re.search(r"color:\{_status_text\}", block), (
            f"the {name} card lost its state colour; one chromatic cue is the "
            f"budget, not zero"
        )
        assert not re.search(r"color:\{border\}", block), (
            f"the {name} card colours text straight from `border` again; that "
            f"is the sub-AA value _status_text exists to replace"
        )


def test_percentile_is_not_a_third_framing_on_the_card():
    """Dev% (raw) and the z-score (standardised) already answer 'how extreme'.

    The percentile is still available in the Details & chart expander, which is
    where the full metric table lives — this only removes the third copy from
    the card face.
    """
    assert "P{pct_rank" not in _CARDS, (
        "percentile on the card face is a third framing of the same statistic"
    )
    assert "Percentile" in _SRC, (
        "percentile should still be in the Details & chart metric table; only "
        "the card-face copy was removed"
    )


def test_the_card_does_not_label_its_own_obvious_parts():
    assert "score/100 · 7d trend · confidence" not in _CARDS, (
        "this caption named the three elements sitting directly above it"
    )
