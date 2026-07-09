#!/usr/bin/env python3
# seo/main.py
# Unstructured Alpha — SEO Web Service
#
# A lightweight FastAPI server that renders server-side HTML for Google to
# crawl. Each ticker and signal gets a properly titled, described, JSON-LD-
# annotated page. Streamlit is an SPA and cannot serve crawlable pages;
# this service fills that gap.
#
# Deployed as a SEPARATE Render web service (see render.yaml).
# Uses the same DATABASE_URL and utils/ package as the main Streamlit app.
#
# Routes:
#   GET /                        → 200 health check (plain text)
#   GET /ticker/{symbol}         → ticker SEO page
#   GET /signals/report          → weekly signal report page
#   GET /signal/{signal_id}      → individual signal SEO page
#   GET /sitemap.xml             → dynamic XML sitemap
#   GET /robots.txt              → robots.txt
#
# Run locally (from dashboard/):
#   uvicorn seo.main:app --reload --port 8502

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── sys.path: ensure dashboard/ is importable ─────────────────────────────────
_here = Path(__file__).resolve().parent.parent   # dashboard/
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

# ── lazy imports from utils/ (deferred to avoid heavy Streamlit dep at startup)
def _get_config():
    from utils.config import TICKERS, SIGNALS
    return TICKERS, SIGNALS

def _get_engine():
    from utils.db import init_db, engine, score_snapshots, signal_snapshots
    init_db()
    return engine, score_snapshots, signal_snapshots

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_URL      = os.environ.get("SEO_BASE_URL", "https://seo.unstructuredalpha.com")
APP_URL       = os.environ.get("APP_URL", "https://unstructuredalpha.com")
SITE_NAME     = "Unstructured Alpha"
BRAND_COLOR   = "#7C3AED"
GREEN         = "#00875A"
RED           = "#C53030"
AMBER         = "#D97706"

app = FastAPI(title="Unstructured Alpha SEO", docs_url=None, redoc_url=None)


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _score_color(score: float) -> str:
    if score >= 60:
        return GREEN
    if score <= 40:
        return RED
    return AMBER


def _case_label(score: float) -> str:
    if score >= 65:
        return "Bullish"
    if score <= 35:
        return "Bearish"
    return "Neutral"


