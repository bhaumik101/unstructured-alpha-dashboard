"""
Page 28 — Report Export
Generate a downloadable PDF research report for any ticker.
Includes Confluence Score, signal table, price metrics, and methodology note.
Uses fpdf2 (pure Python) — no system dependencies.
"""

import io
from datetime import datetime

import numpy as np
import streamlit as st

from utils.header import (
    render_header, render_page_header, render_sidebar_base,
    render_guided_steps, disclose_unavailable_signals, count_unavailable_signals,
)
from utils.signals_cache import get_all_signal_scores
from utils.theme import inject_skeleton_css, skeleton_cards

st.set_page_config(page_title="Export Report — UA", layout="wide")

from utils.billing import require_pro
require_pro("Export Report")
render_header("Report Export")
render_sidebar_base()
render_page_header(
    "Export Report",
    "Download a PDF research report for any ticker — Confluence Score, signals, price metrics, and methodology.",
    icon="",
)

# ── Status colours for PDF (light theme) ─────────────────────────────────────
STATUS_RGB = {
    "bullish":          (0,   120, 60),    # dark green
    "bearish":          (180,  30, 30),    # dark red
    "neutral":          (80,   90, 140),   # medium blue-gray
    "insufficient_data":(130, 130, 130),   # gray
}
STATUS_LABEL = {
    "bullish":           "BULLISH",
    "bearish":           "BEARISH",
    "neutral":           "NEUTRAL",
    "insufficient_data": "NO DATA",
}


# ── Helpers ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, max_entries=10, show_spinner=False)
def _fetch_price_metrics(ticker: str) -> dict:
    """Return basic price metrics dict for the ticker."""
    try:
        import yfinance as yf
        info  = yf.Ticker(ticker).fast_info
        hist  = yf.download(ticker, period="1y", auto_adjust=True,
                            progress=False, threads=False)
        if hist.empty:
            return {}
        close = hist["Close"]
        if hasattr(close, "iloc"):
            if isinstance(close, np.ndarray):
                close = close.flatten()
            else:
                close = close.squeeze()
        current  = float(close.iloc[-1])
        high_52w = float(close.max())
        low_52w  = float(close.min())
        ytd_start_year = datetime.now().year
        ytd_df   = hist[hist.index.year == ytd_start_year]["Close"].squeeze()
        if not ytd_df.empty:
            ytd_ret  = (current / float(ytd_df.iloc[0]) - 1) * 100
        else:
            ytd_ret  = float("nan")
        chg_1d   = (current / float(close.iloc[-2]) - 1) * 100 if len(close) >= 2 else float("nan")
        return {
            "current":  current,
            "high_52w": high_52w,
            "low_52w":  low_52w,
            "ytd_ret":  ytd_ret,
            "chg_1d":   chg_1d,
            "name":     getattr(info, "long_name", ticker) or ticker,
        }
    except Exception:
        return {}


@st.cache_data(ttl=3600, max_entries=20, show_spinner=False)
def _compute_real_score(ticker: str) -> dict:
    """
    Run the full per-ticker correlation-weighted Confluence Score via
    compute_full_ticker_score(). Cached for 1 hour per ticker.
    Falls back gracefully on failure.
    """
    try:
        from utils.score_cache import get_full_ticker_score
        return get_full_ticker_score(ticker).result
    except Exception as exc:
        return {
            "confluence": {"overall_score": 50.0, "case": "neutral"},
            "insider_score": None,
            "short_interest_score": None,
            "thirteenf_score": None,
            "insider_tx": [],
            "thirteenf_fund_rows": [],
            "_error": str(exc),
        }


def _fmt_shares(v) -> str:
    """Format a share count for the PDF, never crashing on non-numeric input
    (compute_full_ticker_score may hand back ints, floats, or strings)."""
    try:
        return f"{int(float(v)):,}"
    except (TypeError, ValueError):
        s = str(v).replace(",", "").replace("$", "").strip()
        try:
            return f"{int(float(s)):,}"
        except Exception:
            return (str(v)[:12] or "0")


