"""The Pro card reads in one order, and only one thing on it is coloured.

The card worked but was overloaded: a category chip tinted per-category sat
ABOVE the signal's own name, the trend badge repeated the score's direction in
green/red, the confidence badge added a third colour scale, and an unbounded
deviation figure could set the card's width on its own.

HIERARCHY
    1 signal name          the subject, read first
    2 score and direction  the one semantic colour
    3 confidence           neutral, mark-encoded
    4 statistical detail   muted, tabular
    5 source and metadata  provenance last, category demoted to text

NOTHING WAS REMOVED. Dev%, z-score, 4-week trend, lead time, streak, PCS,
category and source are all still on the card. Only their order, weight and
colour changed -- and the deviation CLAMP is display-only, with the exact figure
in the tooltip.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = (
    Path(__file__).resolve().parent.parent / "pages" / "1_Signal_Dashboard.py"
).read_text(encoding="utf-8")


def _pro_card() -> str:
    """The Pro branch's card markup."""
    start = _SRC.index("# ── PRO card: full metrics")
    end = _SRC.index("except Exception as _card_err", start)
    return _SRC[start:end]


def test_the_signal_name_comes_before_the_category_chip():
    card = _pro_card()
    name_at = card.index('{_pulse_dot}{cfg["name"]}')
    cat_at = card.index("{_cat_name}")
    assert name_at < cat_at, (
        "the category chip is rendered before the signal's own name, which puts "
        "a taxonomy label ahead of the thing it labels"
    )


def test_the_score_is_the_only_semantically_coloured_element():
    """`border` is the bull/bear colour. It may appear once."""
    card = _pro_card()
    coloured = re.findall(r"color:\{border\}", card)
    assert len(coloured) == 1, (
        f"the bull/bear colour is applied {len(coloured)} times on the Pro card; "
        "it should carry the score and nothing else"
    )


def test_the_trend_badge_does_not_repeat_direction_in_colour():
    card = _pro_card()
    # Assert the INTERPOLATION, not the name. _pro_trend_badge is assigned in
    # this same block, so `"_pro_trend_badge" in card` stays true even when the
    # markup renders {_trend_badge} instead -- that mutation survived the first
    # version of this test.
    assert "{_pro_trend_badge}" in card, (
        "the Pro card renders the raw {_trend_badge}, which colours the 7-day "
        "direction green/red beside a score already coloured by direction"
    )
    assert "{_trend_badge}" not in card.replace("{_pro_trend_badge}", ""), (
        "the unneutralised trend badge is rendered somewhere on the Pro card"
    )
    assert re.search(r'color:var\\\(--ua-\(green\|red\)\\\)', _SRC) or \
           "color:var(--ua-ink-soft)" in _SRC, (
        "the neutralising substitution is gone"
    )


def test_confidence_is_rendered_neutral():
    card = _pro_card()
    assert "neutral=True" in card, (
        "the Pro confidence badge is tinted again, adding a third colour scale "
        "beside a semantically coloured score"
    )


def test_an_extreme_deviation_cannot_set_the_card_width():
    card = _pro_card()
    # Same trap: _dev_shown is assigned in this block, so its mere presence
    # proves nothing about what the markup interpolates.
    assert "{_dev_shown}%" in card, (
        "the Pro card renders {_dev_fmt}% -- the unclamped figure, which for a "
        "series measured against a near-zero 52-week mean can run to four "
        "digits and set the card's width on its own"
    )
    assert re.search(r"abs\(dev\) >= 1000", _SRC), "the display clamp is gone"
    assert "_dev_title" in card, (
        "the exact deviation is no longer available in a tooltip, so clamping "
        "the display now hides the value instead of just containing it"
    )


def test_the_underlying_values_are_untouched():
    """Clamping is presentation. The numbers themselves must be unchanged."""
    card = _pro_card()
    for token in ("_z_fmt", "_trend_fmt", 'cfg["pcs"]', "lag_weeks", "_streak_label"):
        assert token in card, f"{token} disappeared from the Pro card"
    assert re.search(r"_dev_fmt\s*=\s*f\"\{dev:\+\.1f\}\"", _SRC), (
        "the deviation is being rounded or altered at the source rather than "
        "only in the display"
    )


def test_card_height_is_reserved_rather_than_content_truncated():
    card = _pro_card()
    assert "min-height:172px" in card, "the Pro card lost its reserved height"
    assert "margin-top:auto" in card, (
        "the source row no longer pins to the bottom, so cards of different "
        "content length will not line up"
    )


def test_the_mode_and_layout_toggles_survive_a_theme_change():
    """The theme control is an <a href>, so switching themes NAVIGATES.

    That is a fresh Streamlit session with empty session_state. Without the
    query string, a Pro reader was silently returned to Simple/Cards every time
    they changed theme -- the same failure the Deep Dive rail solves with
    ?section=.
    """
    assert re.search(r'st\.query_params\.get\(_qs_key\)', _SRC), (
        "the toggles no longer read their state from the query string"
    )
    assert re.search(r'st\.query_params\[_qs_key\] = _slug', _SRC), (
        "the toggles no longer publish their state, so a theme change resets them"
    )
    read_at = _SRC.index("st.query_params.get(_qs_key)")
    widget_at = _SRC.index('key="dash_mode"')
    assert read_at < widget_at, (
        "the query string is read after the widget is instantiated, so a direct "
        "link cannot override stale session state"
    )


def test_the_default_selection_is_not_written_to_the_url():
    """A shared link should carry what differs from a first visit, and no more."""
    assert re.search(r"del st\.query_params\[_qs_key\]", _SRC), (
        "returning to Simple/Cards leaves a stale parameter in the URL"
    )


def test_neutral_confidence_keeps_its_level_mark():
    """Dropping the tint must not drop the encoding."""
    theme_src = (
        Path(__file__).resolve().parent.parent / "utils" / "theme.py"
    ).read_text(encoding="utf-8")
    fn = theme_src[theme_src.index("def signal_confidence_badge"):]
    fn = fn[: fn.index("\ndef ")]
    assert "neutral" in fn, "the neutral tone is gone"
    for mark in ("◆", "◇", "○"):
        assert mark in fn, f"the {mark} level mark was removed with the colour"
