"""Every semantic colour rendered as text must be readable in BOTH themes.

The product paints a lot of small tinted pills -- category chips, confidence
badges, status labels, score numerals -- as `color: <hue>` over
`rgba(<same hue>, ~0.1)`. Whether that is legible depends entirely on the hue's
own luminance, and nobody checks a hex value for luminance when adding a
category.

Measured in the browser on Signal Dashboard (2026-08-24, dark theme) there were
132 text nodes below the WCAG AA 4.5:1 threshold, in 10 distinct colour pairs:

    #7C3AED  Macro & Liquidity chip    2.94:1   x28
    #6B7FBF  Neutral status            4.10:1   x38
    #6B7FBF  Low confidence            4.20:1   x38
    #CC3333  Bearish status            3.27:1
    #6B7FBF  provider labels           4.27:1   x17

Light theme was worse for the semantic greens and ambers, which the browser
sample did not happen to render: #00D566 measures 1.81:1 and #F59E0B 1.99:1 on
a white card.

theme.on_tint() keeps each hue's identity and lifts only its lightness until it
clears the threshold. This file asserts that EVERY colour the product uses this
way passes -- so a new category with an unreadable hex fails here instead of
shipping.
"""

from __future__ import annotations

import re

import pytest

from utils.config import CATEGORIES
from utils.theme import (
    _hex_to_rgb,
    contrast_ratio,
    on_tint,
    relative_luminance,
    tint_background,
)

AA_NORMAL = 4.5
THEMES = ("dark", "light")

# The score-intensity ramp in pages/1_Signal_Dashboard.py, plus its status
# fallbacks. Each of these is used as TEXT colour, not only as a border.
STATUS_AND_SCORE_COLORS = (
    "#34D399", "#00A847", "#00D566",   # bullish, deepening with conviction
    "#FF2222", "#CC3333", "#FF4444",   # bearish, deepening with conviction
    "#6B7FBF",                          # neutral / insufficient_data
)

CONFIDENCE_COLORS = ("#00D566", "#F59E0B", "#6B7FBF")

# theme.source_badge's provenance palette. Rendered at 10px on a near-card
# neutral tint, so it gets the same treatment.
PROVENANCE_COLORS = ("#00C8E0", "#F59E0B", "#A78BFA", "#6B7FBF")


# ── the maths itself, against values that cannot drift ───────────────────────

def test_contrast_ratio_matches_known_reference_values():
    black, white = (0, 0, 0), (255, 255, 255)
    assert contrast_ratio(black, white) == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio(white, white) == pytest.approx(1.0, abs=0.001)
    assert contrast_ratio(black, black) == pytest.approx(1.0, abs=0.001)
    # order must not matter
    assert contrast_ratio(black, white) == pytest.approx(contrast_ratio(white, black))


def test_relative_luminance_endpoints():
    assert relative_luminance((0, 0, 0)) == pytest.approx(0.0, abs=1e-9)
    assert relative_luminance((255, 255, 255)) == pytest.approx(1.0, abs=1e-9)


def test_hex_parsing_accepts_short_and_long_forms():
    assert _hex_to_rgb("#FFF") == (255, 255, 255)
    assert _hex_to_rgb("7C3AED") == (124, 58, 237)
    assert _hex_to_rgb("#7c3aed") == (124, 58, 237)


# ── the invariant that matters ───────────────────────────────────────────────

@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("key", sorted(CATEGORIES))
def test_every_category_chip_is_readable(key, theme):
    hue = CATEGORIES[key]["color"]
    pill = tint_background(hue, theme=theme, alpha=0.12)
    text = on_tint(hue, theme=theme, alpha=0.12)
    ratio = contrast_ratio(_hex_to_rgb(text), _hex_to_rgb(pill))
    assert ratio >= AA_NORMAL, (
        f"{CATEGORIES[key]['name']} ({hue}) resolves to {text} on {pill} in "
        f"{theme} theme = {ratio:.2f}:1, below AA {AA_NORMAL}:1"
    )


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("hue", CONFIDENCE_COLORS)
def test_every_confidence_badge_is_readable(hue, theme):
    pill = tint_background(hue, theme=theme, alpha=0.10)
    text = on_tint(hue, theme=theme, alpha=0.10)
    ratio = contrast_ratio(_hex_to_rgb(text), _hex_to_rgb(pill))
    assert ratio >= AA_NORMAL, f"{hue} -> {text} on {pill} ({theme}) = {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("hue", STATUS_AND_SCORE_COLORS)
