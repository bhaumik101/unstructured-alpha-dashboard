"""Fund look-through from SEC Form N-PORT (utils/lookthrough.py,
scripts/build_lookthrough.py).

  * The parser keeps facts from the filing: shares by asset, issuer,
    currency and country, and the largest positions combined by issuer.
  * The "why it matters here" line appears only for an exposure the fund
    carries in this report, and only where the mechanism is arithmetic.
  * A fund with no filing is said to have none; stocks are not looked through.
"""

from __future__ import annotations

import copy
import sys
import time
from pathlib import Path

import pytest

from tests.test_exposure import _report
from utils import lookthrough as lt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_lookthrough as bl  # noqa: E402,F401
from utils import nport as bl  # noqa: E402,F811  (the parser lives here now)

XML = b"""<?xml version="1.0"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/nport"><formData><genInfo><seriesName>Test Intl Fund</seriesName>
<repPdDate>2026-07-31</repPdDate></genInfo><fundInfo><netAssets>1000.0</netAssets></fundInfo><invstOrSecs>
<invstOrSec><name>Toyota</name><valUSD>300</valUSD><pctVal>30</pctVal><assetCat>EC</assetCat><issuerCat>CORP</issuerCat>
 <invCountry>JP</invCountry><currencyConditional curCd="JPY" exchangeRt="0.0067"/></invstOrSec>
<invstOrSec><name>US Treasury Note</name><valUSD>200</valUSD><pctVal>20</pctVal><curCd>USD</curCd><assetCat>DBT</assetCat>
 <issuerCat>UST</issuerCat><invCountry>US</invCountry></invstOrSec>
<invstOrSec><name>US Treasury Note</name><valUSD>150</valUSD><pctVal>15</pctVal><curCd>USD</curCd><assetCat>DBT</assetCat>
 <issuerCat>UST</issuerCat><invCountry>US</invCountry></invstOrSec>
<invstOrSec><name>Nestle</name><valUSD>350</valUSD><pctVal>35</pctVal><assetCat>EC</assetCat><issuerCat>CORP</issuerCat>
 <invCountry>CH</invCountry><currencyConditional curCd="CHF" exchangeRt="1.1"/></invstOrSec>
</invstOrSecs></formData></edgarSubmission>"""


def test_the_parser_keeps_the_filings_facts():
    s = bl.summarize(XML, "S000000001")
    assert s["holdings"] == 4 and s["period"] == "2026-07-31" and s["net_assets"] == 1000.0
    assert s["series_name"] == "Test Intl Fund"
    assert dict(s["assets"]) == {"EC": 65.0, "DBT": 35.0}
    assert dict(s["issuers"]) == {"CORP": 65.0, "UST": 35.0}
    assert dict(s["currencies"]) == {"USD": 35.0, "CHF": 35.0, "JPY": 30.0}   # currencyConditional is read
    # positions sharing an issuer are combined before ranking (two Treasury notes -> 35%)
    assert s["top"][0][:2] == ["Nestle", 35.0] and s["top"][1][:2] == ["US Treasury Note", 35.0]
    assert s["top"][1][4] == 2


def _with(funds: dict):
    return {"built": "x", "funds": funds}


@pytest.fixture
def snap(monkeypatch):
    intl = bl.summarize(XML, "S1")
    intl["source"] = "https://www.sec.gov/x"
    bond = {"holdings": 17000, "period": "2026-06-30", "source": "https://www.sec.gov/y",
            "assets": [["DBT", 78.0], ["ABS-MBS", 21.0]], "issuers": [["UST", 48.0], ["CORP", 29.0]],
            "currencies": [["USD", 99.7]], "countries": [["US", 93.0]], "top": [["United States Treasury", 48.0, "DBT", "US", 299]]}
    us = {"holdings": 3500, "period": "2026-06-30", "source": "https://www.sec.gov/z",
          "assets": [["EC", 99.8]], "issuers": [["CORP", 100.0]], "currencies": [["USD", 100.0]],
          "countries": [["US", 100.0]], "top": [["Apple", 6.0, "EC", "US", 1]]}
    monkeypatch.setattr(lt, "_snap_at", time.time())      # a fresh cache: snapshot() serves it as is
    monkeypatch.setattr(lt, "_snap", _with({"XOM": None, "TLT": bond, "VTI": us, "GLDX": {"none": "no N-PORT filer"},
                                         "ODD": {"series": "S9"}}))           # malformed: no holdings, no reason
    return intl, bond, us