def _pdf_safe_text(value, limit: int | None = None) -> str:
    """Return text that FPDF's built-in Helvetica font can always encode.

    Provider data regularly contains smart quotes, em dashes and arrows. One
    such character previously raised FPDFUnicodeEncodingException and aborted
    the whole export. Keep readable ASCII equivalents, then replace any rare
    remaining unsupported glyph instead of failing the report.
    """
    text = str(value or "").translate(str.maketrans({
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "—": "-", "–": "-", "→": "->", "←": "<-",
        "•": "-", "…": "...", "\u00a0": " ",
    }))
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text[:limit] if limit is not None else text


def build_pdf(
    ticker: str,
    company_name: str,
    score: float,
    score_status: str,
    all_signals: dict,
    price_metrics: dict,
    generated_at: str,
    insider_score: float | None = None,
    short_interest_score: float | None = None,
    thirteenf_score: float | None = None,
    insider_tx: list | None = None,
    thirteenf_fund_rows: list | None = None,
) -> bytes:
    """Build and return PDF bytes for the ticker report."""
    from fpdf import FPDF

    # ── Palette ───────────────────────────────────────────────────────────────
    NAVY   = (15,  25,  60)
    GRAY_L = (245, 245, 248)
    GRAY_M = (200, 205, 215)
    WHITE  = (255, 255, 255)
    BLACK  = (20,  20,  30)
    SCORE_RGB = STATUS_RGB.get(score_status, (80, 90, 140))

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    # ── Header band ───────────────────────────────────────────────────────────
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 30, "F")
    pdf.set_xy(10, 7)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*WHITE)
    pdf.cell(130, 8, "UNSTRUCTURED ALPHA")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(160, 170, 200)
    pdf.set_xy(140, 10)
    pdf.cell(60, 6, f"Generated {generated_at}", align="R")

    # Keep source availability inside the file so forwarded reports retain the
    # same real-data integrity contract as the live application.
    _n_unavailable, _n_tot = count_unavailable_signals(all_signals)
    if _n_unavailable > 0:
        pdf.set_xy(10, 20)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(255, 180, 60)
        pdf.cell(
            190, 6,
            f"REAL DATA UNAVAILABLE: {_n_unavailable} of {_n_tot} signals were "
            f"excluded. No placeholder observations are included.",
        )

    # ── Ticker + company ──────────────────────────────────────────────────────
    pdf.set_xy(10, 36)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(*NAVY)
    pdf.cell(100, 12, ticker)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(80, 90, 110)
    pdf.set_xy(10, 50)
    company_name = _pdf_safe_text(company_name)
    name_display = company_name[:60] + ("..." if len(company_name) > 60 else "")
    pdf.cell(190, 7, name_display)

    # ── Confluence Score box ──────────────────────────────────────────────────
    pdf.set_fill_color(*SCORE_RGB)
    pdf.set_xy(140, 34)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*WHITE)
    pdf.cell(60, 7, "CONFLUENCE SCORE", align="C", fill=True)
    pdf.set_xy(140, 41)
    pdf.set_font("Helvetica", "B", 30)
    pdf.cell(60, 16, f"{score:.0f}", align="C", fill=True)
    pdf.set_xy(140, 57)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(60, 7, STATUS_LABEL.get(score_status, ""), align="C", fill=True)

    # ── Price metrics row ─────────────────────────────────────────────────────
    pdf.set_xy(10, 70)
    if price_metrics:
        metrics = [
            ("Price",     f"${price_metrics.get('current', 0):.2f}"),
            ("1D Change", f"{price_metrics.get('chg_1d', float('nan')):+.2f}%"
                          if not np.isnan(price_metrics.get("chg_1d", float("nan"))) else "-"),
            ("YTD",       f"{price_metrics.get('ytd_ret', float('nan')):+.1f}%"
                          if not np.isnan(price_metrics.get("ytd_ret", float("nan"))) else "-"),
            ("52w High",  f"${price_metrics.get('high_52w', 0):.2f}"),
            ("52w Low",   f"${price_metrics.get('low_52w', 0):.2f}"),
        ]
        box_w = 37
        for i, (label, val) in enumerate(metrics):
            x = 10 + i * (box_w + 2)
            pdf.set_fill_color(*GRAY_L)
            pdf.rect(x, 70, box_w, 16, "F")
            pdf.set_xy(x, 72)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(100, 110, 130)
            pdf.cell(box_w, 5, label.upper(), align="C")
            pdf.set_xy(x, 77)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*NAVY)
            pdf.cell(box_w, 7, val, align="C")

    # ── Section divider helper ────────────────────────────────────────────────
    def section_header(title: str, y: float | None = None):
        _y = y if y is not None else pdf.get_y() + 6
        pdf.set_xy(10, _y)
        pdf.set_fill_color(*NAVY)
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.set_text_color(*WHITE)
        pdf.cell(190, 6, f"  {title.upper()}", fill=True)
        pdf.ln(2)

    # ── Top signals summary ───────────────────────────────────────────────────
    section_header("Signal Summary", y=92)

    sorted_sigs = sorted(
        [(sid, sv) for sid, sv in all_signals.items() if not sv.get("error")],
        key=lambda x: abs(x[1].get("score", 50) - 50),
        reverse=True,
    )
    bull_sigs = [(s, sv) for s, sv in sorted_sigs if sv.get("status") == "bullish"][:5]
    bear_sigs = [(s, sv) for s, sv in sorted_sigs if sv.get("status") == "bearish"][:5]

    def _mini_signal_table(sigs: list, start_x: float, label: str, color_rgb: tuple):
        y0 = pdf.get_y()
        pdf.set_xy(start_x, y0)
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.set_text_color(*color_rgb)
        pdf.cell(90, 5, label)
        pdf.ln(1)
        for sid, sv in sigs:
            cfg   = sv.get("config", {})
            name  = _pdf_safe_text(cfg.get("name", sid), 38)
            score = sv.get("score", 50)
            pdf.set_xy(start_x, pdf.get_y())
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*BLACK)
            pdf.cell(72, 5, name)
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(*color_rgb)
            pdf.cell(18, 5, f"{score:.0f}", align="R")
            pdf.ln(0)
            pdf.set_xy(start_x, pdf.get_y() + 5)

    y_before = pdf.get_y()
    _mini_signal_table(bull_sigs, 10,  "Most Bullish Signals", STATUS_RGB["bullish"])
    y_after_bull = pdf.get_y()
    pdf.set_y(y_before)
    _mini_signal_table(bear_sigs, 105, "Most Bearish Signals", STATUS_RGB["bearish"])
    pdf.set_y(max(y_after_bull, pdf.get_y()))

    # ── Full signal table ─────────────────────────────────────────────────────
    if pdf.get_y() > 210:
        pdf.add_page()
    section_header("All Signals")

    # Column headers
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_text_color(80, 90, 110)
    pdf.set_fill_color(*GRAY_M)
    pdf.cell(85, 5, "  Signal", fill=True)
    pdf.cell(35, 5, "Category", fill=True)
    pdf.cell(22, 5, "Score", align="C", fill=True)
    pdf.cell(28, 5, "Status", align="C", fill=True)
    pdf.cell(20, 5, "PCS", align="C", fill=True)
    pdf.ln()

    for i, (sid, sv) in enumerate(sorted_sigs):
        if pdf.get_y() > 270:
            pdf.add_page()
            # Repeat column headers
            pdf.set_font("Helvetica", "B", 6.5)
            pdf.set_text_color(80, 90, 110)
            pdf.set_fill_color(*GRAY_M)
            pdf.cell(85, 5, "  Signal", fill=True)
            pdf.cell(35, 5, "Category", fill=True)
            pdf.cell(22, 5, "Score", align="C", fill=True)
            pdf.cell(28, 5, "Status", align="C", fill=True)
            pdf.cell(20, 5, "PCS", align="C", fill=True)
            pdf.ln()

        cfg    = sv.get("config", {})
        name   = _pdf_safe_text(cfg.get("name", sid), 44)
        cat    = _pdf_safe_text(cfg.get("category", "").replace("_", " ").title(), 22)
        score  = sv.get("score", 50)
        status = sv.get("status", "neutral")
        pcs    = cfg.get("pcs", 0)
        rgb    = STATUS_RGB.get(status, (130, 130, 130))

        fill = GRAY_L if i % 2 == 0 else WHITE
        pdf.set_fill_color(*fill)
        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(*BLACK)
        pdf.cell(85, 4.5, f"  {name}", fill=True)
        pdf.cell(35, 4.5, cat, fill=True)

        pdf.set_font("Helvetica", "B", 6.5)
        pdf.set_text_color(*rgb)
        pdf.cell(22, 4.5, f"{score:.0f}", align="C", fill=True)
        pdf.cell(28, 4.5, STATUS_LABEL.get(status, ""), align="C", fill=True)

        pdf.set_text_color(*BLACK)
        pdf.set_font("Helvetica", "", 6.5)
        pdf.cell(20, 4.5, f"{pcs}/10", align="C", fill=True)
        pdf.ln()

    # ── Positioning & Alternative Data ────────────────────────────────────────
    _alt_data = [
        ("Insider Activity",  insider_score),
        ("Short Interest",    short_interest_score),
        ("13F Institutional", thirteenf_score),
    ]
    _has_alt = any(v is not None for _, v in _alt_data)
    if _has_alt:
        if pdf.get_y() > 248:
            pdf.add_page()
        section_header("Positioning & Alternative Data")
        y0 = pdf.get_y() + 3
        box_w, box_h, gap = 58, 20, 6
        col_i = 0
        for label, val in _alt_data:
            if val is None:
                continue
            st_key = "bullish" if val >= 65 else ("bearish" if val <= 35 else "neutral")
            rgb = STATUS_RGB.get(st_key, (80, 90, 140))
            x = 10 + col_i * (box_w + gap)
            pdf.set_fill_color(*GRAY_L)
            pdf.rect(x, y0, box_w, box_h, "F")
            pdf.set_xy(x, y0 + 2)
            pdf.set_font("Helvetica", "", 6.5)
            pdf.set_text_color(80, 90, 110)
            pdf.cell(box_w, 4, label, align="C")
            pdf.set_xy(x, y0 + 7)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(*rgb)
            pdf.cell(box_w, 8, f"{val:.0f}", align="C")
            pdf.set_xy(x, y0 + 15)
            pdf.set_font("Helvetica", "B", 6)
            pdf.set_text_color(*rgb)
            pdf.cell(box_w, 4, STATUS_LABEL.get(st_key, ""), align="C")
            col_i += 1
        pdf.set_y(y0 + box_h + 4)

        # Insider transactions (top 4)
        if insider_tx:
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(*NAVY)
            pdf.set_x(10)
            pdf.cell(190, 5, "Recent Insider Transactions (SEC Form 4)")
            pdf.ln(1)
            for tx in (insider_tx or [])[:4]:
                name_tx  = _pdf_safe_text(tx.get("insider_name", ""), 26)
                title_tx = _pdf_safe_text(tx.get("title", ""), 18)
                txtype   = str(tx.get("transaction_type", ""))
                shares   = tx.get("shares", 0) or 0
                date_tx  = str(tx.get("transaction_date", ""))[:10]
                is_buy   = txtype.upper() in ("P", "BUY", "PURCHASE", "A")
                t_rgb    = STATUS_RGB["bullish"] if is_buy else STATUS_RGB["bearish"]
                pdf.set_xy(10, pdf.get_y())
                pdf.set_font("Helvetica", "", 6.5)
                pdf.set_text_color(*BLACK)
                pdf.cell(52, 4.5, name_tx)
                pdf.cell(36, 4.5, title_tx)
                pdf.set_text_color(*t_rgb)
                pdf.set_font("Helvetica", "B", 6.5)
                pdf.cell(22, 4.5, "BUY" if is_buy else "SELL")
                pdf.set_text_color(*BLACK)
                pdf.set_font("Helvetica", "", 6.5)
                pdf.cell(40, 4.5, f"{_fmt_shares(shares)} sh")
                pdf.cell(40, 4.5, date_tx, align="R")
                pdf.ln()
            pdf.ln(2)

        # 13F top funds (top 4)
        if thirteenf_fund_rows:
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(*NAVY)
            pdf.set_x(10)
            pdf.cell(190, 5, "Top Institutional Holders (13F)")
            pdf.ln(1)
            for fund in (thirteenf_fund_rows or [])[:4]:
                fname  = _pdf_safe_text(fund.get("fund_name", fund.get("manager", "")), 50)
                shares = fund.get("shares", fund.get("value", 0)) or 0
                pdf.set_xy(10, pdf.get_y())
                pdf.set_font("Helvetica", "", 6.5)
                pdf.set_text_color(*BLACK)
                pdf.cell(145, 4.5, fname)
                pdf.cell(45, 4.5, _fmt_shares(shares), align="R")
                pdf.ln()
            pdf.ln(2)

    # ── Methodology note ──────────────────────────────────────────────────────
    if pdf.get_y() > 255:
        pdf.add_page()
    section_header("Methodology & Disclaimer")
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_text_color(80, 90, 110)
    pdf.set_xy(10, pdf.get_y() + 2)
    pdf.multi_cell(190, 4, (
        "Signal scores are computed as 0-100 percentile ranks within each series' trailing 2-year "
        "distribution, mapped through a tanh function. The Confluence Score is the full "
        "correlation-weighted per-ticker score, blending macro signals (weighted by price correlation), "
        "price momentum (20%), and optional positioning signals (insider activity, short interest, "
        "13F institutional flows, 12% each where available). Signals are sourced from FRED, EIA, "
        "SEC EDGAR, FINRA, and yfinance. All data is public domain. "
        "NOT FINANCIAL ADVICE. Past signal accuracy does not predict future performance. "
        "Always conduct independent due diligence before making any investment decision. "
        "Platform: unstructuredalpha.com | Generated by Unstructured Alpha " + generated_at
    ))

    # ── Footer line ───────────────────────────────────────────────────────────
    pdf.set_y(-14)
    pdf.set_fill_color(*NAVY)
    pdf.set_font("Helvetica", "", 6)
    pdf.set_text_color(*WHITE)
    pdf.cell(190, 6, "Unstructured Alpha  ·  unstructuredalpha.com  ·  Not financial advice",
             align="C", fill=True)

    return bytes(pdf.output())


