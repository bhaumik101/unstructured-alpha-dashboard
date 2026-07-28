"""Every signal named on How Signals Work must exist in the signal config.

The page is what a prospective user reads to judge whether the product is
credible. It listed 27 signals across its categories, 9 of which did not exist
in the 47-signal library -- insider/Form 4, 13F positioning, FINRA short
interest, congressional trades, options activity, social sentiment, earnings
transcripts, rig count. Several of those are real capabilities, but they run
per-ticker in Ticker Deep Dive rather than being scored macro signals, so they
now live in a separate clearly-labelled block instead of being counted in the
library.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from utils.config import SIGNALS

PAGE = Path(__file__).resolve().parent.parent / "pages" / "39_How_Signals_Work.py"
_STOP = {"the", "of", "and", "a"}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - _STOP


def _listed_signals() -> list[str]:
    src = PAGE.read_text(encoding="utf-8")
    out: list[str] = []
    for block in re.findall(r'"signals":\s*(\[[^\]]*\])', src, re.S):
        try:
            out.extend(str(x) for x in ast.literal_eval(block))
        except (ValueError, SyntaxError):
            continue
    return out


def _best_overlap(listed: str) -> float:
    """Fraction of the listed name's tokens found in the closest real signal."""
    want = _tokens(listed.split(" (")[0])
    if not want:
        return 0.0
    return max(
        len(want & _tokens(str(cfg.get("name", "")))) / len(want)
        for cfg in SIGNALS.values()
    )


def test_the_page_actually_lists_signals():
    """Guard against the regex silently matching nothing and vacuously passing."""
    assert len(_listed_signals()) >= 20


def test_no_listed_signal_is_absent_from_the_config():
    phantom = [name for name in _listed_signals() if _best_overlap(name) < 0.6]
    assert not phantom, f"listed but not in SIGNALS config: {phantom}"


def test_per_ticker_capabilities_are_scoped_out_of_the_library():
    """13F / insider / short interest are real but are NOT macro signals, so the
    page must say so rather than listing them among the scored signals."""
    src = PAGE.read_text(encoding="utf-8")
    assert "not part of the" in src
    for term in ("Form 4", "13F", "Short interest"):
        assert term in src, f"{term} should still be credited, just scoped correctly"


def test_no_phantom_capability_names_reappear():
    """These were listed as signals but exist nowhere in the codebase."""
    listed = " | ".join(_listed_signals())
    for gone in ("Social Sentiment Index",
                 "Earnings Transcript Sentiment",
                 "Baker Hughes Rig Count",
                 "Congressional Trade Activity"):
        assert gone not in listed
