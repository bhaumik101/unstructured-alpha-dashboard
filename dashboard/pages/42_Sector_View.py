# pages/42_Sector_View.py
# Unstructured Alpha — Sector View
# Combines Sector Rotation Map, Market Heatmap, and Supply Chain into one page.

import streamlit as st

st.set_page_config(page_title="Sector View — UA", layout="wide")

from utils.header import render_header, render_sidebar_base, render_page_header, disclose_unavailable_signals
from utils.theme import inject_premium_css, source_badge, PLOTLY_CONFIG, empty_state

render_header("Sector View")
render_sidebar_base()
inject_premium_css()

render_page_header(
    "Sector View",
    "Signal-driven sector strength, equity heatmap, and supply chain network — all in one place.",
    icon="",
)

# Data-integrity disclosure: this page presents/acts on macro-signal scores. If
# any underlying signal is synthetic (no FRED/EIA key or a failed live fetch),
# that must be visible here, not only on the Signal Dashboard. Same cached call
# the page's own logic uses, so no extra network cost.
from utils.signals_cache import get_all_signal_scores as _gas_disc
disclose_unavailable_signals(_gas_disc())


tab_sector, tab_heatmap, tab_supply = st.tabs([
    " Sector Rotation",
    " Market Heatmap",
    " Supply Chain",
])

# ─────────────────────────────────────────────────────────────────────────────
# Shared sector metadata (mirrors 12_Sector_Map.py)
# ─────────────────────────────────────────────────────────────────────────────
SECTOR_META = {
    "ai_infrastructure": {"name": "Technology & AI",   "icon": "", "color": "#7C3AED", "etf": "XLK / SMH"},
    "energy":            {"name": "Energy",            "icon": "", "color": "#5D4037", "etf": "XLE / OIH"},
    "nuclear":           {"name": "Nuclear / Utilities","icon": "", "color": "#FF4444", "etf": "XLU / URA"},
    "financials":        {"name": "Financials",        "icon": "", "color": "#F59E0B", "etf": "XLF / KRE"},
    "healthcare":        {"name": "Healthcare",        "icon": "", "color": "#00D566", "etf": "XLV / IBB"},
    "consumer":          {"name": "Consumer",          "icon": "", "color": "#B34700", "etf": "XLY / XLP"},
    "industrials":       {"name": "Industrials",       "icon": "", "color": "#4A1B6B", "etf": "XLI / IYT"},
    "macro":             {"name": "Macro Backdrop",    "icon": "", "color": "#00C8E0", "etf": "SPY / TLT"},
}

STATUS_COLOR = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#6B7FBF"}

@st.cache_data(ttl=7200, show_spinner=False, max_entries=2)
def _sector_scores(_v: int = 1) -> dict:
    from utils.signals_cache import get_all_signal_scores
    from utils.config import SIGNALS
    all_sv = get_all_signal_scores(_v)
    result = {}
    for cat, meta in SECTOR_META.items():
        sigs = [sid for sid, cfg in SIGNALS.items() if cfg.get("category") == cat and not all_sv.get(sid, {}).get("error")]
        if not sigs:
            continue
        scores  = [float(all_sv[s].get("score", 50)) for s in sigs if s in all_sv]
        bulls   = [s for s in sigs if all_sv.get(s, {}).get("status") == "bullish"]
        bears   = [s for s in sigs if all_sv.get(s, {}).get("status") == "bearish"]
        avg     = sum(scores) / len(scores) if scores else 50.0
        status  = "bullish" if avg >= 60 else "bearish" if avg <= 40 else "neutral"
        top_sig = sorted(sigs, key=lambda s: -float(all_sv.get(s, {}).get("score", 50)))[:3]
        result[cat] = {
            **meta, "score": round(avg, 1), "status": status,
            "bull": len(bulls), "bear": len(bears), "n": len(sigs),
            "top_signals": [all_sv[s].get("name", s) for s in top_sig if s in all_sv],
        }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — SECTOR ROTATION MAP
