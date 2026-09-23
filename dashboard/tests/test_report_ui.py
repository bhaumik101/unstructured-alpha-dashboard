"""The report's wording and input handling.

Everything a user reads in the exposure report is built by utils/report_ui.py.
These tests check that holdings are understood the way a person would type or
export them, that the sections render every number the engine produced, and
that nothing in the rendered report forecasts or advises.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import exposure as ex  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from tests.test_exposure import _BANNED, _report  # noqa: E402


# ── input ───────────────────────────────────────────────────────────────────

def test_pasted_holdings_accept_common_formats_and_report_what_was_skipped():
    rows, rejected = ui.parse_holdings_text("vti 40\nBND, 30%\n$VXUS\t20\n\nnot a ticker!!\nGLD ten")
    assert [r["ticker"] for r in rows] == ["VTI", "BND", "VXUS"]
    assert [r["weight_pct"] for r in rows] == [40.0, 30.0, 20.0]
    assert rejected == ["not a ticker!!", "GLD ten"]


def test_a_brokerage_export_with_preamble_and_market_values_is_understood():
    csv_bytes = (
        '"Positions for account Individual ...1234 as of 09/12/2026"\n'
        "\n"
        "Symbol,Description,Quantity,Price,Market Value,% of Account\n"
        'VTI,VANGUARD TOTAL STOCK,100,"$300.00","$30,000.00",60%\n'
        'BND,VANGUARD TOTAL BOND,250,$80.00,"$20,000.00",40%\n'
        "Cash & Cash Investments,--,,,$500.00,1%\n"
        "Account Total,,,,$50500,100%\n"
    ).encode()
    rows, rejected = ui.parse_holdings_csv(csv_bytes)
    assert [r["ticker"] for r in rows] == ["VTI", "BND"]
    assert [r["weight_pct"] for r in rows] == [60.0, 40.0], "the weight column wins over value"
    assert rejected == []


def test_a_csv_with_only_market_values_uses_them_as_weights():
    rows, _ = ui.parse_holdings_csv(b"Ticker,Market Value\nAAPL,1000\nMSFT,3000\n")
    key, _notes = ui.prepare_holdings(rows, 15)
    assert dict(key) == {"AAPL": 25.0, "MSFT": 75.0}


def test_a_csv_without_a_ticker_column_says_what_to_fix():
    rows, rejected = ui.parse_holdings_csv(b"Name,Amount\nApple,100\n")
    assert rows == []
    assert "Ticker or Symbol" in rejected[0]


def test_the_cache_key_ignores_order_and_is_normalized():
    a, _ = ui.prepare_holdings([{"ticker": "BND", "weight_pct": 1}, {"ticker": "VTI", "weight_pct": 3}], 15)
    b, _ = ui.prepare_holdings([{"ticker": "vti", "weight_pct": 75}, {"ticker": "BND", "weight_pct": 25}], 15)
    assert a == b


def test_the_free_holding_limit_is_applied_with_a_note():
    rows = [{"ticker": f"T{i}", "weight_pct": 100 - i} for i in range(20)]
    key, notes = ui.prepare_holdings(rows, ui.FREE_MAX_HOLDINGS)
    assert len(key) == ui.FREE_MAX_HOLDINGS
    assert any("largest holdings" in n for n in notes)


# ── rendering ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def report():
    r = _report()
    assert r["status"] == "ok"
    return r


def _visible_text(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def test_the_exposure_table_shows_every_measured_factor_with_its_range(report):
    html = ui.exposure_table_html(report)
    for reading in report["portfolio"]["readings"].values():
        assert reading["label"] in html
        assert ui.fmt_pct(reading["low"]) in html and ui.fmt_pct(reading["high"]) in html
    assert "it is not a forecast" in html


def test_the_strongest_exposures_are_listed_first(report):
    keys = ui.ordered_keys(report)
    assert keys[: len(report["top_exposures"])] == report["top_exposures"]


def test_factor_detail_lists_the_holdings_behind_the_exposure(report):
    html = ui.factor_detail_html(report, "oil")
    assert "XOM" in html and "Contribution" in html


def test_the_summary_names_clear_exposures_and_the_market_control(report):
    text = ui.summary_text(report)
    assert "clearly sensitive to" in text
    assert "stock market" in text


def test_nothing_rendered_forecasts_or_advises(report):
    pieces = [
        ui.summary_text(report), ui.exposure_table_html(report), ui.shifts_html(report),
        ui.recent_moves_html(report), ui.growth_html(report), ui.notes_html(report),
        ui.portfolio_header_html("Test", report), ui.HOW_TO_READ,
        ui.error_html({"status": "error", "message": ui.GENERIC_ERROR}),
    ] + [ui.factor_detail_html(report, k) for k in report["portfolio"]["readings"]]
    for piece in pieces:
        # The disclaimer itself is the one sanctioned use of the word.
        visible = re.sub(r"(?:is|are) not a forecast", "", _visible_text(piece))
        match = _BANNED.search(visible)
        assert not match, f"forward-looking or advisory language: {match.group(0)!r}"


def test_an_error_explains_which_holdings_could_not_be_measured():
    html = ui.error_html({"status": "error", "message": "None of these holdings has history.",
                          "excluded": [{"ticker": "ZZZZ", "weight_pct": 100,
                                        "reason": "no price data was found for this symbol"}]})
    assert "ZZZZ" in html and "no price data" in html


def test_percentages_use_a_real_minus_sign_and_sensible_precision():
    assert ui.fmt_pct(-0.664) == "−0.66%"
    assert ui.fmt_pct(1.614) == "+1.6%"
    assert ui.fmt_pct(0.0) == "0.00%"
    assert ui.fmt_pct(float("nan")) == "—"


# ── errors are never cached ─────────────────────────────────────────────────

def test_a_failed_report_is_retried_instead_of_served_from_cache(monkeypatch):
    calls = {"n": 0}

    def fake(holdings, max_holdings=25):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"status": "error", "message": "provider down", "retryable": True}
        return {"status": "ok", "marker": True}

    monkeypatch.setattr(ex, "build_live_report", fake)
    ui._cached_ok_report.clear()
    key, _ = ui.prepare_holdings([{"ticker": "CACHETEST", "weight_pct": 100}], 15)

    assert ui.get_report(key, 15)["status"] == "error"
    assert ui.get_report(key, 15).get("marker") is True, "the outage was cached"
    assert ui.get_report(key, 15).get("marker") is True
    assert calls["n"] == 2, "a successful report should be served from cache"
    ui._cached_ok_report.clear()


def test_labels_keep_us_capitalised_mid_sentence(report):
    assert ex.lower_label("U.S. dollar") == "U.S. dollar"
    assert ex.lower_label("Interest rates") == "interest rates"
    assert "u.s." not in ui.summary_text(report)


# ── the map ─────────────────────────────────────────────────────────────────

def test_the_map_shows_every_factor_and_agrees_with_the_table(report):
    svg = ui.exposure_map_html(report)
    readings = report["portfolio"]["readings"]
    for key, reading in readings.items():
        if key in ui._MAP_NODES:
            assert reading["label"] in svg
            if reading["evidence"] in ("clear", "tentative"):
                assert ui.fmt_pct(reading["impact"]) in svg
            else:
                assert "no clear link" in svg
    assert 'role="img"' in svg and "aria-label" in svg


def test_a_thin_report_draws_no_map_rather_than_a_misleading_one():
    assert ui.exposure_map_html({"portfolio": {"readings": {}}}) == ""
    one = {"portfolio": {"readings": {"rates": {"label": "Interest rates", "impact": -1.0,
                                                "evidence": "clear"}}}}
    assert ui.exposure_map_html(one) == ""


# ── shareable links ─────────────────────────────────────────────────────────

def test_a_portfolio_survives_a_round_trip_through_a_link():
    rows = [{"ticker": "VTI", "weight_pct": 40.0}, {"ticker": "BND", "weight_pct": 30.0},
            {"ticker": "BRK.B", "weight_pct": 30.0}]
    param = ui.holdings_param(rows)
    assert param == "VTI:40,BND:30,BRK.B:30"
    assert ui.parse_holdings_param(param) == rows


def test_a_link_without_weights_is_accepted_as_equal_weights():
    rows = ui.parse_holdings_param("VTI,BND,GLD")
    assert [r["ticker"] for r in rows] == ["VTI", "BND", "GLD"]
    assert all(r["weight_pct"] is None for r in rows)
    key, notes = ui.prepare_holdings(rows, 15)
    weights = dict(key)
    assert set(weights) == {"VTI", "BND", "GLD"}
    assert sum(weights.values()) == pytest.approx(100.0, abs=0.001)
    assert all(w == pytest.approx(33.33, abs=0.01) for w in weights.values())
    assert any("equally" in n for n in notes)


def test_junk_in_a_link_is_dropped_never_guessed_at():
    rows = ui.parse_holdings_param("VTI:40, ,<script>:10,BND:oops,,TOOLONGATICKERNAME:5")
    assert [r["ticker"] for r in rows] == ["VTI", "BND"]
    assert rows[1]["weight_pct"] is None, "an unreadable weight is not invented"


def test_the_share_url_is_escaped_and_points_at_the_report():
    url = ui.share_url([{"ticker": "BRK.B", "weight_pct": 100}])
    assert url.startswith("https://app.unstructuredalpha.com/?h=")
    assert " " not in url


def test_a_report_prints_as_a_document():
    """Advisers print or save to PDF; the nav, buttons and radio are furniture."""
    assert "@media print" in ui.REPORT_CSS
    for furniture in (".ua-topnav", "stButton", "stRadio"):
        assert furniture in ui.REPORT_CSS.split("@media print")[1].split("}")[0] + \
            ui.REPORT_CSS.split("@media print")[1][:400]


# ── every holding on its own ────────────────────────────────────────────────

def test_the_matrix_gives_each_holding_its_own_row_and_every_factor_a_column(report):
    html = ui.holdings_matrix_html(report)
    for position in report["positions"]:
        assert position["ticker"] in html
        assert f'{position["weight_pct"]:.1f}% of the portfolio' in html
    for key in ui.ordered_keys(report):
        assert report["portfolio"]["readings"][key]["label"] in html


def test_a_holding_with_no_measurable_link_gets_a_dash_not_a_faint_colour(report):
    """A weak reading drawn in a pale tint reads as a weak exposure. It isn't
    one: it is an absence of evidence, and the table has to say so."""
    html = ui.holdings_matrix_html(report)
    weak = [(c["ticker"], k) for k, rows in report["contributions"].items()
            for c in rows if c["evidence"] not in ("clear", "tentative")]
    assert weak, "the fixture no longer exercises the empty case -- re-point this test"
    assert html.count("uar-m-zero") >= len(weak)
    assert "—" in html


def test_a_single_holding_portfolio_draws_no_matrix():
    """One holding IS the portfolio; the table above already says it twice."""
    one = {"positions": [{"ticker": "VTI", "weight_pct": 100.0}],
           "portfolio": {"readings": {"rates": {"label": "Interest rates"}}},
           "top_exposures": ["rates"],
           "contributions": {"rates": [{"ticker": "VTI", "weight_pct": 100.0, "impact": -1.0,
                                        "evidence": "clear", "contribution": -1.0, "share": 1.0}]}}
    assert ui.holdings_matrix_html(one) == ""
    assert ui.holdings_matrix_html({"contributions": {}}) == ""


def test_the_matrix_colours_clear_white_on_a_hue_that_passes_contrast():
    """Measured, not eyeballed.

    The identity hues exist for dots and map lines, where 3:1 is the bar. Behind
    white 13px text they fail AA: #3b7ddd is 4.07:1 and #d99018 is 2.64:1. The
    matrix uses darkened twins, and an outline colour that clears 4.5:1 as text
    in whichever theme it is read in.
    """
    def _luminance(hex_colour: str) -> float:
        channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def _contrast(a: str, b: str) -> float:
        la, lb = _luminance(a), _luminance(b)
        return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

    assert set(ui.FACTOR_FILL) == set(ui.FACTOR_COLORS) == set(ui.FACTOR_INK_DARK)
    for key, fill in ui.FACTOR_FILL.items():
        assert _contrast(fill, "#ffffff") >= 4.5, f"{key}: white on {fill} fails AA"
        assert _contrast(fill, "#ffffff") >= 4.5, key
        assert _contrast(ui.FACTOR_INK_DARK[key], "#121d2f") >= 4.5, (
            f"{key}: outlined text is unreadable on the dark card")
    # And the sheet must actually carry both sets, or the cells fall back.
    for key in ui.FACTOR_FILL:
        assert f"--fd-{key}:" in ui.REPORT_CSS and f"--fh-{key}:" in ui.REPORT_CSS


def test_the_matrix_describes_the_past_and_never_advises(report):
    html = ui.holdings_matrix_html(report)
    visible = re.sub(r"(?:is|are) not a forecast", "", _visible_text(html))
    match = _BANNED.search(visible)
    assert not match, f"forward-looking or advisory language: {match.group(0)!r}"


def test_the_single_company_examples_are_labelled_as_examples():
    """A list of named stocks on the front door is the one place this product
    could be read as recommending something. The page says it isn't."""
    page = (Path(__file__).resolve().parent.parent / "pages" / "60_Exposure_Report.py").read_text()
    assert "ui.SINGLE_STOCKS" in page
    assert "not suggestions" in page
    for ticker, company in ui.SINGLE_STOCKS:
        assert ticker.isupper() and company
