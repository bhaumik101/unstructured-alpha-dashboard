# utils/scenario_ui.py
# Unstructured Alpha — the scenario lab's result panels
#
# Three blocks, all in the report's visual language (utils/report_ui.py): a
# headline with its 90% range, what each moved force contributed, and which
# holdings carry the move. Diverging bars throughout -- a contribution is
# either up or down, and the colour says which; the number beside it says how
# much, so colour never carries meaning alone.

from __future__ import annotations

from html import escape
from typing import List

from utils import report_ui as ui
from utils import scenario as sc


def _amount(c: dict) -> str:
    return sc.format_amount(c["amount"], c["unit"])


def headline_html(out: dict) -> str:
    impact, low, high = out["impact"], out["low"], out["high"]
    scale = ui._nice_scale([low, high, impact])
    direction = "rise" if impact > 0 else "fall"
    sentence = (f"With {sc.describe_moves(out['moved'])}, and everything else held where it "
                f"was, this portfolio's last {out['n_obs']} weeks suggest it would {direction} "
                f"about {ui.fmt_pct(abs(impact)).lstrip('+')} (90% range {ui.fmt_pct(low)} to "
                f"{ui.fmt_pct(high)}).")
    warn = ('<div class="scn-warn" role="note"><b>Beyond anything in the data.</b> At least '
            'one move here is larger than that force moved over any three months in this '
            'period, so the estimate assumes its effect keeps scaling in a straight line. Treat '
            'it as a rough guide.</div>') if out["extrapolated"] else ""
    return (
        '<div class="uar"><div class="uar-card scn-hero">'
        '<div class="scn-hero-top"><div><div class="scn-kicker">Estimated move</div>'
        f'<div class="scn-big">{ui.fmt_pct(impact)}</div>'
        f'<div class="scn-range">90% range {ui.fmt_pct(low)} to {ui.fmt_pct(high)}</div></div>'
        f'<div class="scn-herobar">{ui.exposure_bar(impact, low, high, scale)}'
        f'<div class="scn-scale"><span>−{scale:g}%</span><span>0</span><span>+{scale:g}%</span></div></div></div>'
        f'<p class="uar-lead scn-sentence">{escape(sentence)}</p>{warn}'
        '</div></div>')


def _rows(items: List[dict], label_fn, value_key: str, scale: float, aria: str,
          low_key: str = "low", high_key: str = "high") -> str:
    rows = []
    for it in items:
        label, sub = label_fn(it)
        v, lo, hi = it[value_key], it.get(low_key), it.get(high_key)
        say = (f"{label}: {ui.fmt_pct(v)}" + (f", 90% range {ui.fmt_pct(lo)} to {ui.fmt_pct(hi)}"
                                               if lo is not None else ""))
        rows.append(
            f'<li class="scn-row" aria-label="{escape(say)}">'
            f'<span class="scn-who"><b>{escape(label)}</b><span>{escape(sub)}</span></span>'
            f'<span class="scn-bar">{ui.exposure_bar(v, lo if lo is not None else v, hi if hi is not None else v, scale)}</span>'
            f'<span class="scn-num"><b>{ui.fmt_pct(v)}</b>'
            + (f'<span>{ui.fmt_pct(lo)} to {ui.fmt_pct(hi)}</span>' if lo is not None else "")
            + '</span></li>')
    return f'<ul class="scn-list" role="list" aria-label="{escape(aria)}">{"".join(rows)}</ul>'


def contributions_html(out: dict) -> str:
    cs = out["contributions"]
    if not cs:
        return ""
    scale = ui._nice_scale([v for c in cs for v in (c["low"], c["high"])])
    body = _rows(cs, lambda c: (c["label"], _amount(c) + (" · beyond any 3-month move in the data"
                                                          if c["extrapolated"] else "")),
                 "impact", scale, "What each moved force contributed")
    return ('<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
            '<div class="uar-title">What each force contributed</div>'
            '<div class="uar-sub">Estimated from one joint fit of all the forces moved, so the '
            'contributions add up to the total and their ranges account for each other.</div>'
            f'</div></div><div class="uar-body">{body}</div></div></div>')


