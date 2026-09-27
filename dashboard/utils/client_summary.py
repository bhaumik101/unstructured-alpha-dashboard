# utils/client_summary.py
# Unstructured Alpha — the one-page client summary
#
# WHY THIS EXISTS
# ---------------
# An adviser does not hand a client a web page. They hand over a sheet of
# paper, or a PDF attached to an email, at a review meeting. The report printed
# — it has had print styles since the redesign — but it printed as eight pages
# of everything, which is a report, not a summary.
#
# This is one page: what the portfolio holds, the one-sentence reading, every
# force with its range and evidence label, what carries the strongest
# exposures, how each has been moving, and the method and the caveat. Nothing
# on it is new; it is the same engine's numbers laid out for a client to read
# in two minutes.
#
# The caveat is not small print. It is the thing an adviser most needs a
# client to take away: this describes how the portfolio has moved, and it is
# not a forecast. It sits in the body, above the method, at the same size as
# everything else.

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Iterable, Tuple

from utils import exposure as ex
from utils import report_charts as charts
from utils import report_ui as ui

SUMMARY_CSS = """<style>
.ucs{--ucs-ink:#13213a;--ucs-ink2:#3a4760;--ucs-ink3:#5b6780;--ucs-line:#dfe5ee;
  --ucs-sub:#f4f6fa;--ucs-accent:#1f5fae;
  --uar-surface:#ffffff;--uar-subtle:#f4f6fa;--uar-ink:#13213a;--uar-ink-2:#3a4760;
  --uar-ink-3:#5b6780;--uar-line:#dfe5ee;--uar-accent:#1f5fae;--uar-pos:#2563a8;
  --uar-neg:#c26a0a;--uar-sky:#edf4fc;--uar-shadow:rgba(13,34,59,.2);
  --uar-t-micro:.74rem;--uar-t-meta:.78rem;--uar-t-sm:.82rem;--uar-t-body:.88rem;
  --uar-t-price:1.25rem;
  background:#ffffff;color:var(--ucs-ink);font-family:Inter,"SF Pro Text","Segoe UI",system-ui,sans-serif;
  font-variant-numeric:tabular-nums;max-width:820px;margin:0 auto;padding:28px 32px;
  border:1px solid var(--ucs-line);border-radius:14px;}
.ucs-top{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;
  border-bottom:3px solid transparent;border-image:linear-gradient(90deg,#3b7ddd,#7c5ce0,#e0664a,#d99018,#1a9a70,#1497b0) 1;
  padding-bottom:12px;margin-bottom:14px;}
.ucs-kicker{font-size:var(--uar-t-micro);font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:var(--ucs-accent);}
.ucs-name{font-size:var(--uar-t-price);font-weight:750;letter-spacing:-0.02em;margin-top:2px;}
.ucs-meta{font-size:var(--uar-t-meta);color:var(--ucs-ink3);text-align:right;line-height:1.5;}
.ucs-lead{font-size:var(--uar-t-body);color:var(--ucs-ink2);line-height:1.6;margin:0 0 12px;}
.ucs h3{font-size:var(--uar-t-sm);font-weight:700;text-transform:uppercase;letter-spacing:.05em;
  color:var(--ucs-ink3);margin:14px 0 6px;}
.ucs table{width:100%;border-collapse:collapse;font-size:var(--uar-t-meta);}
.ucs th{text-align:left;font-weight:650;color:var(--ucs-ink3);padding:5px 6px;border-bottom:1px solid var(--ucs-line);}
.ucs td{padding:6px;border-bottom:1px solid var(--ucs-line);color:var(--ucs-ink2);vertical-align:top;}
.ucs td b{color:var(--ucs-ink);}
.ucs-two{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.ucs-mini{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;}
.ucs-mini .uac-sub{font-size:var(--uar-t-micro);}
.ucs-caveat{border-left:3px solid var(--ucs-accent);background:var(--ucs-sub);padding:8px 12px;
  font-size:var(--uar-t-meta);color:var(--ucs-ink2);margin:14px 0 8px;line-height:1.55;}
.ucs-foot{font-size:var(--uar-t-micro);color:var(--ucs-ink3);line-height:1.5;margin-top:8px;}
.ucs-print{display:inline-flex;align-items:center;min-height:44px;padding:0 18px;border-radius:8px;
  background:#1f5fae;color:#ffffff!important;font-weight:650;text-decoration:none!important;}
.ucs-print:hover{background:#184c8c;}
@media (max-width:700px){.ucs{padding:18px;}.ucs-two{grid-template-columns:1fr;}
  .ucs-mini{grid-template-columns:repeat(2,1fr);}.ucs-top{flex-direction:column;}.ucs-meta{text-align:left;}}
@media print{
  @page{size:letter;margin:12mm;}
  html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:#fff!important;}
  .ua-topnav,.st-key-ua_account_row,.st-key-ua_spa_proxy_rail,[data-testid="stButton"],
  [data-testid="stHeader"],.ua-phero,.ucs-screen-only,.st-key-cs_controls,#ua-scroll-top,.ua-scroll-top,
  [data-testid="stCaptionContainer"]{display:none!important;}
  .block-container{padding:0!important;max-width:none!important;}
  .ucs{border:0;padding:0;max-width:none;}
  .ucs *{-webkit-print-color-adjust:exact;print-color-adjust:exact;}
  .ucs-two,.ucs-mini,.ucs table{break-inside:avoid;}
}
</style>"""


