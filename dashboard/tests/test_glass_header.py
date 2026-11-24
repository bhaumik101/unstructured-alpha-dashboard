"""The glass command bar: the nav and the account row as one object.

  * Every glass selector is written once and doubled into the
    html[data-ua-theme] pair -- a bare selector silently loses to the old
    skin (see utils/app_theme.py, SPECIFICITY).
  * The bell keeps the word "Notifications" in its label for screen readers;
    CSS draws only the count.
  * The avatar letter is the only user-derived text that reaches CSS, so it
    is limited to one ASCII letter or digit.
  * The row docks inside the bar only at widths measured to have room, and
    the bar reserves that room.
"""

from __future__ import annotations

import re
from pathlib import Path

from utils import app_theme as at
from utils.header import _avatar_initial

HEADER = (Path(__file__).resolve().parent.parent / "utils" / "header.py").read_text(encoding="utf-8")


def test_every_glass_selector_carries_the_theme_prefix():
    css = at.GLASS_CSS
    assert "@@" not in css and "@@" not in at.PRODUCT_CSS
    assert css.count("{") == css.count("}")
    assert at.GLASS_CSS in at.PRODUCT_CSS
    for block in re.findall(r"([^{}]+)\{[^{}]*\}", css):
        sels = [s.strip() for s in block.split(",") if s.strip()]
        if not sels or sels[0].startswith("@") or sels[0][0].isdigit() or sels[0] in ("from", "to"):
            continue
        for s in sels:
            s = s.split("{")[-1].strip()
            if re.match(r"^\d+%|^from$|^to$", s):
                continue
            assert s.startswith(('html[data-ua-theme="light"]', 'html:not([data-ua-theme="light"])')), s


def test_twin_doubles_each_marked_selector_and_drops_comments():
    out = at._twin('/* a, @@ b */ @@ .x, .y{color:red}')
    assert "/*" not in out
    assert 'html[data-ua-theme="light"] .x' in out and 'html:not([data-ua-theme="light"]) .x' in out
    assert ".y{" in out and 'html[data-ua-theme="light"] .y' not in out


def test_the_bell_keeps_its_word_for_screen_readers():
    assert '_bell_count = f"Notifications **{' in HEADER
    assert 'else "Notifications"' in HEADER
    assert 'icon=":material/notifications:"' in HEADER
    # the word is hidden visually, the bold count is the badge
    assert re.search(r'st-key-ua_bell_"\] button p\{font-size:0!important', at.GLASS_CSS)
    assert ".st-key-ua_bell_unread button p strong{" in at.GLASS_CSS


def test_the_avatar_letter_is_one_safe_character():
    assert _avatar_initial("bg11") == "B"
    assert _avatar_initial("Élan") == "L"            # non-ASCII letters never reach the stylesheet
    assert _avatar_initial("  ✨Zoë") == "Z"
    assert _avatar_initial('";}</style><script>') == "S"
    assert _avatar_initial("✨✨") == "•" and _avatar_initial("") == "•"
    assert 'content:var(--ua-initial,none) / ""' in at.GLASS_CSS   # decorative: no announced letter


def test_the_row_docks_only_where_it_was_measured_to_fit():
    css = at.GLASS_CSS
    dock = css.split("@media (min-width:1320px),(min-width:680px) and (max-width:1000px){")[1].split("@media")[0]
    assert ".st-key-ua_account_row{top:8px!important;right:12px!important;}" in dock
    assert ".ua-topnav{padding-right:138px!important;}" in dock
    assert ":has(.st-key-_notification_tray_toggle) .ua-topnav{padding-right:184px!important;}" in dock


def test_motion_is_off_for_reduced_motion():
    rm = at.GLASS_CSS.split("@media (prefers-reduced-motion:reduce){")[1]
    for frag in (".ua-topnav::after{animation:none", "button p strong{animation:none", 'stIconMaterial"]'):
        assert frag in rm, frag
