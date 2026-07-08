"""
Page 14 — Stock Viewer
TradingView Advanced Chart widget + yfinance stats strip.
- TradingView handles candlesticks, timeframes, 100+ indicators, drawing tools, replay.
- yfinance is used only for the price header and stats strip.
- Symbol auto-converts from Yahoo Finance format to TradingView format.
Not a research page — use Ticker Deep Dive for macro signal analysis.
"""

import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

from utils.config import TICKERS
from utils.header import render_header, render_sidebar_base, render_page_header

st.set_page_config(page_title="Stock Viewer — UA", layout="wide")
render_header("Stock Viewer")
render_sidebar_base()

render_page_header(
    "Stock Viewer",
    "Professional charts powered by TradingView — 100+ indicators, drawing tools, multi-timeframe.",
    icon="📉",
)

# ── Design tokens ─────────────────────────────────────────────────────────────
_BULL = "#00D566"
_BEAR = "#FF4444"
_NAVY = "#E8EEFF"
_TAN  = "#8892AA"
_BG   = "#0B0D12"

# ── Incoming ticker from Watchlist / other pages ───────────────────────────────
if st.session_state.get("chart_ticker"):
    st.session_state["_sc_ticker"] = st.session_state.pop("chart_ticker")

# ── Symbol conversion: Yahoo Finance → TradingView format ─────────────────────
_INDEX_MAP: dict[str, str] = {
    "^GSPC": "SP:SPX",    "^DJI":  "DJ:DJI",     "^IXIC": "NASDAQ:COMP",
    "^RUT":  "TVC:RUT",   "^VIX":  "CBOE:VIX",   "^TNX":  "TVC:TNX",
    "^TYX":  "TVC:US30Y", "^IRX":  "TVC:IRX",
    "^FTSE": "LSE:UKX",   "^N225": "TVC:NI225",  "^HSI":  "TVC:HSI",
    "^DAX":  "XETR:DAX",  "^STOXX50E": "EUREX:FESX1!",
}
_SUFFIX_MAP: dict[str, str] = {
    ".PA": "EURONEXT", ".L": "LSE",      ".T":  "TSE",
    ".HK": "HKEX",     ".DE": "XETR",   ".MI": "MIL",
    ".TO": "TSX",       ".AX": "ASX",
}


def _to_tv_symbol(yahoo_sym: str) -> str:
    """Convert Yahoo Finance symbol to TradingView symbol string."""
    s = yahoo_sym.upper().strip()
    if s in _INDEX_MAP:
        return _INDEX_MAP[s]
    # Crypto: BTC-USD → COINBASE:BTCUSD
    if s.endswith("-USD") and "-" in s:
        base = s[:-4]
        return f"COINBASE:{base}USD"
    if s.endswith("-USDT"):
        return f"BINANCE:{s[:-5]}USDT"
    # FX pairs: EURUSD=X → FX:EURUSD
    if s.endswith("=X") and len(s) == 8:
        return f"FX:{s[:-2]}"
    # International equities
    for sfx, exch in _SUFFIX_MAP.items():
        if s.endswith(sfx):
            return f"{exch}:{s[:-len(sfx)]}"
    # US stock / ETF — pass bare symbol; TradingView resolves it
    return s


# ── Control bar ────────────────────────────────────────────────────────────────
_c1, _c2 = st.columns([2, 8])
with _c1:
    _raw = st.text_input(
        "Symbol", key="_sc_ticker", max_chars=20,
        label_visibility="collapsed",
        placeholder="AAPL, BTC-USD, ^GSPC, EURUSD=X…",
        help=(
            "Any Yahoo Finance symbol: US stocks, ETFs, indices (^GSPC, ^VIX), "
            "crypto (BTC-USD), FX (EURUSD=X), international (MC.PA, 9984.T)"
        ),
    )
    TICKER = (_raw or "SPY").strip().upper()

tv_symbol = _to_tv_symbol(TICKER)

