"""Reading holdings out of a brokerage statement.

A workplace plan often offers nothing but a PDF, an adviser gets a client's
statement by email, and "export positions" is three menus deep at most brokers.
Those visitors were being asked to retype a portfolio, and they leave instead.

The failure that matters here is NOT a missed row — someone can see that and
add it. It is a confidently produced portfolio that is not theirs, because
every number downstream then describes something they never held and the report
gives no sign of it. So these tests are mostly about what the parser refuses to
do: guess a symbol, count a total as a holding, or return an empty parse when
the real answer is "this is a scan".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import statement_import as si  # noqa: E402

SCHWAB = """\
Schwab One Account of JANE DOE
Statement Period  August 1-31, 2026
Symbol   Description                      Quantity     Price    Market Value   % Acct
VTI      VANGUARD TOTAL STOCK MKT ETF     100.0000   $300.12     $30,012.00    45.2%
BND      VANGUARD TOTAL BOND MARKET ETF   250.0000    $72.40     $18,100.00    27.3%
AAPL     APPLE INC                         50.0000   $190.55      $9,527.50    14.3%
Cash & Cash Investments                                           $8,760.50    13.2%
Total Account Value                                              $66,400.00   100.0%
"""

PARENTHESISED = """\
Your Portfolio Holdings
FIDELITY 500 INDEX FUND (FXAIX)          Quantity 120.500   $210.33   $25,344.77
VANGUARD TOTAL BOND MKT ETF (BND)        Quantity 200.000    $72.40   $14,480.00
FIDELITY GOVERNMENT MONEY MARKET         Quantity 3,200.00    $1.00    $3,200.00
Total Value                                                          $43,024.77
"""


def _tickers(text: str) -> list[str]:
    rows, _notes = si.parse_statement_text(text)
    return [r["ticker"] for r in rows]


def test_a_positions_table_becomes_holdings():
    rows, notes = si.parse_statement_text(SCHWAB)
    assert [r["ticker"] for r in rows] == ["VTI", "BND", "AAPL"]
    assert rows[0]["name"] == "VANGUARD TOTAL STOCK MKT ETF"
    assert rows[0]["value"] == 30012.0 and rows[0]["weight_pct"] == 45.2
    assert any("cash" in n.lower() for n in notes)


def test_a_fund_named_total_is_not_mistaken_for_the_total_row():
    """The first version matched /total/ anywhere on the line, so "VANGUARD
    TOTAL STOCK MKT ETF" and "VANGUARD TOTAL BOND MARKET ETF" both vanished and
    a three-holding statement parsed as one. Summary language belongs at the
    start of a row."""
    assert "VTI" in _tickers(SCHWAB) and "BND" in _tickers(SCHWAB)


def test_the_symbol_column_wins_over_the_words_of_the_name():
    """Scanning for the last capitalised token before the numbers picked the
    last word of the DESCRIPTION: "APPLE" instead of "AAPL", which is not a
    ticker anyone holds. Column position is the signal."""
    assert "AAPL" in _tickers(SCHWAB)
    assert "APPLE" not in _tickers(SCHWAB)


def test_a_symbol_in_parentheses_is_read_when_there_are_no_columns():
    """PDF text extraction often collapses the column spacing entirely."""
    rows, _ = si.parse_statement_text(PARENTHESISED)
    assert [r["ticker"] for r in rows] == ["FXAIX", "BND"]
    assert rows[0]["name"].startswith("FIDELITY 500 INDEX FUND")


def test_a_pdf_that_collapsed_to_single_spaces_still_parses():
    collapsed = ("Holdings as of 09/18/2026\n"
                 "VTI VANGUARD TOTAL STOCK MKT ETF 100.0000 300.12 30,012.00 45.2%\n"
                 "BND VANGUARD TOTAL BOND MARKET ETF 250.0000 72.40 18,100.00 27.3%\n")
    assert _tickers(collapsed) == ["VTI", "BND"]


def test_totals_cash_and_money_market_lines_are_never_holdings():
    rows, _ = si.parse_statement_text(SCHWAB + PARENTHESISED)
    tickers = [r["ticker"] for r in rows]
    for never in ("CASH", "TOTAL", "NAV", "USD", "VALUE"):
        assert never not in tickers


def test_a_holding_with_no_symbol_is_reported_rather_than_guessed_at():
    """Some statements print fund names only. Inventing a ticker from a name
    would produce a portfolio the visitor never held, and nothing downstream
    would show it."""
    rows, notes = si.parse_statement_text(
        "Holdings\n"
        "Growth Fund of America                     1,200.000    $62.11    $74,532.00\n"
        "Balanced Index Portfolio                     900.000    $33.02    $29,718.00\n")
    assert rows == []
    assert notes and "fund names only" in notes[0]


def test_lines_without_money_on_them_are_not_holdings():
    assert _tickers("Symbol Description Quantity Price\nVTI VANGUARD TOTAL STOCK MKT ETF") == []


def test_the_same_holding_in_two_accounts_is_added_up_once():
    rows, _ = si.parse_statement_text(
        "IRA\nVTI  VANGUARD TOTAL STOCK  10.0  $300.12  $3,000.00\n"
        "Taxable\nVTI  VANGUARD TOTAL STOCK  20.0  $300.12  $6,000.00\n")
    assert [r["ticker"] for r in rows] == ["VTI"]
    assert rows[0]["value"] == 9000.0


# ── weights ─────────────────────────────────────────────────────────────────

def test_the_statements_own_percentages_are_used_when_it_prints_them():
    rows, _ = si.parse_statement_text(SCHWAB)
    draft = si.to_draft(rows)
    assert [d["ticker"] for d in draft] == ["VTI", "BND", "AAPL"]
    assert sum(d["weight_pct"] for d in draft) == pytest.approx(100.0, abs=0.2)
    assert draft[0]["weight_pct"] > draft[1]["weight_pct"] > draft[2]["weight_pct"]


def test_market_values_are_used_when_there_are_no_percentages():
    rows, _ = si.parse_statement_text(PARENTHESISED)
    draft = si.to_draft(rows)
    assert draft[0]["weight_pct"] == pytest.approx(63.6, abs=0.2)
    assert sum(d["weight_pct"] for d in draft) == pytest.approx(100.0, abs=0.2)


def test_an_empty_parse_produces_an_empty_draft_not_a_divide_by_zero():
    assert si.to_draft([]) == []
    equal = si.to_draft([{"ticker": "A", "value": 0.0, "weight_pct": None},
                         {"ticker": "B", "value": 0.0, "weight_pct": None}])
    assert [d["weight_pct"] for d in equal] == [50.0, 50.0]


# ── PDFs ────────────────────────────────────────────────────────────────────

def _pdf(lines: list[str]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", size=9)
    for line in lines:
        pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_a_real_pdf_statement_round_trips():
    data = _pdf([
        "BRIGHTWATER SECURITIES              Account 1234-5678",
        "Symbol   Description                      Quantity     Price    Market Value   % Acct",
        "VTI      VANGUARD TOTAL STOCK MKT ETF     100.0000   $300.12     $30,012.00    45.2%",
        "XOM      EXXON MOBIL CORP                  40.0000   $118.20      $4,728.00     7.1%",
        "Cash & Cash Investments                                           $3,632.50     5.5%",
    ])
    draft, notes = si.read_statement("statement.pdf", data)
    assert [d["ticker"] for d in draft] == ["VTI", "XOM"]
    assert sum(d["weight_pct"] for d in draft) == pytest.approx(100.0, abs=0.2)
    assert any("cash" in n.lower() for n in notes)


def test_a_scanned_pdf_says_it_is_a_scan_rather_than_finding_no_holdings():
    """An empty parse reads as "your statement has no holdings in it", which is
    both wrong and impossible to act on."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    empty = bytes(pdf.output())
    draft, notes = si.read_statement("scan.pdf", empty)
    assert draft == []
    assert notes and "scan" in notes[0].lower()


