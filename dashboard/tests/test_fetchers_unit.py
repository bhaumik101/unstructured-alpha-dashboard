"""
Unit tests for utils/fetchers.py's parsing logic, with the network layer
mocked out — these run offline and verify two things:

1. fetch_fred() / fetch_eia() correctly parse a real response shape.
2. Missing credentials and failures return explicitly unavailable empty data;
   no provider path manufactures observations.

The EIA response fixture below is the exact JSON shape captured live from
api.eia.gov/v2/seriesid/PET.WCESTUS1.W with a real key (verified directly
against the live API, not assumed) — this locks that parsing path in so a
future change to fetch_eia() can't silently break it.
"""

from unittest.mock import patch, MagicMock

import pandas as pd
import streamlit as st

from utils.fetchers import (
    fetch_fred, fetch_eia, fetch_fda_approval_velocity, fetch_live_quote,
    fetch_insider_transactions_detail, fetch_short_interest, fetch_13f_holdings,
    is_unavailable,
)


EIA_RESPONSE_FIXTURE = {
    "response": {
        "total": 2,
        "dateFormat": "YYYY-MM-DD",
        "frequency": "weekly",
        "data": [
            {
                "period": "2026-06-12", "duoarea": "NUS", "area-name": "U.S.",
                "product": "EPC0", "product-name": "Crude Oil",
                "process": "SAX", "process-name": "Ending Stocks Excluding SPR",
                "series": "WCESTUS1",
                "series-description": "U.S. Ending Stocks excluding SPR of Crude Oil (Thousand Barrels)",
                "value": 418222, "units": "MBBL",
            },
            {
                "period": "2026-06-05", "duoarea": "NUS", "area-name": "U.S.",
                "product": "EPC0", "product-name": "Crude Oil",
                "process": "SAX", "process-name": "Ending Stocks Excluding SPR",
                "series": "WCESTUS1",
                "series-description": "U.S. Ending Stocks excluding SPR of Crude Oil (Thousand Barrels)",
                "value": 426485, "units": "MBBL",
            },
        ],
    }
}

FRED_RESPONSE_FIXTURE = {
    "observations": [
        {"date": "2026-06-01", "value": "100.5"},
        {"date": "2026-06-08", "value": "101.2"},
    ]
}


def _mock_response(json_body):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = json_body
    return m


def test_fetch_eia_parses_real_response_shape_when_key_present():
    fetch_eia.clear()  # bypass @st.cache_data between test runs
    with patch("utils.fetchers.resilient_get", return_value=_mock_response(EIA_RESPONSE_FIXTURE)):
        s = fetch_eia("PET.WCESTUS1.W", "2026-01-01", "2026-12-31", api_key="fake-key-for-test")
    assert not is_unavailable(s)
    assert len(s) == 2
    assert float(s.iloc[-1]) == 418222.0  # most recent period, sorted ascending


def test_fetch_eia_is_unavailable_without_key():
    fetch_eia.clear()
    s = fetch_eia("PET.WCESTUS1.W", "2024-01-01", "2024-06-01", api_key="")
    assert is_unavailable(s) and s.empty


def test_fetch_eia_is_unavailable_on_request_exception():
    fetch_eia.clear()
    with patch("utils.fetchers.resilient_get", side_effect=ConnectionError("network down")):
        s = fetch_eia("PET.WCESTUS1.W", "2024-01-01", "2024-06-01", api_key="fake-key-for-test")
    assert is_unavailable(s) and s.empty


def test_fetch_fred_parses_real_response_shape_when_key_present():
    fetch_fred.clear()
    with patch("utils.fetchers.resilient_get", return_value=_mock_response(FRED_RESPONSE_FIXTURE)):
        s = fetch_fred("SOME_SERIES", "2026-01-01", "2026-12-31", api_key="fake-key-for-test")
    assert not is_unavailable(s)
    assert len(s) == 2


def test_fetch_fred_is_unavailable_without_key():
    fetch_fred.clear()
    s = fetch_fred("SOME_SERIES", "2024-01-01", "2024-06-01", api_key="")
    assert is_unavailable(s) and s.empty


def test_fetch_fred_cache_is_keyed_on_api_key_not_just_series_and_dates():
    """
    Regression test for a real concurrency bug found during a multi-user
    hardening pass: fetch_fred is @st.cache_data (a server-wide cache shared
    across every concurrent Streamlit session). If api_key were read from
    st.session_state INSIDE the function instead of being a parameter, the
    first user to request a given (series_id, start, end) would silently
    determine what every other user sees for that same request for the next
    hour -- a user with a real key could get served another user's
    unavailable result, or vice versa. This test proves the two calls below,
    which differ ONLY in api_key, do NOT share a cache entry.
    """
    fetch_fred.clear()
    with patch("utils.fetchers.resilient_get", return_value=_mock_response(FRED_RESPONSE_FIXTURE)):
        with_key = fetch_fred("SAME_SERIES", "2024-01-01", "2024-06-01", api_key="real-key")
    without_key = fetch_fred("SAME_SERIES", "2024-01-01", "2024-06-01", api_key="")
    assert not is_unavailable(with_key)
    assert is_unavailable(without_key)