# ── Data fetch (for price header + stats strip only) ──────────────────────────
@st.cache_data(ttl=300, show_spinner=False, max_entries=30)
def _load_meta(ticker: str) -> dict:
    try:
        t  = yf.Ticker(ticker)
        fi = t.fast_info
        df = t.history(period="5d", interval="1d", auto_adjust=True)
        last  = float(df["Close"].iloc[-1])  if not df.empty          else None
        prev  = float(df["Close"].iloc[-2])  if len(df) > 1           else last
        open_ = float(df["Open"].iloc[-1])   if not df.empty          else None
        high_ = float(df["High"].iloc[-1])   if not df.empty          else None
        low_  = float(df["Low"].iloc[-1])    if not df.empty          else None
        vol   = int(df["Volume"].iloc[-1])   if not df.empty          else None
        return {
            "name":       getattr(fi, "long_name",           None) or getattr(fi, "short_name", None),
            "last":       last,
            "prev":       prev,
            "open":       open_,
            "high":       high_,
            "low":        low_,
            "volume":     vol,
            "pre_price":  getattr(fi, "pre_market_price",    None),
            "post_price": getattr(fi, "post_market_price",   None),
            "52w_high":   getattr(fi, "fifty_two_week_high", None) or getattr(fi, "year_high",  None),
            "52w_low":    getattr(fi, "fifty_two_week_low",  None) or getattr(fi, "year_low",   None),
            "mkt_cap":    getattr(fi, "market_cap",          None),
        }
    except Exception:
        return {}


with st.spinner(f"Loading {TICKER}…"):
    meta = _load_meta(TICKER)

last_price = meta.get("last")
prev_close = meta.get("prev") or last_price
chg        = (last_price - prev_close) if (last_price is not None and prev_close) else None
chg_pct    = (chg / prev_close * 100) if (chg is not None and prev_close) else None
chg_color  = (_BULL if chg >= 0 else _BEAR) if chg is not None else _TAN
chg_arrow  = ("▲" if chg >= 0 else "▼") if chg is not None else ""

company_name = TICKERS.get(TICKER, {}).get("name") or meta.get("name") or TICKER

# Pre / post market badges
pre_price  = meta.get("pre_price")
post_price = meta.get("post_price")
_ext_parts: list[str] = []
for _label, _price in [("Pre", pre_price), ("Post", post_price)]:
    if _price and last_price and abs(_price - last_price) > 0.005:
        _pc = (_price - last_price) / last_price * 100
        _cc = _BULL if _pc >= 0 else _BEAR
        _ext_parts.append(
            f'<span style="font-size:0.76rem;color:{_cc};background:rgba(255,255,255,0.06);'
            f'padding:2px 8px;border-radius:6px;margin-left:8px;border:1px solid {_cc}33;">'
            f'{_label} ${_price:,.2f} ({_pc:+.2f}%)</span>'
        )

# ── Price header ───────────────────────────────────────────────────────────────
_hc1, _hc2 = st.columns([6, 1])
with _hc1:
    _price_str = f"${last_price:,.2f}" if last_price is not None else "—"
    _chg_str   = (
        f"{chg_arrow} {abs(chg):,.2f} ({chg_pct:+.2f}%)"
        if chg is not None and chg_pct is not None else ""
    )
    st.markdown(
        f'<div style="margin-bottom:2px;font-family:Inter,sans-serif;">'
        f'<span style="font-size:1.3rem;font-weight:700;color:{_NAVY};">{company_name}</span>'
        f'<span style="font-size:0.82rem;color:{_TAN};margin-left:9px;font-weight:500;">{TICKER}</span>'
        f'</div>'
        f'<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">'
        f'<span style="font-size:2.0rem;font-weight:800;color:{_NAVY};letter-spacing:-1px;">{_price_str}</span>'
        f'<span style="font-size:0.92rem;font-weight:600;color:{chg_color};">{_chg_str}</span>'
        f'{"".join(_ext_parts)}'
        f'</div>',
        unsafe_allow_html=True,
    )