# ── UI ────────────────────────────────────────────────────────────────────────
# Pre-fill ticker if navigated here from Ticker Deep Dive. Assign the widget's
# keyed state directly: passing value= alone is ignored after the widget has
# existed once in this session, which made the export page keep the old ticker.
_requested_export_ticker = st.session_state.pop("export_ticker", "")
if _requested_export_ticker:
    st.session_state["export_ticker_input"] = _requested_export_ticker
_prefill = st.session_state.get("export_ticker_input", "NVDA")

render_guided_steps(
    "Build a presentation-ready research report",
    [
        ("Confirm the company", "Review the ticker and live score preview before generating the report."),
        ("Generate the report", "Select Generate PDF Report to package the current score, signals, positioning, and methodology."),
        ("Download and share", "Use the download action when it appears. Any unavailable live coverage remains clearly disclosed."),
    ],
    eyebrow="PDF report workflow",
    intro="The exported report uses the same live evidence shown across Unstructured Alpha and never substitutes synthetic observations.",
)

col_ticker, col_btn, col_space = st.columns([2, 2, 4])
with col_ticker:
    ticker_input = st.text_input(
        "Ticker",
        value=_prefill,
        placeholder="e.g. AAPL, TSLA, XOM",
        key="export_ticker_input",
    ).strip().upper()