def _html_head(
    title: str,
    description: str,
    canonical: str,
    json_ld: str = "",
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="google-site-verification" content="yo8oBRWmMzqG-7dqyFvVGvlR2XzmeofREFA3__o4ZLQ">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <link rel="canonical" href="{canonical}">

  <!-- Open Graph -->
  <meta property="og:type"        content="website">
  <meta property="og:title"       content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:url"         content="{canonical}">
  <meta property="og:site_name"   content="{SITE_NAME}">

  <!-- Twitter Card -->
  <meta name="twitter:card"        content="summary">
  <meta name="twitter:title"       content="{title}">
  <meta name="twitter:description" content="{description}">

  {json_ld}

  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
      background: #0B0D12;
      color: #C8D0E4;
      line-height: 1.6;
    }}
    a {{ color: {BRAND_COLOR}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    .nav {{
      background: #12151E;
      border-bottom: 1px solid #1E2535;
      padding: 14px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .nav-brand {{
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: {BRAND_COLOR};
    }}
    .nav-cta {{
      background: {BRAND_COLOR};
      color: #fff;
      padding: 7px 18px;
      border-radius: 6px;
      font-size: 0.82rem;
      font-weight: 600;
    }}
    .nav-cta:hover {{ text-decoration: none; background: #6D28D9; }}

    .container {{
      max-width: 800px;
      margin: 0 auto;
      padding: 40px 24px 80px;
    }}

    .hero {{
      text-align: center;
      padding: 48px 0 32px;
    }}
    .hero-eyebrow {{
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: #6B7A95;
      margin-bottom: 12px;
    }}
    .hero-ticker {{
      font-size: 2.6rem;
      font-weight: 900;
      color: #E8EEFF;
      letter-spacing: -0.02em;
    }}
    .hero-name {{
      font-size: 1rem;
      color: #6B7A95;
      margin-top: 4px;
    }}

    .score-card {{
      background: #12151E;
      border: 1px solid #1E2535;
      border-radius: 16px;
      padding: 32px;
      text-align: center;
      margin: 32px 0;
    }}
    .score-label {{
      font-size: 0.60rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #6B7A95;
      margin-bottom: 8px;
    }}
    .score-value {{
      font-size: 5rem;
      font-weight: 900;
      line-height: 1;
      letter-spacing: -0.04em;
    }}
    .score-denom {{
      font-size: 1.2rem;
      color: #4A5280;
      font-weight: 600;
    }}
    .score-case {{
      font-size: 1rem;
      font-weight: 700;
      margin-top: 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .score-updated {{
      font-size: 0.68rem;
      color: #4A5280;
      margin-top: 10px;
    }}

    .signal-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin: 32px 0;
    }}
    .signal-stat {{
      background: #12151E;
      border: 1px solid #1E2535;
      border-radius: 10px;
      padding: 18px 14px;
      text-align: center;
    }}
    .signal-stat .val {{
      font-size: 1.8rem;
      font-weight: 800;
    }}
    .signal-stat .lbl {{
      font-size: 0.65rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #6B7A95;
      margin-top: 4px;
    }}

    .section-head {{
      font-size: 0.60rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #6B7A95;
      margin-bottom: 14px;
      margin-top: 36px;
    }}

    .signal-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
    }}
    .signal-table th {{
      text-align: left;
      font-size: 0.60rem;
      font-weight: 700;
      letter-spacing: 0.10em;
      text-transform: uppercase;
      color: #4A5280;
      padding: 6px 10px;
      border-bottom: 1px solid #1E2535;
    }}
    .signal-table td {{
      padding: 10px 10px;
      border-bottom: 1px solid #1A1E2A;
      color: #B8C0D4;
    }}
    .signal-table tr:last-child td {{ border-bottom: none; }}
    .badge {{
      display: inline-block;
      font-size: 0.65rem;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 999px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .badge-bull {{ background: #064E3B; color: #34D399; }}
    .badge-bear {{ background: #7F1D1D; color: #FCA5A5; }}
    .badge-neut {{ background: #1E2535; color: #6B7A95; }}

    .cta-block {{
      background: linear-gradient(135deg, #1A1340 0%, #0B0D12 100%);
      border: 1px solid {BRAND_COLOR}44;
      border-radius: 16px;
      padding: 36px 32px;
      text-align: center;
      margin-top: 48px;
    }}
    .cta-block h2 {{
      font-size: 1.3rem;
      font-weight: 800;
      color: #E8EEFF;
      margin-bottom: 10px;
    }}
    .cta-block p {{
      font-size: 0.88rem;
      color: #8892AA;
      margin-bottom: 24px;
      line-height: 1.7;
    }}
    .cta-btn {{
      display: inline-block;
      background: {BRAND_COLOR};
      color: #fff;
      padding: 14px 36px;
      border-radius: 8px;
      font-size: 0.92rem;
      font-weight: 700;
    }}
    .cta-btn:hover {{ text-decoration: none; background: #6D28D9; }}

    .disclaimer {{
      font-size: 0.68rem;
      color: #4A5280;
      text-align: center;
      margin-top: 48px;
      line-height: 1.7;
    }}

    @media (max-width: 600px) {{
      .signal-grid {{ grid-template-columns: 1fr 1fr; }}
      .hero-ticker {{ font-size: 1.8rem; }}
      .score-value  {{ font-size: 3.5rem; }}
    }}
  </style>
</head>
<body>
<nav class="nav">
  <span class="nav-brand">Unstructured Alpha</span>
  <a href="{APP_URL}" class="nav-cta">Open App →</a>
</nav>
"""


def _html_foot() -> str:
    return f"""
  <p class="disclaimer">
    Scores are derived from macro signals (FRED, EIA, SEC filings, FINRA short interest)
    and updated as new data arrives. This is not financial advice. Past signal accuracy
    does not guarantee future results.<br>
    <a href="{APP_URL}">unstructuredalpha.com</a> · Not financial advice
  </p>
</div></body></html>"""


# ── DB helpers ────────────────────────────────────────────────────────────────

def _latest_ticker_score(engine, score_snapshots, ticker: str) -> dict | None:
    """Return {score, case, snapshot_date} for the most recent snapshot."""
    from sqlalchemy import select
    try:
        with engine.begin() as conn:
            row = conn.execute(
                select(
                    score_snapshots.c.score,
                    score_snapshots.c.case,
                    score_snapshots.c.snapshot_date,
                )
                .where(score_snapshots.c.ticker == ticker.upper())
                .order_by(score_snapshots.c.snapshot_date.desc())
                .limit(1)
            ).mappings().fetchone()
        if row:
            return dict(row)
    except Exception:
        pass
    return None


def _latest_signal_statuses(engine, signal_snapshots) -> dict[str, str]:
    """Return {signal_id: status} for the most recent snapshot of each signal."""
    from sqlalchemy import select, text
    try:
        with engine.begin() as conn:
            # Get the latest row per signal_id using a subquery approach
            rows = conn.execute(
                text("""
                    SELECT DISTINCT ON (signal_id) signal_id, status
                    FROM signal_snapshots
                    ORDER BY signal_id, snapshot_date DESC
                """)
            ).fetchall()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def _signal_history_30d(engine, signal_snapshots, signal_id: str) -> list[dict]:
    """Return [{snapshot_date, score, status}] for the last 30 days."""
    from sqlalchemy import select
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(
                    signal_snapshots.c.snapshot_date,
                    signal_snapshots.c.score,
                    signal_snapshots.c.status,
                )
                .where(signal_snapshots.c.signal_id == signal_id)
                .where(signal_snapshots.c.snapshot_date >= cutoff)
                .order_by(signal_snapshots.c.snapshot_date.asc())
            ).mappings().fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=PlainTextResponse)
def health() -> str:
    return "OK"


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt() -> str:
    return f"""User-agent: *
Allow: /

Sitemap: {BASE_URL}/sitemap.xml
"""


@app.get("/sitemap.xml")
def sitemap_xml():
    TICKERS, SIGNALS = _get_config()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    urls = [
        f"  <url><loc>{BASE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>",
        f"  <url><loc>{BASE_URL}/signals/report</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>0.9</priority></url>",
    ]
    for symbol in sorted(TICKERS.keys()):
        urls.append(
            f"  <url><loc>{BASE_URL}/ticker/{symbol}</loc>"
            f"<lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq>"
            f"<priority>0.8</priority></url>"
        )
    for sig_id in sorted(SIGNALS.keys()):
        urls.append(
            f"  <url><loc>{BASE_URL}/signal/{sig_id}</loc>"
            f"<lastmod>{today}</lastmod>"
            f"<changefreq>daily</changefreq>"
            f"<priority>0.7</priority></url>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@app.get("/ticker/{symbol}", response_class=HTMLResponse)
def ticker_page(symbol: str):
    symbol = symbol.upper().strip()
    TICKERS, SIGNALS = _get_config()

    meta = TICKERS.get(symbol)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Ticker {symbol} not tracked.")

    name    = meta.get("name", symbol)
    sector  = meta.get("sector", "")
    rel_ids = set(meta.get("signals", list(SIGNALS.keys())))

    engine, score_snapshots, signal_snapshots = _get_engine()

    # Latest score from DB
    snap       = _latest_ticker_score(engine, score_snapshots, symbol)
    score      = float(snap["score"]) if snap else None
    snap_date  = snap["snapshot_date"] if snap else None

    # Signal statuses
    all_statuses = _latest_signal_statuses(engine, signal_snapshots)
    rel_statuses = {sid: all_statuses[sid] for sid in rel_ids if sid in all_statuses}

    bull = sum(1 for s in rel_statuses.values() if s == "bullish")
    bear = sum(1 for s in rel_statuses.values() if s == "bearish")
    neut = len(rel_statuses) - bull - bear

    # Score display
    if score is not None:
        case       = _case_label(score)
        score_col  = _score_color(score)
        score_disp = f"{score:.0f}"
    else:
        case       = "Unknown"
        score_col  = "#4A5280"
        score_disp = "—"

    # SEO metadata
    if score is not None:
        seo_desc = (
            f"{symbol} ({name}) currently scores {score_disp}/100 on the Unstructured Alpha "
            f"Confluence Score — a macro-driven signal that aggregates {len(rel_statuses)} "
            f"data sources including FRED, EIA, SEC insider filings, and FINRA short interest. "
            f"{bull} of {len(rel_statuses)} signals are currently bullish."
        )
    else:
        seo_desc = (
            f"Unstructured Alpha tracks {symbol} ({name}) across {len(rel_ids)} macro signals "
            f"including FRED economic data, EIA energy inventories, SEC insider filings, and FINRA "
            f"short interest. Sign up to see the live Confluence Score."
        )

    page_title = (
        f"{symbol} Confluence Score: {score_disp}/100 — {SITE_NAME}"
        if score is not None else
        f"{symbol} ({name}) Macro Signal Analysis — {SITE_NAME}"
    )

    canonical = f"{BASE_URL}/ticker/{symbol}"

    # JSON-LD
    json_ld = f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "{page_title}",
  "description": "{seo_desc}",
  "url": "{canonical}",
  "publisher": {{
    "@type": "Organization",
    "name": "{SITE_NAME}",
    "url": "{APP_URL}"
  }},
  "dateModified": "{snap_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
  "about": {{
    "@type": "FinancialProduct",
    "name": "{name}",
    "tickerSymbol": "{symbol}"
  }}
}}
</script>"""

    # Build relevant signal rows
    signal_rows = ""
    for sig_id in sorted(rel_ids):
        cfg    = SIGNALS.get(sig_id, {})
        status = rel_statuses.get(sig_id, "—")
        if status == "bullish":
            badge = '<span class="badge badge-bull">▲ Bullish</span>'
        elif status == "bearish":
            badge = '<span class="badge badge-bear">▼ Bearish</span>'
        elif status in ("neutral", "insufficient_data"):
            badge = '<span class="badge badge-neut">● Neutral</span>'
        else:
            badge = f'<span class="badge badge-neut">{status}</span>'

        signal_rows += f"""
        <tr>
          <td>{cfg.get("name", sig_id)}</td>
          <td style="color:#6B7A95;font-size:0.78rem;">{cfg.get("category","").title()}</td>
          <td>{badge}</td>
        </tr>"""

    updated_str = f"Updated {snap_date}" if snap_date else "No snapshot data yet"

    html = _html_head(page_title, seo_desc, canonical, json_ld)
    html += f"""
<div class="container">

  <div class="hero">
    <div class="hero-eyebrow">Confluence Score · {sector or "Equity"}</div>
    <div class="hero-ticker">{symbol}</div>
    <div class="hero-name">{name}</div>
  </div>

  <div class="score-card">
    <div class="score-label">Confluence Score</div>
    <div class="score-value" style="color:{score_col};">{score_disp}<span class="score-denom">/100</span></div>
    <div class="score-case" style="color:{score_col};">{case}</div>
    <div class="score-updated">{updated_str}</div>
  </div>

  <div class="signal-grid">
    <div class="signal-stat">
      <div class="val" style="color:{GREEN};">{bull}</div>
      <div class="lbl">Bullish Signals</div>
    </div>
    <div class="signal-stat">
      <div class="val" style="color:{RED};">{bear}</div>
      <div class="lbl">Bearish Signals</div>
    </div>
    <div class="signal-stat">
      <div class="val" style="color:{AMBER};">{neut}</div>
      <div class="lbl">Neutral Signals</div>
    </div>
  </div>

  <div class="section-head">Tracked Macro Signals for {symbol}</div>
  <table class="signal-table">
    <thead>
      <tr>
        <th>Signal</th>
        <th>Category</th>
        <th>Current Status</th>
      </tr>
    </thead>
    <tbody>
      {signal_rows}
    </tbody>
  </table>

  <div class="cta-block">
    <h2>See the Full Analysis for {symbol}</h2>
    <p>
      Unstructured Alpha tracks {len(rel_statuses)} data sources in real time — from EIA crude
      inventories to Congressional stock trades to SEC Form 4 insider filings. The Confluence Score
      combines them into a single 0–100 number updated as new data arrives.
    </p>
    <a class="cta-btn" href="{APP_URL}/Ticker_Deep_Dive?ticker={symbol}">
      Open {symbol} Deep Dive →
    </a>
  </div>
"""
    html += _html_foot()
    return html


@app.get("/signal/{signal_id}", response_class=HTMLResponse)
def signal_page(signal_id: str):
    TICKERS, SIGNALS = _get_config()

    cfg = SIGNALS.get(signal_id)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not tracked.")

    sig_name   = cfg.get("name", signal_id)
    category   = cfg.get("category", "macro").title()
    description= cfg.get("description", "")
    lag_weeks  = cfg.get("lag_weeks", 0)
    relevant_t = cfg.get("relevant_tickers", [])

    engine, _, signal_snapshots = _get_engine()

    history  = _signal_history_30d(engine, signal_snapshots, signal_id)
    cur_status = history[-1]["status"] if history else "unknown"
    cur_score  = float(history[-1]["score"]) if history else None
    snap_date  = history[-1]["snapshot_date"] if history else None

    if cur_status == "bullish":
        status_badge = '<span class="badge badge-bull">▲ Bullish</span>'
        status_word  = "bullish"
    elif cur_status == "bearish":
        status_badge = '<span class="badge badge-bear">▼ Bearish</span>'
        status_word  = "bearish"
    else:
        status_badge = '<span class="badge badge-neut">● Neutral</span>'
        status_word  = "neutral"

    page_title = f"{sig_name} — Macro Signal Analysis — {SITE_NAME}"
    seo_desc   = (
        f"{sig_name} is currently {status_word}. "
        f"{description[:160].rstrip('.')}. "
        f"Tracked by Unstructured Alpha as part of its {category} signal library."
    )
    canonical  = f"{BASE_URL}/signal/{signal_id}"

    json_ld = f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "{page_title}",
  "description": "{seo_desc}",
  "url": "{canonical}",
  "publisher": {{
    "@type": "Organization",
    "name": "{SITE_NAME}",
    "url": "{APP_URL}"
  }},
  "dateModified": "{snap_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
}}
</script>"""

    # Relevant ticker links
    ticker_links = " · ".join(
        f'<a href="{BASE_URL}/ticker/{t}">{t}</a>'
        for t in relevant_t[:10]
    )

    # 30-day history table (last 7 rows)
    history_rows = ""
    for h in reversed(history[-7:]):
        st  = h["status"]
        if st == "bullish":
            b = '<span class="badge badge-bull">▲ Bullish</span>'
        elif st == "bearish":
            b = '<span class="badge badge-bear">▼ Bearish</span>'
        else:
            b = '<span class="badge badge-neut">● Neutral</span>'
        sc = f"{float(h['score']):.0f}" if h.get("score") is not None else "—"
        history_rows += f"""
        <tr>
          <td style="color:#6B7A95;font-size:0.80rem;">{h['snapshot_date']}</td>
          <td>{sc}/100</td>
          <td>{b}</td>
        </tr>"""

    html = _html_head(page_title, seo_desc, canonical, json_ld)
    html += f"""
<div class="container">

  <div class="hero">
    <div class="hero-eyebrow">{category} Signal</div>
    <div class="hero-ticker" style="font-size:1.8rem;line-height:1.3;">{sig_name}</div>
  </div>

  <div class="score-card">
    <div class="score-label">Current Status</div>
    <div style="font-size:1.6rem;font-weight:800;color:#E8EEFF;margin:12px 0;">{status_badge}</div>
    {"<div class='score-value' style='font-size:3rem;color:" + _score_color(cur_score) + ";'>" + f"{cur_score:.0f}" + "<span class='score-denom'>/100</span></div>" if cur_score is not None else ""}
    <div class="score-updated">{"Updated " + snap_date if snap_date else "No snapshot data yet"}</div>
  </div>

  <div class="section-head">About This Signal</div>
  <p style="color:#B8C0D4;line-height:1.8;font-size:0.92rem;">{description}</p>

  {"<div class='section-head' style='margin-top:24px;'>Lead Time</div><p style='color:#B8C0D4;font-size:0.92rem;'>This signal leads relevant price moves by approximately <strong style='color:#E8EEFF;'>" + str(lag_weeks) + " weeks</strong> based on historical correlation analysis.</p>" if lag_weeks else ""}

  {"<div class='section-head'>Relevant Tickers</div><p style='color:#B8C0D4;font-size:0.88rem;'>" + ticker_links + "</p>" if ticker_links else ""}

  {"<div class='section-head'>Recent History (30 days)</div><table class='signal-table'><thead><tr><th>Date</th><th>Score</th><th>Status</th></tr></thead><tbody>" + history_rows + "</tbody></table>" if history_rows else ""}

  <div class="cta-block">
    <h2>Track This Signal in Real Time</h2>
    <p>
      Unstructured Alpha aggregates {sig_name} alongside {len(SIGNALS) - 1} other macro data
      sources to compute a real-time Confluence Score for each equity. See how this signal
      is currently affecting the tickers you care about.
    </p>
    <a class="cta-btn" href="{APP_URL}/Signal_Dashboard">
      Open Signal Dashboard →
    </a>
  </div>
"""
    html += _html_foot()
    return html


@app.get("/signals/report", response_class=HTMLResponse)
def signals_report():
    TICKERS, SIGNALS = _get_config()
    engine, _, signal_snapshots = _get_engine()

    statuses = _latest_signal_statuses(engine, signal_snapshots)

    bull_sigs = [(sid, SIGNALS[sid]) for sid, st in statuses.items() if st == "bullish" and sid in SIGNALS]
    bear_sigs = [(sid, SIGNALS[sid]) for sid, st in statuses.items() if st == "bearish" and sid in SIGNALS]
    neut_sigs = [(sid, SIGNALS[sid]) for sid, st in statuses.items() if st not in ("bullish", "bearish") and sid in SIGNALS]

    total = len(bull_sigs) + len(bear_sigs) + len(neut_sigs) or 1
    regime = (
        "Bullish" if len(bull_sigs) / total >= 0.50 else
        "Bearish" if len(bear_sigs) / total >= 0.50 else
        "Mixed"
    )
    regime_color = GREEN if regime == "Bullish" else (RED if regime == "Bearish" else AMBER)

    today_str  = datetime.now(timezone.utc).strftime("%B %-d, %Y")
    page_title = f"Macro Signal Report — {today_str} — {SITE_NAME}"
    seo_desc   = (
        f"Daily macro signal report from Unstructured Alpha. As of {today_str}: "
        f"{len(bull_sigs)} bullish, {len(bear_sigs)} bearish, {len(neut_sigs)} neutral signals. "
        f"Overall regime: {regime}."
    )
    canonical  = f"{BASE_URL}/signals/report"

    json_ld = f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "{page_title}",
  "description": "{seo_desc}",
  "url": "{canonical}",
  "datePublished": "{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
  "publisher": {{
    "@type": "Organization",
    "name": "{SITE_NAME}",
    "url": "{APP_URL}"
  }}
}}
</script>"""

    def _sig_rows(pairs: list, badge_class: str, sym: str) -> str:
        rows = ""
        for sid, cfg in sorted(pairs, key=lambda x: x[1].get("name", "")):
            rows += f"""
            <tr>
              <td><a href="{BASE_URL}/signal/{sid}" style="color:#B8C0D4;">{cfg.get("name", sid)}</a></td>
              <td style="color:#6B7A95;font-size:0.78rem;">{cfg.get("category","").title()}</td>
              <td><span class="badge {badge_class}">{sym}</span></td>
            </tr>"""
        return rows

    html = _html_head(page_title, seo_desc, canonical, json_ld)
    html += f"""
<div class="container">

  <div class="hero">
    <div class="hero-eyebrow">Daily Signal Report · {today_str}</div>
    <div class="hero-ticker" style="font-size:1.8rem;">Macro Signal Report</div>
  </div>

  <div class="score-card">
    <div class="score-label">Overall Macro Regime</div>
    <div style="font-size:2.8rem;font-weight:900;color:{regime_color};">{regime}</div>
  </div>

  <div class="signal-grid">
    <div class="signal-stat">
      <div class="val" style="color:{GREEN};">{len(bull_sigs)}</div>
      <div class="lbl">Bullish</div>
    </div>
    <div class="signal-stat">
      <div class="val" style="color:{RED};">{len(bear_sigs)}</div>
      <div class="lbl">Bearish</div>
    </div>
    <div class="signal-stat">
      <div class="val" style="color:{AMBER};">{len(neut_sigs)}</div>
      <div class="lbl">Neutral</div>
    </div>
  </div>

  {"<div class='section-head'>Bullish Signals (" + str(len(bull_sigs)) + ")</div><table class='signal-table'><thead><tr><th>Signal</th><th>Category</th><th>Status</th></tr></thead><tbody>" + _sig_rows(bull_sigs, "badge-bull", "▲ Bullish") + "</tbody></table>" if bull_sigs else ""}

  {"<div class='section-head'>Bearish Signals (" + str(len(bear_sigs)) + ")</div><table class='signal-table'><thead><tr><th>Signal</th><th>Category</th><th>Status</th></tr></thead><tbody>" + _sig_rows(bear_sigs, "badge-bear", "▼ Bearish") + "</tbody></table>" if bear_sigs else ""}

  {"<div class='section-head'>Neutral Signals (" + str(len(neut_sigs)) + ")</div><table class='signal-table'><thead><tr><th>Signal</th><th>Category</th><th>Status</th></tr></thead><tbody>" + _sig_rows(neut_sigs, "badge-neut", "● Neutral") + "</tbody></table>" if neut_sigs else ""}

  <div class="cta-block">
    <h2>Get the Full Signal Dashboard</h2>
    <p>
      See how today's macro signals affect the individual equities you follow.
      Unstructured Alpha's Confluence Score aggregates {len(SIGNALS)} data sources
      into a single 0–100 number, updated as FRED, EIA, and SEC data arrives.
    </p>
    <a class="cta-btn" href="{APP_URL}/Today%27s_Brief">
      Open Today's Brief →
    </a>
  </div>
"""
    html += _html_foot()
    return html


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("seo.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8502)), reload=False)
