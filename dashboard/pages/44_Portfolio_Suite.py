# pages/44_Portfolio_Suite.py
# Unstructured Alpha — Portfolio Intelligence (Pro)
# Combines: Portfolio Backtest · Macro Stress Tester · Signal Backtester ·
#           Portfolio Macro Analyzer · Basket Builder
# All tools in one Pro-gated hub.

import streamlit as st

st.set_page_config(page_title="Portfolio Intelligence — UA", layout="wide")

from utils.header import render_header, render_sidebar_base, render_page_header, disclose_unavailable_signals
from utils.theme import inject_premium_css, PLOTLY_CONFIG
from utils.billing import require_pro

render_header("Portfolio Intelligence")
_portfolio_section = render_sidebar_base(
    page_title="Portfolio Intelligence",
    sections=("Holdings", "Portfolio Review", "Macro Exposure", "Stress Tester", "Portfolio Backtest", "Signal Backtester", "Basket Builder"),
    section_key="portfolio_suite_section_rail",
)
try:
    from utils.instrumentation import record_once
    record_once("portfolio_suite_viewed")
except Exception:
    pass
inject_premium_css()

require_pro(page_name="Portfolio Intelligence")

render_page_header(
    "Portfolio Intelligence",
    "Save the portfolio you actually own, then monitor its macro exposure, scenario risk, signal history, and concentration from one workspace.",
    icon="",
)

# Data-integrity disclosure: this page presents/acts on macro-signal scores. If
# any underlying signal is synthetic (no FRED/EIA key or a failed live fetch),
# that must be visible here, not only on the Signal Dashboard. Same cached call
# the page's own logic uses, so no extra network cost.
from utils.signals_cache import get_all_signal_scores as _gas_disc
disclose_unavailable_signals(_gas_disc())


# ── Persistent portfolio context ─────────────────────────────────────────────
# One source of truth feeds every tool below. A watchlist is a set of ideas; a
# portfolio is an owned book with weights, so the two must not be conflated.
from utils.portfolio_workspace import get_default_holdings, parse_holdings_text, replace_default_holdings

_portfolio_user = st.session_state.get("user")
_saved_holdings = get_default_holdings(_portfolio_user["id"]) if _portfolio_user else []
_workspace_holdings = [
    {
        "ticker": row["ticker"],
        "weight": float(row["weight_pct"]),
        "shares": row.get("shares"),
        "cost_basis": row.get("cost_basis"),
    }
    for row in _saved_holdings
]


if _portfolio_section == "Holdings":
    import pandas as pd

    st.markdown("#### Your saved portfolio")
    st.caption(
        "These positions persist across sessions and power Portfolio Macro X-Ray, "
        "scenario analysis, and the personalized daily intelligence workspace. "
        "Weights are normalized to 100% when saved."
    )

    if _workspace_holdings:
        _holdings_frame = pd.DataFrame([
            {
                "Ticker": row["ticker"],
                "Portfolio weight": row["weight"],
                "Shares": row.get("shares"),
                "Cost basis": row.get("cost_basis"),
            }
            for row in _workspace_holdings
        ])
        st.dataframe(
            _holdings_frame,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Portfolio weight": st.column_config.ProgressColumn(
                    "Portfolio weight", min_value=0, max_value=100, format="%.1f%%"
                ),
                "Shares": st.column_config.NumberColumn("Shares", format="%.3f"),
                "Cost basis": st.column_config.NumberColumn("Cost basis", format="$%.2f"),
            },
        )
        _largest = max(_workspace_holdings, key=lambda row: row["weight"])
        _summary_cols = st.columns(3)
        _summary_cols[0].metric("Holdings", len(_workspace_holdings))
        _summary_cols[1].metric("Total weight", f'{sum(row["weight"] for row in _workspace_holdings):.1f}%')
        _summary_cols[2].metric("Largest position", f'{_largest["ticker"]} · {_largest["weight"]:.1f}%')
    else:
        st.info(
            "No portfolio is saved yet. Paste the stocks you own below to activate weighted "
            "portfolio exposure and daily monitoring."
        )

    _default_portfolio_text = "\n".join(
        f'{row["ticker"]}, {row["weight"]:.4g}' for row in _workspace_holdings
    )
    with st.form("portfolio_holdings_form"):
        _portfolio_text = st.text_area(
            "Holdings — one per line",
            value=_default_portfolio_text,
            placeholder="NVDA, 30\nAAPL, 25\nMSFT, 20\nXOM, 15\nJPM, 10",
            height=180,
            help="Use TICKER, weight%. If weights are omitted, positions are equal-weighted.",
        )
        _save_portfolio = st.form_submit_button(
            "Save portfolio", type="primary", use_container_width=True
        )

    if _save_portfolio:
        try:
            from utils.symbols import get_symbol_index
            _known_symbols = set(get_symbol_index())
        except Exception:
            from utils.config import TICKERS
            _known_symbols = set(TICKERS)
        _parsed_holdings, _rejected_holdings = parse_holdings_text(
            _portfolio_text, valid_symbols=_known_symbols
        )
        if not _parsed_holdings and _portfolio_text.strip():
            st.error("No valid US-listed ticker symbols were found. Check the symbols and try again.")
        else:
            replace_default_holdings(_portfolio_user["id"], _parsed_holdings)
            st.session_state.pop("stress_holdings", None)
            st.session_state.pop("macro_holdings", None)
            st.session_state["ps_macro_analyzed"] = False
            try:
                from utils.analytics import Event, track
                track(
                    Event.PORTFOLIO_SAVED,
                    user_id=_portfolio_user["id"],
                    properties={"holdings_count": len(_parsed_holdings)},
                )
            except Exception:
                pass
            if _rejected_holdings:
                st.warning(
                    "Saved the valid holdings. Skipped: " + ", ".join(_rejected_holdings[:8])
                )
            else:
                st.success("Portfolio saved. Every Portfolio Intelligence view now uses these weights.")
            st.rerun()

    if _workspace_holdings:
        st.markdown("---")
        st.markdown("#### Continue your workflow")
        _next_cols = st.columns(4)
        if _next_cols[0].button("Open portfolio review", use_container_width=True):
            st.session_state["portfolio_suite_section_rail"] = "Portfolio Review"
            st.rerun()
        if _next_cols[1].button("Analyze macro exposure", use_container_width=True):
            st.session_state["portfolio_suite_section_rail"] = "Macro Exposure"
            st.rerun()
        if _next_cols[2].button("Run a stress scenario", use_container_width=True):
            st.session_state["portfolio_suite_section_rail"] = "Stress Tester"
            st.rerun()
        if _next_cols[3].button("Open Today's Brief", use_container_width=True):
            st.switch_page("pages/2_Today_Digest.py")


