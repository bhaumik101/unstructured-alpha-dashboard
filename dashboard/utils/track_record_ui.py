# utils/track_record_ui.py
# Unstructured Alpha — the evidence page's panels
#
# The numbers come from utils/track_record.py. These panels show them against
# the line that gives them meaning: a coin flip (50%) for "same direction", and
# the ~90% a perfectly stable relationship would reach for "consistent". Every
# bar carries its number and its count, so nothing is read from colour or
# length alone, and every chart has a table beside it.

from __future__ import annotations

from html import escape
from typing import Optional

from utils import exposure as ex
from utils import report_ui as ui

LABEL_NAMES = {"clear": "Clear", "tentative": "Tentative",
               "indistinct": "Not distinguishable from zero"}


def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{100 * x:.0f}%"


def empty_html() -> str:
    return ('<div class="uar"><div class="uar-card"><div class="uar-body"><p class="uar-lead">'
            'The first run of this study has not been published yet. It runs with the weekly '
            'measurement job, on ten years of prices for every S&amp;P 500 company, and this page '
            'shows its results, whatever they are, as soon as it finishes.</p></div></div></div>')


def coverage_html(r: dict) -> str:
    """When the run happened and how much of the index it reached."""
    when = ui.fmt_date(str(r.get("computed_at") or "")[:10]) if r.get("computed_at") else "—"
    reached = f'{r.get("n_stocks", 0):,} of {r.get("universe") or r.get("n_stocks", 0):,} S&amp;P 500 companies'
    line = f'Latest run: {escape(when)} · {reached}'
    if r.get("stopped"):
        return ('<div class="uar"><div class="evd-partial" role="note">'
                f'{line}. This run stopped at its time limit before reaching the whole index, so these '
                'figures cover only the companies it reached. The full study reruns with the next '
                'weekly job.</div></div>')
    return f'<div class="uar"><div class="evd-coverage">{line}</div></div>'


def headline_html(r: dict) -> str:
    bl = r["by_label"]
    clear, zero = bl.get("clear") or {}, bl.get("indistinct") or {}
    slope = r.get("shrinkage_slope")
    tiles = [
        (_pct(clear.get("same_direction")), "Clear readings that kept their direction a year later",
         f'{clear.get("n", 0):,} readings'),
        (_pct(zero.get("same_direction")), "The same for readings indistinguishable from zero",
         "the coin-flip baseline"),
        ("—" if slope is None else f"{slope:.2f}", "How much readings carry over at full size",
         "1.00 = no shrinkage out of sample"),
    ]
    cells = "".join(f'<li><div class="udb-tile"><div class="udb-v">{escape(v)}</div>'
                    f'<div class="udb-l">{escape(label)}</div><div class="udb-d">{escape(d)}</div>'
                    '</div></li>' for v, label, d in tiles)
    return f'<ul class="udb-tiles evd-tiles" role="list" aria-label="Headline results">{cells}</ul>'


def _bars(r: dict, metric: str, reference: float, ref_label: str, title: str, sub: str) -> str:
    rows = []
    for lab in ("clear", "tentative", "indistinct"):
        st = r["by_label"].get(lab)
        if not st:
            continue
        v = st[metric]
        rows.append(
            f'<li class="evd-row" aria-label="{escape(LABEL_NAMES[lab])}: {_pct(v)} of {st["n"]:,} readings">'
            f'<span class="evd-name">{escape(LABEL_NAMES[lab])}<span>{st["n"]:,} readings</span></span>'
            f'<span class="evd-track" aria-hidden="true"><span class="evd-fill" style="width:{100 * v:.1f}%"></span>'
            f'<span class="evd-ref" style="left:{100 * reference:.1f}%"></span></span>'
            f'<span class="evd-val">{_pct(v)}</span></li>')
    return ('<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
            f'<div class="uar-title">{escape(title)}</div><div class="uar-sub">{escape(sub)}</div>'
            f'</div></div><div class="uar-body"><ul class="evd-list" role="list" aria-label="{escape(title)}">'
            f'{"".join(rows)}</ul><div class="evd-legend"><span class="evd-refkey"></span>'
            f'{escape(ref_label)}</div></div></div></div>')


def direction_html(r: dict) -> str:
    return _bars(r, "same_direction", 0.5, "50%: a coin flip",
                 "Same direction a year later",
                 "Of the readings carrying each label, the share whose next-year reading had the "
                 "same sign. Readings that are only noise should land near the coin-flip line.")


