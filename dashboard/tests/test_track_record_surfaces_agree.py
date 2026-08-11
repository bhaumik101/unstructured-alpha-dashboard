"""Both public track-record surfaces must show the same evidence.

The log is rendered twice: as cards at /track-record, and as a table inside the
Signal Research Center. app.py describes the standalone page as a compatibility
route whose workflow "now lives in Signal Research Center" -- so the table is the
canonical one, and it was the one missing the entry price.

That is the number the entire claim rests on. A reader could see that a call was
made and how it resolved, but not the price it was measured from, on the surface
the product treats as authoritative.

The table also rendered unresolved returns as the literal string "None", because
st.dataframe prints a Python None in an object column verbatim. "None" reads as
a value; an unresolved return is an absence.

Two surfaces over one dataset drift silently. These tests make them fail loudly.
"""

from __future__ import annotations

import sys
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

RESEARCH = DASHBOARD / "pages" / "51_Signal_Research.py"
CARDS = DASHBOARD / "pages" / "30_Track_Record_Live.py"


def test_research_table_shows_the_entry_price() -> None:
    source = RESEARCH.read_text(encoding="utf-8")
    assert '"Entry"' in source, (
        "the canonical track-record table must show the price each call was "
        "measured from"
    )
    assert 'row.get("price_at_event")' in source


def test_research_table_never_prints_the_string_none() -> None:
    """An unresolved return is unknown, not the value None."""
    source = RESEARCH.read_text(encoding="utf-8")
    assert '"4w return": _ret(' in source
    assert '"8w return": _ret(' in source
    assert '"12w return": _ret(' in source
    # The raw pass-through that produced literal "None" cells.
    assert '"4w return": row.get("return_4w")' not in source


def test_both_surfaces_disclose_a_reconstructed_entry() -> None:
    """If one surface marks an estimated price and the other doesn't, the
    unmarked one is quietly the more trustworthy-looking of the two."""
    for path in (RESEARCH, CARDS):
        source = path.read_text(encoding="utf-8")
        assert 'price_source") == "backfilled"' in source, (
            f"{path.name} does not distinguish a reconstructed entry price"
        )
        assert "est." in source, f"{path.name} has no visible marker for it"


def test_the_feed_carries_every_field_both_surfaces_need() -> None:
    """Both read the same helper; if it ever narrows its projection, the
    surfaces lose columns silently rather than erroring."""
    source = (DASHBOARD / "utils" / "prediction_log.py").read_text(encoding="utf-8")
    feed = source.split("def get_predictions_feed", 1)[1].split("\ndef ", 1)[0]
    assert "select(prediction_log)" in feed, (
        "the feed must project every column; a narrowed select would drop "
        "price_at_event or price_source without failing"
    )
