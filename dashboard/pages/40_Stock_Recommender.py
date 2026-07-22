# pages/40_Stock_Recommender.py
# Unstructured Alpha — Signal-Driven Stock Recommender
#
# Two-phase scoring:
#   Phase 1 (fast, all 193 tickers): macro signal confluence via signals_cache.
#     Ranks the full universe so we know which tickers to enrich.
#   Phase 2 (full, top 20 per side): compute_full_ticker_score() in parallel
#     via ThreadPoolExecutor — adds per-ticker price correlation weights,
#     momentum, insider activity, FINRA short interest, and 13F positioning.
#     This is the EXACT same score shown on Ticker Deep Dive.
#
# Track Record section: pulls historical score_snapshots rows where the
# model was high-conviction (≥70 or ≤30), then computes realized 30-day
# forward returns to show whether those calls paid off.
#
# Pro-gated.

import streamlit as st

st.set_page_config(
    page_title="Stock Recommender — UA",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.header import render_header, render_sidebar_base, render_page_header, render_footer, disclose_unavailable_signals
from utils.theme import inject_premium_css, source_badge, PLOTLY_CONFIG
from utils.config import SIGNALS, TICKERS
from utils.billing import require_pro
from utils.conviction import get_signal_alignment

render_header("Stock Recommender")
_recommender_section = render_sidebar_base(
    page_title="Stock Recommender",
    sections=("Top Ideas", "Track Record", "Ranked Universe", "Score Distribution"),
    section_key="stock_recommender_section_rail",
)
try:
    from utils.instrumentation import record_once
    record_once("recommender_viewed")
except Exception:
    pass
inject_premium_css()

require_pro(page_name="Stock Recommender")
_recommender_user = st.session_state.get("user")

render_page_header(
    "Stock Recommender",
    f"Highest-conviction long and short ideas — macro signals ranked across {len(TICKERS)} tickers, "
    "with the top picks fully enriched with insider activity, 13F positioning, and short interest.",
    icon="",
)

# Data-integrity disclosure: this page RANKS tickers by macro-signal confluence.
# If any underlying signal is synthetic (no FRED/EIA key, or a failed fetch), the
# ranking is built on placeholder data and must say so — a recommender that sorts
# stocks on fabricated inputs while looking authoritative is the worst version of
# quiet wrongness. get_all_signal_scores() is the same cached call the scorer uses,
# so this adds no network cost.
if _recommender_section != "Track Record":
    from utils.signals_cache import get_all_signal_scores as _gas_disc
    disclose_unavailable_signals(_gas_disc())

# ─────────────────────────────────────────────────────────────────────────────
if _recommender_section != "Track Record":
    # Configuration
    # ─────────────────────────────────────────────────────────────────────────────

    from utils.recommender_screens import delete_screen, list_saved_screens, save_screen

    _sector_options = sorted(set(m.get("sector", "Other") for m in TICKERS.values()))
    _saved_screens = (
        list_saved_screens(_recommender_user["id"], allowed_sectors=_sector_options)
        if _recommender_user else []
    )
    _screen_by_id = {screen["id"]: screen for screen in _saved_screens}

    # Saved presets restore only cheap filter state. Deep enrichment remains an
    # explicit action so opening a preset can never start a burst of provider
    # calls or surprise the single-core production service.
    if _recommender_user:
        with st.container(border=True):
            _saved_c1, _saved_c2, _saved_c3 = st.columns([4, 1, 1])
            with _saved_c1:
                _selected_screen_id = st.selectbox(
                    "Saved Pro screens",
                    options=list(_screen_by_id),
                    index=None,
                    format_func=lambda screen_id: _screen_by_id[screen_id]["name"],
                    placeholder="Choose a saved strategy…",
                    key="rec_saved_screen_selector",
                    help="Restore a complete Recommender filter setup without rerunning deep scoring.",
                )
            _apply_screen = _saved_c2.button(
                "Apply", use_container_width=True, disabled=_selected_screen_id is None,
                key="rec_apply_saved_screen",
            )
            _delete_screen = _saved_c3.button(
                "Delete", use_container_width=True, disabled=_selected_screen_id is None,
                key="rec_delete_saved_screen",
            )
            if _apply_screen and _selected_screen_id is not None:
                _selected = _screen_by_id[_selected_screen_id]
                _screen_cfg = _selected["config"]
                st.session_state["rec_time_horizon"] = _screen_cfg["time_horizon"]
                st.session_state["rec_n_show"] = _screen_cfg["n_show"]
                st.session_state["rec_n_enrich"] = _screen_cfg["n_enrich"]
                st.session_state["rec_min_signals"] = _screen_cfg["min_signals"]
                st.session_state["rec_sector_filter"] = _screen_cfg["sectors"]
                st.session_state["rec_active_screen_name"] = _selected["name"]
                st.session_state["rec_screen_name_input"] = _selected["name"]
                st.session_state["rec_screen_notice"] = f'Applied “{_selected["name"]}”.'
                st.rerun()
            if _delete_screen and _selected_screen_id is not None:
                _selected = _screen_by_id[_selected_screen_id]
                if delete_screen(_recommender_user["id"], _selected_screen_id):
                    if st.session_state.get("rec_active_screen_name") == _selected["name"]:
                        st.session_state.pop("rec_active_screen_name", None)
                        st.session_state.pop("rec_screen_name_input", None)
                    st.session_state.pop("rec_saved_screen_selector", None)
                    st.session_state["rec_screen_notice"] = f'Deleted “{_selected["name"]}”.'
                    st.rerun()
            if st.session_state.get("rec_active_screen_name"):
                st.caption(
                    f'Active screen: **{st.session_state["rec_active_screen_name"]}** · '
                    "Deep-score enrichment still runs only when you request it."
                )
        if st.session_state.get("rec_screen_notice"):
            st.success(st.session_state.pop("rec_screen_notice"))

    st.session_state.setdefault("rec_time_horizon", "All")
    st.session_state.setdefault("rec_n_show", 8)
    st.session_state.setdefault("rec_n_enrich", 10)
    st.session_state.setdefault("rec_min_signals", 2)
    st.session_state.setdefault("rec_sector_filter", [])
    st.session_state["rec_sector_filter"] = [
        sector for sector in st.session_state["rec_sector_filter"] if sector in _sector_options
    ]

    cfg_c1, cfg_c2, cfg_c3 = st.columns([2, 2, 3])
    with cfg_c1:
        time_horizon = st.radio(
            "Time horizon",
            ["Short-term (1–2 wks)", "Medium-term (1–2 mo)", "Long-term (3+ mo)", "All"],
            help="Filters by signal lag_weeks — how far ahead each signal historically leads price.",
            key="rec_time_horizon",
        )
    with cfg_c2:
        n_show       = st.slider("Picks to show per side", 3, 15, key="rec_n_show")
        n_enrich     = st.slider("Full-score enrichment depth", 5, 20,
                                  help="Top N per side enriched with insider/13F/short interest (slower).",
                                  key="rec_n_enrich")
        min_signals  = st.slider("Min signals required", 1, 8, key="rec_min_signals")
    with cfg_c3:
        sector_filter = st.multiselect(
            "Filter by sector",
            _sector_options,
            placeholder="All sectors",
            key="rec_sector_filter",
        )

    if _recommender_user:
        with st.expander("Save this setup as a Pro screen", expanded=False):
            _save_c1, _save_c2 = st.columns([4, 1])
            _screen_name = _save_c1.text_input(
                "Screen name",
                value=st.session_state.get("rec_active_screen_name", ""),
                placeholder="e.g. Long-term energy leaders",
                key="rec_screen_name_input",
                max_chars=64,
            )
            _save_current_screen = _save_c2.button(
                "Save", type="primary", use_container_width=True, key="rec_save_current_screen"
            )
            st.caption(
                f"Save up to 10 private filter presets. Results are recomputed from current real data; "
                "cached charts and provider responses are never stored in a preset."
            )
            if _save_current_screen:
                try:
                    _saved = save_screen(
                        _recommender_user["id"],
                        _screen_name,
                        {
                            "time_horizon": time_horizon,
                            "n_show": n_show,
                            "n_enrich": n_enrich,
                            "min_signals": min_signals,
                            "sectors": sector_filter,
                        },
                        allowed_sectors=_sector_options,
                    )
                    st.session_state["rec_active_screen_name"] = _saved["name"]
                    st.session_state["rec_screen_notice"] = f'Saved “{_saved["name"]}”.'
                    try:
                        from utils.instrumentation import record
                        record("recommender_screen_saved", sector_count=len(sector_filter))
                    except Exception:
                        pass
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

    _horizon_weeks = {
        "Short-term (1–2 wks)":  (0, 3),
        "Medium-term (1–2 mo)":  (3, 9),
        "Long-term (3+ mo)":     (9, 999),
        "All":                   (0, 999),
    }
    _min_lag, _max_lag = _horizon_weeks[time_horizon]

    st.markdown("---")

    # ─────────────────────────────────────────────────────────────────────────────
# Phase 1: macro-only ranking — all tickers
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False, max_entries=4)
def _macro_rank_all(min_lag: int, max_lag: int) -> list[dict]:
    """
    Score all 193 tickers using cached macro signal scores only.
    Fast (~1s). Returns list sorted by score desc.
    """
    from utils.signals_cache import get_all_signal_scores
    from utils.analysis import compute_confluence

    all_scores = get_all_signal_scores()

    rows = []
    for ticker, meta in TICKERS.items():
        sig_ids = meta.get("signals", [])
        if min_lag > 0 or max_lag < 999:
            sig_ids = [
                s for s in sig_ids
                if min_lag <= SIGNALS.get(s, {}).get("lag_weeks", 4) <= max_lag
            ]
        ticker_scores = {
            sid: all_scores[sid]
            for sid in sig_ids
            if sid in all_scores and not all_scores[sid].get("error")
        }
        if len(ticker_scores) < 1:
            continue

        weights = {
            sid: SIGNALS[sid].get("pcs", 5) / 10.0
            for sid in ticker_scores if sid in SIGNALS
        }
        conf = compute_confluence(ticker_scores, weights=weights)

        bull_sigs = [
            {"id": sid, "name": SIGNALS.get(sid, {}).get("name", sid),
             "lag": SIGNALS.get(sid, {}).get("lag_weeks", "?"),
             "score": ticker_scores[sid].get("score", 50)}
            for sid in ticker_scores if ticker_scores[sid].get("status") == "bullish"
        ]
        bear_sigs = [
            {"id": sid, "name": SIGNALS.get(sid, {}).get("name", sid),
             "lag": SIGNALS.get(sid, {}).get("lag_weeks", "?"),
             "score": ticker_scores[sid].get("score", 50)}
            for sid in ticker_scores if ticker_scores[sid].get("status") == "bearish"
        ]

        _aligned, _total = get_signal_alignment(ticker, conf["overall_score"], all_scores)
        rows.append({
            "ticker":        ticker,
            "name":          meta.get("name", ticker),
            "sector":        meta.get("sector", "Other"),
            "score":         round(conf["overall_score"], 1),
            "case":          conf["case"],
            "conviction":    conf["conviction"],
            "bull_count":    conf["bull_count"],
            "bear_count":    conf["bear_count"],
            "n_signals":     len(ticker_scores),
            "bull_signals":  sorted(bull_sigs, key=lambda x: -x["score"]),
            "bear_signals":  sorted(bear_sigs, key=lambda x: x["score"]),
            "enriched":      False,
            "has_insider":   False,
            "has_13f":       False,
            "has_short_int": False,
            "has_contracts": False,
            "momentum_score": 50.0,
            "aligned":       _aligned,
            "total_relevant": _total,
        })

    rows.sort(key=lambda r: -r["score"])
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: full enrichment — top N per side
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False, max_entries=8)
def _enrich_tickers(tickers_tuple: tuple[str, ...]) -> dict[str, dict]:
    """
    Run compute_full_ticker_score() in parallel on the given tickers.
    Returns {ticker: result_dict} for successfully scored tickers.
    """
    from utils.ticker_score import compute_full_ticker_score, price_window
    from utils.fetchers import fetch_prices_batch

    # Batch-fetch every candidate's price history in ONE yfinance request,
    # then hand each ticker its own series — instead of N separate downloads
    # inside N parallel compute_full_ticker_score() calls. Output is identical.
    _pstart, _pend = price_window()
    _prices = fetch_prices_batch(tickers_tuple, _pstart, _pend)

    results: dict[str, dict] = {}
    # Worker count: prices are already batch-fetched above, so each worker is
    # CPU-bound scoring on in-memory data — BUT each in-flight full ticker score
    # holds a 3yr price frame + factor intermediates, so N workers ≈ N such frames
    # resident at once. On Starter (512MB) 3 was the OOM-safe ceiling; on Standard
    # (2GB) there's ample RAM for a handful, so default 5 (pandas/numpy release the
    # GIL, so >1 helps overlap even on 1 CPU). Raise via RECOMMENDER_WORKERS on a
    # multi-core plan. Bounded [1,16] so a bad env value can't oversubscribe.
    import os as _os
    _rec_workers = max(1, min(16, int(_os.getenv("RECOMMENDER_WORKERS", "5"))))
    with ThreadPoolExecutor(max_workers=_rec_workers) as pool:
        futures = {
            pool.submit(compute_full_ticker_score, t, None, _prices.get(t)): t
            for t in tickers_tuple
        }
        for fut in as_completed(futures, timeout=180):
            t = futures[fut]
            try:
                results[t] = fut.result()
            except Exception:
                pass  # leave unenriched

    # Release the batch price dict + intermediate frames back to the OS before
    # the page renders — keeps the enrich scan from leaving a high-water mark.
    from utils.memory import release_memory
    del _prices
    release_memory()
    return results


