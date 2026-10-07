"""The public pages' app links go to the app, not the marketing site.

unstructuredalpha.com redirects to the www landing page, so an APP_URL on the
apex sent every "Open the interactive report", "Methodology" and "Stress-test
it" link to a 404. The SEO service's APP_URL (render.yaml and its default)
must be the same host the landing page links to.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _landing_app_url() -> str:
    page = (ROOT / "unstructured-alpha-web" / "app" / "page.tsx").read_text(encoding="utf-8")
    return re.search(r'const APP_URL = "([^"]+)"', page).group(1)


def test_render_gives_the_seo_service_the_landing_pages_app_url():
    services = yaml.safe_load((ROOT / "render.yaml").read_text())["services"]
    env = {}
    for s in services:
        for e in s.get("envVars", []) or []:
            if e.get("key") == "SEO_BASE_URL":
                env = {x["key"]: x.get("value") for x in s["envVars"]}
    assert env.get("APP_URL") == _landing_app_url() == "https://app.unstructuredalpha.com"


def test_the_code_default_matches():
    src = (ROOT / "seo" / "main.py").read_text(encoding="utf-8")
    assert f'os.environ.get("APP_URL", "{_landing_app_url()}")' in src
