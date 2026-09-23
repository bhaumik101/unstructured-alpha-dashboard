# utils/symbol_search.py
# Unstructured Alpha — find a holding by name instead of by ticker
#
# WHY THIS EXISTS
# ---------------
# The exposure report's front door asked for tickers. That is a real barrier:
# people know they own "the Vanguard total stock market fund" and "Apple", not
# that those are VTI and AAPL, and a 401(k) statement lists fund names with no
# symbol at all. Every one of those visitors had to leave, look something up,
# and come back — most do not.
#
# So: type a name, pick from a list, and the ticker is filled in.
#
# MUTUAL FUNDS ARE INCLUDED, and that is the bigger half of this change. The
# page used to say "U.S.-listed stocks or ETFs", which turned away anyone whose
# portfolio is a 401(k) or an adviser's model — exactly the customer this
# product is for. Checked before claiming it: VTSAX and FXAIX both return 750
# daily NAV observations over three years from the same provider the engine
# already uses, which is more than the 104 weeks it requires.
#
# TWO SOURCES, AND THE UI SAYS WHICH
# ----------------------------------
# Live search is Yahoo's public search endpoint — the same provider as prices,
# so it adds no new dependency. When it is unreachable or returns nothing, the
# bundled table below answers instead. That fallback is deliberately small and
# it is NOT presented as a complete search: search_symbols returns the source
# so the page can say results are limited, rather than implying a name is not
# a real fund when the truth is that the lookup is down. Quietly degrading
# into a short list would teach people the product does not know their holding.

from __future__ import annotations

import json
import re
from typing import Callable, Iterable, List, Optional

SEARCH_URL = ("https://query2.finance.yahoo.com/v1/finance/search"
              "?q={q}&quotesCount={n}&newsCount=0&enableFuzzyQuery=false")

# Yahoo's quoteType, mapped to words a person uses. Anything not here — an
# index, a future, a currency pair, a crypto — is dropped: the engine measures
# holdings, and offering something it cannot price is a worse answer than none.
_KINDS = {"EQUITY": "Stock", "ETF": "ETF", "MUTUALFUND": "Fund"}

# US listings only. The engine's factors are US rates, US inflation, the dollar
# and US credit; a London or Toronto listing would be measured against them
# without comment, which would read as a result rather than a mismatch.
_US_EXCHANGES = {
    "NYQ", "NMS", "NGM", "NCM", "NAS", "ASE", "PCX", "BTS", "PSE", "NYS",
    "AMX", "ARCA", "BATS", "NIM", "OPR", "YHD",
}

_TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