if not ticker_input:
    st.info("Enter a ticker symbol to generate a report.")
    st.stop()

# Load signals (shared cache from Signal Dashboard)
inject_skeleton_css()
_sk = st.empty()
_sk.markdown(skeleton_cards(n=3, height=60, cols=3), unsafe_allow_html=True)
all_signals = get_all_signal_scores()

# Data-integrity disclosure. Exported files preserve the same provider-availability
# warning and never contain placeholder observations.
disclose_unavailable_signals(all_signals)
_sk.empty()

# Real per-ticker correlation-weighted Confluence Score
with st.spinner(f"Computing {ticker_input} score…"):
    _score_result = _compute_real_score(ticker_input)

_confluence_data   = _score_result.get("confluence", {})
score              = float(_confluence_data.get("overall_score", 50.0))
_raw_score_status  = str(_confluence_data.get("case", "neutral")).strip().lower()
score_status       = {
    "bull": "bullish", "bullish": "bullish",
    "bear": "bearish", "bearish": "bearish",
    "neutral": "neutral", "mixed": "neutral",
    "insufficient_data": "insufficient_data",
}.get(_raw_score_status, "neutral")
insider_score      = _score_result.get("insider_score")
short_interest_score = _score_result.get("short_interest_score")
thirteenf_score    = _score_result.get("thirteenf_score")
_insider_tx        = _score_result.get("insider_tx") or []
_thirteenf_rows    = _score_result.get("thirteenf_fund_rows") or []

