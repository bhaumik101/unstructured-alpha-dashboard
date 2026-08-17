"""Both themes must be legible, and the light-theme remapper must stay complete.

Measured on the deployed app 2026-08-17, authenticated, both themes:

  Ticker Deep Dive, light   92 of 583 text nodes below WCAG AA
  Ticker Deep Dive, dark    97 of 597
  worst light               1.08:1  "Analyze ticker" (the primary CTA)
                            2.10:1  "Why it matters:"

The cause was NOT the token palette. Every light token pair clears AA (worst
5.34:1); only two dark pairs fail, and both are blocked from correction by
non-CSS consumers (see _KNOWN_LOW below).

The cause is how inline colours are re-mapped for the light theme. Pages emit
dark-theme hex inline -- `color:#8892AA` appears inline 45 times, `#E8EEFF` 32,
`#B8C0D4` 14 -- and header.py flips them with attribute selectors that match the
STRING, so each colour needs every spelling the codebase actually emits:

    [style^="color: #X"]     start, with space
    [style^="color:#X"]      start, no space      <-- was missing for all 35
    [style*="; color: #X"]   mid,   with space
    [style*=";color:#X"]     mid,   no space

`utils/score_attribution.py` emits `style="color:#B79CFF;font-weight:600;"` --
start of attribute, no space -- which matched none of the three forms that
existed, so it stayed light purple on a light background at 2.10:1.

This test pins the completeness of that mapping. It is a stopgap by design: the
real fix is emitting tokens instead of hex, which is Phase 1 of the design-system
work. Until then, an incomplete mapping is invisible until someone opens the
light theme on the right page.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = (Path(__file__).resolve().parent.parent / "utils" / "header.py").read_text(
    encoding="utf-8"
)

AA_NORMAL = 4.5


# ── contrast maths ────────────────────────────────────────────────────────────
def _rgb(v: str) -> tuple[float, float, float]:
    v = v.strip()
    if v.startswith("#"):
        return tuple(int(v[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
    nums = [float(x) for x in re.findall(r"[\d.]+", v)]
    return tuple(nums[:3])  # type: ignore[return-value]


def _lum(c) -> float:
    out = []
    for v in c:
        v /= 255.0
        out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a: str, b: str) -> float:
    la, lb = _lum(_rgb(a)), _lum(_rgb(b))
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _tokens(block: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for m in re.finditer(r"--ua-([\w-]+):\s*(#[0-9A-Fa-f]{6}|rgba?\([^)]+\))", block):
        found.setdefault(m.group(1), m.group(2))
    return found


def _dark() -> dict[str, str]:
    i = _SRC.index("--ua-bg:")
    return _tokens(_SRC[i : i + 6000])


def _light() -> dict[str, str]:
    i = _SRC.index("--ua-bg:", _SRC.index('data-ua-theme="light"'))
    return _tokens(_SRC[i : i + 3000])


INKS = ["text-hi", "text-mid", "text-lo", "text-cap", "text", "muted",
        "ink", "ink-mut", "ink-label", "ink-soft", "ink-dim"]
SURFACES = ["bg", "bg-card", "bg-raised"]

# Pairs below AA that CANNOT be fixed by editing the hex, because the value is a
# semantic constant with non-CSS consumers. Traced 2026-08-17:
#
#   ink-label #6B7FBF -> utils/theme.py NEUTRAL, utils/regime.py (MIXED SIGNALS),
#     utils/analysis.py, utils/webhook.py (0x6B7FBF, integer-parsed for Discord),
#     utils/lead_time_ui.py (Plotly title_font), --ua-label-rgb 107,127,191,
#     tests/test_price_chart.py
#   ink-dim   #747E94 -> utils/price_chart.py "faint", tests/test_theme_everywhere.py
#
# Correcting these means a coordinated change across all of the above, not a CSS
# edit. Until then they are recorded here so they cannot silently get WORSE, and
# so nobody "fixes" the token in isolation and desyncs it from NEUTRAL.
_KNOWN_LOW = {
    ("ink-label", "bg-raised"): 4.28,
    ("ink-dim", "bg-card"): 4.48,
    ("ink-dim", "bg-raised"): 4.07,
}


def test_light_theme_tokens_all_meet_aa():
    """The light palette has no excuses — every pair must clear AA."""
    t = _light()
    bad = []
    for ink in INKS:
        for surf in SURFACES:
            if ink not in t or surf not in t:
                continue
            r = contrast(t[ink], t[surf])
            if r < AA_NORMAL:
                bad.append(f"{ink} on {surf}: {r:.2f}")
    assert not bad, "light theme token pairs below AA:\n" + "\n".join(bad)


def test_dark_theme_tokens_meet_aa_except_the_traced_constants():
    t = _dark()
    bad = []
    for ink in INKS:
        for surf in SURFACES:
            if ink not in t or surf not in t:
                continue
            r = contrast(t[ink], t[surf])
            if r >= AA_NORMAL:
                continue
            known = _KNOWN_LOW.get((ink, surf))
            if known is None:
                bad.append(f"NEW failure {ink} on {surf}: {r:.2f}")
            elif r < known - 0.01:
                bad.append(f"REGRESSED {ink} on {surf}: {r:.2f} (was {known})")
    assert not bad, "\n".join(bad)


def test_known_low_pairs_are_still_low_or_the_allowlist_is_stale():
    """If someone does the coordinated fix, this fails and prompts the cleanup."""
    t = _dark()
    fixed = []
    for (ink, surf), was in _KNOWN_LOW.items():
        if ink in t and surf in t and contrast(t[ink], t[surf]) >= AA_NORMAL:
            fixed.append(f"{ink}/{surf} now passes — remove it from _KNOWN_LOW")
    assert not fixed, "\n".join(fixed)


# ── the remapper ──────────────────────────────────────────────────────────────
def _remap_hexes() -> set[str]:
    return {m.group(1).upper() for m in
            re.finditer(r'\[style\^="color: (#[0-9A-Fa-f]{3,8})" i\]', _SRC)}


def test_every_remapped_colour_has_all_four_spellings():
    """The bug this file exists for.

    A colour mapped in only three of the four forms is silently unmapped for any
    call site that emits the fourth. `color:#B79CFF` at the start of a style
    attribute is exactly that case, and it shipped at 2.10:1.
    """
    missing = []
    for hexv in sorted(_remap_hexes()):
        forms = {
            "start+space": f'[style^="color: {hexv}" i]',
            "start+nospace": f'[style^="color:{hexv}" i]',
            "mid+space": f'[style*="; color: {hexv}" i]',
            "mid+nospace": f'[style*=";color:{hexv}" i]',
        }
        absent = [k for k, sel in forms.items() if sel.lower() not in _SRC.lower()]
        if absent:
            missing.append(f"{hexv}: missing {', '.join(absent)}")
    assert not missing, (
        "these inline colours are only partly remapped for the light theme, so "
        "some call sites keep their dark-theme colour on a light background:\n"
        + "\n".join(missing)
    )


def test_the_remapper_covers_the_colours_pages_actually_emit():
    """Coverage is measured against real emission, not against a wish list."""
    root = Path(__file__).resolve().parent.parent
    emitted: dict[str, int] = {}
    for path in list(root.glob("pages/*.py")) + list(root.glob("utils/*.py")):
        if path.name == "header.py":
            continue
        for m in re.finditer(r"color:\s*(#[0-9A-Fa-f]{6})", path.read_text(encoding="utf-8")):
            emitted[m.group(1).upper()] = emitted.get(m.group(1).upper(), 0) + 1

    mapped = _remap_hexes()
    # #FFFFFF is deliberately NOT remappable. It is emitted both standalone and
    # as `background:#6D28D9;color:#FFFFFF`, where white is correct. A blanket
    # remap would break every badge and filled button. The standalone uses need
    # per-site treatment (the "Analyze ticker" CTA measured 1.08:1 in light for
    # exactly this reason) and belong to the component phase, not to a colour map.
    emitted.pop("#FFFFFF", None)
    # Only the ones emitted enough to matter; a single decorative use is noise.
    heavy = {h: n for h, n in emitted.items() if n >= 10}
    unmapped = {h: n for h, n in heavy.items() if h not in mapped}
    assert not unmapped, (
        "these hex colours are emitted inline 10+ times but have no light-theme "
        f"remap, so they keep their dark value on a light page: {unmapped}"
    )
