"""
Unit tests for the audit-trail "evidence" field added to
score_insider_activity(), score_short_interest(), and
score_13f_positioning() in utils/analysis.py -- confirms each score
function returns a well-formed evidence list pointing back to real source
data, not just that the page renders without crashing (which the existing
AppTest-based suite already covers separately).
"""

import pandas as pd

from utils.analysis import score_insider_activity, score_short_interest, score_13f_positioning


def test_insider_evidence_includes_source_url_per_transaction():
    tx_df = pd.DataFrame({
        "date": pd.to_datetime(["2026-06-01", "2026-06-02"]),
        "insider": ["Jane Smith", "John Doe"],
        "role": ["CEO", "Director"],
        "code": ["P", "P"],
        "shares": [1000.0, 500.0],
        "price": [50.0, 52.0],
        "value": [50000.0, 26000.0],
        "accession": ["0001-26-000001", "0001-26-000002"],
        "filer_cik": ["123", "456"],
        "source_url": ["https://www.sec.gov/Archives/edgar/data/123/0001260000011/doc4.xml",
                       "https://www.sec.gov/Archives/edgar/data/456/0001260000021/form4.xml"],
    })
    result = score_insider_activity(tx_df)

    assert len(result["evidence"]) == 2
    for ev in result["evidence"]:
        assert ev["source_url"] is not None
        assert ev["source_url"].startswith("https://www.sec.gov/Archives/edgar/")
        assert "date" in ev and "description" in ev and "value" in ev


def test_insider_evidence_empty_for_no_data():
    result = score_insider_activity(pd.DataFrame())
    assert result["evidence"] == []


def test_insider_evidence_capped_at_20_most_recent():
    n = 35
    tx_df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="D"),
        "insider": [f"Person {i}" for i in range(n)],
        "role": ["Officer"] * n,
        "code": ["P"] * n,
        "shares": [100.0] * n,
        "price": [10.0] * n,
        "value": [1000.0] * n,
        "source_url": [f"https://example.test/{i}" for i in range(n)],
    })
    result = score_insider_activity(tx_df)
    assert len(result["evidence"]) == 20
    # Must be the 20 MOST RECENT, not just any 20.
    assert result["evidence"][0]["date"] == tx_df["date"].max()


def test_short_interest_evidence_has_no_fake_deep_link():
    si_df = pd.DataFrame({
        "date": pd.to_datetime(["2026-05-15", "2026-05-31"]),
        "short_shares": [1_000_000, 1_100_000],
        "change_pct": [5.0, 10.0],
        "days_to_cover": [2.1, 2.4],
    })
    result = score_short_interest(si_df)

    assert len(result["evidence"]) == 2
    for ev in result["evidence"]:
        # FINRA has no stable per-record deep link -- must NOT be faked.
        assert ev["source_url"] is None
        assert "FINRA" in ev["source_label"]


def test_short_interest_evidence_empty_for_no_data():
    result = score_short_interest(pd.DataFrame())
    assert result["evidence"] == []


def test_13f_evidence_includes_source_url_and_trend_description():
    fund_rows = [{
        "fund": "Example Capital", "style": "Value",
        "latest_shares": 10000.0, "latest_period": pd.Timestamp("2026-03-31"),
        "prior_shares": 8000.0, "prior_period": pd.Timestamp("2025-12-31"),
        "latest_source_url": "https://www.sec.gov/Archives/edgar/data/999/000099900001/infotable.xml",
    }]
    result = score_13f_positioning(fund_rows)

    assert len(result["evidence"]) == 1
    ev = result["evidence"][0]
    assert ev["source_url"] == fund_rows[0]["latest_source_url"]
    assert "adding to position" in ev["description"]


def test_13f_evidence_empty_for_no_data():
    result = score_13f_positioning([])
    assert result["evidence"] == []


def test_13f_evidence_handles_missing_source_url_gracefully():
    """Older callers / partial data might not have latest_source_url at
    all -- must not KeyError, just report no source."""
    fund_rows = [{
        "fund": "Example Capital", "style": "Value",
        "latest_shares": 10000.0, "latest_period": pd.Timestamp("2026-03-31"),
        "prior_shares": None, "prior_period": None,
    }]
    result = score_13f_positioning(fund_rows)
    assert result["evidence"][0]["source_url"] is None