def _merge_enriched(macro_rows: list[dict], enriched: dict[str, dict]) -> list[dict]:
    """
    Replace macro-only rows with the full score for enriched tickers.
    Re-sorts by final score.
    """
    merged = []
    for row in macro_rows:
        t = row["ticker"]
        if t in enriched and enriched[t] is not None:
            r = enriched[t]
            conf = r["confluence"]
            final_score = conf["overall_score"]

            # Rebuild signal driver lists from full signal_scores dict
            sig_scores = r.get("signal_scores", {})
            bull_sigs = [
                {"id": sid, "name": SIGNALS.get(sid, {}).get("name", sid),
                 "lag": SIGNALS.get(sid, {}).get("lag_weeks", "?"),
                 "score": sv.get("score", 50)}
                for sid, sv in sig_scores.items() if sv.get("status") == "bullish"
            ]
            bear_sigs = [
                {"id": sid, "name": SIGNALS.get(sid, {}).get("name", sid),
                 "lag": SIGNALS.get(sid, {}).get("lag_weeks", "?"),
                 "score": sv.get("score", 50)}
                for sid, sv in sig_scores.items() if sv.get("status") == "bearish"
            ]

            merged.append({
                **row,
                "score":         round(final_score, 1),
                "case":          conf.get("case", row["case"]),
                "conviction":    conf.get("conviction", row["conviction"]),
                "bull_count":    conf.get("bull_count", row["bull_count"]),
                "bear_count":    conf.get("bear_count", row["bear_count"]),
                "bull_signals":  sorted(bull_sigs, key=lambda x: -x["score"])[:6],
                "bear_signals":  sorted(bear_sigs, key=lambda x: x["score"])[:6],
                "enriched":      True,
                "has_insider":   r.get("has_insider_signal", False),
                "has_13f":       r.get("has_13f_signal", False),
                "has_short_int": r.get("has_short_interest_signal", False),
                "has_contracts": r.get("has_contract_signal", False),
                "momentum_score": r.get("momentum_score", 50.0),
                "insider_score": r.get("insider_score", {}),
                "thirteenf_score": r.get("thirteenf_score", {}),
                "short_interest_score": r.get("short_interest_score", {}),
            })
        else:
            merged.append(row)
    merged.sort(key=lambda r: -r["score"])
    return merged


