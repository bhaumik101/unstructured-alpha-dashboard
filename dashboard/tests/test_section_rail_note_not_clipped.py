"""The section rail must be tall enough for the text it renders.

The rail's bottom padding was 11px, which left its scrollHeight (143px) taller
than its clientHeight (139px). Combined with overflow-y:auto and a rounded
border, the last line of the note -- "…visible while you scroll." -- was sliced
off on every page that renders a section rail. It is small, it is on every page,
and it is the kind of detail that reads as unfinished.

Measured in the browser rather than reasoned about: 12px still clipped, 16px sat
exactly on the boundary with zero slack, 24px cleared it. The value therefore
has to stay >= 20px, and a future tidy-up that "rounds it back down" would
silently restore the bug.
"""

from __future__ import annotations

import re
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent
HEADER = DASHBOARD / "utils" / "header.py"

_SPACING = {"--ua-space-1": 4, "--ua-space-2": 8, "--ua-space-3": 12,
            "--ua-space-4": 16, "--ua-space-5": 24, "--ua-space-6": 32,
            "--ua-space-7": 48, "--ua-space-8": 64}
MIN_BOTTOM_PADDING_PX = 20


def _rail_padding_bottom_px() -> int:
    css = HEADER.read_text(encoding="utf-8")
    block = css.split(".st-key-ua_page_section_rail {", 1)[1].split("}", 1)[0]
    decl = re.search(r"padding:\s*([^;]+);", block)
    assert decl, "the rail no longer declares padding"
    parts = decl.group(1).split()
    bottom = parts[2] if len(parts) >= 3 else parts[-1]

    token = re.match(r"var\((--ua-space-\d)\)", bottom.strip())
    if token:
        return _SPACING[token.group(1)]
    px = re.match(r"(\d+)px", bottom.strip())
    assert px, f"unrecognised padding-bottom value: {bottom!r}"
    return int(px.group(1))


def test_rail_has_room_for_its_last_line() -> None:
    got = _rail_padding_bottom_px()
    assert got >= MIN_BOTTOM_PADDING_PX, (
        f"rail padding-bottom is {got}px; below {MIN_BOTTOM_PADDING_PX}px the "
        "note's final line is clipped by the rounded edge (11px was the bug, "
        "16px is the exact boundary with no slack)"
    )


def test_rail_padding_stays_on_the_spacing_grid() -> None:
    css = HEADER.read_text(encoding="utf-8")
    block = css.split(".st-key-ua_page_section_rail {", 1)[1].split("}", 1)[0]
    decl = re.search(r"padding:\s*([^;]+);", block).group(1)
    assert "var(--ua-space-" in decl, (
        "use a spacing token rather than a one-off px value — the fix for a "
        "clipped element should not introduce a new magic number"
    )
