"""One type system in the app.

The July redesign paired an editorial serif (Fraunces) hero against Inter
chrome. On 2026-08-02 that pairing was retired: the app now renders Inter
everywhere. The marketing site never used Fraunces, so this also removes a
divergence rather than creating one.

These guard the two ways it could silently come back: a stray font-family
literal in a page, or the shared token quietly resolving to a serif.
"""

from __future__ import annotations

import re
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent
HEADER = (DASHBOARD / "utils" / "header.py").read_text()

# Surfaces intentionally outside this rule:
#   unstructured-alpha-web — the Next.js marketing site, its own type system.
#   utils/email.py         — HTML email. Mail clients do not reliably support
#                            webfonts, so `Georgia, serif` there is a correct
#                            deliberate choice, not a leak of the old hero face.
_EXEMPT_FILES = {"email.py"}
APP_PY = [
    p for p in DASHBOARD.rglob("*.py")
    if "unstructured-alpha-web" not in p.parts
    and "tests" not in p.parts
    and "__pycache__" not in p.parts
    and p.name not in _EXEMPT_FILES
]

# Only font VALUES count. `--ua-serif: var(--ua-display)` is a deprecated alias
# whose name contains "serif" while resolving to Inter — matching on the token
# name instead of the declaration would fail on the very thing keeping old call
# sites safe.
# Capture to the end of the declaration, NOT to the first quote: font stacks
# routinely quote family names ("font-family: 'Fraunces', Georgia, serif"), and
# an earlier version of this pattern excluded quotes — so it captured a single
# space and cheerfully passed while a Fraunces hero sat right there. Caught by
# mutation-testing this file; do not narrow it again.
_FONT_DECL = re.compile(r"font-family\s*:\s*([^;\n]+)", re.I)


def _strip_comments(src: str) -> str:
    """Drop CSS block comments and Python line comments.

    The rationale comments explaining WHY Fraunces was removed legitimately
    name it; only live declarations should fail these tests.
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(l.split("#", 1)[0] for l in src.splitlines())


def test_no_serif_font_is_declared_anywhere_in_the_app():
    offenders = {}
    for path in APP_PY:
        body = _strip_comments(path.read_text())
        for value in _FONT_DECL.findall(body):
            hits = [f for f in ("Fraunces", "Georgia", "Times New Roman")
                    if f in value]
            if re.search(r"(?<!sans-)\bserif\b", value):
                hits.append("serif")
            if hits:
                offenders.setdefault(path.name, set()).update(hits)
    offenders = {k: sorted(v) for k, v in offenders.items()}
    assert not offenders, f"serif faces declared in app surfaces: {offenders}"


def test_display_token_exists_and_is_inter():
    m = re.search(r"--ua-display:\s*([^;]+);", HEADER)
    assert m, "--ua-display token is missing"
    assert "Inter" in m.group(1)
    assert "serif" not in m.group(1).replace("sans-serif", "")


def test_deprecated_serif_alias_still_resolves_to_the_display_face():
    """--ua-serif is kept deliberately.

    Any surface that still says var(--ua-serif) — including ones a grep might
    miss — must land on Inter, not on a browser default serif.
    """
    m = re.search(r"--ua-serif:\s*([^;]+);", HEADER)
    assert m, "--ua-serif alias was removed; old call sites would fall back to serif"
    assert "var(--ua-display)" in m.group(1)


def test_google_fonts_request_no_longer_downloads_fraunces():
    imports = re.findall(r"@import url\(([^)]+)\)", HEADER)
    joined = " ".join(imports)
    assert "Inter" in joined
    assert "Fraunces" not in joined, "still paying for a webfont we do not render"