# ── the offline table ───────────────────────────────────────────────────────
# Widely held US names, core ETFs and the index funds that dominate workplace
# plans. It exists so a failed lookup still lets someone start, not so it can
# stand in for search.
_COMMON: tuple[tuple[str, str, str], ...] = (
    # Broad-market and core ETFs
    ("VTI", "Vanguard Total Stock Market ETF", "ETF"),
    ("VOO", "Vanguard S&P 500 ETF", "ETF"),
    ("SPY", "SPDR S&P 500 ETF Trust", "ETF"),
    ("IVV", "iShares Core S&P 500 ETF", "ETF"),
    ("QQQ", "Invesco QQQ Trust", "ETF"),
    ("VXUS", "Vanguard Total International Stock ETF", "ETF"),
    ("VEA", "Vanguard FTSE Developed Markets ETF", "ETF"),
    ("VWO", "Vanguard FTSE Emerging Markets ETF", "ETF"),
    ("IEFA", "iShares Core MSCI EAFE ETF", "ETF"),
    ("VUG", "Vanguard Growth ETF", "ETF"),
    ("VTV", "Vanguard Value ETF", "ETF"),
    ("VB", "Vanguard Small-Cap ETF", "ETF"),
    ("IWM", "iShares Russell 2000 ETF", "ETF"),
    ("VIG", "Vanguard Dividend Appreciation ETF", "ETF"),
    ("SCHD", "Schwab U.S. Dividend Equity ETF", "ETF"),
    ("DIA", "SPDR Dow Jones Industrial Average ETF", "ETF"),
    # Bonds and cash-like
    ("BND", "Vanguard Total Bond Market ETF", "ETF"),
    ("AGG", "iShares Core U.S. Aggregate Bond ETF", "ETF"),
    ("TLT", "iShares 20+ Year Treasury Bond ETF", "ETF"),
    ("IEF", "iShares 7-10 Year Treasury Bond ETF", "ETF"),
    ("SHY", "iShares 1-3 Year Treasury Bond ETF", "ETF"),
    ("TIP", "iShares TIPS Bond ETF", "ETF"),
    ("VTIP", "Vanguard Short-Term Inflation-Protected Securities ETF", "ETF"),
    ("LQD", "iShares iBoxx Investment Grade Corporate Bond ETF", "ETF"),
    ("HYG", "iShares iBoxx High Yield Corporate Bond ETF", "ETF"),
    ("MUB", "iShares National Muni Bond ETF", "ETF"),
    ("BNDX", "Vanguard Total International Bond ETF", "ETF"),
    # Real assets and sectors
    ("GLD", "SPDR Gold Shares", "ETF"),
    ("IAU", "iShares Gold Trust", "ETF"),
    ("VNQ", "Vanguard Real Estate ETF", "ETF"),
    ("XLE", "Energy Select Sector SPDR Fund", "ETF"),
    ("XLF", "Financial Select Sector SPDR Fund", "ETF"),
    ("XLK", "Technology Select Sector SPDR Fund", "ETF"),
    ("XLU", "Utilities Select Sector SPDR Fund", "ETF"),
    ("XLV", "Health Care Select Sector SPDR Fund", "ETF"),
    ("XLP", "Consumer Staples Select Sector SPDR Fund", "ETF"),
    ("XLI", "Industrial Select Sector SPDR Fund", "ETF"),
    ("XLY", "Consumer Discretionary Select Sector SPDR Fund", "ETF"),
    ("XLB", "Materials Select Sector SPDR Fund", "ETF"),
    ("DBC", "Invesco DB Commodity Index Tracking Fund", "ETF"),
    # Index funds that dominate workplace plans
    ("VTSAX", "Vanguard Total Stock Market Index Fund Admiral", "Fund"),
    ("VFIAX", "Vanguard 500 Index Fund Admiral", "Fund"),
    ("VBTLX", "Vanguard Total Bond Market Index Fund Admiral", "Fund"),
    ("VTIAX", "Vanguard Total International Stock Index Fund Admiral", "Fund"),
    ("VGSLX", "Vanguard Real Estate Index Fund Admiral", "Fund"),
    ("FXAIX", "Fidelity 500 Index Fund", "Fund"),
    ("FSKAX", "Fidelity Total Market Index Fund", "Fund"),
    ("FTIHX", "Fidelity Total International Index Fund", "Fund"),
    ("FXNAX", "Fidelity U.S. Bond Index Fund", "Fund"),
    ("SWPPX", "Schwab S&P 500 Index Fund", "Fund"),
    ("SWTSX", "Schwab Total Stock Market Index Fund", "Fund"),
    ("VBIAX", "Vanguard Balanced Index Fund Admiral", "Fund"),
    ("VWELX", "Vanguard Wellington Fund", "Fund"),
    ("VTTHX", "Vanguard Target Retirement 2035 Fund", "Fund"),
    ("VFIFX", "Vanguard Target Retirement 2050 Fund", "Fund"),
    # Widely held individual companies
    ("AAPL", "Apple Inc.", "Stock"),
    ("MSFT", "Microsoft Corporation", "Stock"),
    ("NVDA", "NVIDIA Corporation", "Stock"),
    ("AMZN", "Amazon.com, Inc.", "Stock"),
    ("GOOGL", "Alphabet Inc. Class A", "Stock"),
    ("META", "Meta Platforms, Inc.", "Stock"),
    ("TSLA", "Tesla, Inc.", "Stock"),
    ("BRK.B", "Berkshire Hathaway Inc. Class B", "Stock"),
    ("JPM", "JPMorgan Chase & Co.", "Stock"),
    ("BAC", "Bank of America Corporation", "Stock"),
    ("WFC", "Wells Fargo & Company", "Stock"),
    ("V", "Visa Inc.", "Stock"),
    ("MA", "Mastercard Incorporated", "Stock"),
    ("UNH", "UnitedHealth Group Incorporated", "Stock"),
    ("JNJ", "Johnson & Johnson", "Stock"),
    ("LLY", "Eli Lilly and Company", "Stock"),
    ("PFE", "Pfizer Inc.", "Stock"),
    ("ABBV", "AbbVie Inc.", "Stock"),
    ("MRK", "Merck & Co., Inc.", "Stock"),
    ("XOM", "Exxon Mobil Corporation", "Stock"),
    ("CVX", "Chevron Corporation", "Stock"),
    ("COP", "ConocoPhillips", "Stock"),
    ("PG", "Procter & Gamble Company", "Stock"),
    ("KO", "Coca-Cola Company", "Stock"),
    ("PEP", "PepsiCo, Inc.", "Stock"),
    ("COST", "Costco Wholesale Corporation", "Stock"),
    ("WMT", "Walmart Inc.", "Stock"),
    ("HD", "Home Depot, Inc.", "Stock"),
    ("MCD", "McDonald's Corporation", "Stock"),
    ("NKE", "NIKE, Inc.", "Stock"),
    ("DIS", "Walt Disney Company", "Stock"),
    ("CAT", "Caterpillar Inc.", "Stock"),
    ("DE", "Deere & Company", "Stock"),
    ("BA", "Boeing Company", "Stock"),
    ("HON", "Honeywell International Inc.", "Stock"),
    ("GE", "GE Aerospace", "Stock"),
    ("UNP", "Union Pacific Corporation", "Stock"),
    ("T", "AT&T Inc.", "Stock"),
    ("VZ", "Verizon Communications Inc.", "Stock"),
    ("CMCSA", "Comcast Corporation", "Stock"),
    ("NFLX", "Netflix, Inc.", "Stock"),
    ("CRM", "Salesforce, Inc.", "Stock"),
    ("ORCL", "Oracle Corporation", "Stock"),
    ("ADBE", "Adobe Inc.", "Stock"),
    ("AMD", "Advanced Micro Devices, Inc.", "Stock"),
    ("INTC", "Intel Corporation", "Stock"),
    ("QCOM", "QUALCOMM Incorporated", "Stock"),
    ("TXN", "Texas Instruments Incorporated", "Stock"),
    ("IBM", "International Business Machines Corporation", "Stock"),
    ("CSCO", "Cisco Systems, Inc.", "Stock"),
    ("NEE", "NextEra Energy, Inc.", "Stock"),
    ("DUK", "Duke Energy Corporation", "Stock"),
    ("SO", "Southern Company", "Stock"),
    ("AMT", "American Tower Corporation", "Stock"),
    ("PLD", "Prologis, Inc.", "Stock"),
    ("O", "Realty Income Corporation", "Stock"),
    ("GS", "Goldman Sachs Group, Inc.", "Stock"),
    ("MS", "Morgan Stanley", "Stock"),
    ("SCHW", "Charles Schwab Corporation", "Stock"),
    ("AXP", "American Express Company", "Stock"),
    ("BLK", "BlackRock, Inc.", "Stock"),
    ("MMM", "3M Company", "Stock"),
    ("LMT", "Lockheed Martin Corporation", "Stock"),
    ("RTX", "RTX Corporation", "Stock"),
    ("F", "Ford Motor Company", "Stock"),
    ("GM", "General Motors Company", "Stock"),
    ("FCX", "Freeport-McMoRan Inc.", "Stock"),
    ("NEM", "Newmont Corporation", "Stock"),
    ("SLB", "SLB", "Stock"),
    ("PSX", "Phillips 66", "Stock"),
    ("MPC", "Marathon Petroleum Corporation", "Stock"),
)


