"""Render builds only when code a service runs has changed (pipeline minutes)."""

from pathlib import Path

import yaml

BLUEPRINT = Path(__file__).resolve().parent.parent / "render.yaml"


def _services():
    return yaml.safe_load(BLUEPRINT.read_text(encoding="utf-8"))["services"]


def test_docs_tests_and_the_vercel_landing_never_trigger_a_render_build():
    # 18 services each rebuild on every push to main; a docs-only or
    # landing-only merge used to cost 18 pip-install builds.
    for s in _services():
        f = s.get("buildFilter") or {}
        assert f.get("paths") == ["dashboard/**"], s["name"]
        ignored = set(f.get("ignoredPaths") or [])
        assert {"dashboard/docs/**", "dashboard/tests/**", "dashboard/unstructured-alpha-web/**"} <= ignored, s["name"]


def test_retired_jobs_are_not_rebuilt():
    text = BLUEPRINT.read_text(encoding="utf-8")
    retired = [s for s in _services() if f"name: {s['name']}   # RETIRED" in text]
    assert len(retired) == 8
    assert all(s.get("autoDeployTrigger") == "off" for s in retired)
    assert all(s.get("autoDeployTrigger") != "off" for s in _services() if s not in retired)
