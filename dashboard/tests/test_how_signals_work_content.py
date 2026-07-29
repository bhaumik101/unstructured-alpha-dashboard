"""Guards for the How Signals Work page's mechanism/honesty content and its
signal-count consistency.

The 'Why It Works' section explains WHY macro data can lead price (under-reaction /
gradual information diffusion) and sets honest expectations — the credibility
layer that keeps the product from over-claiming. These tests keep that content
present and keep the on-page signal count aligned with the SSOT.
"""

from __future__ import annotations

import re
from pathlib import Path

from utils.config import SIGNAL_COUNT
from utils.product_metrics import ACTIVE_SIGNAL_COUNT

PAGE = Path(__file__).resolve().parent.parent / "pages" / "39_How_Signals_Work.py"


def _src() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_why_it_works_section_is_in_the_rail_and_rendered():
    src = _src()
    # Present in the section rail tuple AND as a render branch.
    assert '"Why It Works"' in src
    assert '_method_section == "Why It Works"' in src


def test_mechanism_and_honesty_are_both_covered():
    src = _src()
    # The mechanism (why lead times exist) and the honest-limits framing must
    # both be present — one without the other is either hand-wavy or hype.
    assert "under-react" in src.lower()
    assert "time-series momentum" in src.lower()
    assert "out-of-sample" in src.lower()
    # Points users to the measured numbers rather than asserting its own.
    assert "Model Validation" in src


def test_page_signal_count_matches_ssot_everywhere():
    """The education page must render the SSOT instead of copying its value."""
    src = _src()
    assert ACTIVE_SIGNAL_COUNT == SIGNAL_COUNT
    assert "ACTIVE_SIGNAL_COUNT" in src
    hardcoded_counts = set(int(n) for n in re.findall(r"\b(\d+)[ -]signals\b", src))
    assert not hardcoded_counts, f"page hardcodes signal counts: {hardcoded_counts}"