# ── openFDA drug approval velocity ───────────────────────────────────────────

OPENFDA_RESPONSE_FIXTURE = {
    "meta": {"results": {"total": 25368}},
    "results": [
        {
            "submissions": [
                {"submission_type": "ORIG", "submission_status": "AP", "submission_status_date": "20260612"},
            ]
        },
        {
            "submissions": [
                {"submission_type": "ORIG", "submission_status": "AP", "submission_status_date": "20260605"},
                {"submission_type": "SUPPL", "submission_status": "PEND", "submission_status_date": "20260701"},
            ]
        },
    ],
}


def test_fetch_fda_approval_velocity_parses_real_response_shape():
    fetch_fda_approval_velocity.clear()
    with patch("utils.fetchers.resilient_get", return_value=_mock_response(OPENFDA_RESPONSE_FIXTURE)):
        s = fetch_fda_approval_velocity()
    assert not s.empty
    assert s.sum() == 2  # two AP-status submissions in the fixture; the PEND one must be excluded


def test_fetch_fda_approval_velocity_falls_back_to_empty_on_request_exception():
    fetch_fda_approval_velocity.clear()
    with patch("utils.fetchers.resilient_get", side_effect=ConnectionError("network down")):
        s = fetch_fda_approval_velocity()
    assert s.empty


# ── short interest (real FINRA consolidated short interest) ──────────────────
#
# This exact field shape (camelCase names, values) was confirmed live against
# api.finra.org/data/group/otcMarket/name/consolidatedShortInterest for real
# MSFT records on 2026-06-21 -- including the surprising part: that dataset,
# despite its "otcMarket" group name, genuinely contains NYSE/NASDAQ-listed
# securities (confirmed marketClassCode "NNM" for MSFT, "NYSE" for Agilent),
# unlike the "EquityShortInterest" dataset in the same group, which returned
# zero rows (HTTP 204) for AAPL -- that one really is OTC-only.
FINRA_SHORT_INTEREST_FIXTURE = [
    {
        "settlementDate": "2026-05-15", "symbolCode": "MSFT",
        "issueName": "Microsoft Corporation Common S",
        "currentShortPositionQuantity": 77302679, "previousShortPositionQuantity": 79107882,
        "changePercent": -2.28, "daysToCoverQuantity": 1.2, "averageDailyVolumeQuantity": 64000000,
        "marketClassCode": "NNM",
    },
    {
        "settlementDate": "2026-05-29", "symbolCode": "MSFT",
        "issueName": "Microsoft Corporation Common S",
        "currentShortPositionQuantity": 88696120, "previousShortPositionQuantity": 77302679,
        "changePercent": 14.74, "daysToCoverQuantity": 2.4, "averageDailyVolumeQuantity": 37000000,
        "marketClassCode": "NNM",
    },
]


def test_fetch_short_interest_parses_real_response_shape():
    fetch_short_interest.clear()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = FINRA_SHORT_INTEREST_FIXTURE
    with patch("utils.fetchers.resilient_post", return_value=mock_resp):
        df = fetch_short_interest("MSFT", years=1.5)

    assert len(df) == 2
    assert list(df["date"]) == sorted(df["date"])  # ascending, oldest first
    last = df.iloc[-1]
    assert last["short_shares"] == 88696120
    assert last["change_pct"] == 14.74
    assert last["days_to_cover"] == 2.4


def test_fetch_short_interest_empty_on_204_no_rows():
    """FINRA returns HTTP 204 (no content) rather than an empty JSON array
    when a symbol genuinely has no matching rows -- must not be treated as
    an error/exception, just an empty, valid result."""
    fetch_short_interest.clear()
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    with patch("utils.fetchers.resilient_post", return_value=mock_resp):
        df = fetch_short_interest("ZZZZ_NOT_A_REAL_TICKER", years=1.5)
    assert df.empty


def test_fetch_short_interest_empty_on_request_exception():
    fetch_short_interest.clear()
    with patch("utils.fetchers.resilient_post", side_effect=ConnectionError("network down")):
        df = fetch_short_interest("MSFT", years=1.5)
    assert df.empty