# Preview metrics
with st.spinner(f"Loading {ticker_input} price data…"):
    price_metrics = _fetch_price_metrics(ticker_input)

company_name = price_metrics.get("name", ticker_input)

# ── Preview card ──────────────────────────────────────────────────────────────
score_color = (
    "#00D566" if score_status == "bullish" else
    "#FF4444" if score_status == "bearish" else
    "#6B7FBF"
)
score_label = {
    "bullish": "Bullish",
    "bearish": "Bearish",
    "neutral": "Neutral",
}.get(score_status, "—")

st.markdown(f"""
<div style="background:rgba(18,21,30,0.85);border:1px solid rgba(255,255,255,0.07);
            border-radius:12px;padding:20px 24px;font-family:Inter,sans-serif;margin-bottom:16px;">
  <div style="display:flex;align-items:flex-start;gap:24px;flex-wrap:wrap;">
    <div style="flex:1;min-width:200px;">
      <div style="font-size:1.4rem;font-weight:700;color:#E8EEFF;">{ticker_input}</div>
      <div style="font-size:0.82rem;color:#6B7FBF;margin-bottom:12px;">{company_name}</div>
      <div style="display:flex;gap:20px;flex-wrap:wrap;font-size:0.82rem;color:#B8C0D4;">
        {"".join(
            f'<div><span style="color:#6B7FBF;">{k}</span><br>'
            f'<b style="color:#E8EEFF;">{v}</b></div>'
            for k, v in [
                ("Price",    f"${price_metrics.get('current', 0):.2f}" if price_metrics else "—"),
                ("1D",       f"{price_metrics.get('chg_1d', float('nan')):+.2f}%" if price_metrics and not (isinstance(price_metrics.get('chg_1d'), float) and price_metrics.get('chg_1d') != price_metrics.get('chg_1d')) else "—"),
                ("YTD",      f"{price_metrics.get('ytd_ret', float('nan')):+.1f}%" if price_metrics and not (isinstance(price_metrics.get('ytd_ret'), float) and price_metrics.get('ytd_ret') != price_metrics.get('ytd_ret')) else "—"),
                ("52w High", f"${price_metrics.get('high_52w', 0):.2f}" if price_metrics else "—"),
                ("52w Low",  f"${price_metrics.get('low_52w', 0):.2f}" if price_metrics else "—"),
            ]
        )}
      </div>
    </div>
    <div style="text-align:center;background:rgba({','.join(str(c) for c in STATUS_RGB.get(score_status,(80,90,140)))},0.15);
                border:1px solid rgba({','.join(str(c) for c in STATUS_RGB.get(score_status,(80,90,140)))},0.3);
                border-radius:10px;padding:14px 24px;min-width:120px;">
      <div style="font-size:0.60rem;font-weight:700;color:#8892AA;letter-spacing:0.10em;
                  text-transform:uppercase;margin-bottom:4px;">Confluence Score</div>
      <div style="font-size:2.4rem;font-weight:700;color:{score_color};">{score:.0f}</div>
      <div style="font-size:0.78rem;color:{score_color};font-weight:600;">{score_label}</div>
    </div>
  </div>
  <div style="margin-top:14px;font-size:0.75rem;color:#6B7FBF;">
    {sum(1 for sv in all_signals.values() if sv.get('status')=='bullish')} bullish ·
    {sum(1 for sv in all_signals.values() if sv.get('status')=='bearish')} bearish ·
    {sum(1 for sv in all_signals.values() if sv.get('status')=='neutral')} neutral ·
    {sum(1 for sv in all_signals.values() if sv.get('error'))} no data
    across {len(all_signals)} signals
  </div>
</div>
""", unsafe_allow_html=True)