def holdings_html(out: dict, limit: int = 12) -> str:
    hs = out["holdings"]
    if len(hs) < 2:
        return ""
    ranked = sorted(hs, key=lambda h: -abs(h["contribution"]))[:limit]
    scale = ui._nice_scale([v for h in ranked for v in (h["c_low"], h["c_high"])])
    body = _rows(ranked, lambda h: (h["ticker"], f'{h["weight_pct"]:.0f}% of the portfolio · '
                                                 f'its own move {ui.fmt_pct(h["impact"])}'),
                 "contribution", scale, "Which holdings carry the move", "c_low", "c_high")
    more = (f'<div class="uar-foot">Showing the {len(ranked)} largest of {len(hs)} holdings.</div>'
            if len(hs) > len(ranked) else "")
    return ('<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
            '<div class="uar-title">Which holdings carry the move</div>'
            '<div class="uar-sub">Each holding&#39;s weight times its own estimated move. Measured '
            'on the same weeks and forces as the portfolio, so these add up to the total.</div>'
            f'</div></div><div class="uar-body">{body}</div>{more}</div></div>')


def method_html(out: dict) -> str:
    return ('<div class="uar"><div class="uar-foot scn-method">'
            f'One regression of weekly returns over {out["n_obs"]} weeks '
            f'({escape(ui.fmt_date(out["start"]))} to {escape(ui.fmt_date(out["end"]))}) on the stock '
            'market, the five core forces and every extra force this scenario moves, with '
            'Newey-West standard errors. The range comes from the full covariance of the estimates. '
            'Each figure is linear in the size of the move. <b>This describes how the portfolio has '
            'moved, and it is not a forecast</b>: relationships change, and nothing here is a '
            'recommendation to buy, sell or hold any security.</div></div>')


SCENARIO_CSS = """<style>
.scn-hero{padding:18px 20px;}
.scn-hero-top{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:20px;align-items:center;}
.scn-kicker{font-size:var(--uar-t-micro);font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--uar-ink-3);}
.scn-big{font-size:2.6rem;font-weight:780;letter-spacing:-.03em;line-height:1.05;color:var(--uar-ink);font-variant-numeric:tabular-nums;}
.scn-range{font-size:var(--uar-t-sm);color:var(--uar-ink-2);margin-top:2px;}
.scn-herobar .uar-bar{height:22px;}
.scn-scale{display:flex;justify-content:space-between;font-size:var(--uar-t-micro);color:var(--uar-ink-3);margin-top:4px;}
.stApp .uar p.scn-sentence{margin:14px 0 0;}
.scn-warn{margin-top:12px;padding:10px 12px;border-radius:10px;background:var(--uar-sky);
  border-left:3px solid var(--uar-neg);font-size:var(--uar-t-sm);color:var(--uar-ink-2);}
.scn-list{list-style:none;margin:0;padding:0;}
.scn-list li{list-style:none;margin:0;}
.scn-row{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1.6fr) auto;gap:14px;align-items:center;
  padding:9px 0;border-bottom:1px solid var(--uar-line);}
.scn-row:last-child{border-bottom:0;}
.scn-who{display:flex;flex-direction:column;min-width:0;}
.scn-who b{color:var(--uar-ink);}
.scn-who span{font-size:var(--uar-t-micro);color:var(--uar-ink-3);}
.scn-num{display:flex;flex-direction:column;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;}
.scn-num b{color:var(--uar-ink);}
.scn-num span{font-size:var(--uar-t-micro);color:var(--uar-ink-3);}
@media (max-width:640px){.scn-hero-top{grid-template-columns:1fr;}.scn-row{grid-template-columns:1fr auto;}
  .scn-bar{display:none;}.scn-big{font-size:2.2rem;}}
</style>"""