# ─────────────────────────────────────────────────────────────────────────────
with tab_sector:
    import plotly.graph_objects as go

    with st.spinner("Scoring sectors…"):
        sectors = _sector_scores()

    if not sectors:
        st.warning("Signal data unavailable.")
    else:
        sorted_sectors = sorted(sectors.items(), key=lambda x: -x[1]["score"])

        st.caption(
            "Signal-based sector posture — not stock price momentum. "
            "Score = average of all signals in that sector's category. "
            " ≥ 60 bullish ·  ≤ 40 bearish ·  mixed."
        )

        cols = st.columns(4)
        for i, (cat, info) in enumerate(sorted_sectors):
            with cols[i % 4]:
                sc = info["score"]
                color = STATUS_COLOR[info["status"]]
                st.markdown(
                    f'<div style="background:rgba(255,255,255,0.025);border:1px solid {color}33;'
                    f'border-left:4px solid {color};border-radius:10px;'
                    f'padding:14px 16px;margin-bottom:12px;">'
                    f'<div style="font-size:1.1rem;">{info["icon"]} '
                    f'<b style="font-size:0.85rem;color:#E8EEFF;">{info["name"]}</b></div>'
                    f'<div style="font-size:1.6rem;font-weight:800;color:{color};margin:4px 0;">{sc:.0f}</div>'
                    f'<div style="font-size:0.60rem;color:#6B7FBF;">ETF: {info["etf"]}</div>'
                    f'<div style="font-size:0.60rem;color:#8892AA;margin-top:4px;">'
                    f'▲ {info["bull"]} bull · ▼ {info["bear"]} bear · {info["n"]} signals</div>'
                    f'<div style="font-size:0.60rem;color:#4A5568;margin-top:3px;">'
                    f'{" · ".join(info["top_signals"][:2])}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        names  = [v["name"]  for _, v in sorted_sectors]
        scores = [v["score"] for _, v in sorted_sectors]
        colors = [STATUS_COLOR[v["status"]] for _, v in sorted_sectors]
        fig = go.Figure(go.Bar(
            x=names, y=scores, marker=dict(color=colors, line=dict(width=0)),
            hovertemplate="%{x}<br>Score: %{y:.0f}<extra></extra>",
        ))
        fig.add_hline(y=60, line_dash="dash", line_color="#00D566", line_width=1)
        fig.add_hline(y=40, line_dash="dash", line_color="#FF4444", line_width=1)
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8892AA", family="Inter", size=11),
            xaxis=dict(showgrid=False, color="#4A5568"),
            yaxis=dict(range=[0,100], showgrid=True, gridcolor="rgba(255,255,255,0.06)", color="#4A5568"),
            margin=dict(t=10, b=60, l=50, r=20), height=260,
        )
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
        source_badge("FRED · EIA · SEC EDGAR")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — MARKET HEATMAP