def test_every_status_and_score_colour_is_readable(hue, theme):
    pill = tint_background(hue, theme=theme, alpha=0.12)
    text = on_tint(hue, theme=theme, alpha=0.12)
    ratio = contrast_ratio(_hex_to_rgb(text), _hex_to_rgb(pill))
    assert ratio >= AA_NORMAL, f"{hue} -> {text} on {pill} ({theme}) = {ratio:.2f}:1"


def test_on_tint_leaves_an_already_compliant_colour_alone():
    """Only failing colours may move, or this silently restyles the product."""
    # #00D566 on the dark tint measures ~7.9:1 and must be returned verbatim.
    assert on_tint("#00D566", theme="dark", alpha=0.10) == "#00D566"
    assert on_tint("#F59E0B", theme="dark", alpha=0.10) == "#F59E0B"


def test_on_tint_actually_moves_a_failing_colour():
    before = contrast_ratio(_hex_to_rgb("#7C3AED"),
                            _hex_to_rgb(tint_background("#7C3AED", theme="dark")))
    after_hex = on_tint("#7C3AED", theme="dark")
    after = contrast_ratio(_hex_to_rgb(after_hex),
                           _hex_to_rgb(tint_background("#7C3AED", theme="dark")))
    assert before < AA_NORMAL <= after, f"{before:.2f} -> {after:.2f}"
    assert after_hex != "#7C3AED"


def test_on_tint_is_deterministic():
    assert on_tint("#7C3AED", theme="dark") == on_tint("#7C3AED", theme="dark")


def test_on_tint_never_raises_on_odd_input():
    for value in ("#FFF", "000000", "#7c3aed"):
        assert re.fullmatch(r"#[0-9A-F]{6}", on_tint(value, theme="light"))


# ── emoji ────────────────────────────────────────────────────────────────────

_EMOJI = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F000-\U0001F2FF" "]"
)


def test_the_signal_card_no_longer_renders_the_category_emoji():
    """The chip already names the category; the emoji was decoration.

    CATEGORIES keeps its `icon` field -- it is config other surfaces may still
    read -- but the signal card renders the name alone.
    """
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1]
              / "pages" / "1_Signal_Dashboard.py").read_text(encoding="utf-8")
    assert "_cat_icon" not in source, (
        "the signal card is rendering the category emoji again"
    )


def test_category_names_themselves_carry_no_emoji():
    offenders = {k: v["name"] for k, v in CATEGORIES.items()
                 if _EMOJI.search(v.get("name", ""))}
    assert not offenders, f"category NAMES contain emoji: {offenders}"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("hue", PROVENANCE_COLORS)
def test_every_provenance_badge_is_readable(hue, theme):
    from utils.theme import INK_BASES
    wash = INK_BASES["wash"][theme]
    pill = tint_background(hue, theme=theme, alpha=0.04, base=wash)
    text = on_tint(hue, theme=theme, alpha=0.04, base=wash)
    ratio = contrast_ratio(_hex_to_rgb(text), _hex_to_rgb(pill))
    assert ratio >= AA_NORMAL, f"{hue} -> {text} on {pill} ({theme}) = {ratio:.2f}:1"


# ── the generated variable layer ─────────────────────────────────────────────
# Pills emit `color: var(--ua-ink-...)`, never a hex. The theme is resolved in
# the BROWSER (?theme= or localStorage['ua-theme']), so the server cannot pick a
# derivation; and remapping an emitted hex via `[style*=";color:#HEX"]` cannot
# work because Streamlit's sanitizer re-serializes inline styles to rgb().


