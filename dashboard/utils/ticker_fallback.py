# utils/ticker_fallback.py
# Unstructured Alpha — what a ticker without a page gets instead of an error
#
# Two cases used to fall through to a bare JSON 404 ({"detail": ...}):
#   * an S&P 500 tracker (SPY, VOO, IVV, VTI...). These are never measured on
#     purpose: every reading here is a move *beyond the stock market*, and the
#     market control is SPY itself, so a tracker's readings are zero by
#     construction. They are also among the most-searched tickers there are,
#     so each gets a real page that says exactly that and points to the funds
#     that do move beyond the market.
#   * any other ticker not on record. It gets a 404 page (status 404, noindex)
#     that offers to measure it in the app, near matches from the library, and
#     the ticker box -- never an estimated reading.
#
# A stock whose newest reading is well behind the library's week (its price
# history stopped meeting the two-year rule, or the data source dropped it)
# keeps its page and gets stale_notice_html: the reading is shown, dated, and
# the page says it is no longer being refreshed.

from __future__ import annotations

from datetime import date
from html import escape
from typing import Iterable, List

from utils.exposure_pages import SYMBOL_RE, _shell, app_link, tool_header_html

STALE_DAYS = 14
_CSS = '<style>.tf-cols{columns:2 220px;padding-left:18px;margin:0 0 12px}.tf-cols li{margin:0 0 6px}</style>'

TRACKER_NAMES = {
    "SPY": "SPDR S&P 500 ETF Trust", "VOO": "Vanguard S&P 500 ETF", "IVV": "iShares Core S&P 500 ETF",
    "SPLG": "SPDR Portfolio S&P 500 ETF", "VTI": "Vanguard Total Stock Market ETF",
    "ITOT": "iShares Core S&P Total U.S. Stock Market ETF", "SCHX": "Schwab U.S. Large-Cap ETF",
}


def _day(iso: str) -> date | None:
    try:
        return date.fromisoformat(str(iso)[:10])
    except ValueError:
        return None


def _label(iso: str) -> str:
    d = _day(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}" if d else str(iso)


def stale_notice_html(rec_as_of: str, library_week: str) -> str:
    """A notice for a reading more than STALE_DAYS behind the library's week;
    empty otherwise."""
    a, b = _day(rec_as_of), _day(library_week)
    if not a or not b or (b - a).days <= STALE_DAYS:
        return ""
    return ('<p class="caveat" role="status"><b>This reading is no longer being updated.</b> It is through '
            f'{escape(_label(rec_as_of))}; the rest of the library is through {escape(_label(library_week))}. '
            'The latest weekly prices for this ticker could not be measured (a reading needs at least two '
            'years of weekly price history, so a renamed or merged company can drop out). It is shown as it '
            'last stood, not estimated forward.</p>')


def near_matches(symbol: str, stocks: Iterable[dict], n: int = 6) -> List[dict]:
    """Stocks on record whose ticker starts like this one, or sits one letter
    away -- a typo or a share class, never a guess at the company."""
    sym = symbol.upper()
    out = []
    for s in stocks:
        t = s.get("ticker") or ""
        if not SYMBOL_RE.match(t) or t == sym:
            continue
        prefix = len(sym) >= 2 and (t.startswith(sym[:max(2, len(sym) - 1)]) or sym.startswith(t))
        one_off = len(t) == len(sym) and sum(a != b for a, b in zip(t, sym)) == 1
        if prefix or one_off:
            out.append((0 if t.startswith(sym) else 1, t, s))
    return [s for *_, s in sorted(out, key=lambda x: (x[0], x[1]))[:n]]


def _stock_links(stocks: List[dict]) -> str:
    return "".join(f'<li><a href="/exposure/{escape(s["ticker"])}"><b>{escape(s["ticker"])}</b></a>'
                   + (f' <span class="small">{escape(s.get("name") or "")}</span>' if s.get("name") else "")
                   + '</li>' for s in stocks)