if _recommender_section != "Track Record":
    # ─── Phase 1: fast macro ranking — runs automatically (~1s, cached) ───────────
    # This is cheap (cached macro scores only), so the page shows ranked ideas almost
    # immediately.
    with st.status("Ranking the market…", expanded=False) as _scan_status:
        _scan_status.update(label="Ranking all tickers by macro signals…")
        all_rows = _macro_rank_all(_min_lag, _max_lag)

        # Apply filters
        if sector_filter:
            all_rows = [r for r in all_rows if r["sector"] in sector_filter]
        all_rows = [r for r in all_rows if r["n_signals"] >= min_signals]
        _scan_status.update(label="Macro ranking complete", state="complete", expanded=False)

    # ─── Phase 2: full enrichment — OPT-IN (heavy) ────────────────────────────────
    # compute_full_ticker_score() per candidate pulls 3yr price history + insider/13F/
    # short-interest data. Running it automatically on EVERY cold page load blocked the
    # render and spiked memory — on the single-core / 2GB box that froze the page and
    # could restart the service (which cleared the cache and repeated the cycle). So the
    # heavy pass is now gated behind an explicit action; results are cached in session
    # so they survive reruns. The page stays responsive and shows the macro ranking
    # regardless.
    macro_longs  = [r for r in all_rows if r["score"] >= 60][:n_enrich]
    macro_shorts = [r for r in sorted(all_rows, key=lambda r: r["score"])[:n_enrich]
                    if r["score"] <= 40]
    enrich_set = tuple(sorted(set(
        [r["ticker"] for r in macro_longs] + [r["ticker"] for r in macro_shorts]
    )))

    # Invalidate stale session enrichment when the candidate set changes (filters moved).
    if st.session_state.get("_rec_enrich_key") != enrich_set:
        st.session_state["_rec_enriched"] = None
    enriched_data = st.session_state.get("_rec_enriched")

    if enrich_set and _recommender_section == "Top Ideas":
        _ec1, _ec2 = st.columns([1, 3])
        _do_enrich = _ec1.button(
            f" Deep-score top {len(enrich_set)}",
            type="primary", use_container_width=True,
            help="Adds insider activity, 13F positioning, and short interest to the top "
                 "candidates. Heavier — runs on demand so the page stays fast.",
        )
        if _do_enrich:
            with st.status(f"Deep-scoring {len(enrich_set)} candidates "
                           "(insider, 13F, short interest)…", expanded=False) as _es:
                enriched_data = _enrich_tickers(enrich_set)
                st.session_state["_rec_enriched"]   = enriched_data
                st.session_state["_rec_enrich_key"] = enrich_set
                _es.update(label="Deep-score complete", state="complete", expanded=False)
        if enriched_data:
            all_rows = _merge_enriched(all_rows, enriched_data)
        else:
            _ec2.caption("Showing the fast macro-only ranking. Deep-score adds insider, "
                         "13F, and short-interest data to the top candidates.")

    longs  = [r for r in all_rows if r["score"] >= 65][:n_show]
    shorts = sorted(all_rows, key=lambda r: r["score"])[:n_show]
    shorts = [r for r in shorts if r["score"] <= 35]

    # ─────────────────────────────────────────────────────────────────────────────