def test_semantic_ink_entries_covers_the_real_palettes():
    """A palette the registry does not know about gets no variable at all."""
    from utils.theme import semantic_ink_entries
    from utils.regime import _label

    hues = {hue.upper() for hue, _a, _b in semantic_ink_entries()}
    missing = {meta["color"].upper() for meta in CATEGORIES.values()} - hues
    assert not missing, f"category hues unregistered: {missing}"

    regime_hues = {
        _label(*args)[1].upper() for args in
        ((0.0, 0.0, False), (0.9, 0.0, True), (0.0, 0.9, True),
         (0.5, 0.0, True), (0.0, 0.5, True), (0.1, 0.1, True))
    }
    assert not (regime_hues - hues), f"regime hues unregistered: {regime_hues - hues}"


@pytest.mark.parametrize("theme", THEMES)
def test_every_registered_ink_clears_aa_in_both_themes(theme):
    """Walk every registered ink and check the value that theme resolves to."""
    from utils.theme import INK_BASES, ink_hex, semantic_ink_entries

    failures = []
    for hue, alpha, base_kind in semantic_ink_entries():
        rendered = ink_hex(hue, alpha=alpha, base_kind=base_kind, theme=theme)
        base = INK_BASES[base_kind][theme]
        pill = tint_background(hue, theme=theme, alpha=alpha, base=base)
        ratio = contrast_ratio(_hex_to_rgb(rendered), _hex_to_rgb(pill))
        if ratio < AA_NORMAL:
            failures.append(
                f"{hue} @{alpha}/{base_kind} -> {rendered} on {pill} = {ratio:.2f}:1"
            )
    assert not failures, (
        f"{len(failures)} registered ink(s) below AA in {theme}:\n  "
        + "\n  ".join(failures)
    )


def test_ink_emits_a_variable_reference_not_a_hex():
    """A hex here is the bug this architecture exists to prevent."""
    from utils.theme import ink
    value = ink("#7C3AED", alpha=0.12, base_kind="card")
    assert value == "var(--ua-ink-7C3AED-12-card)", value
    assert "#" not in value


def test_every_registered_ink_has_a_variable_in_the_built_stylesheet():
    from scripts.inject_boot_splash import build_global_css
    from utils.theme import ink_var_name, semantic_ink_entries

    built = build_global_css()
    assert "__UA_LIGHT_INK_OVERRIDES__" not in built, (
        "the generated-CSS placeholder shipped unsubstituted"
    )
    missing = [
        ink_var_name(hue, alpha=alpha, base_kind=base_kind)
        for hue, alpha, base_kind in semantic_ink_entries()
        if ink_var_name(hue, alpha=alpha, base_kind=base_kind) not in built
    ]
    assert not missing, f"variables never defined: {sorted(set(missing))}"


def test_the_light_block_redefines_only_what_differs():
    """A light block that restates identical values is noise, not intent."""
    from utils.theme import ink_hex, ink_variables_css, semantic_ink_entries

    entries = semantic_ink_entries()
    css = ink_variables_css(entries)
    assert ':root {' in css and 'html[data-ua-theme="light"]' in css
    light_block = css.split('html[data-ua-theme="light"]', 1)[1]
    for hue, alpha, base_kind in entries:
        d = ink_hex(hue, alpha=alpha, base_kind=base_kind, theme="dark")
        l = ink_hex(hue, alpha=alpha, base_kind=base_kind, theme="light")
        from utils.theme import ink_var_name
        name = ink_var_name(hue, alpha=alpha, base_kind=base_kind)
        if d == l:
            assert f"{name}:" not in light_block, (
                f"{name} is identical in both themes but restated in the light block"
            )


