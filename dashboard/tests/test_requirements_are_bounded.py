"""Every dependency needs an upper bound, not just a lower one.

16 services in render.yaml each run their own `pip install -r
requirements.txt`. With a bare `>=`, each resolves independently at the moment
it builds, so the SAME COMMIT can install different versions on different
services. A resolution that lands on a version with no matching wheel falls
back to a source build — slow and memory-hungry on a small cron instance, and
the likely cause of "the same push built for some services and failed for
others".

It also means a deploy is not reproducible, which quietly undermines verifying
anything at the origin: the artifact you check is not guaranteed to be the
artifact the next service built.

This is the guard, not the cure. The cure is a lockfile generated from a
known-good build. Until that exists, nothing may be added unbounded.
"""

from __future__ import annotations

import re
from pathlib import Path

_REQ = Path(__file__).resolve().parent.parent / "requirements.txt"
_LINES = [
    ln.strip()
    for ln in _REQ.read_text(encoding="utf-8").splitlines()
    if ln.strip() and not ln.strip().startswith("#")
]

# name[extras] then one or more version specifiers
_SPEC = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)(?:\[[^\]]+\])?(?P<vers>.*)$")


def _parsed():
    out = []
    for ln in _LINES:
        m = _SPEC.match(ln)
        assert m, f"cannot parse requirement: {ln!r}"
        out.append((m.group("name"), m.group("vers")))
    return out


def test_the_file_is_not_empty():
    assert len(_LINES) >= 20, f"only {len(_LINES)} requirements parsed — check the format"


def test_every_requirement_has_an_upper_bound():
    unbounded = [name for name, vers in _parsed() if "<" not in vers]
    assert not unbounded, (
        "these can install a new major mid-deploy, and can resolve differently "
        f"on each of the 16 services: {unbounded}"
    )


def test_every_requirement_has_a_lower_bound():
    """An upper bound alone would let pip pick something ancient."""
    missing = [name for name, vers in _parsed() if ">=" not in vers and "==" not in vers]
    assert not missing, f"no minimum version declared: {missing}"


def test_bounds_are_ordered():
    for name, vers in _parsed():
        lo = re.search(r">=\s*([\d.]+)", vers)
        hi = re.search(r"<\s*([\d.]+)", vers)
        if not (lo and hi):
            continue
        def key(v: str):
            return tuple(int(p) for p in v.strip(".").split(".") if p.isdigit())
        assert key(lo.group(1)) < key(hi.group(1)), (
            f"{name}: lower bound {lo.group(1)} is not below upper bound {hi.group(1)}"
        )


def test_no_bare_pins_without_a_recorded_reason():
    """An `==` here is a lockfile in disguise and should be deliberate.

    If exact pins ever land, they should arrive as a real lockfile with a
    comment naming the build they came from — not one-off `==` lines that
    nobody can reproduce.
    """
    pinned = [name for name, vers in _parsed() if "==" in vers]
    if pinned:
        head = _REQ.read_text(encoding="utf-8")[:1200]
        assert "pip freeze" in head or "lockfile" in head.lower(), (
            f"exact pins present ({pinned}) but the file does not say which "
            f"build they were captured from"
        )