if _portfolio_section == "Portfolio Review":
    from utils.personalized_brief import load_portfolio_evidence
    from utils.portfolio_review import (
        build_review_input,
        generate_portfolio_review,
        get_cached_review,
        render_portfolio_review_html,
    )
    from utils.risk_profile import get_risk_profile

    st.markdown("#### Portfolio Review")
    st.caption(
        "An executive read of your saved holdings, position weights, personalized scores, "
        "coverage gaps, and concentration exceptions. Generation is explicit and cached by "
        "the underlying evidence, so reopening an unchanged review creates no model cost."
    )

    if not _portfolio_user or not _workspace_holdings:
        st.info(
            "Save your actual holdings in the Holdings section first. The review requires "
            "position weights and never substitutes a generic or synthetic portfolio."
        )
    else:
        _review_evidence = load_portfolio_evidence(_portfolio_user["id"], limit=25)
        _review_profile = get_risk_profile(_portfolio_user["id"])
        _review_input = build_review_input(_review_evidence, _review_profile)
        _review_summary = _review_input["summary"]

        _review_metrics = st.columns(4)
        _review_metrics[0].metric("Saved holdings", len(_workspace_holdings))
        _review_metrics[1].metric("Scored holdings", _review_summary["n_scored"])
        _review_metrics[2].metric(
            "Evidence coverage", f'{_review_summary["scored_weight_pct"]:.1f}%'
        )
        _weighted_review_score = _review_summary.get("weighted_your_score")
        _review_metrics[3].metric(
            "Weighted Your Score",
            f"{_weighted_review_score:.1f}/100" if _weighted_review_score is not None else "Unavailable",
        )

        if not _review_input["holdings"]:
            st.warning(
                "None of these holdings has trustworthy recorded score evidence yet. Open each "
                "holding in Ticker Deep Dive first; unavailable positions remain excluded."
            )
        else:
            _review = get_cached_review(
                _portfolio_user["id"], _review_input["input_hash"]
            )
            if _review is None:
                with st.container(border=True):
                    st.markdown("##### Generate the current executive review")
                    st.caption(
                        "This reads stored evidence only—no market-data provider calls. A maximum "
                        "of three materially new reviews can be generated per account per day."
                    )
                    if st.button(
                        "Generate portfolio review",
                        type="primary",
                        use_container_width=True,
                        key="portfolio_review_generate",
                    ):
                        with st.status("Building an evidence-constrained review…", expanded=False) as _review_status:
                            _review = generate_portfolio_review(
                                _portfolio_user["id"], _review_input
                            )
                            if _review.get("status") == "limited":
                                _retry_hours = max(1, int(_review.get("retry_after", 3600)) // 3600)
                                _review_status.update(
                                    label="Daily review limit reached", state="error", expanded=True
                                )
                                st.warning(
                                    f"Review generation is limited for cost protection. Try again in "
                                    f"about {_retry_hours} hour{'s' if _retry_hours != 1 else ''}."
                                )
                            else:
                                _review_status.update(
                                    label="Portfolio review ready", state="complete", expanded=False
                                )
                                try:
                                    from utils.instrumentation import record
                                    record(
                                        "portfolio_review_generated",
                                        model=_review.get("model"),
                                        evidence_count=_review_summary["n_scored"],
                                    )
                                except Exception:
                                    pass

            if _review and _review.get("status") == "ready":
                st.html(render_portfolio_review_html(_review))
                _review_age = str(_review.get("updated_at") or "")[:19].replace("T", " ")
                _review_mode = (
                    "AI synthesis + deterministic evidence controls"
                    if _review.get("model_synthesis")
                    else "Deterministic evidence review"
                )
                st.caption(
                    f"{_review_mode} · {_review_age or 'current evidence'} UTC · "
                    "automatically invalidates when holdings, saved weights, risk profile, or recorded scores change."
                )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — PORTFOLIO BACKTEST  (core logic from 39_Portfolio_Backtest.py)
# ─────────────────────────────────────────────────────────────────────────────
if _portfolio_section == "Portfolio Backtest":
    import pandas as pd
    import plotly.graph_objects as go
    from datetime import datetime, timedelta, timezone

    from utils.config import TICKERS as _TK
    from utils.backtest_integrity import (
        DEFAULT_COST_BPS, DEFAULT_BORROW_BPS_ANNUAL,
    )
    st.markdown("#### Signal-Driven Long/Short Backtest")
    st.caption(f"Rank all {len(_TK)} tickers by confluence score at each rebalance date. Go long the top N, short the bottom N.")

    bc1, bc2, bc3, bc4 = st.columns(4)
    bull_thresh = bc1.slider("Bull threshold", 55, 80, 65, key="ps_bull")
    bear_thresh = bc2.slider("Bear threshold", 20, 45, 35, key="ps_bear")
    n_pos       = bc3.slider("N positions/side", 3, 15, 5, key="ps_n")
    lookback_y  = bc4.slider("Lookback (years)", 1, 5, 2, key="ps_ly")

    rebal_freq  = st.radio("Rebalance", ["Weekly (7d)", "Monthly (30d)"], horizontal=True, key="ps_rebal")
    rebal_days  = 7 if "Weekly" in rebal_freq else 30

    @st.cache_data(ttl=3600, show_spinner=False, max_entries=4)
    def _run_backtest(bull_t, bear_t, n, years, rebal):
        from utils.db import engine, score_snapshots
        from sqlalchemy import select
        import yfinance as yf
        import numpy as np

        cutoff = (datetime.now(timezone.utc) - timedelta(days=365*years)).strftime("%Y-%m-%d")
        try:
            with engine.begin() as conn:
                rows = conn.execute(
                    select(score_snapshots)
                    .where(score_snapshots.c.snapshot_date >= cutoff)
                    .order_by(score_snapshots.c.snapshot_date)
                ).mappings().all()
        except Exception:
            return None

        if not rows:
            return None

        df = pd.DataFrame([dict(r) for r in rows])
        pivot = df.pivot_table(index="snapshot_date", columns="ticker", values="score")
        pivot = pivot.ffill()

        dates = pd.to_datetime(pivot.index)
        rebal_dates = []
        last = None
        for d in dates:
            if last is None or (d - last).days >= rebal:
                rebal_dates.append(d)
                last = d

        if len(rebal_dates) < 3:
            return None

        all_tickers = list(pivot.columns)
        start_px = (datetime.now() - timedelta(days=365*years+30)).strftime("%Y-%m-%d")
        end_px   = datetime.now().strftime("%Y-%m-%d")
        try:
            prices = yf.download(all_tickers, start=start_px, end=end_px,
                                  auto_adjust=True, progress=False)["Close"]
            if isinstance(prices, pd.Series):
                prices = prices.to_frame(name=all_tickers[0])
        except Exception:
            return None

        prices.index = pd.to_datetime(prices.index)
        daily_returns = prices.pct_change().fillna(0)

        long_eq = pd.Series(dtype=float)
        short_eq = pd.Series(dtype=float)
        combined_eq = pd.Series(dtype=float)
        contributions: dict[str, float] = {}

        equity = 100.0
        l_eq = s_eq = c_eq = 100.0
        prev_date = None

        from utils.backtest_integrity import (
            point_in_time_row, turnover_cost, borrow_cost,
        )

        prev_longs: set[str] = set()
        prev_shorts: set[str] = set()
        n_rebalances = 0

        for i, rb_date in enumerate(rebal_dates[:-1]):
            next_rb = rebal_dates[i + 1]

            # Most recent score AT OR BEFORE the rebalance date. This previously
            # used get_indexer(method="nearest"), which resolves in either
            # direction — when the closest snapshot postdated the rebalance the
            # backtest selected holdings from a score that did not exist yet,
            # while the caption below claimed the result was out-of-sample.
            score_row = point_in_time_row(pivot, rb_date)
            if score_row is None:
                continue  # no information existed yet; skip rather than guess
            ranked = score_row.dropna().sort_values(ascending=False)

            longs  = [t for t in ranked.index if ranked[t] >= bull_t][:n]
            shorts = [t for t in ranked.index[::-1] if ranked[t] <= bear_t][:n]
            if not longs and not shorts:
                continue
            n_rebalances += 1

            period = daily_returns.loc[rb_date:next_rb]
            if period.empty:
                continue

            l_rets = period[longs].mean(axis=1)  if longs  else pd.Series(0, index=period.index)
            s_rets = -period[shorts].mean(axis=1) if shorts else pd.Series(0, index=period.index)

            # Costs, charged on the first day of each holding period. A weekly
            # long/short book paying nothing in spread, commission or borrow is
            # not a strategy anyone can actually run, and omitting them is what
            # makes paper results look tradeable.
            _held_days = max((next_rb - rb_date).days, 1)
            _l_cost = turnover_cost(prev_longs, set(longs))
            _s_cost = turnover_cost(prev_shorts, set(shorts)) + (
                borrow_cost(_held_days) if shorts else 0.0
            )
            if len(l_rets):
                l_rets = l_rets.copy()
                l_rets.iloc[0] -= _l_cost
            if len(s_rets):
                s_rets = s_rets.copy()
                s_rets.iloc[0] -= _s_cost
            prev_longs, prev_shorts = set(longs), set(shorts)

            c_rets = (l_rets + s_rets) / 2

            for day, r in c_rets.items():
                l_eq  *= (1 + l_rets.get(day, 0))
                s_eq  *= (1 + s_rets.get(day, 0))
                c_eq  *= (1 + r)
                long_eq[day]     = l_eq
                short_eq[day]    = s_eq
                combined_eq[day] = c_eq

            for t in longs:
                if t in period.columns:
                    contributions[t] = contributions.get(t, 0) + period[t].sum()
            for t in shorts:
                if t in period.columns:
                    contributions[t] = contributions.get(t, 0) + (-period[t].sum())

        if long_eq.empty:
            return None

        spy_start = long_eq.index[0].strftime("%Y-%m-%d") if len(long_eq) else start_px
        try:
            spy_px = yf.download("SPY", start=spy_start, end=end_px,
                                  auto_adjust=True, progress=False)["Close"].squeeze()
            spy_eq = (spy_px / spy_px.iloc[0] * 100) if not spy_px.empty else pd.Series()
        except Exception:
            spy_eq = pd.Series()

        return {
            "long_eq": long_eq, "short_eq": short_eq,
            "combined_eq": combined_eq, "spy_eq": spy_eq,
            "rebalances": n_rebalances,
            "contributions": dict(sorted(contributions.items(), key=lambda x: -abs(x[1]))[:15]),
        }

    def _stats(eq: pd.Series, rebalances: int) -> dict:
        """Formatted statistics, with unsupported figures rendered as "—".

        The previous version always computed a CAGR by raising the total return
        to 1/years. On the ~4 weeks of score history that exists today that
        exponent is about 13, so a few percent became tens of percent and was
        displayed beside SPY's genuine multi-year CAGR. utils.backtest_integrity
        returns None for anything the sample cannot support; "—" is the honest
        rendering of None here, not a formatting fallback.
        """
        from utils.backtest_integrity import report as _bt_report

        if eq is None or eq.empty or len(eq) < 5:
            return {}
        r = _bt_report(eq, rebalances)

        def _pct(x, signed=True):
            if x is None:
                return "—"
            return f"{x * 100:+.1f}%" if signed else f"{x * 100:.1f}%"

        sharpe_txt = "—"
        if r["sharpe"] is not None:
            sharpe_txt = f"{r['sharpe']:.2f} ± {r['sharpe_se']:.2f}"

        return {
            "Total Return": _pct(r["total_return"]),
            "CAGR": _pct(r["cagr"]),
            "Sharpe": sharpe_txt,
            "Max Drawdown": _pct(r["max_drawdown"], signed=False),
            "_sufficiency": r["sufficiency"],
        }

    if st.button("Run Backtest", key="ps_run_bt"):
        with st.spinner("Running walk-forward backtest…"):
            result = _run_backtest(bull_thresh, bear_thresh, n_pos, lookback_y, rebal_days)

        if result is None:
            st.info("Not enough score_snapshots history yet. Keep using Ticker Deep Dive to build it up — scores are snapshotted at view time.")
        else:
            # Lead with what the sample can support. Showing the curve first and
            # the caveat last invites reading the curve as the result.
            _rebals = result.get("rebalances", 0)
            _suff = _stats(result["combined_eq"], _rebals).get("_sufficiency")
            if _suff is not None and not _suff.ok:
                st.warning(
                    f"**{_suff.headline}** This run covers {_suff.days} days, "
                    f"{_suff.observations} trading sessions and {_suff.rebalances} "
                    "rebalances.\n\n"
                    + "\n".join(f"- {r}" for r in _suff.reasons)
                    + "\n\nTotal return and drawdown are shown because they make no "
                    "claim about a longer period. CAGR and Sharpe are withheld rather "
                    "than extrapolated — annualising a sample this short multiplies "
                    "the apparent return several-fold."
                )

            s1, s2, s3, s4 = st.columns(4)
            for col, label, eq in [(s1,"Long",result["long_eq"]),(s2,"Short",result["short_eq"]),
                                    (s3,"Combined",result["combined_eq"]),(s4,"SPY",result["spy_eq"])]:
                stats = _stats(eq, _rebals)
                if stats:
                    col.metric(f"{label} Return",  stats.get("Total Return","—"))
                    col.metric(f"{label} Sharpe",  stats.get("Sharpe","—"),
                               help="Shown as estimate ± standard error. Withheld "
                                    "below 60 observations, where the estimate cannot "
                                    "be distinguished from noise.")
                    col.metric(f"{label} Max DD",  stats.get("Max Drawdown","—"))

            fig = go.Figure()
            for label, eq, color in [("Long",result["long_eq"],"#00D566"),
                                       ("Short",result["short_eq"],"#FF4444"),
                                       ("Combined",result["combined_eq"],"#4A9EFF"),
                                       ("SPY",result["spy_eq"],"#6B7FBF")]:
                if not eq.empty:
                    rebased = eq / eq.iloc[0] * 100
                    fig.add_trace(go.Scatter(x=rebased.index, y=rebased.values,
                                              name=label, line=dict(color=color, width=1.5)))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#8892AA", family="Inter", size=11),
                xaxis=dict(showgrid=False, color="#4A5568"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", color="#4A5568", title="Rebased to 100"),
                legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0),
                margin=dict(t=20, b=40, l=50, r=20), height=300,
            )
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

            if result["contributions"]:
                import pandas as pd
                contrib_df = pd.DataFrame([{"Ticker":k,"Contribution (%)":round(v*100,1)}
                                            for k,v in result["contributions"].items()])
                st.markdown("**Top contributing tickers**")
                st.dataframe(contrib_df, use_container_width=True, hide_index=True)

        st.caption(
            "Walk-forward: at each rebalance the most recent score dated **at or "
            "before** that date is used, never a later one. Costs of "
            f"{DEFAULT_COST_BPS:.0f}bps round-trip on turnover plus "
            f"{DEFAULT_BORROW_BPS_ANNUAL:.0f}bps annualised borrow on the short leg "
            "are deducted. Short P&L is shown positive when the short was correct. "
            "Results still carry survivorship bias — the universe is today's tracked "
            "tickers, so names delisted during the period are absent."
        )
    else:
        st.info("Configure parameters above and click **Run Backtest** to begin.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — STRESS TESTER  (delegates to 36_Stress_Tester.py logic via st.switch_page hint)
# ─────────────────────────────────────────────────────────────────────────────
if _portfolio_section == "Stress Tester":
    import pandas as pd

    st.markdown("#### Macro Scenario Stress Tester")
    st.caption("Build a portfolio and test it against macro regime scenarios — credit shock, inflation surge, growth collapse, and more.")

    @st.cache_data(ttl=3600, show_spinner=False, max_entries=4)
    def _stress_signals():
        from utils.signals_cache import get_all_signal_scores
        return get_all_signal_scores()

    SCENARIOS = {
        "Credit Shock":       {"hy_spread": "bearish", "yield_curve": "bearish", "vix": "bearish"},
        "Inflation Surge":    {"tips_breakeven": "bearish", "ten_year_yield": "bearish", "consumer_sentiment": "bearish"},
        "Growth Collapse":    {"ism_pmi": "bearish", "jobless_claims": "bearish", "retail_sales": "bearish"},
        "Energy Spike":       {"crude_oil": "bearish", "crude_inventories": "bearish", "ata_trucking": "bearish"},
        "Risk-On Rally":      {"hy_spread": "bullish", "yield_curve": "bullish", "vix": "bullish"},
        "AI Buildout":        {"hyperscaler_capex": "bullish", "semiconductor_etf": "bullish", "copper": "bullish"},
    }

    SECTOR_EXPOSURE = {
        "Technology":     {"Credit Shock": -0.30, "Inflation Surge": -0.15, "Growth Collapse": -0.25, "Energy Spike": -0.05, "Risk-On Rally": +0.35, "AI Buildout": +0.45},
        "Energy":         {"Credit Shock": -0.10, "Inflation Surge": +0.25, "Growth Collapse": -0.15, "Energy Spike": +0.40, "Risk-On Rally": +0.10, "AI Buildout": +0.05},
        "Financials":     {"Credit Shock": -0.45, "Inflation Surge": -0.05, "Growth Collapse": -0.30, "Energy Spike": -0.10, "Risk-On Rally": +0.30, "AI Buildout": +0.05},
        "Healthcare":     {"Credit Shock": -0.05, "Inflation Surge": -0.10, "Growth Collapse": -0.05, "Energy Spike": -0.05, "Risk-On Rally": +0.10, "AI Buildout": +0.05},
        "Industrials":    {"Credit Shock": -0.20, "Inflation Surge": -0.10, "Growth Collapse": -0.35, "Energy Spike": -0.20, "Risk-On Rally": +0.25, "AI Buildout": +0.20},
        "Consumer":       {"Credit Shock": -0.20, "Inflation Surge": -0.25, "Growth Collapse": -0.30, "Energy Spike": -0.20, "Risk-On Rally": +0.20, "AI Buildout": +0.10},
        "Utilities":      {"Credit Shock": +0.05, "Inflation Surge": -0.15, "Growth Collapse": +0.10, "Energy Spike": -0.05, "Risk-On Rally": -0.10, "AI Buildout": +0.15},
        "Real Estate":    {"Credit Shock": -0.30, "Inflation Surge": -0.20, "Growth Collapse": -0.25, "Energy Spike": -0.10, "Risk-On Rally": +0.15, "AI Buildout": -0.05},
    }

    st.markdown("**Build your portfolio**")
    from utils.config import TICKERS
    all_tickers = list(TICKERS.keys())

    if "stress_holdings" not in st.session_state:
        st.session_state.stress_holdings = [dict(row) for row in _workspace_holdings]

    holdings = st.session_state.stress_holdings
    add_c1, add_c2, add_c3 = st.columns([2,1,1])
    new_t = add_c1.selectbox("Add ticker", [""] + all_tickers, key="stress_add_t")
    new_w = add_c2.number_input("Weight %", 1, 100, 10, key="stress_add_w")
    if add_c3.button("Add", key="stress_add_btn") and new_t:
        holdings.append({"ticker": new_t, "weight": new_w})
        _persisted = replace_default_holdings(_portfolio_user["id"], holdings)
        st.session_state.stress_holdings = [
            {"ticker": row["ticker"], "weight": row["weight_pct"]} for row in _persisted
        ]
        st.rerun()

    if holdings:
        h_df = pd.DataFrame(holdings)
        st.dataframe(h_df, use_container_width=True, hide_index=True)
        total_w = sum(h["weight"] for h in holdings)

        st.markdown("**Run scenario**")
        scenario = st.selectbox("Scenario", list(SCENARIOS.keys()), key="stress_scenario")

        if st.button("Run Stress Test", key="stress_run"):
            from utils.config import TICKERS as TICKER_META
            results = []
            for h in holdings:
                t  = h["ticker"]
                w  = h["weight"] / max(total_w, 1)
                meta = TICKER_META.get(t, {})
                sector = meta.get("sector", "Technology")
                impact = SECTOR_EXPOSURE.get(sector, {}).get(scenario, 0.0)
                portfolio_impact = impact * w
                results.append({
                    "Ticker": t, "Sector": sector,
                    "Weight": f"{w*100:.0f}%",
                    "Scenario Impact": f"{impact*100:+.0f}%",
                    "Portfolio P&L": f"{portfolio_impact*100:+.1f}%",
                })

            res_df = pd.DataFrame(results)
            total_pnl = sum(float(r["Portfolio P&L"].replace("%","")) for r in results)
            color = "#00D566" if total_pnl > 0 else "#FF4444"
            st.markdown(
                f'<div style="background:rgba(255,255,255,0.03);border:1px solid {color}44;'
                f'border-radius:8px;padding:12px 16px;text-align:center;margin-bottom:12px;">'
                f'<div style="font-size:0.70rem;color:#8892AA;">{scenario} — estimated portfolio impact</div>'
                f'<div style="font-size:2rem;font-weight:800;color:{color};">{total_pnl:+.1f}%</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.dataframe(res_df, use_container_width=True, hide_index=True)
            st.caption("Impacts are estimated from historical sector sensitivities to macro regime shifts. Not a price prediction.")
    else:
        st.info("Add some holdings above to run a stress test.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — SIGNAL BACKTESTER
# ─────────────────────────────────────────────────────────────────────────────
if _portfolio_section == "Signal Backtester":
    import pandas as pd
    import plotly.graph_objects as go
    from datetime import datetime, timedelta

    st.markdown("#### Custom Signal Combination Backtester")
    st.caption("Select signals and a ticker, set your thresholds, and see how this combination would have predicted price direction historically.")

    from utils.config import SIGNALS
    sig_opts = {cfg["name"]: sid for sid, cfg in SIGNALS.items()}

    sb1, sb2 = st.columns(2)
    chosen_sig_names = sb1.multiselect("Signals to combine", list(sig_opts.keys()), default=list(sig_opts.keys())[:3], key="sb_sigs")
    from utils.config import TICKERS as TICKER_CFG
    sb_ticker = sb2.selectbox("Ticker to test against", list(TICKER_CFG.keys()), index=0, key="sb_ticker")

    sb3, sb4 = st.columns(2)
    bull_t_sb = sb3.slider("Combined bull threshold", 50, 85, 65, key="sb_bull")
    lookback_sb = sb4.slider("Lookback (months)", 6, 36, 18, key="sb_lookback")

    if st.button("Run Signal Backtest", key="sb_run") and chosen_sig_names:
        chosen_sids = [sig_opts[n] for n in chosen_sig_names if n in sig_opts]
        with st.spinner("Fetching signals and prices…"):
            try:
                from utils.signals_cache import get_all_signal_scores
                from utils.fetchers import fetch_price
                import yfinance as yf
                import numpy as np

                all_sv = get_all_signal_scores()
                end = datetime.now().strftime("%Y-%m-%d")
                start = (datetime.now() - timedelta(days=30*lookback_sb)).strftime("%Y-%m-%d")

                sig_series = {}
                for sid in chosen_sids:
                    sv = all_sv.get(sid, {})
                    s = sv.get("data")
                    if s is not None and not s.empty:
                        sig_series[sid] = s

                if not sig_series:
                    st.warning("No signal data available for the selected signals.")
                else:
                    price = fetch_price(sb_ticker, start, end)
                    if price.empty:
                        st.warning(f"No price data for {sb_ticker}.")
                    else:
                        common_idx = price.index
                        for s in sig_series.values():
                            common_idx = common_idx.intersection(s.index)

                        if len(common_idx) < 30:
                            st.warning("Not enough overlapping data points (need ≥30).")
                        else:
                            from utils.analysis import score_signal
                            # Build weekly score series
                            weekly_dates = pd.date_range(start, end, freq="W")
                            combined_scores = []
                            for d in weekly_dates:
                                scores_at_d = []
                                for sid, s in sig_series.items():
                                    near = s.loc[:d].dropna()
                                    if not near.empty:
                                        recent = near.iloc[-12:] if len(near) >= 12 else near
                                        from utils.config import SIGNALS as SIG_CFG
                                        inv = SIG_CFG.get(sid,{}).get("inverse", False)
                                        sc = score_signal(recent, inverse=inv).get("score", 50)
                                        scores_at_d.append(sc)
                                combined_scores.append({"date": d, "score": np.mean(scores_at_d) if scores_at_d else 50})

                            score_ts = pd.DataFrame(combined_scores).set_index("date")["score"]
                            price_reindexed = price.reindex(score_ts.index, method="nearest")
                            fwd_ret = price_reindexed.pct_change(4).shift(-4) * 100

                            hits = ((score_ts >= bull_t_sb) & (fwd_ret > 0)).sum()
                            total_bull = (score_ts >= bull_t_sb).sum()
                            acc = hits / max(total_bull, 1) * 100

                            m1, m2, m3 = st.columns(3)
                            m1.metric("Bull Signals Fired", int(total_bull))
                            m2.metric("Correct (price +4w later)", int(hits))
                            m3.metric("Accuracy", f"{acc:.0f}%")

                            fig = go.Figure()
                            fig.add_trace(go.Scatter(x=score_ts.index, y=score_ts.values,
                                                      name="Combined Score", line=dict(color="#4A9EFF", width=1.5)))
                            fig.add_hline(y=bull_t_sb, line_dash="dash", line_color="#00D566",
                                          annotation_text="Bull threshold")
                            fig.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                font=dict(color="#8892AA", family="Inter", size=11),
                                xaxis=dict(showgrid=False, color="#4A5568"),
                                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                                           color="#4A5568", range=[0,100]),
                                margin=dict(t=20, b=40, l=50, r=20), height=250,
                            )
                            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
                            st.caption("Accuracy = % of times the combined score ≥ threshold was followed by positive price return 4 weeks later.")
            except Exception as e:
                st.error(f"Error running backtest: {e}")
    else:
        if not chosen_sig_names:
            st.info("Select at least one signal above.")
        else:
            st.info("Click **Run Signal Backtest** to see results.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — MACRO EXPOSURE ANALYZER
# ─────────────────────────────────────────────────────────────────────────────
if _portfolio_section == "Macro Exposure":
    import pandas as pd

    st.markdown("#### Portfolio Macro Exposure")
    st.caption("See which macro signals your portfolio is most exposed to, based on each holding's sector and the current signal regime.")

    from utils.config import TICKERS as TICKER_META2

    if "macro_holdings" not in st.session_state:
        st.session_state.macro_holdings = [dict(row) for row in _workspace_holdings]

    # ── Paste / import holdings ────────────────────────────────────────────────
    # Import a real portfolio in one shot instead of adding tickers one by one.
    # Accepts "TICKER, weight" or "TICKER weight" per line (weight optional →
    # equal-weighted). Only known tickers are kept; capped at MAX_PORTFOLIO_HOLDINGS
    # so a huge paste can't drive an unbounded exposure scan on the 2GB box.
    with st.expander(" Paste / import holdings (bulk)"):
        from utils.guards import MAX_PORTFOLIO_HOLDINGS
        _paste = st.text_area(
            "One holding per line — `TICKER, weight%` (weight optional)",
            placeholder="NVDA, 30\nXOM, 20\nAAPL\nMSFT, 15",
            key="ma_paste", height=120,
        )
        if st.button("Import holdings", key="ma_import_btn"):
            import re as _re
            _parsed, _unknown = [], []
            for _line in (_paste or "").splitlines():
                _line = _line.strip()
                if not _line:
                    continue
                _parts = _re.split(r"[,\s]+", _line)
                _sym = _parts[0].upper().lstrip("$")
                try:
                    _wt = float(_parts[1].rstrip("%")) if len(_parts) > 1 else 0.0
                except ValueError:
                    _wt = 0.0
                if _sym in TICKER_META2:
                    _parsed.append({"ticker": _sym, "weight": _wt})
                else:
                    _unknown.append(_sym)
            if _parsed:
                # de-dupe (keep last), equal-weight any zero-weight rows
                _seen = {}
                for _h in _parsed:
                    _seen[_h["ticker"]] = _h
                _hold = list(_seen.values())[:MAX_PORTFOLIO_HOLDINGS]
                if all(h["weight"] <= 0 for h in _hold):
                    _eq = round(100.0 / max(len(_hold), 1), 2)
                    for _h in _hold:
                        _h["weight"] = _eq
                st.session_state.macro_holdings = _hold
                replace_default_holdings(_portfolio_user["id"], _hold)
                st.session_state["ps_macro_analyzed"] = False  # require an explicit re-analyze
                _msg = f"Imported {len(_hold)} holding(s)."
                if len(_seen) > MAX_PORTFOLIO_HOLDINGS:
                    _msg += f" Capped at {MAX_PORTFOLIO_HOLDINGS}."
                if _unknown:
                    _msg += f" Skipped unknown: {', '.join(_unknown[:8])}" + ("…" if len(_unknown) > 8 else "")
                st.success(_msg)
                st.rerun()
            else:
                st.warning("No known tickers found. Use symbols in our tracked universe, "
                           "one per line.")

    ma_c1, ma_c2, ma_c3 = st.columns([2,1,1])
    # Search the full US-listed universe (~12.6k) rather than only our scored
    # tickers, and use index=None + placeholder (an empty-string sentinel makes
    # Streamlit render the label as the box's VALUE, breaking type-to-search).
    try:
        from utils.symbols import get_symbol_index as _gsi
        _ma_idx = dict(_gsi())
        for _t in TICKER_META2:
            if _t in _ma_idx:
                _ma_idx[_t] = f"✦ {_ma_idx[_t]}"
    except Exception:
        _ma_idx = {t: t for t in TICKER_META2}
    ma_new_t = ma_c1.selectbox(
        "Add ticker", list(_ma_idx.keys()), index=None,
        placeholder="Search any stock…",
        format_func=lambda t: _ma_idx.get(t, t), key="ma_add_t",
    ) or ""
    ma_new_w = ma_c2.number_input("Weight %", 1, 100, 10, key="ma_add_w")
    if ma_c3.button("Add", key="ma_add_btn") and ma_new_t:
        from utils.guards import MAX_PORTFOLIO_HOLDINGS
        if len(st.session_state.macro_holdings) >= MAX_PORTFOLIO_HOLDINGS:
            st.warning(f"Holdings capped at {MAX_PORTFOLIO_HOLDINGS} — remove one to add another. "
                       "(Keeps the exposure scan fast and within memory.)")
        else:
            st.session_state.macro_holdings.append({"ticker": ma_new_t, "weight": ma_new_w})
            _persisted = replace_default_holdings(
                _portfolio_user["id"], st.session_state.macro_holdings
            )
            st.session_state.macro_holdings = [
                {"ticker": row["ticker"], "weight": row["weight_pct"]} for row in _persisted
            ]
            st.rerun()

    holdings2 = st.session_state.macro_holdings

    # Heavy analysis (per-holding full Confluence score + macro exposure) is gated
    # behind an explicit action. Because st.tabs renders EVERY tab's code on every
    # page load, running this automatically meant compute_full_ticker_score() fired
    # for each holding on every visit to the Portfolio Suite — even when the user
    # was on another tab — which froze/spiked the single-core box. Opt-in fixes it.
    if st.button("Analyze portfolio exposure", key="ps_macro_run_btn", type="primary"):
        st.session_state["ps_macro_analyzed"] = True
    _macro_ready = bool(holdings2) and st.session_state.get("ps_macro_analyzed")
    if holdings2 and not _macro_ready:
        st.info("Set your holdings above, then click **Analyze portfolio exposure** "
                "to build the Macro X-Ray and exposure map.")

    # ── Portfolio Macro X-Ray (Point 2) ───────────────────────────────────────
    # The flagship portfolio view: aggregate each holding's real per-ticker
    # Confluence read (correlation-weighted, significant signals only) into a
    # portfolio-level exposure map — macro score, factor concentration,
    # tailwinds/risks, most vulnerable/supported holding, and HIDDEN correlations
    # between holdings that look diversified but share the same macro bet.
    # Engine + tests: utils/portfolio_xray.py. Additive (the simpler signal
    # table below stays) and fully defensive. Framed as context, never advice.
    if _macro_ready:
        try:
            from utils.portfolio_xray import build_portfolio_xray, render_portfolio_xray_html
            from utils.ticker_score import compute_full_ticker_score as _pf_score
            from utils.config import TICKERS as _PX_TICKERS

            @st.cache_data(ttl=3600, show_spinner=False, max_entries=128)
            def _px_holding_read(_ticker: str):
                r = _pf_score(_ticker)
                return {
                    "ticker": _ticker,
                    "score": r["confluence"]["overall_score"],
                    "corr_info": {k: {"weight": v.get("weight"), "significant": v.get("significant")}
                                  for k, v in r["corr_info"].items()},
                    "signal_scores": {k: {"score": v.get("score"), "status": v.get("status")}
                                      for k, v in r["signal_scores"].items()},
                    "sector": (_PX_TICKERS.get(_ticker, {}) or {}).get("sector", ""),
                }

            _px_inputs = []
            with st.spinner("Building your Portfolio Macro X-Ray…"):
                for _h in holdings2:
                    try:
                        _px_row = _px_holding_read(_h["ticker"])
                        _px_row["weight"] = float(_h.get("weight", 0) or 0)
                        _px_inputs.append(_px_row)
                    except Exception:
                        continue
            if _px_inputs:
                st.html(render_portfolio_xray_html(build_portfolio_xray(_px_inputs)))
                st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        except Exception:
            pass

    if _macro_ready:
        from utils.ticker_score import SECTOR_SIGNAL_MAP
        from utils.signals_cache import get_all_signal_scores
        from utils.config import SIGNALS

        with st.spinner("Analyzing macro exposure…"):
            all_sv2 = get_all_signal_scores()

        total_w2 = sum(h["weight"] for h in holdings2)
        exposure: dict[str, float] = {}

        for h in holdings2:
            t = h["ticker"]
            w = h["weight"] / max(total_w2, 1)
            meta = TICKER_META2.get(t, {})
            sector = meta.get("sector", "Technology")
            sigs = SECTOR_SIGNAL_MAP.get(sector, [])
            for sid in sigs:
                sv = all_sv2.get(sid, {})
                if sv and not sv.get("error"):
                    sc = float(sv.get("score", 50))
                    name = sv.get("name", sid)
                    bull_contribution = (sc - 50) / 50 * w
                    exposure[name] = exposure.get(name, 0) + bull_contribution

        if exposure:
            exp_sorted = sorted(exposure.items(), key=lambda x: -abs(x[1]))[:12]
            exp_df = pd.DataFrame([
                {"Signal": k, "Net Exposure": round(v * 100, 1),
                 "Direction": " Bullish" if v > 0.01 else " Bearish" if v < -0.01 else " Neutral"}
                for k, v in exp_sorted
            ])
            st.dataframe(exp_df, use_container_width=True, hide_index=True,
                         column_config={"Net Exposure": st.column_config.ProgressColumn(
                             "Net Exposure", min_value=-30, max_value=30, format="%.1f%%")})
            st.caption("Net Exposure = how much each macro signal moves your portfolio's expected return, weighted by holding size.")
        else:
            st.info("No signal exposure computed. Check that your tickers map to known sectors.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — BASKET BUILDER
# ─────────────────────────────────────────────────────────────────────────────
if _portfolio_section == "Basket Builder":
    import pandas as pd
    import plotly.graph_objects as go

    st.markdown("#### Thematic Basket Builder")
    st.caption("Build a signal-driven thematic basket and see how it scores on macro alignment.")

    from utils.config import TICKERS as TICKER_META3
    from utils.top_tickers import get_top_tickers

    THEMES = {
        "AI Infrastructure":    [t for t,m in TICKER_META3.items() if m.get("theme") in ("AI Infrastructure","ai_infrastructure") or m.get("sector") == "Technology"][:10],
        "Energy Transition":    [t for t,m in TICKER_META3.items() if m.get("sector") in ("Energy","Utilities")][:10],
        "Nuclear Power":        [t for t,m in TICKER_META3.items() if "nuclear" in m.get("theme","").lower() or m.get("sector")=="Utilities"][:8],
        "Financials":           [t for t,m in TICKER_META3.items() if m.get("sector")=="Financial Services"][:8],
        "Defense & Contracts":  [t for t,m in TICKER_META3.items() if "defense" in m.get("theme","").lower() or "aerospace" in m.get("theme","").lower()][:8],
    }

    bb1, bb2 = st.columns(2)
    theme = bb1.selectbox("Theme", list(THEMES.keys()) + ["Custom"], key="bb_theme")
    if theme == "Custom":
        basket_tickers = bb2.multiselect("Pick tickers", list(TICKER_META3.keys()), key="bb_custom")
    else:
        basket_tickers = THEMES.get(theme, [])
        bb2.multiselect("Tickers in basket", basket_tickers, default=basket_tickers, key="bb_view", disabled=True)

    from utils.guards import cap_list, MAX_BASKET_TICKERS
    basket_tickers, _bk_trunc = cap_list(basket_tickers, MAX_BASKET_TICKERS)
    if _bk_trunc:
        st.caption(f"Showing the first {MAX_BASKET_TICKERS} tickers (basket cap).")

    if basket_tickers:
        with st.spinner("Scoring basket…"):
            try:
                top = get_top_tickers()
                score_lookup = {
                    **{r["ticker"]: r["score"] for r in top.get("bullish",[])},
                    **{r["ticker"]: r["score"] for r in top.get("bearish",[])},
                }
            except Exception:
                score_lookup = {}

        rows = []
        for t in basket_tickers:
            meta = TICKER_META3.get(t, {})
            sc = score_lookup.get(t, 50)
            rows.append({
                "Ticker": t, "Name": meta.get("name", t)[:28],
                "Sector": meta.get("sector","—"), "Score": round(sc, 0),
                "Signal": "" if sc >= 65 else "" if sc <= 35 else "",
            })

        basket_df = pd.DataFrame(rows)
        avg_score  = basket_df["Score"].mean()
        bull_count = (basket_df["Score"] >= 65).sum()
        bear_count = (basket_df["Score"] <= 35).sum()

        bm1, bm2, bm3 = st.columns(3)
        bm1.metric("Basket Avg Score", f"{avg_score:.0f}")
        bm2.metric(" Bullish tickers", bull_count)
        bm3.metric(" Bearish tickers", bear_count)

        st.dataframe(
            basket_df,
            use_container_width=True, hide_index=True,
            column_config={"Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f")},
        )

        fig_bk = go.Figure(go.Bar(
            x=basket_df["Ticker"], y=basket_df["Score"],
            marker=dict(
                color=["#00D566" if s>=65 else "#FF4444" if s<=35 else "#6B7FBF" for s in basket_df["Score"]],
                line=dict(width=0),
            ),
        ))
        fig_bk.add_hline(y=65, line_dash="dash", line_color="#00D566", line_width=1)
        fig_bk.add_hline(y=35, line_dash="dash", line_color="#FF4444", line_width=1)
        fig_bk.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8892AA", family="Inter", size=11),
            xaxis=dict(showgrid=False, color="#4A5568"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", color="#4A5568",
                       range=[0,100], title="Score"),
            margin=dict(t=10, b=40, l=50, r=20), height=220,
        )
        st.plotly_chart(fig_bk, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
    else:
        st.info("Select a theme or pick custom tickers above.")
