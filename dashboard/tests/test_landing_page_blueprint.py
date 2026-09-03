"""The landing page moved from Vercel to Render; its blueprint must be complete.

Vercel held this app's environment in its own dashboard. Moving to Render means
render.yaml is now the only declaration of what the service needs, and a variable
the code reads but the blueprint never declares fails SILENTLY in exactly the
places that are hardest to notice:

  TRACK_INGEST_TOKEN unset -> the analytics beacon fails closed by design, so
                              the top of the funnel simply goes invisible
  RESEND_API_KEY unset     -> /api/subscribe errors, the form still looks fine,
                              and it captures nobody

Neither shows up in a health check, so this compares the two lists directly
rather than trusting either to stay in step -- the same approach
test_www_proxies_seo_routes.py takes to the rewrite list.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_BLUEPRINT = yaml.safe_load((_ROOT / "render.yaml").read_text(encoding="utf-8"))
_WEB_DIR = _ROOT / "unstructured-alpha-web"

_SERVICE_NAME = "unstructured-alpha-web"


def _service(name: str) -> dict:
    for svc in _BLUEPRINT["services"]:
        if svc.get("name") == name:
            return svc
    raise AssertionError(f"{name} is not defined in render.yaml")


def _declared_env(name: str) -> set[str]:
    return {e["key"] for e in _service(name).get("envVars", [])}


def _referenced_env() -> set[str]:
    found: set[str] = set()
    for path in list(_WEB_DIR.rglob("*.ts")) + list(_WEB_DIR.rglob("*.tsx")):
        if "node_modules" in path.parts or ".next" in path.parts:
            continue
        found |= set(re.findall(r"process\.env\.([A-Z0-9_]+)", path.read_text(encoding="utf-8")))
    return found


def test_the_landing_page_is_defined_in_the_blueprint():
    svc = _service(_SERVICE_NAME)
    assert svc["type"] == "web"
    assert svc["runtime"] == "node", "Next.js needs the Node runtime, not Python"
    assert svc["rootDir"] == "dashboard/unstructured-alpha-web", (
        "rootDir is relative to the REPO root, not to render.yaml's directory"
    )


def test_every_env_var_the_app_reads_is_declared():
    referenced = _referenced_env()
    declared = _declared_env(_SERVICE_NAME)
    assert referenced, "expected to find process.env references in the app"
    missing = referenced - declared
    assert not missing, (
        f"{sorted(missing)} are read by the landing page but not declared in "
        f"render.yaml. On Vercel these lived in its dashboard; on Render the "
        f"blueprint is the only declaration, and each of these fails silently."
    )


def test_the_analytics_secret_is_shared_with_the_seo_service():
    """Both halves must exist. The values must match, which only the dashboard
    can enforce -- but a missing declaration on either side is catchable here."""
    assert "TRACK_INGEST_TOKEN" in _declared_env(_SERVICE_NAME)
    assert "TRACK_INGEST_TOKEN" in _declared_env("unstructured-alpha-seo")


def test_secrets_are_not_committed_as_values():
    """Every credential must be sync:false so its value lives only in Render."""
    for env in _service(_SERVICE_NAME)["envVars"]:
        if any(word in env["key"] for word in ("TOKEN", "KEY", "SECRET", "PASSWORD")):
            assert env.get("sync") is False, (
                f"{env['key']} must be sync:false, never a literal in git"
            )
            assert "value" not in env, f"{env['key']} must not carry a value in render.yaml"


def test_the_server_binds_to_renders_dynamic_port():
    start = _service(_SERVICE_NAME)["startCommand"]
    assert "$PORT" in start, (
        "Render assigns the listen port dynamically; Next's default localhost:3000 "
        "would never receive proxied traffic"
    )
    assert "0.0.0.0" in start, "binding to localhost only would refuse Render's proxy"


def test_the_proxy_origin_uses_the_private_network():
    """Going back out over seo.unstructuredalpha.com would add a public round
    trip per proxied page and keep a custom domain occupied on a plan that
    includes two."""
    seo_origin = next(
        e for e in _service(_SERVICE_NAME)["envVars"] if e["key"] == "SEO_ORIGIN"
    )
    assert "unstructured-alpha-seo" in seo_origin["value"]
    assert "https://seo." not in seo_origin["value"], (
        "SEO_ORIGIN must point at the internal address, not the public subdomain"
    )


def test_the_app_is_not_configured_for_static_export():
    """It has real server routes; `output: export` would drop them and every
    rewrite with them, turning the SEO consolidation off silently."""
    config = (_WEB_DIR / "next.config.ts").read_text(encoding="utf-8")
    assert 'output: "export"' not in config and "output: 'export'" not in config
    assert (_WEB_DIR / "app" / "api" / "track" / "route.ts").exists(), (
        "if this route ever goes away, re-check whether a static site is viable"
    )