def test_a_file_that_is_not_a_pdf_at_all_fails_with_a_sentence_not_a_traceback():
    draft, notes = si.read_statement("broken.pdf", b"this is not a pdf")
    assert draft == []
    assert notes and notes[0].endswith(".")


def test_a_text_export_is_read_without_a_pdf_reader():
    draft, notes = si.read_statement(
        "positions.txt",
        b"VTI  VANGUARD TOTAL STOCK MKT ETF  100.0000  $300.12  $30,012.00\n")
    assert [d["ticker"] for d in draft] == ["VTI"]


def test_an_unreadable_file_never_raises():
    for name, data in (("x.pdf", b""), ("x.txt", b"\xff\xfe\x00"), ("x.csv", b"")):
        draft, notes = si.read_statement(name, data)
        assert isinstance(draft, list) and isinstance(notes, list)


def test_the_page_reviews_every_import_before_measuring_it():
    """A statement is read, not understood. Nothing parsed out of one may reach
    the engine without a person having seen it first."""
    page = (_ROOT / "pages" / "60_Exposure_Report.py").read_text(encoding="utf-8")
    assert "Check these before measuring" in page
    assert 'st.session_state["uar_draft"] = found' in page, (
        "an import must land in the editable draft, not go straight to a report"
    )
    assert "draft_editor(" in page


def test_the_uploaders_hidden_input_gets_a_label_from_the_runtime():
    """Streamlit renders the uploader's label as a sibling div and never
    associates it with the hidden <input type=file>, which axe reports as a
    real "form element has no label" failure. Only an attribute fixes it, and
    Streamlit owns that markup — so it is done in the injected runtime, beside
    the other repairs it already makes."""
    from scripts.inject_boot_splash import _build_runtime

    runtime = _build_runtime()
    assert "uaLabelUploads" in runtime
    assert "stFileUploaderDropzoneInput" in runtime
    assert "aria-label" in runtime
    # and it has to keep running: Streamlit rebuilds the widget on every rerun
    assert runtime.count("uaLabelUploads") >= 3, "must run on load and on mutation"