# ── Generate PDF ──────────────────────────────────────────────────────────────
with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    generate = st.button("Generate PDF Report", type="primary", use_container_width=True,
                         key="gen_pdf")

# Rate-limit actual PDF generation (not the cached re-display of a ready report).
if generate:
    try:
        from utils.ratelimit import guard as _rl_guard
        _ex_ok, _ex_retry = _rl_guard("export")
    except Exception:
        _ex_ok, _ex_retry = True, 0
    if not _ex_ok:
        st.warning(
            f" You've generated several reports recently — please wait "
            f"~{max(1, _ex_retry // 60)} min before the next one."
        )
        generate = False

if generate:
    try:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        with st.spinner("Building PDF…"):
            pdf_bytes = build_pdf(
                ticker=ticker_input,
                company_name=company_name,
                score=score,
                score_status=score_status,
                all_signals=all_signals,
                price_metrics=price_metrics,
                generated_at=generated_at,
                insider_score=insider_score,
                short_interest_score=short_interest_score,
                thirteenf_score=thirteenf_score,
                insider_tx=_insider_tx,
                thirteenf_fund_rows=_thirteenf_rows,
            )
        st.session_state["pdf_payload"] = {
            "ticker": ticker_input,
            "bytes": pdf_bytes,
            "file_name": f"UA_{ticker_input}_{datetime.now().strftime('%Y%m%d')}.pdf",
        }
    except ImportError:
        st.error(
            "**fpdf2 is not installed.** Run `pip install fpdf2` on your Render instance "
            "or ensure `fpdf2>=2.7.0` is in requirements.txt and redeploy."
        )
    except Exception as e:
        st.error(f"PDF generation failed: {e}")
        st.exception(e)

