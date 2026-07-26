# utils/tradingview.py
# Unstructured Alpha — Reusable TradingView Advanced Chart widget
#
# Extracted from pages/14_Stock_Chart.py so EVERY stock viewer (Ticker Deep Dive,
# Stock Chart, Factor Exposure, …) can embed the same professional candlestick
# chart — 100+ indicators, drawing tools, multi-timeframe — instead of each page
# rolling its own. Free to embed, no API key. Symbols auto-convert Yahoo → TV.

from __future__ import annotations

import streamlit.components.v1 as components

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


def to_tv_symbol(yahoo_sym: str) -> str:
    """Convert a Yahoo Finance symbol to a TradingView symbol string."""
    s = (yahoo_sym or "").upper().strip()
    if not s:
        return s
    if s in _INDEX_MAP:
        return _INDEX_MAP[s]
    if s.endswith("-USD") and "-" in s:
        return f"COINBASE:{s[:-4]}USD"
    if s.endswith("-USDT"):
        return f"BINANCE:{s[:-5]}USDT"
    if s.endswith("=X") and len(s) == 8:
        return f"FX:{s[:-2]}"
    for sfx, exch in _SUFFIX_MAP.items():
        if s.endswith(sfx):
            return f"{exch}:{s[:-len(sfx)]}"
    return s


def render_tradingview_chart(symbol: str, *, chart_height: int = 520,
                             key: str | None = None, studies: bool = True) -> None:
    """
    Render a TradingView Advanced Chart for a Yahoo-format `symbol`.

    chart_height: pixel height of the chart body.
    key:          unique suffix for the container id (needed if two charts render
                  in one Streamlit app run); defaults to the symbol.
    studies:      include Volume/RSI/MACD studies by default (set False for a
                  cleaner compact chart).
    """
    tv_symbol = to_tv_symbol(symbol)
    safe = "".join(c for c in (key or tv_symbol) if c.isalnum()) or "chart"
    container_id = f"tv_chart_{safe}"
    studies_json = (
        '"studies": ["Volume@tv-basicstudies","RSI@tv-basicstudies","MACD@tv-basicstudies"],'
        if studies else ""
    )
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: 100%; height: 100%; background: var(--ua-bg); }}
  #{container_id} {{ width: 100%; height: {chart_height}px; }}
</style>
</head>
<body>
<div id="{container_id}"></div>
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
  "save_image": true,
  {studies_json}
  "show_popup_button": true,
  "popup_width": "1400",
  "popup_height": "800",
  "container_id": "{container_id}",
  "support_host": "https://www.tradingview.com"
}});
</script>
</body>
</html>"""
    components.html(html, height=chart_height + 20, scrolling=False)