def _http_get(url: str, timeout: int = 8) -> str:
    """The default fetcher. Kept tiny and injectable so tests never touch the
    network and a provider change is one argument, not a rewrite."""
    import urllib.request

    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; UnstructuredAlpha/1.0)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def parse_search_payload(text: str, limit: int = 8) -> List[dict]:
    """Yahoo's search JSON -> the rows the page shows. Never raises."""
    try:
        quotes = (json.loads(text or "{}") or {}).get("quotes") or []
    except (ValueError, TypeError):
        return []

    rows: List[dict] = []
    seen: set[str] = set()
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        kind = _KINDS.get(str(quote.get("quoteType") or "").upper())
        if not kind:
            continue
        ticker = str(quote.get("symbol") or "").strip().upper()
        if not _TICKER.match(ticker) or ticker in seen:
            continue
        exchange = str(quote.get("exchange") or "").strip().upper()
        if exchange and exchange not in _US_EXCHANGES:
            continue
        name = str(quote.get("longname") or quote.get("shortname") or "").strip()
        if not name:
            continue
        seen.add(ticker)
        rows.append({"ticker": ticker, "name": name, "kind": kind,
                     "exchange": str(quote.get("exchDisp") or "").strip()})
        if len(rows) >= limit:
            break
    return rows


def search_offline(query: str, limit: int = 8) -> List[dict]:
    """Substring match over the bundled table. Exact ticker matches come first."""
    q = " ".join(str(query or "").split()).lower()
    if not q:
        return []
    exact, starts, contains = [], [], []
    for ticker, name, kind in _COMMON:
        row = {"ticker": ticker, "name": name, "kind": kind, "exchange": ""}
        lower = name.lower()
        if ticker.lower() == q:
            exact.append(row)
        elif ticker.lower().startswith(q) or lower.startswith(q):
            starts.append(row)
        elif q in lower:
            contains.append(row)
    return (exact + starts + contains)[:limit]


def search_symbols(query: str, *, fetcher: Optional[Callable[[str], str]] = None,
                   limit: int = 8) -> tuple[List[dict], str]:
    """Find holdings by name or ticker.

    Returns (rows, source) where source is "live", "offline" or "none". The
    caller shows the source: a short list presented as the whole answer would
    teach people the product does not know their fund, when the truth is that
    the lookup is unavailable.
    """
    q = " ".join(str(query or "").split())
    if len(q) < 2:
        return [], "none"

    from urllib.parse import quote as urlquote

    get = fetcher or _http_get
    try:
        payload = get(SEARCH_URL.format(q=urlquote(q), n=max(limit * 3, 12)))
        rows = parse_search_payload(payload, limit)
    except Exception:
        rows = []
    if rows:
        return rows, "live"

    offline = search_offline(q, limit)
    return (offline, "offline") if offline else ([], "none")


def label(row: dict) -> str:
    """One line per result, ticker first — that is what gets typed next time."""
    name = str(row.get("name") or "")
    if len(name) > 52:
        name = name[:51].rstrip(" ,.-") + "…"
    kind = row.get("kind") or ""
    return f"{row.get('ticker', '')} · {name}" + (f"  ({kind})" if kind else "")


def common_symbols() -> Iterable[tuple[str, str, str]]:
    """The bundled table, for tests and for anything that wants a starter list."""
    return _COMMON
