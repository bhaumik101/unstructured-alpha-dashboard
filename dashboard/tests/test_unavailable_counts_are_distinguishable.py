"""The two "unavailable" counts must say which question they answer.

Observed live on Signal Dashboard: the masthead chip read `⊘ 3` while the
notice a few hundred pixels below read "4 of 47 signals are temporarily
unavailable". Same page, same word, different numbers.

Neither is wrong. They measure different things:

  chip    compute_macro_regime(...).excluded  — signals with no fresh row in
          the latest scoring cycle, read from persisted snapshots (cached 60s)
  notice  count_unavailable_signals(...)      — signals whose live fetch failed
          on this request (sv["unavailable"] or sv["error"])

A signal with a stale-but-present snapshot whose live fetch fails counts in one
and not the other, so they disagree routinely. The product claim here is
first-print honesty, and two contradictory availability numbers on one screen
reads as a bug in exactly the place the app is asking to be trusted.

No number changed. Only the labels, so each states its own scope.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = (Path(__file__).resolve().parent.parent / "utils" / "header.py").read_text(
    encoding="utf-8"
)


def _chip_tooltip() -> str:
    i = _SRC.index("⊘ {_runavail}")
    seg = _SRC[max(0, i - 900) : i]
    titles = re.findall(r'title="([^"]+)"', seg)
    assert titles, "the ⊘ chip has no tooltip"
    return titles[-1]


def _banner_text(headline: str) -> str:
    i = _SRC.index(headline)
    return " ".join(_SRC[i : i + 420].split())


def test_the_chip_says_it_is_about_the_snapshot_cycle():
    tip = _chip_tooltip()
    assert "snapshot" in tip.lower(), (
        f"the ⊘ tooltip must name what it counts — signals with no fresh "
        f"snapshot — not just 'insufficient recent data'. Got: {tip!r}"
    )


def test_the_chip_warns_that_the_other_count_differs():
    """The disagreement is expected, so say so where it is seen."""
    tip = _chip_tooltip().lower()
    assert "disagree" in tip or "different" in tip, (
        f"the ⊘ tooltip should say the notice below counts something else, "
        f"otherwise the mismatch reads as a defect. Got: {tip!r}"
    )


def test_both_banners_scope_themselves_to_this_page_load():
    for headline in ("PARTIAL DATA", "REAL DATA UNAVAILABLE"):
        text = _banner_text(headline)
        assert "on this page load" in text, (
            f"the {headline} notice must scope itself to the live fetch, or it "
            f"reads as contradicting the ⊘ chip. Got: {text[:200]!r}"
        )


def test_the_banner_no_longer_claims_a_bare_temporary_unavailability():
    """"temporarily unavailable" is the wording that collided with ⊘."""
    text = _banner_text("PARTIAL DATA")
    assert "temporarily" not in text, (
        f"'temporarily unavailable' is the phrasing that read as the same "
        f"measurement as the ⊘ chip. Got: {text[:200]!r}"
    )


def test_the_two_counts_still_come_from_different_sources():
    """If they ever became one number this whole file is obsolete — but that is
    a product decision, not a silent refactor."""
    assert "compute_macro_regime(" in _SRC
    assert "count_unavailable_signals(" in _SRC
