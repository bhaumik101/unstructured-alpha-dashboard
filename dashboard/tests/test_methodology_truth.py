"""Regression guards for public methodology and product-fact claims."""

from __future__ import annotations

import ast
from pathlib import Path


PAGES = Path(__file__).resolve().parents[1] / "pages"
ABOUT = PAGES / "8_About.py"
HOW_SIGNALS = PAGES / "39_How_Signals_Work.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_about_is_an_overview_not_a_second_methodology():
    source = _source(ABOUT)
    assert 'sections=("Overview", "Validation Evidence")' in source
    assert 'href="/how-signals-work"' in source
    assert "One canonical methodology" in source


def test_about_uses_derived_product_facts_and_sources():
    source = _source(ABOUT)
    for symbol in (
        "ACTIVE_SIGNAL_COUNT",
        "ACTIVE_SOURCE_COUNT",
        "SUPPORTED_TICKER_COUNT",
        "signal_sources_phrase",
    ):
        assert symbol in source
    assert "platform source families" in source
    assert "not counted as macro signals" in source


def test_about_has_no_literal_metric_placeholders():
    """A plain triple-quoted string previously rendered {ACTIVE_SIGNAL_COUNT}."""
    tree = ast.parse(_source(ABOUT))
    stale_constants = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(
            token in node.value
            for token in (
                "{ACTIVE_SIGNAL_COUNT}",
                "{ACTIVE_SOURCE_COUNT}",
                "{SUPPORTED_TICKER_COUNT}",
            )
        )
    ]
    assert not stale_constants


def test_stale_about_claims_cannot_return():
    source = _source(ABOUT)
    for stale in (
        "38 signals",
        "26 app pages",
        "~6,000",
        "38 × 16 = 608",
        "FRED · EIA · SEC EDGAR · yfinance",
    ):
        assert stale not in source


def test_how_signals_derives_counts_and_provider_inventory():
    source = _source(HOW_SIGNALS)
    assert "ACTIVE_SIGNAL_COUNT" in source
    assert "signal_sources_phrase" in source
    assert "canonical_provider" in source
    assert "_provider_counts = Counter(" in source
    assert "The 47-signal registry" not in source
    assert "all 47 signals" not in source


def test_how_signals_scopes_sec_and_finra_as_per_ticker():
    source = _source(HOW_SIGNALS)
    assert "Separate per-ticker providers" in source
    assert "SEC EDGAR and FINRA support ticker-specific" in source
    assert "do not feed the" in source
    for stale in (
        "Baker Hughes rig count",
        "congressional stock trades",
        "corporate insiders are buying",
    ):
        assert stale not in source


def test_derived_data_sources_section_renders(app_test):
    at = app_test("pages/39_How_Signals_Work.py")
    section = next((r for r in at.radio if r.key == "how_signals_section_rail"), None)
    assert section is not None
    section.set_value("Data Sources").run()
    assert not at.exception
    rendered = " ".join(md.value for md in at.markdown)
    rendered += " " + " ".join(element.proto.body for element in at.get("html"))
    assert "Separate per-ticker providers" in rendered
    assert "SEC EDGAR and FINRA support ticker-specific" in rendered
