"""Full names beside tickers (utils/holding_names.py), for readers who do not
know what VTI is.

  * Names come from local sources only, in a fixed order: what the visitor's
    holdings carried, the bundled common-fund table, the curated universe,
    the stock library. An unknown ticker is shown alone, never given a guess.
  * Every report surface that prints a ticker also prints the name.
"""

from __future__ import annotations

import pytest

from tests.test_exposure import _report
from utils import holding_names as hn
from utils import report_ui as ui


@pytest.fixture(autouse=True)
def _clean_memory():
    hn._remembered.clear()
    yield
    hn._remembered.clear()


def test_names_come_from_local_tables_and_unknowns_stay_bare(monkeypatch):
    monkeypatch.setattr(hn, "_library_names", lambda: {})
    assert hn.full_name("VTI") == "Vanguard Total Stock Market ETF"
    assert hn.full_name("bnd") == "Vanguard Total Bond Market ETF"
    assert hn.full_name("NOTREAL") == ""
    assert hn.with_name("NOTREAL") == "NOTREAL"
    assert hn.with_name("GLD") == "GLD (SPDR Gold Shares)"


def test_what_the_visitor_added_wins_and_is_never_the_ticker_again(monkeypatch):
    monkeypatch.setattr(hn, "_library_names", lambda: {})
    hn.remember([{"ticker": "fxaix", "name": "Fidelity 500 Index Fund"}, {"ticker": "ABC", "name": "ABC"}])
    assert hn.full_name("FXAIX") == "Fidelity 500 Index Fund"
    assert hn.full_name("ABC") == ""                      # a "name" that is just the ticker is no name
    hn.remember([{"ticker": "VTI", "name": "Vanguard Total Stock Market Index Fund ETF Shares"}])
    assert hn.full_name("VTI") == "Vanguard Total Stock Market Index Fund ETF Shares"


def test_the_library_fills_in_a_stock_the_tables_lack(monkeypatch):
    monkeypatch.setattr(hn, "_library_names", lambda: {"ZYXW": "Zyxw Holdings Inc."})
    assert hn.full_name("ZYXW") == "Zyxw Holdings Inc."


def test_long_names_are_trimmed_for_labels_only():
    assert hn.short("Vanguard Total International Stock ETF", 20) == "Vanguard Total Inte…"
    assert hn.short("SPDR Gold Shares", 20) == "SPDR Gold Shares"


def test_every_report_surface_names_its_holdings(monkeypatch):
    monkeypatch.setattr(hn, "_library_names", lambda: {})
    r = _report()                                   # holds TLT, XOM, VTI
    for t in ("TLT", "VTI"):
        assert hn.full_name(t), t
    flow = ui.flow_svg(r)
    assert 'class="uar-flow-n"' in flow and hn.short(hn.full_name("VTI"), 32) in flow
    assert f"<title>{hn.with_name('TLT')} →" in flow                 # each ribbon's tooltip
    assert f"aria-label=\"Where each exposure comes from: {hn.with_name('TLT')}" in flow
    card = ui.factor_detail_html(r, "rates")
    assert 'class="uar-hname"' in card and hn.full_name("TLT") in card
    grid = ui.holdings_matrix_html(r)
    assert 'class="uar-hname"' in grid
    head = ui.workspace_header_html("x", r)
    assert f'title="{hn.full_name("VTI")}"' in head and f'<span class="uar-sr"> {hn.full_name("VTI")}</span>' in head
    take = ui.takeaway_html(r)
    for t in ("TLT", "XOM", "VTI"):
        if f"{t} carries" in take or f"{t} (" in take:
            assert f"{hn.with_name(t)} carries" in take, t


def test_an_unknown_holding_gets_no_invented_name(monkeypatch):
    monkeypatch.setattr(hn, "_library_names", lambda: {})
    row = ui.draft_row_html({"ticker": "NOTREAL"})
    assert '<span class="uar-hit-name"></span>' in row
    assert ui._hname("NOTREAL") == ""
