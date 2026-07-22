"""Guards for the compact notification tray and shared text contrast system."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "utils" / "header.py").read_text(encoding="utf-8")
THEME = (ROOT / "utils" / "theme.py").read_text(encoding="utf-8")


def test_notifications_render_in_a_compact_downward_flow_tray():
    assert 'with st.popover(f"Notifications' not in HEADER
    assert 'st.session_state["_notification_tray_open"]' in HEADER
    assert "with st.container(height=340, border=True):" in HEADER
    assert "_notif_space, _notif_panel_col = st.columns([3.65, 1.35])" in HEADER
    assert "limit=10" in HEADER


def test_notification_feed_is_deferred_until_the_tray_is_open():
    open_guard = HEADER.index(
        'if _uid and _notification_api and st.session_state.get("_notification_tray_open", False):'
    )
    feed_fetch = HEADER.index("_get_recent_notifications(limit=10)")
    assert feed_fetch > open_guard


def test_notification_content_is_escaped_before_html_rendering():
    assert '_n_title = html_escape(str(_n.get("title", "")))' in HEADER
    assert '_n_body = html_escape(str(_n.get("body", "")))' in HEADER


def test_shared_text_palette_is_bright_but_restrained():
    assert '--ua-text-mid:   #C5CBD5;' in HEADER
    assert '--ua-text-lo:    #A7B0BF;' in HEADER
    assert '--ua-text-cap:   #8D97A8;' in HEADER
    assert 'TEXT_SECONDARY = "#A7B0BF"' in THEME
    assert 'TEXT_CAPTION   = "#8D97A8"' in THEME
