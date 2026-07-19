"""Tests for utils.scoring_universe — what we're willing to SCORE (offline)."""
from utils import scoring_universe as su


# ── must be EXCLUDED (scoring these would be noise dressed as signal) ─────────
def test_leveraged_and_inverse_products_excluded():
    for sym, nm in [
        ("RKLX", "Defiance Daily Target 2X Long RKLB ETF"),
        ("SOFA", "Direxion Daily SOFI Bull 2X Shares"),
        ("SQQQ", "ProShares UltraPro Short QQQ"),
        ("SH",   "ProShares Short S&P500"),
        ("THTA", "SoFi Enhanced Yield ETF"),
    ]:
        assert su.classify(sym, nm, False) == su.EXCL_LEVERAGED, f"{sym} should be leveraged/inverse"


def test_plain_etfs_and_funds_excluded():
    assert su.classify("SPY", "SPDR S&P 500 ETF Trust", True) == su.EXCL_ETF
    assert su.classify("XYZ", "Some Closed End Fund", False) == su.EXCL_ETF
    # ETF flag alone is enough even when the name doesn't say so
    assert su.classify("ABCD", "Something Opaque", True) == su.EXCL_ETF


def test_warrants_units_rights_excluded():
    assert su.classify("ABCDW", "Some Co - Warrant", False) == su.EXCL_DERIVATIVE
    assert su.classify("ABCDU", "Some Co - Unit", False) == su.EXCL_DERIVATIVE
    assert su.classify("WXYZ", "Some Co Rights", False) == su.EXCL_DERIVATIVE


def test_preferred_and_debt_excluded():
    assert su.classify("ABC.PRA", "Some Co Preferred Series A", False) == su.EXCL_PREFERRED
    assert su.classify("DEF", "Some Co 6.5% Notes Due 2030", False) == su.EXCL_PREFERRED


def test_spac_shells_excluded_regardless_of_suffix():
    # This was a real miss: only "Acquisition Corp" was matched, so "Acquisition
    # Inc." shells slipped through and would have been scored.
    for sym, nm in [
        ("AACB", "Artius II Acquisition Inc. - Class A Ordinary Shares"),
        ("XPAC", "Some Acquisition Corp - Class A"),
        ("BLNK", "Big Blank Check Company"),
    ]:
        assert su.classify(sym, nm, False) == su.EXCL_SPAC, f"{sym} should be a SPAC/shell"


def test_non_common_symbol_shapes_excluded():
    assert su.classify("ABC.W", "Some Co", False) == su.EXCL_SYMBOL_FORM
    assert su.classify("ABC-P", "Some Co", False) == su.EXCL_SYMBOL_FORM


# ── must be SCOREABLE ────────────────────────────────────────────────────────
def test_common_stocks_are_scoreable():
    for sym, nm in [
        ("AAPL", "Apple Inc. - Common Stock"),
        ("NVDA", "NVIDIA Corporation - Common Stock"),
        ("RKLB", "Rocket Lab Corporation - Common Stock"),
        ("SOFI", "SoFi Technologies, Inc."),
        ("BRK.A", "Berkshire Hathaway Inc. Class A"),   # dotted share class is fine
    ]:
        assert su.classify(sym, nm, False) == su.OK, f"{sym} should be scoreable"


def test_classify_never_raises_on_junk():
    for sym, nm in [("", ""), (None, None), ("X", None), (None, "Name")]:
        assert isinstance(su.classify(sym, nm, False), str)


# ── partition ────────────────────────────────────────────────────────────────
def _records():
    return {
        "AAPL": {"symbol": "AAPL", "name": "Apple Inc. - Common Stock",
                 "short_name": "Apple Inc", "etf": False},
        # NOTE: deliberately NOT SPY — SPY is one of the curated 280, and
        # "curation wins" is intended behaviour (macro-relevant sector ETFs must
        # stay scoreable). Use a fund that isn't tracked.
        "ZZFUND": {"symbol": "ZZFUND", "name": "Generic Index Fund Trust",
                   "short_name": "Generic Index Fund", "etf": True},
        "RKLX": {"symbol": "RKLX", "name": "Defiance Daily Target 2X Long RKLB ETF",
                 "short_name": "Defiance 2X RKLB", "etf": True},
        "AACB": {"symbol": "AACB", "name": "Artius II Acquisition Inc.",
                 "short_name": "Artius II Acquisition", "etf": False},
    }


def test_build_partitions_and_counts():
    out = su.build_scoring_universe(_records())
    assert "AAPL" in out["scoreable"]
    for s in ("ZZFUND", "RKLX", "AACB"):
        assert s in out["excluded"], f"{s} should be excluded"
    assert out["stats"]["total"] == 4
    assert out["stats"]["scoreable"] == len(out["scoreable"])


def test_tracked_tickers_always_scoreable_even_if_rules_would_drop_them():
    """The curated 280 include macro-relevant sector ETFs the generic ETF rule
    would otherwise exclude — curation must win."""
    from utils.config import TICKERS
    etf_like = {t: {"symbol": t, "name": f"{t} ETF Trust", "short_name": t, "etf": True}
                for t in list(TICKERS.keys())[:5]}
    out = su.build_scoring_universe(etf_like)
    for t in etf_like:
        assert t in out["scoreable"], f"tracked {t} must stay scoreable"


def test_build_degrades_on_empty_input():
    out = su.build_scoring_universe({})
    # still returns the tracked set rather than nothing
    assert isinstance(out["scoreable"], dict)
    assert out["stats"]["total"] == 0
