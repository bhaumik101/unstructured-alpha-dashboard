"""Production must run the interpreter the tests were run on.

Found in a Render build log while diagnosing four failed cron builds: every
wheel was `cp314`, not one was `cp312`. render.yaml declares `runtime: python`
with no version, so Render was free to take the newest — 3.14 — while
.github/workflows/quality-gate.yml pins 3.12.

So the suite has been passing on 3.12 and production has been running 3.14.
A green suite is a weaker statement than it looks when the interpreter differs,
and it is the kind of gap that surfaces as a runtime error nothing caught.

It also plausibly contributed to the build failures themselves. The immediate
error was a hash mismatch on a downloaded artifact, and 3.14 wheels were days
old at the time — the population where a freshly published or bad artifact is
most likely.

Render reads .python-version from the service's rootDir, and every service in
render.yaml uses `rootDir: dashboard`, so one file covers all 16.
"""

from __future__ import annotations

import re
from pathlib import Path

_DASHBOARD = Path(__file__).resolve().parent.parent
_REPO = _DASHBOARD.parent
_PIN = _DASHBOARD / ".python-version"
_WORKFLOWS = _REPO / ".github" / "workflows"


def _ci_versions() -> list[str]:
    out = []
    for wf in _WORKFLOWS.glob("*.yml"):
        for m in re.finditer(r'python-version:\s*"?([\d.]+)"?', wf.read_text(encoding="utf-8")):
            out.append(m.group(1))
    return out


def test_the_runtime_is_pinned_at_all():
    assert _PIN.is_file(), (
        ".python-version is missing — Render will take the newest Python "
        "available, which is how production ended up on 3.14 while CI ran 3.12"
    )


def test_the_pin_matches_ci():
    pinned = _PIN.read_text(encoding="utf-8").strip()
    ci = _ci_versions()
    assert ci, "no python-version found in any workflow — re-point this test"
    mismatched = [v for v in set(ci) if not v.startswith(pinned) and not pinned.startswith(v)]
    assert not mismatched, (
        f"deploy pins Python {pinned} but CI runs {sorted(set(ci))}. The suite "
        f"would be verifying an interpreter production does not use."
    )


def test_every_python_service_shares_the_root_dir_the_pin_lives_in():
    """One .python-version covers every PYTHON service because they share a rootDir.

    Scoped to the Python runtime deliberately. The landing page is a Node
    service rooted at dashboard/unstructured-alpha-web and has no business
    inheriting an interpreter pin; counting it here would assert something the
    file this test exists to protect does not govern.
    """
    import yaml as _yaml

    spec = _yaml.safe_load((_DASHBOARD / "render.yaml").read_text(encoding="utf-8"))
    python_services = [s for s in spec.get("services", [])
                       if s.get("runtime", "python") == "python"]
    assert python_services, "no python services parsed from render.yaml"
    unrooted = [s["name"] for s in python_services if s.get("rootDir") != "dashboard"]
    assert not unrooted, (
        f"{unrooted} are Python services that do not declare rootDir: dashboard — "
        f".python-version in dashboard/ would not reach them"
    )