with _hc2:
    if st.button("→ Deep Dive", key="_sc_tdd",
                 help="Ticker Deep Dive: signals, earnings, insider data"):
        st.session_state["selected_ticker"] = TICKER
        st.switch_page("pages/3_Ticker_Deep_Dive.py")

# ── TradingView Advanced Chart widget ─────────────────────────────────────────
# Widget docs: https://www.tradingview.com/widget/advanced-chart/
# Free to embed; no API key required. All indicators, drawing tools, and
# timeframes are available natively inside the widget.
_tv_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: 100%; height: 100%; background: #0b0d12; }}
  #tv_chart {{ width: 100%; height: 620px; }}
</style>
</head>
<body>
<div id="tv_chart"></div>
<script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
<script type="text/javascript">
new TradingView.widget({{
  "autosize": true,
  "symbol": "{tv_symbol}",
  "interval": "D",
  "timezone": "America/New_York",
  "theme": "dark",
  "style": "1",
  "locale": "en",
  "toolbar_bg": "#12151e",
  "backgroundColor": "rgba(11,13,18,1)",
  "gridColor": "rgba(255,255,255,0.04)",
  "enable_publishing": false,
  "withdateranges": true,
  "hide_side_toolbar": false,
  "allow_symbol_change": false,
  "details": true,
  "hotlist": false,
  "calendar": false,
  "save_image": true,
  "studies": [
    "Volume@tv-basicstudies",
    "RSI@tv-basicstudies",
    "MACD@tv-basicstudies"
  ],
  "show_popup_button": true,
  "popup_width": "1400",
  "popup_height": "800",
  "container_id": "tv_chart",
  "support_host": "https://www.tradingview.com"
}});
</script>
</body>
</html>"""

components.html(_tv_html, height=640, scrolling=False)

# ── Stats strip ────────────────────────────────────────────────────────────────
def _fv(v) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        if f >= 1e12: return f"${f/1e12:.2f}T"
        if f >= 1e9:  return f"${f/1e9:.2f}B"
        if f >= 1e6:  return f"${f/1e6:.1f}M"
        return f"{f:,.0f}"
    except Exception:
        return "—"


_stats = [
    ("Open",     f"${meta['open']:,.2f}"       if meta.get("open")     else "—"),
    ("High",     f"${meta['high']:,.2f}"       if meta.get("high")     else "—"),
    ("Low",      f"${meta['low']:,.2f}"        if meta.get("low")      else "—"),
    ("Close",    f"${last_price:,.2f}"         if last_price is not None else "—"),
    ("Volume",   _fv(meta.get("volume"))),
    ("52W High", f"${meta['52w_high']:,.2f}"   if meta.get("52w_high") else "—"),
    ("52W Low",  f"${meta['52w_low']:,.2f}"    if meta.get("52w_low")  else "—"),
    ("Mkt Cap",  _fv(meta.get("mkt_cap"))),
]

_s_cols = st.columns(len(_stats))
for _col, (label, val) in zip(_s_cols, _stats):
    _col.markdown(
        f'<div style="text-align:center;padding:8px 0 4px;font-family:Inter,sans-serif;">'
        f'<div style="font-size:0.62rem;color:#6B7FBF;letter-spacing:0.10em;'
        f'text-transform:uppercase;margin-bottom:3px;font-weight:700;">{label}</div>'
        f'<div style="font-size:0.92rem;font-weight:700;color:{_NAVY};">{val}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown(
    f'<div style="font-size:0.68rem;color:#6B7FBF;padding:6px 0;font-family:Inter,sans-serif;">'
    f'Charts powered by '
    f'<a href="https://www.tradingview.com" target="_blank" style="color:#8892AA;">TradingView</a>. '
    f'Price stats via Yahoo Finance. '
    f'Accepts any global symbol: US stocks, ETFs, indices (^GSPC, ^VIX), '
    f'crypto (BTC-USD), FX (EURUSD=X), international equities (MC.PA, 9984.T). '
    f'For macro signal analysis, use <b style="color:#8892AA">Ticker Deep Dive</b>.</div>',
    unsafe_allow_html=True,
)
