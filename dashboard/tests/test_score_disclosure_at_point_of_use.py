"""The score's validation status must appear where the score is delivered.

The walk-forward null result — "no statistically significant relationship
between the score and forward returns" — was written down and surfaced on Model
Validation, Signal Research and About. It was NOT on Ticker Deep Dive, which is
where a reader types a ticker and receives a 0-100 number and a conviction
label. The honest finding was two clicks from the confident claim.

That ordering is what an external reviewer encounters first, and it is the
difference between a product that survives inspection and one that does not.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEEP_DIVE = (_ROOT / "pages" / "3_Ticker_Deep_Dive.py").read_text(encoding="utf-8")


def test_the_deep_dive_shows_the_scores_validation_status():
    assert "confluence_disclosure" in _DEEP_DIVE, (
        "the page that delivers the score must also carry its validation status"
    )


def test_the_disclosure_is_rendered_not_merely_imported():
    call = _DEEP_DIVE.index("confluence_disclosure")
    nearby = _DEEP_DIVE[call:call + 600]
    assert "st.caption" in nearby, "importing it without rendering it changes nothing"
    assert "_disc['status']" in nearby and "_disc['detail']" in nearby


def test_the_disclosure_appears_with_the_score_not_buried_at_the_bottom():
    """Below the banner is right; below the page is not."""
    banner = _DEEP_DIVE.index("Confluence Score Banner")
    disclosure = _DEEP_DIVE.index("confluence_disclosure")
    curve = _DEEP_DIVE.index("Macro Conviction Curve")
    assert banner < disclosure < curve, (
        "the validation status belongs immediately after the score banner, "
        "before the page moves on to other content"
    )


def test_the_claim_is_not_restated_in_the_page():
    """One source of truth. A second copy drifts from the first."""
    assert "no statistically significant relationship" not in _DEEP_DIVE, (
        "the wording must come from utils.validation_status, not be duplicated "
        "here where it can quietly diverge from the validation page"
    )


def test_the_disclosure_matches_the_validation_page():
    from utils.validation_status import confluence_disclosure, get_static_validation_summary

    disclosure = confluence_disclosure()
    entry = next(e for e in get_static_validation_summary()
                 if e["category"].startswith("Confluence Score"))
    assert disclosure["detail"] == entry["detail"]
    assert disclosure["status"] == entry["status"]
    assert "not yet mean they're right" in disclosure["detail"]


def test_pcs_is_no_longer_described_as_historically_predictive():
    """PCS is a hand-assigned 1-10 prior, never validated, and since 2026-09-03
    it does not even set the signal's weight."""
    source = (_ROOT / "utils" / "analysis.py").read_text(encoding="utf-8")
    start = source.index("def compute_signal_confidence")
    nxt = source.find("\ndef ", start + 10)
    body = source[start:nxt if nxt != -1 else len(source)]
    # Strip comments: the comment explaining WHY the phrase was removed quotes
    # it, and a naive search would flag the explanation as the offence.
    code = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
    assert "historically predictive" not in code, (
        "PCS was never shown to be predictive; calling it so was the strongest "
        "unearned claim in the product's own copy"
    )
    assert "hand-assigned" in code, "say what PCS actually is"