# ── 13F institutional holdings (curated fund whitelist) ───────────────────────
#
# All fixture shapes below are simplified but structurally exact copies of
# real responses fetched live from Berkshire Hathaway's actual CIK/filings:
# data.sec.gov/submissions/CIK....json (filing history with reportDate
# already included), a filing's /index.json, and a real infoTable XML entry.
# The 13F-HR/A amendment entry in the submissions fixture is there
# specifically to verify it gets excluded -- confirmed live that Berkshire
# files those (e.g. accession 0000950123-25-008361) and they must not be
# treated as a distinct reporting period.
#
# This endpoint replaced an earlier version that used the legacy
# cgi-bin/browse-edgar atom feed plus a separate primary_doc.xml fetch per
# filing -- switched after that atom feed intermittently returned empty
# responses on valid CIK lookups during live testing (data.sec.gov returned
# correct results for the exact same CIKs moments later).
THIRTEENF_SUBMISSIONS_FIXTURE = {
    "filings": {
        "recent": {
            "form": ["13F-HR", "13F-HR/A", "13F-HR"],
            "accessionNumber": ["0001193125-26-226661", "0000950123-25-008361", "0000950123-25-008343"],
            "reportDate": ["2026-03-31", "2025-06-30", "2025-06-30"],
        }
    }
}

THIRTEENF_INDEX_JSON_FIXTURE_1 = {
    "directory": {"item": [
        {"name": "0001193125-26-226661-index.html"},
        {"name": "primary_doc.xml"},
        {"name": "53405.xml"},
    ]}
}
THIRTEENF_INDEX_JSON_FIXTURE_2 = {
    "directory": {"item": [
        {"name": "0000950123-25-008343-index.html"},
        {"name": "primary_doc.xml"},
        {"name": "infotable.xml"},
    ]}
}

# Real shape confirmed live: a plain long stock position (no putCall field)
# and a Put options position (Scion's actual NVIDIA holding) in the same
# table -- the parser must tell these apart, not treat every row as a share.
THIRTEENF_INFOTABLE_FIXTURE_1 = b"""<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>CHEVRON CORPORATION</nameOfIssuer>
    <cusip>166764100</cusip>
    <value>12052286868</value>
    <shrsOrPrnAmt><sshPrnamt>58251749</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>NVIDIA CORPORATION</nameOfIssuer>
    <cusip>67066G104</cusip>
    <value>186580000</value>
    <shrsOrPrnAmt><sshPrnamt>1000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <putCall>Put</putCall>
  </infoTable>
</informationTable>"""
THIRTEENF_INFOTABLE_FIXTURE_2 = b"""<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>CHEVRON CORPORATION</nameOfIssuer>
    <cusip>166764100</cusip>
    <value>9000000000</value>
    <shrsOrPrnAmt><sshPrnamt>50000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
</informationTable>"""


def _xml_mock(content_bytes):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.content = content_bytes
    return m


def test_fetch_13f_holdings_excludes_amendments_and_parses_put_options():
    fetch_13f_holdings.clear()
    sub_resp = _mock_response(THIRTEENF_SUBMISSIONS_FIXTURE)
    idx1 = _mock_response(THIRTEENF_INDEX_JSON_FIXTURE_1)
    tbl1 = _xml_mock(THIRTEENF_INFOTABLE_FIXTURE_1)
    idx2 = _mock_response(THIRTEENF_INDEX_JSON_FIXTURE_2)
    tbl2 = _xml_mock(THIRTEENF_INFOTABLE_FIXTURE_2)

    with patch("utils.fetchers.resilient_get",
               side_effect=_mock_get_sequence(sub_resp, idx1, tbl1, idx2, tbl2)):
        df = fetch_13f_holdings("1067983", "Berkshire Hathaway", max_filings=2)

    # Only 2 filing periods worth of rows (3 infoTable rows total across both
    # periods) -- the 13F-HR/A amendment must NOT have produced a 3rd period.
    assert len(df) == 3
    assert df["period"].nunique() == 2

    nvda_row = df[df["cusip"] == "67066G104"].iloc[0]
    assert nvda_row["direction"] == "short"  # Put position, not a plain long share

    cvx_rows = df[df["cusip"] == "166764100"]
    assert (cvx_rows["direction"] == "long").all()
    assert set(cvx_rows["shares"]) == {58251749.0, 50000000.0}


def test_fetch_13f_holdings_empty_on_request_exception():
    fetch_13f_holdings.clear()
    with patch("utils.fetchers.resilient_get", side_effect=ConnectionError("network down")):
        df = fetch_13f_holdings("1067983", "Berkshire Hathaway")
    assert df.empty