# ─────────────────────────────────────────────────────────────────────────────
with tab_heatmap:
    import plotly.graph_objects as go
    from utils.config import TICKERS
    from utils.top_tickers import get_top_tickers

    with st.spinner("Building heatmap…"):
        try:
            top = get_top_tickers()
            all_tickers_scores = {
                **{r["ticker"]: r["score"] for r in top.get("bullish", [])},
                **{r["ticker"]: r["score"] for r in top.get("bearish", [])},
                **{r["ticker"]: r["score"] for r in top.get("neutral", []) if "score" in r},
            }
        except Exception:
            all_tickers_scores = {}

    if not all_tickers_scores:
        st.markdown(
            empty_state(
                title="Sector scores are still warming up",
                body="Scores are computed from the latest signal snapshot. This view fills "
                     "in once today's scores have been written — usually within the hour after refresh.",
                action="Browse the Signal Dashboard for the live signal reads →",
            ),
            unsafe_allow_html=True,
        )
    else:
        by_sector: dict[str, list] = {}
        for t, score in all_tickers_scores.items():
            meta = TICKERS.get(t, {})
            sector = meta.get("sector", "Other")
            by_sector.setdefault(sector, []).append({"ticker": t, "score": score, "name": meta.get("name", t)})

        labels, parents, values, colors_list, text_list = [], [], [], [], []
        for sector, tlist in sorted(by_sector.items()):
            labels.append(sector); parents.append(""); values.append(1); colors_list.append(50); text_list.append(sector)
            for r in tlist:
                labels.append(r["ticker"]); parents.append(sector)
                values.append(1); colors_list.append(r["score"]); text_list.append(f'{r["ticker"]}<br>{r["score"]:.0f}')

        fig2 = go.Figure(go.Treemap(
            labels=labels, parents=parents, values=values,
            customdata=colors_list, text=text_list,
            textinfo="text",
            marker=dict(
                colors=colors_list,
                colorscale=[[0,"#FF4444"],[0.35,"#2D3555"],[0.5,"#1E2340"],[0.65,"#1B3B2F"],[1,"#00D566"]],
                cmin=0, cmax=100,
                colorbar=dict(title="Score", tickfont=dict(color="#8892AA"), len=0.6),
            ),
            hovertemplate="<b>%{label}</b><br>Score: %{customdata:.0f}<extra></extra>",
        ))
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#E8EEFF", family="Inter", size=11),
            margin=dict(t=10, b=10, l=0, r=0), height=480,
        )
        st.plotly_chart(fig2, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
        st.caption("Color = Confluence Score. Green ≥65 bullish · Red ≤35 bearish. Scores via macro signal cache (fast, no price fetch).")
        source_badge("FRED · EIA · UA Signals Cache")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — SUPPLY CHAIN
# ─────────────────────────────────────────────────────────────────────────────
with tab_supply:
    import plotly.graph_objects as go

    st.markdown("### Supply Chain Signal Network")
    st.caption(
        "Which macro signals are most interconnected with supply-chain sensitive tickers? "
        "Use this to spot upstream disruptions before they hit earnings."
    )

    SUPPLY_NODES = [
        {"id": "FRED:AINTRATX", "label": "Rail Traffic",      "type": "signal",  "color": "#4A9EFF"},
        {"id": "FRED:DAUPSA",   "label": "Auto Sales",        "type": "signal",  "color": "#4A9EFF"},
        {"id": "EIA:crude",     "label": "Crude Inventories", "type": "signal",  "color": "#FFB347"},
        {"id": "FRED:ISM",      "label": "ISM PMI",           "type": "signal",  "color": "#4A9EFF"},
        {"id": "UPS",           "label": "UPS",               "type": "ticker",  "color": "#00D566"},
        {"id": "FDX",           "label": "FedEx",             "type": "ticker",  "color": "#00D566"},
        {"id": "CAT",           "label": "Caterpillar",       "type": "ticker",  "color": "#00D566"},
        {"id": "DE",            "label": "Deere",             "type": "ticker",  "color": "#00D566"},
        {"id": "XOM",           "label": "Exxon",             "type": "ticker",  "color": "#FFB347"},
        {"id": "CVX",           "label": "Chevron",           "type": "ticker",  "color": "#FFB347"},
    ]
    SUPPLY_EDGES = [
        ("FRED:AINTRATX","UPS"),("FRED:AINTRATX","FDX"),("FRED:AINTRATX","CAT"),
        ("FRED:DAUPSA","CAT"),("FRED:DAUPSA","DE"),
        ("EIA:crude","XOM"),("EIA:crude","CVX"),("EIA:crude","UPS"),
        ("FRED:ISM","CAT"),("FRED:ISM","DE"),("FRED:ISM","UPS"),
    ]

    import math
    n = len(SUPPLY_NODES)
    for i, node in enumerate(SUPPLY_NODES):
        angle = 2 * math.pi * i / n
        node["x"] = math.cos(angle)
        node["y"] = math.sin(angle)

    node_map = {nd["id"]: nd for nd in SUPPLY_NODES}
    ex = []; ey = []
    for a, b in SUPPLY_EDGES:
        if a in node_map and b in node_map:
            ex += [node_map[a]["x"], node_map[b]["x"], None]
            ey += [node_map[a]["y"], node_map[b]["y"], None]

    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=ex, y=ey, mode="lines",
        line=dict(color="rgba(255,255,255,0.10)", width=1), hoverinfo="skip",
    ))
    for nd in SUPPLY_NODES:
        fig3.add_trace(go.Scatter(
            x=[nd["x"]], y=[nd["y"]], mode="markers+text",
            marker=dict(size=18 if nd["type"]=="ticker" else 14, color=nd["color"], line=dict(width=0)),
            text=[nd["label"]], textposition="top center",
            textfont=dict(color="#E8EEFF", size=10),
            name=nd["label"], hovertemplate=f'{nd["label"]}<extra></extra>',
        ))

    fig3.update_layout(
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        margin=dict(t=20, b=20, l=20, r=20), height=420,
    )
    st.plotly_chart(fig3, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

    st.markdown("#### Supply Chain Signal Scores")
    with st.spinner("Loading supply chain signals…"):
        from utils.signals_cache import get_all_signal_scores
        all_sv = get_all_signal_scores()
        SUPPLY_SIGS = ["ata_trucking", "rail_traffic", "ism_pmi", "durable_goods",
                       "crude_oil", "crude_inventories", "shipping_index", "construction_spending"]
        rows = []
        for sid in SUPPLY_SIGS:
            sv = all_sv.get(sid, {})
            if sv and not sv.get("error"):
                rows.append({
                    "Signal": sv.get("name", sid),
                    "Score":  round(float(sv.get("score", 50)), 1),
                    "Status": (" Bullish" if sv.get("status")=="bullish"
                               else " Bearish" if sv.get("status")=="bearish"
                               else " Neutral"),
                })
        if rows:
            import pandas as pd
            sc_df = pd.DataFrame(rows).sort_values("Score", ascending=False)
            st.dataframe(sc_df, use_container_width=True, hide_index=True,
                         column_config={"Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f")})
        source_badge("FRED · EIA")
