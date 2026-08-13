"""Email buttons must survive clients that are not browsers.

utils/email.py is deliberately excluded from the design-token migration: mail
clients do not support CSS custom properties, so a var(--ua-royal) in an email
body silently falls back to the client's default. That exclusion is documented
in test_design_tokens.py, and it is the first thing this file guards.

The rest is Outlook. Outlook on Windows renders through Word, which ignores
padding on an anchor and border-radius entirely — a "button" built as a styled
<a> arrives there as bare underlined text. The VML block gives Word a real
rounded button; every other client skips it inside the mso conditional.
"""

from __future__ import annotations

import re

from utils.email import email_button

BTN = email_button("https://app.unstructuredalpha.com/today-s-brief", "Read today's brief")


def test_no_css_custom_properties():
    """The rule this whole file exists under."""
    assert "var(--" not in BTN, (
        "mail clients do not support CSS custom properties — every colour in "
        "utils/email.py must be a literal"
    )


def test_it_is_a_table_not_a_div():
    """Word's box model is not CSS's; tables are the portable primitive."""
    assert "<table" in BTN and 'role="presentation"' in BTN, (
        "email layout must be table-based, and presentational tables must be "
        "marked role=presentation so screen readers skip them"
    )


def test_outlook_gets_a_vml_button():
    assert "v:roundrect" in BTN, "Outlook/Word needs a VML button"
    assert "[if mso]" in BTN, "the VML must sit inside an mso conditional"
    assert "[if !mso]" in BTN, "non-Outlook clients need the anchor variant"
    assert "w:anchorlock" in BTN, (
        "without anchorlock, Word renders the VML text as editable and the "
        "whole button stops being clickable"
    )


def test_the_anchor_variant_carries_its_own_colours():
    """Clients strip <style> blocks; the resting state must work inline."""
    anchor = BTN[BTN.index("[if !mso]") :]
    assert "background:" in anchor and "color:" in anchor
    assert "padding:" in anchor and "border-radius:" in anchor


def test_no_hover_styles():
    """A hover rule in email is ignored at best and sticky at worst."""
    assert ":hover" not in BTN, (
        "contrast has to work in the resting state; hover is not reliable in "
        "email clients"
    )


def test_the_href_and_label_are_escaped():
    evil = email_button('https://x.test/?a=1"&b=2', '<script>alert(1)</script>')
    assert '"&b=2' not in evil, "the href must be attribute-escaped"
    assert "<script>" not in evil, "the label must be HTML-escaped"
    assert "&lt;script&gt;" in evil


def test_full_width_variant_is_centred():
    wide = email_button("https://x.test", "Go", full_width=True)
    assert 'width="100%"' in wide
    assert 'align="center"' in wide
