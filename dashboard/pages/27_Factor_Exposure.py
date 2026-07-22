"""
Page 27 — Factor Exposure Dashboard
Fama-French style multi-factor regression for any ticker using ETF factor proxies.
Decomposes returns into market, size, value, momentum, and quality factors.

Factor proxies (all via yfinance — no external data dependencies):
  Market (MKT-RF) : SPY excess return over approximate risk-free rate
  Size     (SMB)  : IWM return minus SPY return (small-cap minus large-cap)
  Value    (HML)  : VTV return minus VUG return (value minus growth)
  Momentum (MOM)  : MTUM (iShares MSCI USA Momentum Factor ETF)
  Quality  (QMJ)  : QUAL (iShares MSCI USA Quality Factor ETF)

Regression: R_ticker - R_f = alpha + B_mkt*MKT + B_smb*SMB + B_hml*HML
                               + B_mom*MOM + B_qual*QUAL + epsilon

All computations use daily log-returns over a rolling 2-year window.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from utils.header import render_header, render_page_header, render_sidebar_base
from utils.theme import source_badge, PLOTLY_CONFIG

st.set_page_config(page_title="Factor Exposure — UA", layout="wide")

from utils.billing import require_pro
require_pro("Factor Exposure")
render_header("Factor Exposure Dashboard")
_factor_section = render_sidebar_base(
    page_title="Factor Exposure",
    sections=("Exposure Summary", "Rolling Beta", "Risk Decomposition", "Compare Tickers"),
    section_key="factor_exposure_section_rail",
)
render_page_header(
    "Factor Exposure",
    "Decompose any stock into market, size, value, momentum, and quality factor risk using Fama-French style regression.",
    icon="",
)

# ── Constants ─────────────────────────────────────────────────────────────────
RF_DAILY       = 0.0435 / 252          # approximate annual risk-free rate / 252
LOOKBACK_DAYS  = 756                   # ~3 years of trading days
ROLL_WINDOW    = 63                    # ~1 quarter for rolling betas
MIN_OBS        = 120                   # minimum observations for regression

FACTOR_META = {
    "MKT":  {"label": "Market (β)",    "color": "#00C8E0", "desc": "Sensitivity to overall equity market moves (SPY excess return)"},
    "SMB":  {"label": "Size (SMB)",    "color": "#7C3AED", "desc": "Small-cap tilt: positive = small-cap-like, negative = large-cap-like"},
    "HML":  {"label": "Value (HML)",   "color": "#F59E0B", "desc": "Value vs growth tilt: positive = value-like (low P/B), negative = growth-like"},
    "MOM":  {"label": "Momentum",      "color": "#00D566", "desc": "Momentum loading: positive = tends to rise with recent winners"},
    "QUAL": {"label": "Quality",       "color": "#A78BFA", "desc": "Quality tilt: positive = high-profitability / low-leverage companies"},
}

FACTOR_TICKERS = {
    "SPY":  "Market proxy",
    "IWM":  "Small-cap proxy (for SMB)",
    "VTV":  "Value proxy (for HML)",
    "VUG":  "Growth proxy (for HML)",
    "MTUM": "Momentum proxy",
    "QUAL": "Quality proxy",
}


# ── Data fetcher ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, max_entries=20, show_spinner=False)
def _fetch_price_series(ticker: str, start: str, end: str) -> pd.Series:
    """Return adjusted close as a daily price series."""
    try:
        import yfinance as yf
        df = yf.download(ticker, start=start, end=end, auto_adjust=True,
                         progress=False, threads=False)
        if df.empty:
            return pd.Series(dtype=float)
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return close.dropna()
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=3600, max_entries=5, show_spinner=False)
def _build_factor_frame(start: str, end: str) -> pd.DataFrame:
    """
    Build a DataFrame of daily factor returns (log-returns, RF-adjusted where applicable).
    Columns: MKT, SMB, HML, MOM, QUAL
    """
    spy  = _fetch_price_series("SPY",  start, end)
    iwm  = _fetch_price_series("IWM",  start, end)
    vtv  = _fetch_price_series("VTV",  start, end)
    vug  = _fetch_price_series("VUG",  start, end)
    mtum = _fetch_price_series("MTUM", start, end)
    qual = _fetch_price_series("QUAL", start, end)

    # Log daily returns
    r = pd.DataFrame({
        "SPY":  np.log(spy  / spy.shift(1)),
        "IWM":  np.log(iwm  / iwm.shift(1)),
        "VTV":  np.log(vtv  / vtv.shift(1)),
        "VUG":  np.log(vug  / vug.shift(1)),
        "MTUM": np.log(mtum / mtum.shift(1)),
        "QUAL": np.log(qual / qual.shift(1)),
    }).dropna()

    factors = pd.DataFrame(index=r.index)
    factors["MKT"]  = r["SPY"] - RF_DAILY           # market excess return
    factors["SMB"]  = r["IWM"] - r["SPY"]           # small minus big
    factors["HML"]  = r["VTV"] - r["VUG"]           # value minus growth
    factors["MOM"]  = r["MTUM"] - RF_DAILY          # momentum factor
    factors["QUAL"] = r["QUAL"] - RF_DAILY           # quality factor
    return factors.dropna()


def _run_ols(y: np.ndarray, X: np.ndarray) -> dict:
    """Minimal OLS with t-stats, p-values, and R²."""
    from scipy import stats as sp_stats

    X_const = np.column_stack([np.ones(len(X)), X])
    try:
        coefs, residuals, rank, _ = np.linalg.lstsq(X_const, y, rcond=None)
    except Exception:
        return {}

    n, k = X_const.shape
    if n <= k:
        return {}
    ss_res = float(np.sum((y - X_const @ coefs) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2      = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    r2_adj  = 1 - (1 - r2) * (n - 1) / (n - k) if (n - k) > 0 else float("nan")
    mse     = ss_res / (n - k)
    cov     = mse * np.linalg.pinv(X_const.T @ X_const)
    se      = np.sqrt(np.maximum(np.diag(cov), 0))
    t_stats = coefs / (se + 1e-12)
    p_vals  = 2 * (1 - sp_stats.t.cdf(np.abs(t_stats), df=n - k))

    alpha   = float(coefs[0])
    f_coefs = coefs[1:]
    f_se    = se[1:]
    f_t     = t_stats[1:]
    f_p     = p_vals[1:]

    return {
        "alpha":      alpha,
        "alpha_ann":  alpha * 252,
        "alpha_se":   float(se[0]),
        "alpha_t":    float(t_stats[0]),
        "alpha_p":    float(p_vals[0]),
        "r2":         r2,
        "r2_adj":     r2_adj,
        "n":          n,
        "coefs":      f_coefs.tolist(),
        "se":         f_se.tolist(),
        "t_stats":    f_t.tolist(),
        "p_vals":     f_p.tolist(),
        "residual_vol": float(np.std(y - X_const @ coefs)) * np.sqrt(252),
        "systematic_vol": float(np.std((X_const @ coefs) - coefs[0])) * np.sqrt(252),
        "total_vol":  float(np.std(y)) * np.sqrt(252),
    }


def _rolling_beta(y: pd.Series, x: pd.Series, window: int) -> pd.Series:
    """Rolling OLS beta of y on x (no constant) using a simple covariance formula."""
    cov = y.rolling(window).cov(x)
    var = x.rolling(window).var()
    return (cov / var.replace(0, np.nan)).dropna()


# ── UI ────────────────────────────────────────────────────────────────────────
ticker_col, period_col, spacer = st.columns([2, 2, 4])
with ticker_col:
    ticker_input = st.text_input(
        "Ticker",
        value="NVDA",
        placeholder="e.g. AAPL, TSLA, XOM",
        key="fe_ticker",
    ).strip().upper()
with period_col:
    period_choice = st.selectbox(
        "Lookback period",
        ["1 Year", "2 Years", "3 Years"],
        index=1,
        key="fe_period",
    )

period_map = {"1 Year": 252, "2 Years": 504, "3 Years": 756}
lookback   = period_map[period_choice]
end_date   = date.today()
start_date = end_date - timedelta(days=int(lookback * 1.45))  # extra buffer for weekends/holidays
start_str  = start_date.strftime("%Y-%m-%d")
end_str    = end_date.strftime("%Y-%m-%d")

if not ticker_input:
    st.info("Enter a ticker above to begin.")
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner(f"Fetching factor proxies and {ticker_input} returns…"):
    factors = _build_factor_frame(start_str, end_str)
    ticker_prices = _fetch_price_series(ticker_input, start_str, end_str)

if ticker_prices.empty:
    st.error(f"Could not fetch price data for **{ticker_input}**. Check the ticker and try again.")
    st.stop()

if factors.empty or len(factors) < MIN_OBS:
    st.error("Could not fetch enough factor data. Please try again in a moment.")
    st.stop()

# Align ticker returns with factors
ticker_rets = np.log(ticker_prices / ticker_prices.shift(1)).dropna()
aligned     = pd.concat([ticker_rets.rename("R"), factors], axis=1).dropna()

if len(aligned) < MIN_OBS:
    st.warning(
        f"Only {len(aligned)} overlapping trading days found — results may be unreliable. "
        f"Try extending the lookback period."
    )

y = (aligned["R"] - RF_DAILY).values
X = aligned[list(FACTOR_META.keys())].values
factor_names = list(FACTOR_META.keys())

ols = _run_ols(y, X)
if not ols:
    st.error("Regression could not be computed. Try a different ticker or longer period.")
    st.stop()

# Shared regression outputs are prepared once because multiple lazy sections
# consume them independently. Previously these variables were created while
# rendering the first chart, which made later views depend on visiting the
# summary section first.
coefs = ols["coefs"]
ses = ols["se"]
t_stats = ols["t_stats"]
p_vals = ols["p_vals"]
r2 = ols["r2"]

if _factor_section == "Exposure Summary":
    # ── TradingView Advanced Chart — same professional widget as the Stock Chart page.
    try:
        from utils.tradingview import render_tradingview_chart
        render_tradingview_chart(ticker_input, chart_height=440, key=f"fe_{ticker_input}")
    except Exception:
        pass

    # ── Header KPIs ───────────────────────────────────────────────────────────────
    alpha_ann   = ols["alpha_ann"]
    r2          = ols["r2"]
    alpha_sig   = ols["alpha_p"] < 0.05
    sys_pct     = (ols["systematic_vol"] ** 2) / (ols["total_vol"] ** 2 + 1e-12) * 100
    idio_pct    = 100 - sys_pct

    alpha_color = "#00D566" if alpha_ann > 0 else "#FF4444"
    r2_color    = "#00C8E0"

    kpi_css = (
        "background:rgba(18,21,30,0.85);border:1px solid rgba(255,255,255,0.07);"
        "border-radius:10px;padding:16px 18px;font-family:Inter,sans-serif;text-align:center;"
    )
    k1, k2, k3, k4, k5 = st.columns(5)
    for col, label, val, color, hint in [
        (k1, "Annual Alpha", f"{alpha_ann*100:+.2f}%", alpha_color,
         f"{'Statistically significant (p<0.05)' if alpha_sig else 'Not significant (p≥0.05)'}"),
        (k2, "R² (factor fit)", f"{r2:.1%}", r2_color,
         "Share of return variance explained by the five factors"),
        (k3, "Systematic Risk", f"{sys_pct:.0f}%", "#7C3AED",
         "Fraction of total return variance attributable to factor exposures"),
        (k4, "Idiosyncratic Risk", f"{idio_pct:.0f}%", "#F59E0B",
         "Unexplained variance — ticker-specific alpha opportunity"),
        (k5, "Obs (days)", str(ols["n"]), "#6B7FBF",
         f"Daily return observations used in regression"),
    ]:
        col.markdown(
            f'<div style="{kpi_css}">'
            f'<div style="font-size:0.60rem;font-weight:700;color:#6B7FBF;letter-spacing:0.08em;'
            f'text-transform:uppercase;margin-bottom:6px;">{label}</div>'
            f'<div style="font-size:1.55rem;font-weight:700;color:{color};">{val}</div>'
            f'<div style="font-size:0.68rem;color:#8892AA;margin-top:4px;line-height:1.3;">{hint}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("")

    # ── Factor Loadings ───────────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#8892AA;letter-spacing:0.13em;'
        'text-transform:uppercase;border-bottom:1px solid rgba(255,255,255,0.05);'
        'padding-bottom:8px;margin:4px 0 18px;font-family:Inter,sans-serif;">Factor Loadings</div>',
        unsafe_allow_html=True,
    )

    load_col, detail_col = st.columns([3, 2])

    with load_col:
        coefs    = ols["coefs"]
        ses      = ols["se"]
        t_stats  = ols["t_stats"]
        p_vals   = ols["p_vals"]
        labels   = [FACTOR_META[f]["label"] for f in factor_names]
        colors   = [
            FACTOR_META[f]["color"] if abs(c) > se else "rgba(107,127,191,0.4)"
            for f, c, se in zip(factor_names, coefs, ses)
        ]
        bar_colors = [
            ("#00D566" if c >= 0 else "#FF4444") for c in coefs
        ]
        err_plus  = [1.96 * s for s in ses]
        err_minus = [1.96 * s for s in ses]

        fig_bar = go.Figure(go.Bar(
            x=coefs,
            y=labels,
            orientation="h",
            marker_color=bar_colors,
            marker_line_width=0,
            error_x=dict(
                type="data",
                array=err_plus,
                arrayminus=err_minus,
                color="rgba(255,255,255,0.25)",
                thickness=1.5,
                width=4,
            ),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Loading: %{x:.3f}<br>"
                "95% CI: ±%{error_x.array:.3f}"
                "<extra></extra>"
            ),
        ))
        fig_bar.add_vline(x=0, line_color="rgba(255,255,255,0.15)", line_width=1)
        fig_bar.update_layout(
            height=300, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
            margin=dict(l=0, r=10, t=10, b=10),
            xaxis=dict(
                title="Factor Loading (β)",
                showgrid=True, gridcolor="rgba(255,255,255,0.05)",
                tickfont=dict(color="#8892AA", size=10),
                title_font=dict(color="#8892AA", size=10),
                zeroline=False,
            ),
            yaxis=dict(tickfont=dict(color="#E8EEFF", size=11)),
            font=dict(family="Inter, sans-serif"),
            showlegend=False,
        )
        st.plotly_chart(fig_bar, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
        st.markdown(
            source_badge("yfinance", "ETF factor proxies") + "&nbsp;" +
            source_badge("yfinance", ticker_input),
            unsafe_allow_html=True,
        )

    with detail_col:
        # Factor detail table
        rows_html = ""
        for i, fname in enumerate(factor_names):
            coef  = coefs[i]
            se    = ses[i]
            t     = t_stats[i]
            p     = p_vals[i]
            sig   = "p<0.05" if p < 0.05 else ("p<0.10" if p < 0.10 else "")
            c_col = "#00D566" if coef >= 0 else "#FF4444"
            p_col = "#00D566" if p < 0.05 else ("#F59E0B" if p < 0.10 else "#6B7FBF")
            rows_html += (
                f'<tr style="border-bottom:1px solid rgba(255,255,255,0.04);">'
                f'<td style="padding:7px 10px;color:#E8EEFF;font-weight:600;">'
                f'{FACTOR_META[fname]["label"]}</td>'
                f'<td style="padding:7px 10px;color:{c_col};font-weight:700;text-align:right;">'
                f'{coef:+.3f}</td>'
                f'<td style="padding:7px 10px;color:#8892AA;text-align:right;">{se:.3f}</td>'
                f'<td style="padding:7px 10px;color:#8892AA;text-align:right;">{t:+.2f}</td>'
                f'<td style="padding:7px 10px;color:{p_col};text-align:right;font-weight:600;">'
                f'{p:.3f} {sig}</td>'
                f'</tr>'
            )
        st.markdown(f"""
    <div style="font-family:Inter,sans-serif;font-size:0.80rem;">
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.10);">
          <th style="padding:7px 10px;text-align:left;color:#6B7FBF;font-size:0.60rem;
                     letter-spacing:0.08em;text-transform:uppercase;">Factor</th>
          <th style="padding:7px 10px;text-align:right;color:#6B7FBF;font-size:0.60rem;
                     letter-spacing:0.08em;text-transform:uppercase;">β</th>
          <th style="padding:7px 10px;text-align:right;color:#6B7FBF;font-size:0.60rem;
                     letter-spacing:0.08em;text-transform:uppercase;">SE</th>
          <th style="padding:7px 10px;text-align:right;color:#6B7FBF;font-size:0.60rem;
                     letter-spacing:0.08em;text-transform:uppercase;">t</th>
          <th style="padding:7px 10px;text-align:right;color:#6B7FBF;font-size:0.60rem;
                     letter-spacing:0.08em;text-transform:uppercase;">p-value</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    <div style="font-size:0.67rem;color:#6B7FBF;margin-top:8px;">
      Significance labels show p&lt;0.05 or p&lt;0.10 &nbsp;·&nbsp; Error bars = 95% CI
    </div>
    </div>
    """, unsafe_allow_html=True)

        # Plain-English interpretation
        mkt_b  = coefs[0]
        sig_fs = [factor_names[i] for i in range(len(factor_names)) if p_vals[i] < 0.05]
        if sig_fs:
            interp_parts = []
            if "MKT" in sig_fs:
                interp_parts.append(
                    f"<b style='color:#00C8E0;'>Market β = {mkt_b:.2f}</b> — "
                    f"{'amplifies' if mkt_b > 1 else 'dampens'} broad market moves"
                )
            if "SMB" in sig_fs:
                smb = coefs[1]
                interp_parts.append(
                    f"<b style='color:#7C3AED;'>Size</b>: trades like a "
                    f"{'small-cap' if smb > 0 else 'large-cap'}"
                )
            if "HML" in sig_fs:
                hml = coefs[2]
                interp_parts.append(
                    f"<b style='color:#F59E0B;'>Value</b>: {'value' if hml > 0 else 'growth'} tilt"
                )
            if "MOM" in sig_fs:
                mom = coefs[3]
                interp_parts.append(
                    f"<b style='color:#00D566;'>Momentum</b>: {'rides' if mom > 0 else 'bucks'} recent winners"
                )
            if "QUAL" in sig_fs:
                q = coefs[4]
                interp_parts.append(
                    f"<b style='color:#A78BFA;'>Quality</b>: {'high-quality' if q > 0 else 'low-quality'} tilt"
                )
            interp_html = " &nbsp;·&nbsp; ".join(interp_parts)
        else:
            interp_html = (
                f"<b style='color:#00C8E0;'>Market β = {mkt_b:.2f}</b>. "
                "No other factors are statistically significant at the 5% level — "
                "returns are predominantly driven by broad market movements."
            )

        st.markdown(
            f'<div style="background:rgba(18,21,30,0.85);border:1px solid rgba(255,255,255,0.07);'
            f'border-radius:8px;padding:12px 14px;font-family:Inter,sans-serif;'
            f'font-size:0.79rem;color:#B8C0D4;line-height:1.6;margin-top:12px;">'
            f'<b style="color:#E8EEFF;">Interpretation: </b>{interp_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

if _factor_section == "Rolling Beta":
    # ── Rolling Beta ──────────────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#8892AA;letter-spacing:0.13em;'
        'text-transform:uppercase;border-bottom:1px solid rgba(255,255,255,0.05);'
        'padding-bottom:8px;margin:24px 0 18px;font-family:Inter,sans-serif;">Rolling Market Beta (63-day)</div>',
        unsafe_allow_html=True,
    )

    roll_y = aligned["R"] - RF_DAILY
    roll_x = aligned["MKT"]
    rolling_mkt_beta = _rolling_beta(roll_y, roll_x, ROLL_WINDOW)

    if len(rolling_mkt_beta) > 10:
        # Color segments above/below 1.0
        beta_arr   = rolling_mkt_beta.values
        dates_arr  = rolling_mkt_beta.index

        fig_roll = go.Figure()
        fig_roll.add_hline(y=1.0, line_dash="dot", line_color="rgba(255,255,255,0.20)",
                           line_width=1, annotation_text="β = 1.0 (market)",
                           annotation_font_color="#6B7FBF", annotation_font_size=9)
        fig_roll.add_trace(go.Scatter(
            x=dates_arr, y=beta_arr,
            mode="lines",
            line=dict(color="#00C8E0", width=2),
            fill="tozeroy",
            fillcolor="rgba(0,200,224,0.07)",
            hovertemplate="%{x|%Y-%m-%d}: β = %{y:.2f}<extra></extra>",
            name="Market β",
        ))
        # Current beta annotation
        cur_beta = float(beta_arr[-1]) if len(beta_arr) else float("nan")
        if not np.isnan(cur_beta):
            fig_roll.add_trace(go.Scatter(
                x=[dates_arr[-1]], y=[cur_beta],
                mode="markers+text",
                marker=dict(color="#00C8E0", size=8),
                text=[f"  β={cur_beta:.2f}"],
                textfont=dict(color="#E8EEFF", size=10),
                textposition="middle right",
                showlegend=False,
                hoverinfo="skip",
            ))
        fig_roll.update_layout(
            height=220, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
            margin=dict(l=0, r=40, t=10, b=10),
            xaxis=dict(showgrid=False, tickfont=dict(color="#8892AA", size=10)),
            yaxis=dict(
                showgrid=True, gridcolor="rgba(255,255,255,0.05)",
                tickfont=dict(color="#8892AA", size=10),
                title=dict(text="β (Market)", font=dict(color="#8892AA", size=10)),
            ),
            showlegend=False,
            font=dict(family="Inter, sans-serif"),
        )
        st.plotly_chart(fig_roll, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
        st.caption(
            f"63-day (quarterly) rolling OLS beta against SPY. Current: {cur_beta:.2f}. "
            "High market beta means the stock amplifies index moves; below 1.0 means it dampens them."
        )
    else:
        st.info("Not enough aligned data for rolling beta chart.")

if _factor_section == "Risk Decomposition":
    # ── Risk Decomposition ────────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#8892AA;letter-spacing:0.13em;'
        'text-transform:uppercase;border-bottom:1px solid rgba(255,255,255,0.05);'
        'padding-bottom:8px;margin:24px 0 18px;font-family:Inter,sans-serif;">Return Variance Decomposition</div>',
        unsafe_allow_html=True,
    )

    vol_c1, vol_c2, vol_c3 = st.columns(3)

    total_vol = ols["total_vol"] * 100
    sys_vol   = ols["systematic_vol"] * 100
    idio_vol  = np.sqrt(max(0, total_vol**2 - sys_vol**2))

    _vol_css = (
        "background:rgba(18,21,30,0.85);border:1px solid rgba(255,255,255,0.07);"
        "border-radius:10px;padding:14px 16px;font-family:Inter,sans-serif;text-align:center;"
    )
    for col, label, val, color, desc in [
        (vol_c1, "Total Annualized Vol", f"{total_vol:.1f}%", "#E8EEFF",
         "sqrt(252) × daily log-return std dev"),
        (vol_c2, "Systematic Vol", f"{sys_vol:.1f}%", "#7C3AED",
         "Explained by factor exposures"),
        (vol_c3, "Idiosyncratic Vol", f"{idio_vol:.1f}%", "#F59E0B",
         "Unexplained by any factor"),
    ]:
        col.markdown(
            f'<div style="{_vol_css}">'
            f'<div style="font-size:0.60rem;font-weight:700;color:#6B7FBF;letter-spacing:0.08em;'
            f'text-transform:uppercase;margin-bottom:6px;">{label}</div>'
            f'<div style="font-size:1.45rem;font-weight:700;color:{color};">{val}</div>'
            f'<div style="font-size:0.68rem;color:#8892AA;margin-top:4px;">{desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        col.markdown("")

    # Donut chart: factor variance attribution
    factor_variances = []
    factor_labels_pie = []
    factor_colors_pie = []

    aligned_Xmat = aligned[factor_names].values
    coef_arr     = np.array(coefs)
    for i, fname in enumerate(factor_names):
        xi     = aligned_Xmat[:, i]
        contrib = float(coef_arr[i]**2 * np.var(xi))
        factor_variances.append(contrib)
        factor_labels_pie.append(FACTOR_META[fname]["label"])
        factor_colors_pie.append(FACTOR_META[fname]["color"])

    # Add idiosyncratic component
    total_var_factors = sum(factor_variances)
    y_arr  = y
    fitted = aligned_Xmat @ coef_arr + ols["alpha"]
    resid_var = float(np.var(y_arr - fitted))
    factor_variances.append(resid_var)
    factor_labels_pie.append("Idiosyncratic")
    factor_colors_pie.append("#3A3F55")

    pie_col, interp_col2 = st.columns([2, 3])

    with pie_col:
        fig_pie = go.Figure(go.Pie(
            labels=factor_labels_pie,
            values=factor_variances,
            marker=dict(colors=factor_colors_pie, line=dict(color="#0B0D12", width=2)),
            hole=0.55,
            textfont=dict(color="#E8EEFF", size=10),
            hovertemplate="<b>%{label}</b><br>%{percent:.1%} of variance<extra></extra>",
            sort=False,
        ))
        fig_pie.update_layout(
            height=240, paper_bgcolor="#0B0D12", plot_bgcolor="#0B0D12",
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=True,
            legend=dict(
                font=dict(color="#B8C0D4", size=9),
                bgcolor="rgba(0,0,0,0)",
                orientation="v", x=1.0, y=0.5,
            ),
            font=dict(family="Inter, sans-serif"),
        )
        # Center label
        fig_pie.add_annotation(
            text=f"R²<br><b style='color:#00C8E0'>{r2:.0%}</b>",
            x=0.5, y=0.5, showarrow=False,
            font=dict(color="#E8EEFF", size=11, family="Inter"),
        )
        st.plotly_chart(fig_pie, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

    with interp_col2:
        # Factor description cards
        for i, fname in enumerate(factor_names):
            b = coefs[i]
            p = p_vals[i]
            c = FACTOR_META[fname]["color"]
            sig_marker = "●" if p < 0.05 else "○"
            st.markdown(
                f'<div style="background:rgba(18,21,30,0.7);border-left:2px solid {c};'
                f'border-radius:6px;padding:7px 12px;margin-bottom:7px;font-family:Inter,sans-serif;">'
                f'<span style="color:{c};font-weight:700;font-size:0.78rem;">'
                f'{sig_marker} {FACTOR_META[fname]["label"]}: {b:+.3f}</span>'
                f'<span style="color:#6B7FBF;font-size:0.70rem;"> (p={p:.3f})</span><br>'
                f'<span style="color:#8892AA;font-size:0.74rem;">{FACTOR_META[fname]["desc"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

if _factor_section == "Compare Tickers":
    # ── Multi-ticker comparison ───────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.62rem;font-weight:700;color:#8892AA;letter-spacing:0.13em;'
        'text-transform:uppercase;border-bottom:1px solid rgba(255,255,255,0.05);'
        'padding-bottom:8px;margin:24px 0 18px;font-family:Inter,sans-serif;">Compare Across Tickers</div>',
        unsafe_allow_html=True,
    )

    compare_input = st.text_input(
        "Add tickers to compare (comma-separated)",
        placeholder="e.g. AAPL, MSFT, JPM",
        key="fe_compare",
        help="Compare factor loadings across multiple tickers side-by-side. Leave blank to skip.",
    ).strip()

    compare_tickers = [t.strip().upper() for t in compare_input.split(",") if t.strip()]
    if ticker_input not in compare_tickers:
        compare_tickers = [ticker_input] + compare_tickers
    compare_tickers = compare_tickers[:6]  # cap at 6

    if len(compare_tickers) > 1:
        compare_results = {}
        with st.spinner("Running factor regressions for comparison tickers…"):
            for ct in compare_tickers:
                cp = _fetch_price_series(ct, start_str, end_str)
                if cp.empty:
                    continue
                cr = np.log(cp / cp.shift(1)).dropna()
                ca = pd.concat([cr.rename("R"), factors], axis=1).dropna()
                if len(ca) < MIN_OBS:
                    continue
                cy = (ca["R"] - RF_DAILY).values
                cX = ca[factor_names].values
                cr2 = _run_ols(cy, cX)
                if cr2:
                    compare_results[ct] = cr2

        if len(compare_results) >= 2:
            # Grouped bar chart: each factor, grouped by ticker
            fig_cmp = go.Figure()
            compare_colors = ["#00C8E0", "#7C3AED", "#00D566", "#F59E0B", "#FF4444", "#A78BFA"]
            for ti, (ct, cr2) in enumerate(compare_results.items()):
                fig_cmp.add_trace(go.Bar(
                    name=ct,
                    x=[FACTOR_META[f]["label"] for f in factor_names],
                    y=cr2["coefs"],
                    marker_color=compare_colors[ti % len(compare_colors)],
                    error_y=dict(
                        type="data",
                        array=[1.96 * s for s in cr2["se"]],
                        color="rgba(255,255,255,0.20)",
                        thickness=1, width=3,
                    ),
                    hovertemplate=f"<b>{ct}</b> — %{{x}}: %{{y:.3f}}<extra></extra>",
                ))
            fig_cmp.add_hline(y=0, line_color="rgba(255,255,255,0.12)", line_width=1)
            fig_cmp.update_layout(
                barmode="group",
                height=320, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
                margin=dict(l=0, r=0, t=10, b=10),
                xaxis=dict(tickfont=dict(color="#E8EEFF", size=11)),
                yaxis=dict(
                    showgrid=True, gridcolor="rgba(255,255,255,0.05)",
                    tickfont=dict(color="#8892AA", size=10),
                    title=dict(text="Factor Loading (β)", font=dict(color="#8892AA", size=10)),
                ),
                legend=dict(font=dict(color="#E8EEFF", size=10), bgcolor="rgba(18,21,30,0.85)"),
                font=dict(family="Inter, sans-serif"),
            )
            st.plotly_chart(fig_cmp, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

            # Summary table
            rows = []
            for ct, cr2 in compare_results.items():
                row = {"Ticker": ct, "Alpha (ann.)": f"{cr2['alpha_ann']*100:+.2f}%",
                       "R²": f"{cr2['r2']:.1%}"}
                for i, fname in enumerate(factor_names):
                    row[FACTOR_META[fname]["label"]] = f"{cr2['coefs'][i]:+.2f}"
                rows.append(row)
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Could not fetch enough data for comparison tickers. Try different ones.")

# ── Disclaimer ────────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:rgba(18,21,30,0.6);border:1px solid rgba(255,255,255,0.05);border-radius:8px;
            padding:10px 14px;font-size:0.73rem;color:#6B7FBF;font-family:Inter,sans-serif;
            line-height:1.5;margin-top:20px;">
<b style="color:#8892AA;">Methodology note:</b> Factor proxies use liquid ETFs (SPY, IWM, VTV/VUG, MTUM, QUAL)
as stand-ins for the academic Fama-French factors, which require daily Ken French library data.
ETF proxies introduce tracking error and expense ratios. Results are indicative, not replicable as
exact academic factors. Not financial advice.
</div>
""", unsafe_allow_html=True)