def test_the_why_line_needs_the_exposure_and_the_mechanism(snap):
    intl, bond, us = snap
    r = _report()
    r["portfolio"]["readings"]["rates"]["evidence"] = "clear"
    r["contributions"]["rates"] = [{"ticker": "TLT", "weight_pct": 40, "impact": -1, "evidence": "clear",
                                    "contribution": -0.4, "share": 0.8}]
    assert "a bond's price falls when interest rates rise" in lt.why_here("TLT", bond, r)
    assert lt.why_here("VTI", us, r) == ""                       # carries nothing here
    r2 = copy.deepcopy(r)
    r2["portfolio"]["readings"]["rates"]["evidence"] = "indistinct"
    assert lt.why_here("TLT", bond, r2) == ""                    # a reading that did not hold up explains nothing
    r3 = copy.deepcopy(r)
    r3["portfolio"]["readings"]["dollar"]["evidence"] = "clear"
    r3["contributions"]["dollar"] = [{"ticker": "VXUSX", "weight_pct": 20, "impact": -2, "evidence": "clear",
                                      "contribution": -0.4, "share": 0.78}]
    line = lt.why_here("VXUSX", intl, r3)
    assert "65% of it is priced in other currencies" in line
    us_heavy = dict(intl, currencies=[["USD", 80.0], ["JPY", 20.0]])
    assert lt.why_here("VXUSX", us_heavy, r3) == ""             # mostly dollars: the mechanism does not apply


def test_the_section_names_filers_and_admits_non_filers(snap):
    r = _report()                                                # TLT, XOM, VTI
    r["positions"].append({"ticker": "GLDX", "weight_pct": 5.0})
    r["positions"].append({"ticker": "ODD", "weight_pct": 1.0})
    html = lt.lookthrough_html(r)
    assert html.count('class="ult-card"') == 2                   # TLT and VTI; XOM is a stock
    assert "No holdings filing for GLDX" in html
    assert "SEC Form N-PORT" in html and "Jun 30, 2026" in html
    assert "17,000 holdings" in html


def test_nothing_is_shown_without_a_filing(monkeypatch):
    monkeypatch.setattr(lt, "_snap_at", time.time())
    monkeypatch.setattr(lt, "_snap", _with({}))
    assert lt.lookthrough_html(_report()) == ""


def test_the_copy_describes_and_never_advises(snap):
    from tests.test_exposure import _BANNED
    import re
    r = _report()
    text = re.sub(r"<[^>]+>", " ", lt.lookthrough_html(r))
    assert not _BANNED.search(text)


def test_shares_never_read_above_100_or_below_0():
    assert lt._pct(101.2) == "100%" and lt._pct(-0.3) == "0%" and lt._pct(0.4) == "<1%"


def test_collateral_never_reads_as_a_holding_or_pushes_past_100():
    hyg = {"holdings": 1324, "period": "2026-08-31", "source": "https://www.sec.gov/h",
           "assets": [["DBT", 96.67], ["STIV", 14.52]], "issuers": [["CORP", 111.0]],
           "currencies": [["USD", 111.38]], "countries": [["US", 90.0]],
           "top": [["BlackRock Funds III", 13.2, "STIV", "US", 1], ["CCO HLDGS", 2.02, "DBT", "US", 13]]}
    assert abs(sum(v for _, v in lt.mix(hyg, "assets")) - 100.0) < 1e-6
    assert lt.non_usd(hyg) == 0.0
    html = lt.card_html("HYG", hyg, _report())
    assert "BlackRock Funds III" not in html and "CCO HLDGS" in html


def test_the_dollar_share_is_never_folded_into_other():
    rows = "".join(
        f"<invstOrSec><name>F{i}</name><pctVal>{v}</pctVal><assetCat>EC</assetCat><issuerCat>CORP</issuerCat>"
        f'<invCountry>X{i}</invCountry><currencyConditional curCd="C{i}"/></invstOrSec>'
        for i, v in enumerate((20, 19, 18, 17, 16, 7)))
    rows += ("<invstOrSec><name>Cash</name><pctVal>3</pctVal><curCd>USD</curCd><assetCat>STIV</assetCat>"
             "<issuerCat>RF</issuerCat><invCountry>US</invCountry></invstOrSec>")
    xml = ('<edgarSubmission xmlns="http://www.sec.gov/edgar/nport"><formData><invstOrSecs>'
           + rows + "</invstOrSecs></formData></edgarSubmission>").encode()
    s = bl.summarize(xml, "S2")
    assert dict(s["currencies"]).get("USD") == 3.0 and dict(s["countries"]).get("US") == 3.0
    assert round(lt.non_usd(s), 6) == 97.0


def test_the_bundled_snapshot_is_sane():
    lt._snap = None
    funds = lt.snapshot()["funds"]
    filed = {t: f for t, f in funds.items() if f.get("holdings")}
    assert len(filed) >= 60
    for t, f in filed.items():
        assert f["period"] and f["source"].startswith("https://www.sec.gov/"), t
        assert "USD" in dict(f["currencies"]) or lt.non_usd(f) > 99, t      # the dollar line is never folded away
    assert 90 < lt.non_usd(funds["VXUS"]) < 99.9
    assert lt.bonds(funds["BND"]) > 90 and lt.non_usd(funds["BND"]) < 2
    for t in ("GLD", "SPY"):
        assert funds[t].get("none"), t                                    # recorded as filing none, not estimated
