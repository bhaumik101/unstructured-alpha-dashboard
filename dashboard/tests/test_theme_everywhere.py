"""Cross-page guards for light/dark behavioral and presentation consistency."""

from pathlib import Path

from utils.header import _theme_switch_href


ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "utils" / "header.py").read_text(encoding="utf-8")
SPLASH = (ROOT / "scripts" / "inject_boot_splash.py").read_text(encoding="utf-8")
TRACK_RECORD = (ROOT / "pages" / "30_Track_Record_Live.py").read_text(encoding="utf-8")

TOKENIZED_PRESENTATION_FILES = [
    ROOT / "utils" / "command_center.py",
    ROOT / "utils" / "what_changed.py",
    ROOT / "utils" / "score_explainer.py",
    ROOT / "utils" / "portfolio_xray.py",
]


def test_theme_links_preserve_existing_page_query_state():
    assert "def _theme_switch_href(" in HEADER
    assert "st.query_params.get_all(key)" in HEADER
    assert 'href="__LIGHT_THEME_HREF__"' in HEADER
    assert 'href="__DARK_THEME_HREF__"' in HEADER
    assert 'href="?theme=light"' not in HEADER
    assert 'href="?theme=dark"' not in HEADER


def test_theme_href_replaces_only_theme_and_preserves_multi_value_parameters():
    href = _theme_switch_href(
        "dark",
        {
            "ticker": ["BRK.B"],
            "view": ["history"],
            "tag": ["macro", "quality"],
            "theme": ["light"],
        },
    )
    assert href == "?ticker=BRK.B&view=history&tag=macro&tag=quality&theme=dark"


def test_button_labels_inherit_their_actual_button_contrast_color():
    assert ".stFormSubmitButton > button p," in HEADER
    assert 'button[data-testid^="stBaseButton"] p' in HEADER
    assert "color: inherit !important;" in HEADER
    assert 'button[data-testid="stBaseButton-secondary"]' in HEADER


def test_light_plotly_chrome_uses_theme_tokens_without_rewriting_traces():
    prefix = 'html[data-ua-theme="light"] [data-testid="stPlotlyChart"]'
    assert f"{prefix} .main-svg" in HEADER
    assert f"{prefix} .plot-container .bg" in HEADER
    assert ".xtick text, .ytick text, .gtitle, .legendtext" in HEADER
    assert "fill: var(--ua-ink-mut) !important;" in HEADER
    assert ".gridlayer path" in HEADER
    assert ".barlayer .bartext" in HEADER
    assert ".hoverlayer .hovertext path" in HEADER
    assert ".rangeselector .button rect" in HEADER


def test_compact_inline_styles_receive_the_same_semantic_remap():
    # Several page helpers emit minified `;color:#...` rather than browser-
    # normalized `; color: rgb(...)`. These remain delimiter-anchored so a
    # background-color or border-color cannot be changed accidentally.
    for color in ("#00D566", "#34D399", "#FF4D6A", "#F97316", "#7C3AED", "#E8EEFF"):
        assert f'[style*=";color:{color}" i]' in HEADER


def test_mobile_navigation_and_boot_splash_follow_light_theme():
    assert 'html[data-ua-theme="light"] .ua-tnav-links' in HEADER
    assert 'html[data-ua-theme="light"] .ua-tnav-burger span' in HEADER
    assert 'html[data-ua-theme="light"] #ua-boot-splash{background:#F6F5FB;}' in SPLASH
    assert "migration finishes" not in SPLASH
    assert "ua-boot-fact::before{color:#62697E;}" in SPLASH
    assert 'html[data-ua-theme="light"] .ua-guide-step-num' in HEADER


def test_final_render_only_colors_use_theme_tokens():
    assert "--ua-ink-dim:    #747E94;" in HEADER
    assert "--ua-ink-dim-2:  #707A91;" in HEADER
    assert "color:#AAB3C5" not in HEADER

    for path in TOKENIZED_PRESENTATION_FILES:
        source = path.read_text(encoding="utf-8")
        assert "#C3CBE0" not in source
        assert "var(--ua-ink-soft)" in source

    assert 'color:{"var(--ua-green)"' in TRACK_RECORD
    assert 'else "var(--ua-red)"};' in TRACK_RECORD
    assert "rgba(var(--ua-green-rgb),0.27)" in TRACK_RECORD
    assert 'if is_res else "var(--ua-ink-mut)"' in TRACK_RECORD
