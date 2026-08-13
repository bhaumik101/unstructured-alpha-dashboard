"""Motion must stay on the compositor.

The signature-polish layer ships to all 33 routes through the shared
stylesheet, and Signal Dashboard alone renders 47 cards. That makes "which
properties animate" a performance decision, not a style one:

  transform / opacity  -> composited on the GPU, skips layout and paint
  everything else      -> at least a paint, often a full layout pass

The layer this guards replaced a pre-existing `transition: all 0.18s` on every
button. `all` includes width, padding and colour, so each hover risked a layout
pass on an element that only wanted to lift 1px.

Two further rules are pinned here because both are easy to lose in a later
edit and neither shows up in a screenshot:

  - hover effects sit behind @media (hover: hover), so touch devices do not
    latch a stuck hover state on tap
  - reduced motion suppresses TRANSFORMS, not just durations. A 0.01ms
    translate is still a jump; a user asking for reduced motion should get no
    movement at all.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = (Path(__file__).resolve().parent.parent / "utils" / "header.py").read_text(
    encoding="utf-8"
)

_LAYOUT_PROPS = re.compile(
    r"\b(width|height|top|left|right|bottom|margin|padding|font-size|inset)\b"
)


def _polish_block() -> str:
    marker = _SRC.index("SIGNATURE POLISH")
    # Back up to the banner comment's OPENING delimiter. Slicing from the
    # marker itself starts mid-comment, so the opening /* falls outside the
    # slice and the stripper below silently matches nothing — which made these
    # tests fail on prose describing the anti-patterns they ban.
    start = _SRC.rindex("/*", 0, marker)
    end = _SRC.index("@media (prefers-reduced-motion", marker)
    block = _SRC[start:end]
    # Strip comments: they quote the very anti-patterns being banned.
    return re.sub(r"/\*.*?\*/", "", block, flags=re.S)


def test_nothing_animates_a_layout_property():
    block = _polish_block()
    offenders = []
    for decl in re.findall(r"(?:transition|animation):[^;]+;", block):
        flat = " ".join(decl.split())
        if _LAYOUT_PROPS.search(flat):
            offenders.append(flat[:140])
    assert not offenders, (
        "these animate a layout-triggering property; use transform/opacity:\n"
        + "\n".join(offenders)
    )


def test_transition_all_is_not_reintroduced():
    block = _polish_block()
    assert not re.search(r"transition:\s*all\b", block), (
        "`transition: all` animates every property including layout ones — "
        "enumerate the properties instead"
    )


def test_hover_effects_are_gated_for_touch():
    """A tap on a touch device leaves :hover applied until the next tap."""
    block = _polish_block()
    hover_rules = [
        m.start() for m in re.finditer(r":hover", block)
    ]
    assert hover_rules, "expected hover styling in the polish layer"
    gates = [m.start() for m in re.finditer(r"@media \(hover: hover\)", block)]
    assert gates, "no @media (hover: hover) gate found"
    first_gate = min(gates)
    ungated = [h for h in hover_rules if h < first_gate]
    assert not ungated, (
        f"{len(ungated)} hover rule(s) appear before any (hover: hover) gate; "
        f"touch devices will latch them"
    )


def test_reduced_motion_kills_transforms_not_just_durations():
    tail = _SRC[_SRC.index("@media (prefers-reduced-motion") :]
    guard = tail[: tail.index("}\n}") + 3] if "}\n}" in tail else tail[:1200]
    assert "transform: none" in guard, (
        "reduced motion must neutralise transforms — a 0.01ms translate is "
        "still a jump, just a fast one"
    )


def test_the_motion_tokens_exist_and_are_ordered():
    fast = re.search(r"--ua-dur-fast:\s*(\d+)ms", _SRC)
    base = re.search(r"--ua-dur-base:\s*(\d+)ms", _SRC)
    slow = re.search(r"--ua-dur-slow:\s*(\d+)ms", _SRC)
    assert fast and base and slow, "the duration tokens are missing"
    f, b, s = int(fast.group(1)), int(base.group(1)), int(slow.group(1))
    assert f < b < s, f"durations must ascend, got {f}/{b}/{s}"
    assert s <= 400, (
        f"{s}ms is past the point where an interface feels like it is waiting "
        f"on the user"
    )