_pdf_payload = st.session_state.get("pdf_payload") or {}
if _pdf_payload.get("ticker") == ticker_input and _pdf_payload.get("bytes"):
    pdf_bytes = _pdf_payload["bytes"]
    st.success(f"Report ready — {len(pdf_bytes)//1024} KB")
    st.download_button(
        label=f"Download {ticker_input} Research Report (PDF)",
        data=pdf_bytes,
        file_name=_pdf_payload["file_name"],
        mime="application/pdf",
        use_container_width=True,
        key="pdf_dl",
    )
    st.caption(
        "Report includes: full correlation-weighted Confluence Score, all signal scores, "
        "price metrics, insider activity, short interest, 13F institutional positioning, "
        "and methodology note."
    )

# ── Signal preview table ───────────────────────────────────────────────────────
st.markdown(
    '<div style="font-size:0.62rem;font-weight:700;color:#8892AA;letter-spacing:0.13em;'
    'text-transform:uppercase;border-bottom:1px solid rgba(255,255,255,0.05);'
    'padding-bottom:8px;margin:20px 0 14px;font-family:Inter,sans-serif;">Signal Preview</div>',
    unsafe_allow_html=True,
)

STATUS_COLOR_HEX = {
    "bullish":           "#00D566",
    "bearish":           "#FF4444",
    "neutral":           "#6B7FBF",
    "insufficient_data": "#4A4A6A",
}

preview_rows = []
for sid, sv in sorted(
    all_signals.items(),
    key=lambda x: abs(x[1].get("score", 50) - 50),
    reverse=True,
):
    if sv.get("error"):
        continue
    cfg = sv.get("config", {})
    preview_rows.append({
        "Signal":   cfg.get("name", sid),
        "Category": cfg.get("category", "").replace("_", " ").title(),
        "Score":    round(sv.get("score", 50), 1),
        "Status":   sv.get("status", "neutral").upper(),
        "PCS":      cfg.get("pcs", 0),
        "Source":   "Live",
    })

if preview_rows:
    import pandas as pd
    st.dataframe(
        pd.DataFrame(preview_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%.0f"
            ),
        },
    )
