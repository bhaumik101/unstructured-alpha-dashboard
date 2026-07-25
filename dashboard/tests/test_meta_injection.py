"""Build-time server-side meta injection for social/SEO crawlers.

Streamlit sets <title> and OG tags via JavaScript, which X/Reddit/Slack crawlers
never execute — so link previews are broken unless the tags are baked into the
served index.html at build time. scripts/inject_boot_splash._inject_meta does
that. These tests lock its contract: title replaced, OG + Twitter tags present,
the count is current (47), and re-running is idempotent (no duplicate blocks).
"""

from __future__ import annotations

import scripts.inject_boot_splash as m

STREAMLIT_HEAD = (
    '<!doctype html><html><head><meta charset="utf-8">'
    "<title>Streamlit</title></head><body><div id=\"root\"></div></body></html>"
)


def test_meta_replaces_title_and_injects_og_and_twitter():
    out, action = m._inject_meta(STREAMLIT_HEAD)
    assert "<title>Streamlit</title>" not in out
    assert f"<title>{m.META_TITLE}</title>" in out
    for needle in ('property="og:title"', 'property="og:description"',
                   'name="twitter:card"', 'name="description"'):
        assert needle in out, needle
    assert "title" in action and "meta" in action


def test_meta_uses_current_signal_count_not_stale_43():
    out, _ = m._inject_meta(STREAMLIT_HEAD)
    assert "47" in m.META_DESC
    assert "43" not in m.META_DESC          # the stale X-cached value must not return
    assert "47" in out and "43 macro" not in out


def test_meta_injection_is_idempotent():
    out1, _ = m._inject_meta(STREAMLIT_HEAD)
    out2, _ = m._inject_meta(out1)
    assert out2.count(m.META_START) == 1     # no duplicated meta block
    assert out2.count("<title>") == 1        # no duplicated title


def test_meta_description_is_on_message():
    assert "first-print" in m.META_DESC.lower()
    assert "no synthetic" in m.META_DESC.lower()
