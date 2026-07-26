"""Static safety guards for the bounded light-mode contrast completion."""

from pathlib import Path


HEADER = (Path(__file__).resolve().parents[1] / "utils" / "header.py").read_text(encoding="utf-8")


def test_inline_remap_is_anchored_to_the_text_color_declaration():
    assert '[style^="color: #00D566" i]' in HEADER
    assert '[style*="; color: #00D566" i]' in HEADER
    assert '[style^="color: rgb(0, 213, 102)" i]' in HEADER
    assert '[style*="; color: rgb(0, 213, 102)" i]' in HEADER
    assert 'html[data-ua-theme="light"] :is(' in HEADER
    assert '[style*="color: #00D566" i]' not in HEADER


def test_semantic_remaps_cover_live_serialized_color_families():
    for serialized_color in (
        "rgb(52, 211, 153)",
        "rgb(255, 68, 68)",
        "rgb(255, 34, 34)",
        "rgb(0, 200, 224)",
        "rgb(14, 165, 233)",
        "rgb(245, 158, 11)",
        "rgb(124, 58, 237)",
        "rgb(107, 127, 191)",
        "rgb(216, 192, 138)",
        "rgb(231, 192, 99)",
    ):
        assert serialized_color in HEADER


def test_light_button_groups_override_late_dark_premium_rules():
    prefix = 'html[data-ua-theme="light"] [data-testid="stButtonGroup"]'
    assert f'{prefix} button,' in HEADER
    assert f'{prefix} button[aria-checked="true"]' in HEADER
    assert "background: var(--ua-bg-card) !important;" in HEADER
    assert "background: rgba(var(--ua-royal-rgb),0.12) !important;" in HEADER


def test_light_semantic_tokens_are_kept_in_sync_with_rgb_triples():
    assert "--ua-green:      #087443;" in HEADER
    assert "--ua-green-rgb:  8,116,67;" in HEADER
    assert "--ua-red:        #B01F2A;" in HEADER
    assert "--ua-red-rgb:    176,31,42;" in HEADER
    assert "--ua-cyan:       #076879;" in HEADER
    assert "--ua-cyan-rgb:   7,104,121;" in HEADER


def test_remapped_small_status_text_does_not_keep_legacy_opacity():
    assert "{ color: var(--ua-green) !important; opacity: 1 !important; }" in HEADER
    assert "{ color: var(--ua-red) !important; opacity: 1 !important; }" in HEADER
    assert "{ color: var(--ua-cyan) !important; opacity: 1 !important; }" in HEADER