if _recommender_section == "Top Ideas":
    # Overview metrics
    # ─────────────────────────────────────────────────────────────────────────────

    n_bull   = len([r for r in all_rows if r["score"] >= 65])
    n_bear   = len([r for r in all_rows if r["score"] <= 35])
    n_neut   = len(all_rows) - n_bull - n_bear
    n_enr    = len([r for r in all_rows if r.get("enriched")])

    ov1, ov2, ov3, ov4, ov5 = st.columns(5)
    ov1.metric("Tickers Scored", len(all_rows))
    ov2.metric(" Bullish", n_bull)
    ov3.metric(" Bearish", n_bear)
    ov4.metric(" Neutral", n_neut)
    ov5.metric(" Full-Score Enriched", n_enr,
               help="Top candidates scored with insider, 13F, and short interest data.")

    st.markdown("---")

    # ─────────────────────────────────────────────────────────────────────────────
    # Recommendation cards
    # ─────────────────────────────────────────────────────────────────────────────

    def _signal_tags(signals: list[dict], color: str) -> str:
        tags = ""
        for s in signals[:5]:
            lag = s.get("lag", "?")
            lag_str = f"{lag}w" if isinstance(lag, (int, float)) else ""
            tags += (
                f'<span style="display:inline-block;background:rgba(255,255,255,0.05);'
                f'border:1px solid rgba(255,255,255,0.10);border-radius:12px;'
                f'padding:2px 8px;font-size:0.58rem;color:{color};margin:2px 3px 2px 0;">'
                f'{s["name"]}{f" · {lag_str}" if lag_str else ""}'
                f'</span>'
            )
        return tags


    def _optional_badges(row: dict, side: str) -> str:
        if not row.get("enriched"):
            return '<span style="font-size:0.58rem;color:#4A5568;">macro signals only</span>'
        badges = []
        if row.get("has_insider"):
            sc = row.get("insider_score", {})
            status = sc.get("status", "neutral")
            c = "#00D566" if status == "bullish" else "#FF4444" if status == "bearish" else "#6B7FBF"
            badges.append(f'<span style="font-size:0.58rem;color:{c};background:rgba(255,255,255,0.04);'
                          f'border:1px solid {c}44;border-radius:10px;padding:2px 7px;">Insiders</span>')
        if row.get("has_13f"):
            sc = row.get("thirteenf_score", {})
            status = sc.get("status", "neutral")
            c = "#00D566" if status == "bullish" else "#FF4444" if status == "bearish" else "#6B7FBF"
            badges.append(f'<span style="font-size:0.58rem;color:{c};background:rgba(255,255,255,0.04);'
                          f'border:1px solid {c}44;border-radius:10px;padding:2px 7px;"> 13F</span>')
        if row.get("has_short_int"):
            sc = row.get("short_interest_score", {})
            status = sc.get("status", "neutral")
            c = "#00D566" if status == "bullish" else "#FF4444" if status == "bearish" else "#6B7FBF"
            badges.append(f'<span style="font-size:0.58rem;color:{c};background:rgba(255,255,255,0.04);'
                          f'border:1px solid {c}44;border-radius:10px;padding:2px 7px;"> Short Int.</span>')
        if row.get("has_contracts"):
            badges.append('<span style="font-size:0.58rem;color:#4A9EFF;background:rgba(255,255,255,0.04);'
                          'border:1px solid #4A9EFF44;border-radius:10px;padding:2px 7px;"> Gov Contracts</span>')
        if row.get("momentum_score", 50) >= 65:
            badges.append('<span style="font-size:0.58rem;color:#FFB347;background:rgba(255,255,255,0.04);'
                          'border:1px solid #FFB34744;border-radius:10px;padding:2px 7px;"> Momentum</span>')
        return " ".join(badges) if badges else '<span style="font-size:0.58rem;color:#4A5568;">no optional signals</span>'


    def _score_bar(score: float, color: str) -> str:
        return (
            f'<div style="background:rgba(255,255,255,0.06);border-radius:4px;height:5px;margin:6px 0 2px;">'
            f'<div style="width:{int(score)}%;background:{color};border-radius:4px;height:5px;'
            f'box-shadow:0 0 8px {color}55;"></div></div>'
        )


    def _alignment_badge(row: dict, color: str) -> str:
        """Small 'X/Y aligned' conviction badge for rec cards."""
        aligned = row.get("aligned", 0)
        total   = row.get("total_relevant", 0)
        if total == 0:
            return ""
        pct = aligned / total
        opacity = "1.0" if pct >= 0.65 else "0.7"
        return (
            f'<span style="font-size:0.58rem;color:{color};opacity:{opacity};">'
            f'⬡ {aligned}/{total} signals aligned</span>'
        )


    def _why_line(row: dict, side: str) -> str:
        """One-line plain-English 'why this pick' — synthesises the drivers already on
        the row (top signals, alignment, and any enrichment) into a readable sentence.
        Reuses existing data; no extra compute."""
        sigs = row["bull_signals"] if side == "long" else row["bear_signals"]
        dir_word = "bullish" if side == "long" else "bearish"
        top = [s.get("name", "") for s in sigs[:3] if s.get("name")]
        if not top:
            return "Ranked on overall macro-regime alignment (no single dominant signal)."
        n = len(sigs)
        lead = f"Scores {row['score']:.0f}, led by {n} {dir_word} macro signal{'s' if n != 1 else ''}"
        names = ", ".join(top) + ("…" if n > 3 else "")
        aligned, total = row.get("aligned", 0), row.get("total_relevant", 0)
        align = f" · {aligned}/{total} relevant signals aligned" if total else ""
        enrich = ""
        if row.get("enriched"):
            extras = []
            if row.get("has_insider"):   extras.append("insider activity")
            if row.get("has_13f"):       extras.append("13F positioning")
            if row.get("has_short_int"): extras.append("short interest")
            if row.get("momentum_score", 50) >= 65: extras.append("price momentum")
            if extras:
                enrich = " Confirmed by " + ", ".join(extras) + "."
        return f"{lead} ({names}){align}.{enrich}"


    def _why_block(row: dict, side: str) -> str:
        accent = "#00D566" if side == "long" else "#FF4444"
        return (
            f'<div style="margin-top:10px;padding:8px 10px;border-radius:8px;'
            f'background:rgba(255,255,255,0.03);border-left:2px solid {accent}66;">'
            f'<span style="font-size:0.56rem;color:{accent};text-transform:uppercase;'
            f'letter-spacing:0.08em;font-weight:700;"> Why this pick</span>'
            f'<div style="font-size:0.68rem;color:#B8C2D9;margin-top:3px;line-height:1.4;">'
            f'{_why_line(row, side)}</div></div>'
        )


    def _rec_card(row: dict, side: str) -> str:
        if side == "long":
            border = "#00D566"; glow = "#00D56618"; badge = "BUY"
            sig_html = _signal_tags(row["bull_signals"], "#00D566")
            driver_label = f"Bullish drivers ({row['bull_count']})"
        else:
            border = "#FF4444"; glow = "#FF444418"; badge = "SELL / SHORT"
            sig_html = _signal_tags(row["bear_signals"], "#FF4444")
            driver_label = f"Bearish drivers ({row['bear_count']})"

        enriched_star = (
            '<span style="font-size:0.55rem;color:#4A9EFF;margin-left:6px;'
            'background:rgba(74,158,255,0.12);padding:1px 6px;border-radius:8px;"> Full Score</span>'
            if row.get("enriched") else
            '<span style="font-size:0.55rem;color:#4A5568;margin-left:6px;">macro only</span>'
        )

        opt_badges = _optional_badges(row, side)
        conv = (row["conviction"] or "—").capitalize()

        return f"""
    <div style="background:rgba(255,255,255,0.025);border:1px solid {border}33;
                border-left:4px solid {border};border-radius:10px;
                padding:16px 18px;margin-bottom:12px;
                box-shadow:inset 0 0 30px {glow};">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:6px;">
        <div>
          <span style="font-size:1.1rem;font-weight:900;color:#E8EEFF;">{row["ticker"]}</span>
          <span style="font-size:0.70rem;color:#8892AA;margin-left:8px;">{row["name"]}</span>
          <span style="font-size:0.60rem;color:#4A5568;margin-left:6px;">· {row["sector"]}</span>
          {enriched_star}
        </div>
        <div style="display:flex;align-items:center;gap:10px;flex-shrink:0;">
          <span style="font-size:0.60rem;font-weight:700;color:{border};
                       background:rgba(0,0,0,0.35);padding:3px 10px;
                       border-radius:12px;border:1px solid {border}55;">{badge}</span>
          <span style="font-size:1.1rem;font-weight:800;color:{border};">{row["score"]:.0f}</span>
        </div>
      </div>
      {_score_bar(row["score"], border)}
      {_why_block(row, side)}
      <div style="margin-top:8px;">
        <span style="font-size:0.58rem;color:#6B7FBF;text-transform:uppercase;letter-spacing:0.08em;">{driver_label}</span>
        <div style="margin-top:4px;">{sig_html or "<span style='font-size:0.62rem;color:#4A5568;'>Macro regime alignment</span>"}</div>
      </div>
      <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
        {opt_badges}
      </div>
      <div style="margin-top:6px;display:flex;gap:14px;flex-wrap:wrap;">
        <span style="font-size:0.58rem;color:#8892AA;">Conviction: <b style="color:{border};">{conv}</b></span>
        <span style="font-size:0.58rem;color:#8892AA;">{row["n_signals"]} signals scored</span>
        {_alignment_badge(row, border)}
      </div>
    </div>"""


    col_long, col_short = st.columns(2)

    with col_long:
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#00D566;'
            'text-transform:uppercase;letter-spacing:0.12em;margin-bottom:12px;">'
            ' Top Long Ideas</div>',
            unsafe_allow_html=True,
        )
        if longs:
            for r in longs:
                st.html(_rec_card(r, "long"))
        else:
            st.info("No high-conviction longs under this filter. Try 'All' horizons or reduce the min-signal requirement.")

    with col_short:
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#FF4444;'
            'text-transform:uppercase;letter-spacing:0.12em;margin-bottom:12px;">'
            ' Top Short / Avoid Ideas</div>',
            unsafe_allow_html=True,
        )
        if shorts:
            for r in shorts:
                st.html(_rec_card(r, "short"))
        else:
            st.info("No high-conviction shorts under this filter.")

    # ─────────────────────────────────────────────────────────────────────────────