def test_no_render_path_guesses_the_theme_at_request_time():
    """The regression this architecture exists to prevent.

    An earlier pass resolved the theme from st.query_params and baked a hex in.
    Every returning light-theme visitor -- theme from localStorage, no query
    param -- got dark inks on a light page: measured 181 sub-AA nodes where
    there had been 7.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for rel in ("utils/theme.py", "utils/header.py", "pages/1_Signal_Dashboard.py"):
        source = (root / rel).read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            code = line.split("#", 1)[0]
            if "active_theme(" in code:
                offenders.append(f"{rel}:{lineno}: {line.strip()[:70]}")
    assert not offenders, (
        "these resolve the theme at request time; the server cannot know it "
        "(localStorage), so emit a var() and let CSS choose:\n  "
        + "\n  ".join(offenders)
    )


# ── muted body/caption tiers ─────────────────────────────────────────────────

MUTED_TIERS = {
    # token            dark fg    light fg   dark bg    light bg
    "--ua-text-lo":  ("#A7B0BF", "#4A5069", "#0B0D12", "#F6F5FB"),
    "--ua-text-cap": ("#8D97A8", "#5E657C", "#0B0D12", "#F6F5FB"),
}


@pytest.mark.parametrize("token", sorted(MUTED_TIERS))
@pytest.mark.parametrize("theme", THEMES)
def test_muted_text_tiers_clear_aa_in_both_themes(token, theme):
    """These carry captions, provenance lines and freshness notes.

    A global override in utils/header.py used to pin this tier to a flat hex.
    No single hex can serve both themes -- #68707E clears light at 4.60:1 and
    fails dark at 3.89:1 -- which is why the rule uses the theme-aware token.
    """
    dark_fg, light_fg, dark_bg, light_bg = MUTED_TIERS[token]
    fg, bg = (dark_fg, dark_bg) if theme == "dark" else (light_fg, light_bg)
    ratio = contrast_ratio(_hex_to_rgb(fg), _hex_to_rgb(bg))
    assert ratio >= AA_NORMAL, f"{token} {fg} on {bg} ({theme}) = {ratio:.2f}:1"


def test_the_dim_override_uses_a_token_not_a_hex():
    from pathlib import Path
    header = (Path(__file__).resolve().parents[1] / "utils" / "header.py").read_text(
        encoding="utf-8"
    )
    block = header[header.index('[style*="color:var(--ua-ink-dim-2)"'):][:600]
    assert "var(--ua-text-cap)" in block, (
        "the ink-dim override should resolve through a theme-aware token"
    )


# ── the surface is an approximation, so the derivation needs headroom ────────

def _shift(hex_value: str, delta: int) -> str:
    from utils.theme import _hex_to_rgb, _rgb_to_hex
    return _rgb_to_hex(tuple(c + delta for c in _hex_to_rgb(hex_value)))


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("delta", (-8, 8))
def test_inks_survive_the_surface_variation_we_actually_observed(theme, delta):
    """INK_BASES is measured on one page; other pages differ.

    The provenance badge composites onto a card on Signal Dashboard and
    straight onto the page background on Market Overview -- about 8 RGB units
    apart, which moved its measured ratio by 0.34 and shipped a 4.42:1 label.
    Deriving to DERIVATION_TARGET rather than exactly AA_TEXT is what absorbs
    that, so this perturbs the base by the observed amount and requires the
    result still clears AA.
    """
    from utils.theme import INK_BASES, ink_hex, semantic_ink_entries

    failures = []
    for hue, alpha, base_kind in semantic_ink_entries():
        rendered = ink_hex(hue, alpha=alpha, base_kind=base_kind, theme=theme)
        shifted = _shift(INK_BASES[base_kind][theme], delta)
        pill = tint_background(hue, theme=theme, alpha=alpha, base=shifted)
        ratio = contrast_ratio(_hex_to_rgb(rendered), _hex_to_rgb(pill))
        if ratio < AA_NORMAL:
            failures.append(
                f"{hue} @{alpha}/{base_kind} -> {rendered} on {pill} = {ratio:.2f}:1"
            )
    assert not failures, (
        f"{len(failures)} ink(s) drop below AA when the surface moves {delta:+d} "
        f"in {theme}:\n  " + "\n  ".join(failures)
    )


def test_the_derivation_aims_above_the_assertion_threshold():
    from utils.theme import AA_TEXT, DERIVATION_TARGET
    assert DERIVATION_TARGET > AA_TEXT, (
        "deriving to exactly the assertion threshold leaves no room for the "
        "measured-surface approximation; that shipped a 4.42:1 label"
    )