# ── insider transaction detail (real Form 4 XML parsing) ─────────────────────
#
# The search-hit shape below is the exact field structure confirmed live
# against efts.sec.gov (Lockheed Martin and Microsoft Form 4 filings,
# 2026-06-21) -- "_id" is "{accession}:{filename}", "ciks"[0] is the FILER's
# CIK (confirmed the filename varies by filing agent: one company's agent
# used "doc4.xml", another's used "form4.xml" -- this is why the parser
# must read the filename from the search hit, not assume one).
INSIDER_SEARCH_FIXTURE = {
    "hits": {"hits": [{
        "_id": "0000789019-26-000128:form4.xml",
        "_source": {"ciks": ["0001487290", "0000789019"], "display_names": ["Mason Mark"]},
    }]}
}

# This XML shape (tag nesting) is the exact structure confirmed live via
# the reportingOwner/nonDerivativeTable paths fetched directly from
# sec.gov/Archives -- a P (purchase) transaction is synthesized here since
# live examples found during research were grants/vesting (codes A/F), not
# open-market buys, but the schema itself (SEC's Form 4 XML spec, stable
# for two decades) is identical in structure regardless of which code value
# appears.
INSIDER_XML_PURCHASE = b"""<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Mason Mark</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isOfficer>1</isOfficer>
      <officerTitle>Chief Financial Officer</officerTitle>
      <isDirector>0</isDirector>
      <isTenPercentOwner>0</isTenPercentOwner>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-03-15</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>50.25</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def _mock_get_sequence(*responses):
    """Returns a side_effect function yielding each mock response in order."""
    it = iter(responses)
    def _side_effect(*args, **kwargs):
        return next(it)
    return _side_effect


def test_fetch_insider_transactions_detail_parses_real_response_shapes():
    fetch_insider_transactions_detail.clear()
    search_resp = _mock_response(INSIDER_SEARCH_FIXTURE)
    xml_resp = MagicMock()
    xml_resp.raise_for_status = MagicMock()
    xml_resp.content = INSIDER_XML_PURCHASE

    with patch("utils.fetchers.resilient_get", side_effect=_mock_get_sequence(search_resp, xml_resp)):
        df = fetch_insider_transactions_detail("MSFT", days=180)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["code"] == "P"
    assert row["insider"] == "Mason Mark"
    assert row["role"] == "Chief Financial Officer"
    assert row["shares"] == 1000.0
    assert row["price"] == 50.25
    assert row["value"] == 1000.0 * 50.25  # positive: purchase


def test_fetch_insider_transactions_detail_skips_non_open_market_codes():
    """Grants/vesting (code A) and option exercises (M) must NOT be counted
    as buy/sell signal -- only P and S reflect a genuine market decision."""
    fetch_insider_transactions_detail.clear()
    xml_grant = INSIDER_XML_PURCHASE.replace(b"<transactionCode>P</transactionCode>",
                                              b"<transactionCode>A</transactionCode>")
    search_resp = _mock_response(INSIDER_SEARCH_FIXTURE)
    xml_resp = MagicMock()
    xml_resp.raise_for_status = MagicMock()
    xml_resp.content = xml_grant

    with patch("utils.fetchers.resilient_get", side_effect=_mock_get_sequence(search_resp, xml_resp)):
        df = fetch_insider_transactions_detail("MSFT", days=180)

    assert df.empty


def test_fetch_insider_transactions_detail_empty_on_search_failure():
    fetch_insider_transactions_detail.clear()
    with patch("utils.fetchers.resilient_get", side_effect=ConnectionError("network down")):
        df = fetch_insider_transactions_detail("MSFT", days=180)
    assert df.empty


# ── live quote (st.fragment auto-refresh feature) ────────────────────────────

def test_fetch_live_quote_parses_fast_info():
    fetch_live_quote.clear()
    mock_fast_info = {"lastPrice": 190.5, "previousClose": 188.0}
    mock_ticker = MagicMock()
    mock_ticker.fast_info = mock_fast_info
    mock_ticker.info = {}
    with patch("utils.fetchers.yf.Ticker", return_value=mock_ticker):
        q = fetch_live_quote("AAPL")
    assert q["price"] == 190.5
    assert q["prev_close"] == 188.0
    assert round(q["pct_change"], 4) == round((190.5 - 188.0) / 188.0 * 100, 4)


def test_fetch_live_quote_handles_missing_price():
    fetch_live_quote.clear()
    mock_ticker = MagicMock()
    mock_ticker.fast_info = {"previousClose": 188.0}  # no lastPrice
    mock_ticker.info = {}
    with patch("utils.fetchers.yf.Ticker", return_value=mock_ticker):
        q = fetch_live_quote("AAPL")
    assert q["price"] is None and q["prev_close"] is None and q["pct_change"] is None


def test_fetch_live_quote_falls_back_on_exception():
    fetch_live_quote.clear()
    with patch("utils.fetchers.yf.Ticker", side_effect=ConnectionError("network down")):
        q = fetch_live_quote("AAPL")
    assert q["price"] is None and q["prev_close"] is None and q["pct_change"] is None
