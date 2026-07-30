"""Global CSS must be a build-time asset, not a per-rerun websocket payload."""

from __future__ import annotations

from scripts import inject_boot_splash as boot
from utils.header import _CSS
from utils.theme import (
    _COUNTER_CSS,
    _MODERN_UI_CSS,
    _SKELETON_CSS,
    inject_all_css,
)
from utils.ua_charts import CHART_CSS


def test_global_bundle_contains_each_source_once():
    expected = "\n".join(
        (_CSS, _SKELETON_CSS, _COUNTER_CSS, _MODERN_UI_CSS, CHART_CSS)
    )
    assert boot._build_global_css() == expected
    assert len(expected.encode("utf-8")) > 100_000


def test_css_link_is_injected_and_updated_idempotently():
    html = "<html><head></head><body></body></html>"
    injected, action = boot._inject_global_css_link(
        html, "/_stapp/static/ua-global.css?v=one"
    )
    assert action == "css-injected"
    assert injected.count('id="ua-global-css"') == 1

    updated, action = boot._inject_global_css_link(
        injected, "/_stapp/static/ua-global.css?v=two"
    )
    assert action == "css-updated"
    assert updated.count('id="ua-global-css"') == 1
    assert "v=two" in updated and "v=one" not in updated


def test_css_link_fails_closed_without_a_head():
    html, action = boot._inject_global_css_link(
        "<html><body></body></html>",
        "/_stapp/static/ua-global.css?v=one",
    )
    assert action == "css-skipped"
    assert 'id="ua-global-css"' not in html


def test_static_asset_disables_runtime_theme_payload(monkeypatch, tmp_path):
    import streamlit as st
    from utils import theme

    asset = tmp_path / "ua-global.css"
    calls: list[str] = []
    monkeypatch.setattr(theme, "_STATIC_GLOBAL_CSS_PATH", str(asset))
    monkeypatch.setattr(
        st,
        "markdown",
        lambda body, **_kwargs: calls.append(body),
    )

    inject_all_css()
    assert len(calls) == 1  # local-development fallback

    asset.write_text("/* generated */", encoding="utf-8")
    inject_all_css()
    assert len(calls) == 1  # production sends no second CSS payload


def test_generated_asset_is_versioned_and_complete(tmp_path):
    href = boot._write_global_css_asset(str(tmp_path))
    asset = tmp_path / "ua-global.css"
    assert href.startswith("/_stapp/static/ua-global.css?v=")
    assert asset.read_text(encoding="utf-8") == boot._build_global_css()
