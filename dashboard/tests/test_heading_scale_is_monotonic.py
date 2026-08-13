"""A deeper heading must never render larger than a shallower one.

Measured on the deployed app: h1 28px, h2 20.8px, h3 16.8px — then **h4 24px
and h5 20px**. h4 and h5 had no rule at all, so they kept Streamlit's defaults,
which are larger than this app's h3.

Every page mixing the levels rendered its hierarchy upside down. On Ticker Deep
Dive the h5 subsections were visibly bigger than the h3 section heading above
them. 17 of 22 pages open at h3 or h4, so this was not a corner case.

This is the cheap half of the heading problem: one CSS rule fixes the ordering
on every page at once. The other half — that most pages skip from h1 straight
to h3 or h4 — is 118 markdown headings across 22 pages and is deliberately not
attempted here.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = (Path(__file__).resolve().parent.parent / "utils" / "header.py").read_text(
    encoding="utf-8"
)
_CSS = re.sub(r"/\*.*?\*/", "", _SRC, flags=re.S)

# The token scale, read from source so this cannot drift from the definitions.
_TOKEN_PX = {
    name: round(float(value) * 16, 2)
    for name, value in re.findall(r"--ua-text-([\w]+):\s*([\d.]+)rem", _CSS)
}


def _declared_px(tag: str) -> float:
    """The font-size this tag is given by a bare element rule, in px."""
    for m in re.finditer(r"(?m)^([hH][1-6](?:\s*,\s*[hH][1-6])*)\s*\{([^}]*)\}", _CSS):
        tags = [t.strip().lower() for t in m.group(1).split(",")]
        if tag not in tags:
            continue
        size = re.search(r"font-size:\s*([^;!]+)", m.group(2))
        if not size:
            continue
        raw = size.group(1).strip()
        token = re.match(r"var\(--ua-text-([\w]+)\)", raw)
        if token:
            assert token.group(1) in _TOKEN_PX, f"unknown token in {tag}: {raw}"
            return _TOKEN_PX[token.group(1)]
        rem = re.match(r"([\d.]+)rem", raw)
        if rem:
            return round(float(rem.group(1)) * 16, 2)
        px = re.match(r"([\d.]+)px", raw)
        if px:
            return float(px.group(1))
    return -1.0


def test_every_heading_level_has_a_size():
    missing = [f"h{n}" for n in range(1, 7) if _declared_px(f"h{n}") < 0]
    assert not missing, (
        f"{missing} have no size rule, so they fall back to Streamlit's "
        f"defaults — which are larger than this app's h3"
    )


def test_the_scale_is_monotonic():
    sizes = [(f"h{n}", _declared_px(f"h{n}")) for n in range(1, 7)]
    for (a, sa), (b, sb) in zip(sizes, sizes[1:]):
        assert sa > sb, (
            f"{b} ({sb}px) is not smaller than {a} ({sa}px) — a deeper heading "
            f"rendering larger inverts the hierarchy on every page that mixes "
            f"them. Full scale: {sizes}"
        )


def test_the_new_levels_use_tokens_not_new_literals():
    """The ratchet counts raw font-size values; the scale already exists."""
    for tag in ("h4", "h5", "h6"):
        rule = None
        for m in re.finditer(rf"(?m)^{tag}\s*\{{([^}}]*)\}}", _CSS):
            if "font-size" in m.group(1):
                rule = m.group(1)
        assert rule, f"{tag} has no font-size rule"
        assert "var(--ua-text-" in rule, (
            f"{tag} should size from a --ua-text-* token, not a raw value: {rule.strip()}"
        )
