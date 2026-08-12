"""Acquisition copy on Home must not render to signed-in users.

"No account needed" is true for a visitor and false for someone who is signed
in. Three instances existed on Home; one was correctly inside `if _anon_user:`
and two were not -- the caption under the hero CTA, and the Instant Macro
Check block's eyebrow and body line. Both rendered to everyone.

The reason the bug was easy to introduce is worth pinning too: `_anon_user`
used to be computed at the "START HERE" guide, several hundred lines *after*
the first copy that should have been reading it, so the flag simply was not in
scope where it was needed. It is now computed immediately after
render_header(), which is what restores the session.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_HOME = _ROOT / "pages" / "home_page.py"
_SRC = _HOME.read_text(encoding="utf-8")
_LINES = _SRC.splitlines()

# Copy that is only true for a visitor without an account.
ANON_ONLY = re.compile(
    r"No account needed|NO ACCOUNT NEEDED|No account required", re.I
)
FLAG = "_anon_user"


def _indent(s: str) -> int:
    return len(s) - len(s.lstrip())


def _is_guarded(lineno: int) -> bool:
    """True if this line only renders for anonymous visitors.

    Three accepted forms: an enclosing `if _anon_user:` block; an inline
    conditional naming the flag on the same line (used inside the f-string
    blocks, which cannot host a statement); or an explicit `# anon-copy-ok`
    marker, for copy that describes the product rather than pitching it.

    The marker is deliberately a source comment and not a list of line numbers
    here -- an exemption should be readable next to the string it exempts, and
    should have to state its reason.
    """
    line = _LINES[lineno - 1]
    if FLAG in line:
        return True

    # An explicit, justified exemption on any of the few lines above.
    seen = 0
    for j in range(lineno - 2, -1, -1):
        prev = _LINES[j]
        if not prev.strip():
            continue
        if "anon-copy-ok" in prev:
            return True
        seen += 1
        if seen >= 6:
            break
    base = _indent(line)
    for j in range(lineno - 2, -1, -1):
        prev = _LINES[j]
        if not prev.strip() or prev.lstrip().startswith("#"):
            continue
        if _indent(prev) < base and prev.lstrip().startswith(("if ", "elif ", "else")):
            if FLAG in prev:
                return True
            base = _indent(prev)
    return False


def test_anon_only_copy_is_guarded_on_home():
    offenders = [
        (i, ln.strip()[:70])
        for i, ln in enumerate(_LINES, 1)
        if ANON_ONLY.search(ln) and not _is_guarded(i)
    ]
    assert not offenders, (
        "this copy renders to signed-in users, for whom it is false:\n"
        + "\n".join(f"  home_page.py:{i}  {t}" for i, t in offenders)
    )


def test_the_auth_flag_is_in_scope_before_the_first_copy_that_needs_it():
    """A flag defined after its first use is how this shipped.

    Guarding is only possible if `_anon_user` exists by the time the first
    piece of acquisition copy is emitted.
    """
    defs = [i for i, ln in enumerate(_LINES, 1)
            if re.match(rf"\s*{FLAG}\s*=", ln)]
    assert defs, f"{FLAG} is not defined in home_page.py"
    first_def = min(defs)

    uses = [i for i, ln in enumerate(_LINES, 1) if ANON_ONLY.search(ln)]
    assert uses, "no acquisition copy found -- re-point this test"
    assert first_def < min(uses), (
        f"{FLAG} is defined at line {first_def} but acquisition copy starts at "
        f"line {min(uses)}; it cannot be guarded before it exists"
    )


def test_the_flag_is_read_from_the_session_not_recomputed_per_block():
    """One definition. Two would drift, and the second would win silently."""
    defs = [i for i, ln in enumerate(_LINES, 1) if re.match(rf"\s*{FLAG}\s*=", ln)]
    assert len(defs) == 1, (
        f"{FLAG} is assigned {len(defs)} times (lines {defs}); keep a single "
        f"definition so every guard reads the same value"
    )