if _recommender_section == "Track Record":
    # Track Record
    # ─────────────────────────────────────────────────────────────────────────────

    st.markdown("---")
    st.markdown("###  Track Record — Past High-Conviction Calls")
    st.caption(
        "Tickers the model scored ≥70 (bullish) or ≤30 (bearish) in the last 6 months, "
        "resolved to their realized 30-day forward return. "
        "**These are retrospective lookups, not advance predictions** — they answer 'how did the stock "
        "perform in the 30 days after the model gave it a high score?' Score history accumulates "
        "organically via Ticker Deep Dive views."
    )


    @st.cache_data(ttl=7200, show_spinner=False, max_entries=2)
    def _load_track_record() -> pd.DataFrame:
        """Pull high-conviction snapshot rows and resolve 30-day forward returns."""
        from utils.score_history import get_high_confidence_snapshot_calls
        import yfinance as yf

        calls = get_high_confidence_snapshot_calls(min_score=70, days_back=180, min_days_ago=35)
        if not calls:
            return pd.DataFrame()

        # Deduplicate: keep only the earliest high-conviction call per ticker
        seen: dict[str, dict] = {}
        for c in sorted(calls, key=lambda x: x["snapshot_date"]):
            if c["ticker"] not in seen:
                seen[c["ticker"]] = c
        calls = list(seen.values())

        # Batch price fetch
        tickers_needed = [c["ticker"] for c in calls]
        start_date = (
            datetime.now(timezone.utc) - timedelta(days=210)
        ).strftime("%Y-%m-%d")
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        try:
            prices = yf.download(
                tickers_needed, start=start_date, end=end_date,
                auto_adjust=True, progress=False
            )["Close"]
            if len(tickers_needed) == 1:
                prices = prices.to_frame(name=tickers_needed[0])
        except Exception:
            return pd.DataFrame()

        rows = []
        for c in calls:
            t   = c["ticker"]
            dt  = c["snapshot_date"]
            score_at_call = float(c.get("score", 50))
            case  = c.get("case", "BULL" if score_at_call >= 65 else "BEAR")

            try:
                ts = prices[t].dropna()
                start_px = ts.loc[ts.index >= dt].iloc[0] if len(ts.loc[ts.index >= dt]) else None
                end_ts   = ts.loc[ts.index >= dt].iloc[0:30]
                end_px   = end_ts.iloc[-1] if len(end_ts) >= 15 else None
                if start_px and end_px and start_px > 0:
                    fwd_ret = (end_px / start_px - 1) * 100
                    # For short ideas, flip sign: negative return = model was right
                    if case == "BEAR":
                        model_correct = fwd_ret < 0
                        model_ret = -fwd_ret  # gain for short
                    else:
                        model_correct = fwd_ret > 0
                        model_ret = fwd_ret
                    rows.append({
                        "Ticker":          t,
                        "Call Date":       dt,
                        "Score":           round(score_at_call, 0),
                        "Direction":       " LONG" if case == "BULL" else " SHORT",
                        "30d Return (%)":  round(fwd_ret, 1),
                        "Model P&L (%)":   round(model_ret, 1),
                        "Correct":         "" if model_correct else "",
                    })
            except Exception:
                pass

        return pd.DataFrame(rows) if rows else pd.DataFrame()


    with st.spinner("Loading track record…"):
        tr_df = _load_track_record()

    if tr_df.empty:
        st.info(
            "Not enough score history yet. Track record builds organically as users view tickers on "
            "Ticker Deep Dive — scores are snapshotted at view time. Check back as history accumulates."
        )
    else:
        # Summary stats
        n_calls  = len(tr_df)
        n_right  = (tr_df["Correct"] == "").sum()
        win_rate = round(n_right / n_calls * 100, 1) if n_calls else 0
        avg_ret  = round(tr_df["Model P&L (%)"].mean(), 1)

        tr1, tr2, tr3, tr4 = st.columns(4)
        tr1.metric("Past Calls", n_calls)
        tr2.metric("Win Rate", f"{win_rate}%")
        tr3.metric("Avg Model P&L", f"{avg_ret:+.1f}%")
        tr4.metric("Resolved via 30-day window", n_calls)

        # Bar chart: realized returns per call
        if len(tr_df) > 0:
            tr_sorted = tr_df.sort_values("30d Return (%)")
            colors = [
                "#00D566" if v >= 0 else "#FF4444"
                for v in tr_sorted["30d Return (%)"]
            ]
            fig = go.Figure(go.Bar(
                x=tr_sorted["Ticker"] + " (" + tr_sorted["Call Date"] + ")",
                y=tr_sorted["Model P&L (%)"],
                marker=dict(color=colors, line=dict(width=0)),
                hovertemplate=(
                    "<b>%{x}</b><br>Model P&L: %{y:.1f}%<extra></extra>"
                ),
            ))
            fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#8892AA", family="Inter"),
                xaxis=dict(showgrid=False, color="#4A5568",
                           tickangle=-45, tickfont=dict(size=9)),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                           color="#4A5568", title="Model P&L (%)"),
                margin=dict(t=20, b=80, l=50, r=20),
                height=280,
            )
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

        st.dataframe(
            tr_df[[c for c in ["Ticker", "Call Date", "Score", "Direction",
                                "30d Return (%)", "Model P&L (%)", "Correct"] if c in tr_df.columns]],
            use_container_width=True,
            hide_index=True,
        )

    # ─────────────────────────────────────────────────────────────────────────────
