"""What Investor Pro actually gets for $20.

Before this, the only concrete difference between free and paid was 25 holdings
instead of 15 — everything else on the pricing page was "in development". That
is a hard thing to charge for, and the 25 was not even a considered number: it
came from utils/guards.MAX_PORTFOLIO_HOLDINGS, whose comment says "each = 1
full score", sized for the retired scorer's per-ticker price fetch. The
exposure engine does one OLS on 156 weekly returns per holding and shares a
single batched price request across all of them.

These tests pin the three things Pro now has, and the two rules that keep them
honest: a portfolio belongs to exactly one account, and an exported number
carries its evidence label.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_exposure import _report  # noqa: E402
from utils import exposure as ex  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from utils.guards import MAX_EXPOSURE_HOLDINGS, MAX_SAVED_PORTFOLIOS  # noqa: E402


@pytest.fixture(scope="module")
def report():
    r = _report()
    assert r["status"] == "ok"
    return r


# ── the holdings cap ────────────────────────────────────────────────────────

def test_pro_measures_meaningfully_more_than_free():
    assert ui.PRO_MAX_HOLDINGS == MAX_EXPOSURE_HOLDINGS >= 60
    assert ui.PRO_MAX_HOLDINGS >= 3 * ui.FREE_MAX_HOLDINGS


def test_the_exposure_cap_is_separate_from_the_retired_scorers():
    """Raising the old cap would have raised the retired Portfolio Suite's
    per-ticker scoring cost with it, on a 2 GB box. They are different numbers
    because they bound different work."""
    from utils.guards import MAX_PORTFOLIO_HOLDINGS

    assert MAX_EXPOSURE_HOLDINGS != MAX_PORTFOLIO_HOLDINGS
    source = (_ROOT / "utils" / "guards.py").read_text(encoding="utf-8")
    assert "MAX_EXPOSURE_HOLDINGS" in source and "OLS fit" in source


def test_the_cap_can_be_lowered_without_a_deploy():
    source = (_ROOT / "utils" / "guards.py").read_text(encoding="utf-8")
    assert '_cap("MAX_EXPOSURE_HOLDINGS"' in source


def test_nothing_quotes_the_old_number_by_hand():
    """Three places said "25 holdings". Two of them are Python and now read the
    constant; the landing page cannot import it, so it is checked instead."""
    for path in ("utils/billing.py", "pages/65_Pricing.py"):
        text = (_ROOT / path).read_text(encoding="utf-8")
        assert "25 holdings" not in text, path
    landing = (_ROOT / "unstructured-alpha-web" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "up to 25 holdings" not in landing
    assert f"up to {MAX_EXPOSURE_HOLDINGS} holdings" in landing


# ── the CSV ─────────────────────────────────────────────────────────────────

def test_the_csv_carries_every_number_the_page_shows(report):
    text = ui.report_csv(report, "Test portfolio").decode("utf-8")
    assert "Test portfolio" in text
    for key in ui.ordered_keys(report):
        assert report["portfolio"]["readings"][key]["label"] in text
    for row in report["contributions"][ui.ordered_keys(report)[0]]:
        assert row["ticker"] in text


def test_every_exported_number_carries_its_evidence_label(report):
    """A figure lifted out of a spreadsheet without "Not distinguishable from
    zero" beside it is exactly the misuse the report is built to prevent."""
    text = ui.report_csv(report, "Test").decode("utf-8")
    # Only the table, not the metadata block above it -- "Portfolio,Test" is
    # the portfolio's NAME and has no number on it to mislabel.
    table = text[text.index("Scope,Economic force"):]
    data_rows = [r for r in table.splitlines()[1:] if r.strip()]
    labels = set(ex.EVIDENCE_LABELS.values())
    assert data_rows
    for row in data_rows:
        assert any(label in row for label in labels), row


def test_the_csv_says_it_is_not_a_forecast(report):
    assert "Not a forecast" in ui.report_csv(report, "Test").decode("utf-8")


def test_the_csv_is_plain_numbers_not_page_typography(report):
    """The page writes −0.66% with a real minus sign and an em dash for a gap.
    A spreadsheet cannot add those up."""
    text = ui.report_csv(report, "Test").decode("utf-8")
    body = "\n".join(line for line in text.splitlines() if line.startswith(("Portfolio,", "Holding,")))
    assert "−" not in body and "%" not in body and "—" not in body


def test_the_filename_survives_a_portfolio_called_anything():
    name = ui.csv_filename("Client — Smith/Jones (IRA)", "2026-09-18")
    assert name.endswith("-2026-09-18.csv")
    assert "/" not in name and " " not in name
    assert ui.csv_filename("", "2026-09-18").startswith("unstructured-alpha-portfolio")


# ── saved portfolios ────────────────────────────────────────────────────────

def test_saved_portfolios_are_scoped_to_the_account_that_owns_them():
    """A portfolio id is a small integer. Reading one by id alone would let
    anyone page through everybody's holdings."""
    source = (_ROOT / "utils" / "portfolio_workspace.py").read_text(encoding="utf-8")
    body = source[source.index("def list_portfolios"):]
    for function in ("def get_holdings", "def delete_portfolio"):
        block = body[body.index(function):]
        block = block[: block.index("\n\ndef ") if "\n\ndef " in block else len(block)]
        assert "user_id" in block, function
        assert "portfolios.c.user_id" in block, f"{function} must filter on the owner"


def test_the_limit_still_lets_someone_at_the_cap_fix_what_they_have():
    """Refusing an overwrite because the account is full would strand them."""
    source = (_ROOT / "utils" / "portfolio_workspace.py").read_text(encoding="utf-8")
    block = source[source.index("def save_named_portfolio"):]
    assert "clean_name not in existing" in block, (
        "overwriting a name that already exists must always be allowed"
    )


def test_a_saved_portfolio_can_hold_a_pro_sized_list():
    source = (_ROOT / "utils" / "portfolio_workspace.py").read_text(encoding="utf-8")
    assert "normalize_holdings(rows, limit=MAX_EXPOSURE_HOLDINGS)" in source, (
        "saving must not silently truncate a portfolio the engine just measured"
    )


def test_pro_is_worth_more_than_ten_extra_holdings():
    """The point of this change. Behaviour is covered end to end in
    tests/test_redesign_pages.py, which drives the page as a subscriber; this
    only pins that the three things are actually on offer and priced as Pro."""
    from utils.billing import PRO_FEATURES

    assert MAX_SAVED_PORTFOLIOS >= 2
    joined = " ".join(PRO_FEATURES).lower()
    assert "csv" in joined
    assert "saved portfolios" in joined
    assert str(MAX_EXPOSURE_HOLDINGS) in joined

    page = (_ROOT / "pages" / "60_Exposure_Report.py").read_text(encoding="utf-8")
    assert "ui.report_csv(" in page and "save_named_portfolio" in page
