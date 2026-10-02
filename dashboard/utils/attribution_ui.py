# utils/attribution_ui.py
# Unstructured Alpha — the return-attribution waterfall
#
# A waterfall reads left to right as running arithmetic: each bar starts where
# the previous one ended, so the eye follows the market, then each force, then
# what nothing explains, to the total. Up and down use the report's diverging
# pair; the total is ink, because it is a sum, not a direction. Every bar has
# its number beside it and the whole chart is an ordered list a screen reader
# reads as sentences.

from __future__ import annotations

from html import escape

from utils import report_ui as ui


def waterfall_html(att: dict) -> str:
    lines = sorted([l for l in att["lines"] if l["kind"] == "force"],
                   key=lambda l: -abs(l["contribution"]))
    ordered = ([l for l in att["lines"] if l["kind"] == "market"] + lines
               + [l for l in att["lines"] if l["kind"] == "other"])
    points, run = [0.0], 0.0
    for l in ordered:
        run += l["contribution"]
        points.append(run)
    points.append(att["total"])
    scale = ui._nice_scale(points)

    def x(v: float) -> float:
        return 50.0 + max(-scale, min(scale, v)) / scale * 50.0

    rows, run = [], 0.0
    for l in ordered:
        start, end = run, run + l["contribution"]
        run = end
        left, width = min(x(start), x(end)), max(abs(x(end) - x(start)), 0.4)
        colour = "var(--uar-pos)" if l["contribution"] >= 0 else "var(--uar-neg)"
        weak = (l["kind"] == "force" and l["evidence"] not in ("clear", "tentative"))
        note = " · reading not distinguishable from zero" if weak else ""
        rng = (f' (90% range {ui.fmt_pct(l["contribution"] - 1.645 * l["se"])} to '
               f'{ui.fmt_pct(l["contribution"] + 1.645 * l["se"])})') if l.get("se") else ""
        say = f'{l["label"]}: {ui.fmt_pct(l["contribution"])}{rng}. {l["what_happened"]}.'
        rows.append(
            f'<li class="atw-row{" atw-weak" if weak else ""}" aria-label="{escape(say)}">'
            f'<span class="atw-name"><b>{escape(l["label"])}</b>'
            f'<span>{escape(l["what_happened"][:1].upper() + l["what_happened"][1:])}{escape(note)}</span></span>'
            f'<span class="atw-track" aria-hidden="true"><span class="atw-zero"></span>'
            f'<span class="atw-bar" style="left:{left:.2f}%;width:{width:.2f}%;background:{colour}"></span></span>'
            f'<span class="atw-val">{ui.fmt_pct(l["contribution"])}</span></li>')
    t = att["total"]
    rows.append(
        f'<li class="atw-row atw-total" aria-label="Total: {escape(ui.fmt_pct(t))} summed over '
        f'{att["weeks"]} weeks.">'
        '<span class="atw-name"><b>Total</b><span>Summed weekly returns</span></span>'
        '<span class="atw-track" aria-hidden="true"><span class="atw-zero"></span>'
        f'<span class="atw-bar atw-sum" style="left:{min(x(0), x(t)):.2f}%;width:{max(abs(x(t) - x(0)), 0.4):.2f}%"></span></span>'
        f'<span class="atw-val">{ui.fmt_pct(t)}</span></li>')
    return (
        '<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
        f'<div class="uar-title">What drove the last {att["weeks"]} weeks</div>'
        f'<div class="uar-sub">{escape(ui.fmt_date(att["start"]))} to {escape(ui.fmt_date(att["end"]))}. '
        f'Summed weekly returns {ui.fmt_pct(t)}; compounded {ui.fmt_pct(att["compounded"])}.</div>'
        '</div></div><div class="uar-body">'
        f'<ol class="atw-list" aria-label="Return attribution, largest first">{"".join(rows)}'
        # The scale is a row of the same grid, so its ticks sit under the bars'
        # own zero line and ends at every width.
        f'<li class="atw-scale" aria-hidden="true"><span></span><span class="atw-ticks"><span>−{scale:g}%</span>'
        f'<span>0</span><span>+{scale:g}%</span></span><span></span></li></ol>'
        '</div><div class="uar-foot">Each line is the portfolio&#39;s measured weekly sensitivity times '
        'what that force actually did, week by week. Faded bars rest on readings that could not be '
        'told apart from zero. The sensitivities were measured on data that includes these weeks, so this '
        'describes the past; it is not a test or a forecast.</div></div></div>')


ATTRIBUTION_CSS = """<style>
.atw-list{list-style:none;margin:0;padding:0;}
.atw-list li{list-style:none;}
.atw-row{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1.7fr) 84px;gap:14px;align-items:center;
  padding:8px 0;border-bottom:1px solid var(--uar-line);}
.atw-name{display:flex;flex-direction:column;min-width:0;}
.atw-name b{color:var(--uar-ink);font-size:var(--uar-t-sm);}
.atw-name span{font-size:var(--uar-t-micro);color:var(--uar-ink-3);}
.atw-track{position:relative;height:16px;}
.atw-zero{position:absolute;left:50%;top:-6px;bottom:-6px;width:1px;background:var(--uar-line);}
.atw-bar{position:absolute;top:2px;bottom:2px;border-radius:3px;}
.atw-weak .atw-bar{opacity:.45;}
.atw-sum{background:var(--uar-ink);}
.atw-total{border-bottom:0;border-top:2px solid var(--uar-ink-3);}
.atw-val{text-align:right;font-weight:700;color:var(--uar-ink);font-variant-numeric:tabular-nums;white-space:nowrap;}
.atw-scale{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1.7fr) 84px;gap:14px;
  font-size:var(--uar-t-micro);color:var(--uar-ink-3);margin-top:4px;}
.atw-ticks{display:flex;justify-content:space-between;}
.stApp .uar .atw-scale,.stApp .uar .atw-scale span{font-size:var(--uar-t-micro)!important;line-height:1.4;}
@media (max-width:640px){.atw-row{grid-template-columns:1fr 84px;}.atw-track,.atw-scale{display:none;}}
</style>"""