if _recommender_section == "Ranked Universe":
    # Full ranked table
    # ─────────────────────────────────────────────────────────────────────────────

    st.markdown("---")
    st.markdown("### Full Ranked Universe")
    st.caption("All scored tickers sorted by confluence score.  = enriched with full signal set.")

    if all_rows:
        table_df = pd.DataFrame([{
            "Ticker":     r["ticker"],
            "Name":       r["name"],
            "Score":      r["score"],
            "Case":       (" " if r["case"] == "BULL" else " " if r["case"] == "BEAR" else " ") + r["case"],
            "Conviction": (r["conviction"] or "—").capitalize(),
            "▲ Bull":     r["bull_count"],
            "▼ Bear":     r["bear_count"],
            "Sigs":       r["n_signals"],
            "Sector":     r["sector"],
            "Full Score": "" if r.get("enriched") else "—",
        } for r in all_rows])

        st.dataframe(
            table_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=100, format="%.0f"
                ),
            },
        )

    # ─────────────────────────────────────────────────────────────────────────────
if _recommender_section == "Score Distribution":
    # Score distribution histogram
    # ─────────────────────────────────────────────────────────────────────────────

    st.markdown("### Score Distribution")
    if all_rows:
        scores = [r["score"] for r in all_rows]
        colors = ["#00D566" if s >= 65 else "#FF4444" if s <= 35 else "#6B7FBF" for s in scores]
        fig2 = go.Figure(go.Histogram(
            x=scores, nbinsx=20,
            marker=dict(color=colors, line=dict(width=0)),
            hovertemplate="Score: %{x:.0f}<br>Count: %{y}<extra></extra>",
        ))
        fig2.add_vline(x=65, line_dash="dash", line_color="#00D566",
                       annotation_text="Bull threshold", annotation_position="top right",
                       annotation_font=dict(color="#00D566", size=10))
        fig2.add_vline(x=35, line_dash="dash", line_color="#FF4444",
                       annotation_text="Bear threshold", annotation_position="top left",
                       annotation_font=dict(color="#FF4444", size=10))
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8892AA", family="Inter"),
            xaxis=dict(showgrid=False, color="#4A5568", title="Confluence Score"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                       color="#4A5568", title="# Tickers"),
            margin=dict(t=20, b=40, l=50, r=20), height=250, bargap=0.08,
        )
        st.plotly_chart(fig2, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

render_footer()