def _top_contributors(report: dict, key: str, n: int = 3) -> str:
    rows = (report.get("contributions") or {}).get(key) or []
    parts = [f'{escape(r["ticker"])} {ui.fmt_pct(r["contribution"])}' for r in rows[:n]]
    return ", ".join(parts) if parts else "—"


def summary_html(report: dict, name: str, prepared_for: str = "",
                 prepared_by: str = "", when: datetime | None = None) -> str:
    """The whole page, as one HTML block. Never raises on a thin report."""
    if report.get("status") != "ok":
        return ""
    when = when or datetime.now(timezone.utc)
    readings = report["portfolio"]["readings"]
    order = ui.ordered_keys(report)
    positions = sorted(report.get("positions") or [], key=lambda p: -p["weight_pct"])
    holdings = " · ".join(f'{p["weight_pct"]:.0f}% {escape(p["ticker"])}' for p in positions[:14])
    if len(positions) > 14:
        holdings += f" · +{len(positions) - 14} more"

    rows = "".join(
        f'<tr><td><span class="uar-dot" style="background:{ui.FACTOR_COLORS.get(k, "#3b7ddd")}"></span>'
        f'<b>{escape(readings[k]["label"])}</b><br>{escape(readings[k]["shock_phrase"])}</td>'
        f'<td><b>{ui.fmt_pct(readings[k]["impact"])}</b><br>'
        f'{ui.fmt_pct(readings[k]["low"])} to {ui.fmt_pct(readings[k]["high"])}</td>'
        f'<td>{escape(readings[k]["evidence_label"])}</td>'
        f'<td>{_top_contributors(report, k) if readings[k]["evidence"] in ("clear", "tentative") else "—"}</td></tr>'
        for k in order)

    minis = []
    for k in order:
        points = (report.get("rolling") or {}).get(k)
        if not points or len(points) < 3:
            continue
        words = (f"{readings[k]['label']} sensitivity over rolling years, from "
                 f"{ui.fmt_pct(points[0]['impact'])} to {ui.fmt_pct(points[-1]['impact'])}.")
        minis.append(
            f'<div><div class="uac-sub"><b>{escape(readings[k]["label"])}</b></div>'
            f'{charts.sparkline_svg([p["impact"] for p in points], ui.FACTOR_COLORS.get(k, "#3b7ddd"), words)}'
            f'<div class="uac-sub">{ui.fmt_pct(points[0]["impact"])} → {ui.fmt_pct(points[-1]["impact"])}</div></div>')

    method = report.get("method") or {}
    who = []
    if prepared_for:
        who.append(f"Prepared for {escape(prepared_for)}")
    if prepared_by:
        who.append(f"by {escape(prepared_by)}")
    meta = (" ".join(who) + "<br>" if who else "") + \
        f'{when:%B} {when.day}, {when.year}<br>Data through {escape(ui.fmt_date(report.get("as_of")))}'

    return (
        '<div class="ucs">'
        '<div class="ucs-top"><div>'
        '<div class="ucs-kicker">Portfolio exposure summary</div>'
        f'<div class="ucs-name">{escape(name)}</div>'
        f'<div class="ucs-meta" style="text-align:left">{holdings}</div></div>'
        f'<div class="ucs-meta">{meta}</div></div>'
        f'<p class="ucs-lead">{ui.summary_text(report)}</p>'
        '<div class="ucs-two">'
        f'<div>{ui.exposure_map_html(report)}</div>'
        '<div><h3>How to read the numbers</h3><p class="ucs-lead">Each figure is how this '
        'portfolio typically moved in a week when that force moved by the stated amount, with the '
        'stock market&#39;s own movement removed first. The range shows how precisely it was '
        'measured; <b>Clear</b> means it held up after allowing for testing five forces at once, '
        '<b>Tentative</b> means it could still be noise.</p></div></div>'
        '<h3>Exposure to each economic force</h3>'
        '<table><thead><tr><th>Force and move</th><th>Typical weekly move · 90% range</th>'
        f'<th>Evidence</th><th>Largest contributors</th></tr></thead><tbody>{rows}</tbody></table>'
        + (f'<h3>How each exposure has moved (rolling year)</h3><div class="ucs-mini">{"".join(minis)}</div>'
           if minis else "")
        + '<div class="ucs-caveat"><b>This describes the past, and it is not a forecast.</b> It shows '
        'how this portfolio has moved alongside five economic forces over the last three years. '
        'Relationships change, and nothing here is a recommendation to buy, sell or hold any '
        'security.</div>'
        f'<div class="ucs-foot">Method: weekly returns over {method.get("window_weeks", 156)} weeks, '
        f'regressed on weekly changes in the 10-year Treasury yield, 10-year inflation expectations, '
        f'the trade-weighted dollar, oil and corporate credit spreads, controlling for the S&amp;P 500 '
        f'({escape(str(method.get("market_control", "SPY")))}). Newey-West standard errors; "Clear" '
        f'requires |t| ≥ {ex.CLEAR_T:.2f}. Prices from Yahoo Finance; economic series from FRED. '
        'Prepared with Unstructured Alpha, an educational and informational tool — not personalized '
        'financial, investment, tax or legal advice.</div>'
        '</div>')