def consistency_html(r: dict) -> str:
    return _bars(r, "consistent", 0.9, "90%: what a perfectly stable relationship would reach",
                 "Consistent within the uncertainty",
                 "The share where the next-year reading agreed with the first within their combined "
                 "90% range. Below the line means relationships drifted more than the ranges allow.")


def by_force_html(r: dict) -> str:
    rows = "".join(
        f'<tr><th scope="row">{escape(f.label)}</th><td>{_pct((r["by_factor"].get(f.key) or {}).get("same_direction"))}</td>'
        f'<td>{_pct((r["by_factor"].get(f.key) or {}).get("consistent"))}</td>'
        f'<td>{(r["by_factor"].get(f.key) or {}).get("n", 0):,}</td></tr>'
        for f in ex.FACTORS)
    return ('<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
            '<div class="uar-title">By force (Clear and Tentative readings)</div></div></div>'
            '<div class="uar-body evd-table" tabindex="0" role="region" aria-label="Results by force">'
            '<table><thead><tr><th scope="col">Force</th><th scope="col">Same direction</th>'
            '<th scope="col">Consistent</th><th scope="col">Readings</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></div></div>')


def method_html(r: dict) -> str:
    origins = r.get("origins") or []
    span = (f"{ui.fmt_date(origins[0])} to {ui.fmt_date(origins[-1])}" if origins else "—")
    return ('<div class="uar"><div class="uar-foot">'
            f'{r["n_pairs"]:,} reading pairs from {r["n_stocks"]:,} S&amp;P 500 companies, at '
            f'{len(origins)} start dates every six months ({escape(span)}). At each start date the '
            f'five core forces were measured on the {r["then_weeks"]} weeks before it, exactly as the '
            f'product measures them, and again on the {r["next_weeks"]} weeks after it, which the first '
            'measurement never saw. Pairs from neighbouring start dates share data, so they are not '
            'independent; the percentages are descriptive, not a significance test. The study is '
            'rerun monthly and every run is kept. It describes how readings held up in the past; it '
            'is not a forecast.</div></div>')


EVIDENCE_CSS = """<style>
.evd-tiles{grid-template-columns:repeat(3,1fr);}
.evd-list{list-style:none;margin:0;padding:0;}
.evd-list li{list-style:none;}
.evd-row{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,2fr) 56px;gap:14px;align-items:center;padding:10px 0;
  border-bottom:1px solid var(--uar-line);}
.evd-row:last-child{border-bottom:0;}
.evd-name{display:flex;flex-direction:column;color:var(--uar-ink);font-weight:650;font-size:var(--uar-t-sm);}
.evd-name span{font-weight:400;font-size:var(--uar-t-micro);color:var(--uar-ink-3);}
.evd-track{position:relative;height:14px;background:var(--uar-subtle);border-radius:4px;}
.evd-fill{position:absolute;left:0;top:0;bottom:0;background:var(--uar-pos);border-radius:4px;}
.evd-ref{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--uar-ink-2);}
.evd-val{text-align:right;font-weight:700;color:var(--uar-ink);font-variant-numeric:tabular-nums;}
.evd-legend{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:var(--uar-t-micro);color:var(--uar-ink-3);}
.evd-refkey{display:inline-block;width:2px;height:14px;background:var(--uar-ink-2);}
.evd-coverage{font-size:var(--uar-t-micro);color:var(--uar-ink-3);margin:0 0 10px;}
.evd-partial{border:1px solid var(--uar-line);border-left:3px solid var(--uar-ink-2);border-radius:6px;
  padding:10px 12px;margin:0 0 12px;color:var(--uar-ink);font-size:var(--uar-t-sm);background:var(--uar-subtle);}
.evd-table{overflow-x:auto;}
.evd-table table{width:100%;border-collapse:collapse;font-size:var(--uar-t-sm);}
.evd-table th,.evd-table td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--uar-line);color:var(--uar-ink-2);}
.evd-table th[scope=row]{color:var(--uar-ink);font-weight:650;}
@media (max-width:700px){.evd-tiles{grid-template-columns:1fr;}.evd-row{grid-template-columns:1fr 56px;}.evd-track{display:none;}}
</style>"""
