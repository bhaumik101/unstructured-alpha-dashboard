"""Regression guards for the shared top-navigation dropdown hierarchy."""

from pathlib import Path


HEADER = Path("utils/header.py").read_text(encoding="utf-8")


def test_dropdown_subpages_have_distinct_bordered_surfaces():
    assert ".ua-tnav-drop a {" in HEADER
    assert "border: 1px solid rgba(var(--ua-onbg-rgb),0.075);" in HEADER
    assert "border-color: rgba(var(--ua-royal-rgb),0.42);" in HEADER
    assert "box-shadow: inset 2px 0 0 rgba(var(--ua-royal-rgb),0.88);" in HEADER


def test_dark_theme_pro_links_have_badge_and_purple_surface():
    assert ".ua-tnav-drop a.pro-link::after {" in HEADER
    assert 'content: "PRO";' in HEADER
    assert "background: rgba(var(--ua-purple-rgb),0.08);" in HEADER
    assert "border-color: rgba(var(--ua-purple-rgb),0.25);" in HEADER


def test_light_theme_keeps_pro_links_distinct():
    assert 'html[data-ua-theme="light"] .ua-tnav-drop a.pro-link {' in HEADER
    assert "color: #6D4FC2 !important;" in HEADER
    assert 'html[data-ua-theme="light"] .ua-tnav-drop a.pro-link::after {' in HEADER
    assert "color: #4B2A91 !important;" in HEADER
    assert "background: rgba(var(--ua-purple-rgb),0.14) !important;" in HEADER
    assert "border-color: rgba(var(--ua-purple-rgb),0.42) !important;" in HEADER


def test_light_theme_pro_status_keeps_admin_gold_override():
    assert 'html[data-ua-theme="light"] .ua-tnav-pro:not(.ua-tnav-admin) {' in HEADER
    assert "color: #4B2A91;" in HEADER
