"""Signal Research Center information architecture and lazy-loading guards."""

from pathlib import Path


DASHBOARD = Path(__file__).resolve().parent.parent


def _section_control(app):
    return next(
        control
        for control in app.radio
        if control.key == "signal_research_section_rail"
    )


def test_signal_research_default_is_fast_and_does_not_fetch_live_stack(
    app_test, monkeypatch
):
    import utils.signals_cache as signals_cache

    monkeypatch.setattr(
        signals_cache,
        "get_all_signal_scores",
        lambda: (_ for _ in ()).throw(
            AssertionError("overview must not fetch the live signal stack")
        ),
    )
    app = app_test("pages/51_Signal_Research.py")

    assert not app.exception
    assert _section_control(app).value == "Trust Overview"
    rendered = " ".join(element.value for element in app.markdown)
    rendered += " ".join(element.proto.body for element in app.get("html"))
    assert "The evidence behind the signal stack" in rendered
    assert "Composite models" in rendered


def test_signal_research_sections_render_independently(app_test, monkeypatch):
    import utils.signals_cache as signals_cache

    monkeypatch.setattr(signals_cache, "get_all_signal_scores", lambda: {})
    app = app_test("pages/51_Signal_Research.py")
    section = _section_control(app)

    for label, expected in (
        ("Validation", "Signal-level validation"),
        ("Track Record", "Timestamped calls and realized outcomes"),
        ("Data Quality", "Signal freshness"),
        ("Methodology", "How the signal stack works"),
    ):
        section.set_value(label).run()
        assert not app.exception, f"{label} failed: {list(app.exception)}"
        rendered = " ".join(element.value for element in app.markdown)
        rendered += " ".join(element.proto.body for element in app.get("html"))
        assert expected in rendered
        section = _section_control(app)


def test_overview_cards_open_their_research_section(app_test):
    app = app_test("pages/51_Signal_Research.py")
    button = next(
        button for button in app.button if button.key == "src_open_validation"
    )
    button.click().run()

    assert not app.exception
    assert _section_control(app).value == "Validation"
    assert any(
        "Signal-level validation" in element.value for element in app.markdown
    )


def test_visible_signal_nav_is_consolidated_but_compatibility_routes_remain():
    header = (DASHBOARD / "utils/header.py").read_text(encoding="utf-8")
    app = (DASHBOARD / "app.py").read_text(encoding="utf-8")
    signals_menu = header.split(
        '<span class="ua-tnav-trigger">Signals ', 1
    )[1].split("</div>\n    </div>", 1)[0]

    assert signals_menu.count("<a href=") == 4
    assert "/signal-dashboard" in signals_menu
    assert "/market-overview" in signals_menu
    assert "/sector-view" in signals_menu
    assert "/signal-research" in signals_menu
    for retired_visible_link in (
        "/model-validation",
        "/track-record",
        "/how-signals-work",
        "/data-trust",
        "/power-supercycle",
    ):
        assert retired_visible_link not in signals_menu

    assert 'url_path="signal-research"' in app
    for compatibility_route in (
        'url_path="model-validation"',
        'url_path="track-record"',
        'url_path="how-signals-work"',
        'url_path="data-trust"',
    ):
        assert compatibility_route in app


def test_power_supercycle_moved_to_research_navigation():
    header = (DASHBOARD / "utils/header.py").read_text(encoding="utf-8")
    research_menu = header.split(
        '<span class="ua-tnav-trigger">Research ', 1
    )[1].split("</div>\n    </div>", 1)[0]
    assert "/power-supercycle" in research_menu
