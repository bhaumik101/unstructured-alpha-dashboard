"""Prevent the separate public landing site from drifting from the app theme."""

from pathlib import Path


DASHBOARD = Path(__file__).resolve().parent.parent
WEB = DASHBOARD / "unstructured-alpha-web"
WORKFLOW = DASHBOARD.parent / ".github" / "workflows" / "quality-gate.yml"


def test_public_landing_has_persistent_dark_and_light_themes():
    page = (WEB / "app" / "page.tsx").read_text(encoding="utf-8")
    layout = (WEB / "app" / "layout.tsx").read_text(encoding="utf-8")
    css = (WEB / "app" / "globals.css").read_text(encoding="utf-8")

    assert ':root[data-theme="light"]' in css
    assert "--accent:" in css
    assert "--nav-bg:" in css
    assert 'localStorage.setItem("ua-theme"' in page
    assert 'localStorage.getItem("ua-theme"' in layout
    assert "suppressHydrationWarning" in layout


def test_public_landing_uses_current_brand_and_product_facts():
    page = (WEB / "app" / "page.tsx").read_text(encoding="utf-8")
    layout = (WEB / "app" / "layout.tsx").read_text(encoding="utf-8")
    logo = (WEB / "public" / "logo.svg").read_text(encoding="utf-8")

    assert "47 macro signals" in page
    assert "43 macro signals" not in layout
    assert "next/font/google" not in layout
    assert "#8b7cff" in logo
    assert not any(icon in page for icon in "⚡🔍📋📈🏭🔔📊🏦⚙️")


def test_public_landing_has_an_independent_ci_gate():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "public-landing:" in workflow
    assert "working-directory: dashboard/unstructured-alpha-web" in workflow
    assert "npm ci" in workflow
    assert "npm run lint" in workflow
    assert "npm run build" in workflow
