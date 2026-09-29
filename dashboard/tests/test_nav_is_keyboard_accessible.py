"""The top nav works from a keyboard and survives st.html's sanitizer.

Found by a keyboard walk on 2026-09-29: the Research and Account menus were
<span>s that opened on mouse hover only, so eight pages (Your portfolios,
Pricing, Alerts, Profile, Research record, Track record, Model validation,
Data trust) could not be reached without a mouse. And while fixing it, one CSS
comment that mentioned a button tag made DOMPurify drop the nav's entire
stylesheet -- the bar rendered as a row of bare blue links.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_HEADER = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")
_NAV = _HEADER.split("def _render_topnav", 1)[1].split("\ndef ", 1)[0]


def test_every_style_block_in_the_nav_survives_dompurify():
    """DOMPurify removes a style element whose text matches <[/\\w]."""
    styles = re.findall(r"<style[^>]*>(.*?)</style>", _NAV, flags=re.S)
    assert styles, "the nav's stylesheet was not found"
    for css in styles:
        hit = re.search(r"<[/\w]", css)
        assert not hit, f"tag-like text in the nav stylesheet: {css[max(0, hit.start() - 40):hit.start() + 20]!r}"


def test_the_menu_triggers_are_buttons_that_report_their_state():
    triggers = re.findall(r"<(\w+)[^>]*class=\"ua-tnav-trigger\"[^>]*>", _NAV)
    assert triggers and set(triggers) == {"button"}, triggers
    for name in ("research", "account"):
        assert f'aria-controls="ua-drop-{name}"' in _NAV and f'id="ua-drop-{name}"' in _NAV
    assert 'aria-expanded="false"' in _NAV


def test_menus_open_on_keyboard_focus_not_only_hover():
    assert ".ua-tnav-group:focus-within .ua-tnav-drop" in _HEADER
    assert ".ua-tnav-group.ua-closed .ua-tnav-drop" in _HEADER, "Escape must be able to close one"


def test_a_skip_link_is_the_first_thing_in_the_nav():
    first = re.search(r'<nav class="ua-topnav"[^>]*>\s*(?:<!--.*?-->\s*)*<a ([^>]*)>', _NAV, flags=re.S)
    assert first and 'class="ua-skip"' in first.group(1) and 'href="#ua-main"' in first.group(1)


def test_the_mobile_menu_control_is_a_real_button():
    assert '<button type="button" class="ua-tnav-burger"' in _NAV
    assert 'role="button"' not in _NAV.split('class="ua-tnav-burger"', 1)[0][-200:]


def test_the_runtime_wires_landmark_iframe_and_menu_state():
    from scripts.inject_boot_splash import _build_runtime

    rt = _build_runtime()
    assert "m.id = 'ua-main'; m.setAttribute('role','main')" in rt
    assert "iframe[title*=\"cookie_manager\"]" in rt and "setAttribute('tabindex','-1')" in rt
    assert "ev.key !== 'Escape'" in rt and "aria-expanded" in rt
