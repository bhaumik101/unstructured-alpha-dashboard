"""Guards for the shared, professional workflow-instruction treatment."""

from pathlib import Path


DASHBOARD = Path(__file__).resolve().parents[1]


def test_guided_workflow_component_has_themed_responsive_structure():
    source = (DASHBOARD / "utils" / "header.py").read_text(encoding="utf-8")
    assert "def render_guided_steps(" in source
    assert ".ua-guide-shell" in source
    assert ".ua-guide-grid" in source
    assert "@media (max-width: 900px)" in source
    assert "html_escape(str(_heading))" in source
    assert "html_escape(str(_body))" in source


def test_feature_workflows_use_shared_guidance_instead_of_flat_instruction_boxes():
    pages = (
        "3_Ticker_Deep_Dive.py",
        "28_Export.py",
        "46_Thesis_Journal.py",
    )
    for page_name in pages:
        source = (DASHBOARD / "pages" / page_name).read_text(encoding="utf-8")
        assert "render_guided_steps(" in source, f"{page_name} lacks themed workflow guidance"

    ticker_source = (DASHBOARD / "pages" / "3_Ticker_Deep_Dive.py").read_text(encoding="utf-8")
    assert "HOW TO USE THIS PAGE" not in ticker_source