def tracker_page_html(symbol: str, stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    from utils.funds import MARKET_TRACKERS, is_fund
    assert symbol in MARKET_TRACKERS
    stocks = list(stocks)
    name = TRACKER_NAMES.get(symbol, "")
    canonical = f"{base_url}/exposure/{symbol}"
    title = f"{symbol} and the economy: why an S&P 500 fund has no readings here"
    desc = (f"{symbol} tracks the U.S. stock market, and every reading on Unstructured Alpha is a move beyond "
            "the stock market. Here is what that means, and the funds and stocks that do move with oil, "
            "rates and the dollar.")
    funds = sorted((s for s in stocks if is_fund(s.get("ticker") or "")), key=lambda s: s["ticker"])
    examples = [s for s in funds if s["ticker"] in ("QQQ", "XLE", "XLU", "TLT", "GLD", "KRE", "IWM", "XLF")]
    body = (
        _CSS + f'<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › <a href="/exposure">Stock exposures</a> '
        f'› {escape(symbol)}</nav>'
        + tool_header_html(f"{symbol}: the market itself", ["Tracks the S&amp;P 500" if symbol != "VTI" and symbol != "ITOT"
                                                             else "Tracks the U.S. market", "No readings, by design"],
                           escape(name + ". " if name else "") + "Every reading on this site is measured beyond "
                           "the stock market&#39;s own move, so the market has nothing left to show.")
        + '<h2>Why there are no readings</h2>'
        '<p>Each reading answers one question: in a week when a force such as oil or interest rates moved, how '
        'did a stock move <b>beyond what the market as a whole did</b>? '
        + ('The market&#39;s move is measured with SPY itself'
           if symbol == "SPY" else f'The market&#39;s move is measured with SPY, and {escape(symbol)} moves almost '
           'exactly with it')
        + ', so once the market&#39;s move is taken out, nothing is left: every reading would be zero by '
        'construction. Showing zeros would look like a finding; it is not one.</p>'
        '<p>In a portfolio, this site counts S&amp;P 500 funds as zero beyond the market. That is the point: '
        'a mix that is mostly an index fund has little economic tilt of its own, and the tilt comes from '
        'everything else you hold.</p>'
        + (f'<h2>Funds that do move beyond the market</h2><ul class="tf-cols">{_stock_links(examples)}</ul>'
           '<p><a href="/etfs">Every ETF on record</a></p>' if examples else "")
        + '<div class="actions">'
        f'<a class="btn btn-primary" href="/xray#p={escape(symbol)}:60,AGG:40">X-ray a mix with {escape(symbol)} in it</a>'
        '<a class="btn btn-secondary" href="/forces">Every economic force</a>'
        '<a class="btn btn-secondary" href="/learn#market">What &ldquo;beyond the market&rdquo; means</a></div>'
        '<p class="caveat"><b>This describes how the readings are made; it is not a forecast.</b> Nothing '
        'here is a recommendation to buy, sell or hold any security.</p>')
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc,
          "url": canonical}
    return _shell(title, desc, canonical, ld, body, app_url)


def missing_page_html(symbol: str, stocks: Iterable[dict], base_url: str, app_url: str) -> str:
    """The 404 page for a ticker not on record (serve it with status 404)."""
    stocks = list(stocks)
    sym = escape(symbol)
    canonical = f"{base_url}/exposure/{symbol}"
    title = f"{symbol} has not been measured yet"
    desc = f"{symbol} is not in the library yet. Measure it free in the app, or browse the stocks on record."
    near = near_matches(symbol, stocks)
    body = (
        _CSS + f'<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › <a href="/exposure">Stock exposures</a> '
        f'› {sym}</nav>'
        + tool_header_html(f"{symbol} has not been measured yet",
                           [f"{len(stocks):,} stocks and ETFs on record"],
                           "The library holds every S&amp;P 500 company and the most-held ETFs. Anything "
                           "else can be measured in the app, and is added here once it is.")
        + '<div class="actions">'
        f'<a class="btn btn-primary" href="{escape(app_link(app_url, "/stock", canonical, t=symbol))}">'
        f'Measure {sym} in the app, free</a>'
        '<a class="btn btn-secondary" href="/exposure">Browse every stock on record</a></div>'
        + (f'<h2>On record with a similar ticker</h2><ul class="tf-cols">{_stock_links(near)}</ul>' if near else "")
        + '<p class="small">A ticker gets a page only once it has at least two years of weekly prices and '
        'has been measured. Nothing on this site is estimated for a stock that has not been.</p>')
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc,
          "url": canonical}
    return _shell(title, desc, canonical, ld, body, app_url, robots="noindex, follow")
