# utils/walkforward_ui.py
# Unstructured Alpha — the walk-forward results, drawn
#
# docs/RESEARCH_2026-11.md §6-9 tested every kind of reading the same way:
# measure on earlier years, then check the year after, which the measurement
# never saw, and count how often the portfolio's move beyond the market went
# the way the reading said in that year's biggest weeks. A coin flip scores
# 50%. These are those published numbers, drawn so a reader sees in one look
# that a "Clear" label carries information and a weaker one barely does.
#
# RULES
#   * Numbers are the studies' results, copied here with their sample sizes;
#     a test pins them to the research doc. Past results; not a forecast.
#   * Every bar is labelled with its number and a word, never colour alone.

from __future__ import annotations

from html import escape
from typing import List, Optional, Tuple

COIN = 50

# (label, funds %, stocks %): how often readings of each evidence tier held up.
TIERS: List[Tuple[str, Optional[int], Optional[int]]] = [
    ("Clear, 5-yr confirmed", 75, 74),
    ("Clear", 74, 71),
    ("Tentative", 55, 56),
    ("Not distinguishable", None, 51),
]

# (force, % held up, big weeks tested, which test): Clear readings, by force.
FORCES: List[Tuple[str, int, int, str]] = [
    ("Interest rates", 90, 80, "core"),
    ("Credit spreads", 85, 26, "core"),
    ("Value vs growth", 82, 3552, "extra"),
    ("U.S. dollar", 78, 102, "core"),
    ("Emerging markets", 78, 212, "extra"),
    ("Copper", 72, 172, "extra"),
    ("Small vs large", 71, 1627, "extra"),
    ("Volatility", 69, 107, "extra"),
    ("Oil and energy", 66, 116, "core"),
    ("Gold", 66, 541, "extra"),
    ("Bitcoin", 64, 42, "extra"),
    ("Momentum", 61, 189, "extra"),
    ("China", 56, 215, "extra"),
    ("Natural gas", 52, 48, "extra"),
    ("Inflation expectations", 50, 40, "core"),
    ("Mortgage rates", 50, 26, "extra"),
]
EXTRA_TESTED = {"Bitcoin", "Momentum", "China", "Natural gas", "Inflation expectations", "Mortgage rates"}


def _tone(pct: int) -> Tuple[str, str]:
    if pct >= 70:
        return "ok", "holds up"
    if pct >= 55:
        return "mid", "partly"
    return "bad", "coin flip"


def tiers_html() -> str:
    rows = []
    for label, f, s in TIERS:
        cells = []
        for who, v, cls in (("Funds", f, "wfa"), ("Stocks", s, "wfb")):
            if v is None:
                cells.append(f'<div class="wf-bar-row"><span class="wf-who">{who}</span><span class="wf-na">not measured</span></div>')
                continue
            cells.append(
                f'<div class="wf-bar-row" title="{escape(label)} · {who}: {v}% of next-year big weeks">'
                f'<span class="wf-who">{who}</span><span class="wf-track"><i class="wf-fill {cls}" style="width:{v}%"></i>'
                f'<i class="wf-coin" style="left:{COIN}%"></i></span><b>{v}%</b></div>')
        rows.append(f'<div class="wf-tier"><div class="wf-tier-k">{escape(label)}</div>{"".join(cells)}</div>')
    return ('<div class="wf-card"><div class="wf-head"><span class="wf-k">How often each label held up</span>'
            '<span class="wf-legend"><span><i class="wfa"></i>35 funds</span><span><i class="wfb"></i>70 stocks</span>'
            '<span><i class="wf-coin-k"></i>coin flip (50%)</span></span></div>'
            f'<div class="wf-tiers">{"".join(rows)}</div>'
            '<p class="wf-note">Share of the following year&#39;s biggest weeks in which the move beyond the market went '
            'the way the reading said, measured before that year began. Three held-out years ending Nov 2024, 2025 '
            'and 2026.</p></div>')


def forces_html() -> str:
    rows = []
    for name, pct, n, kind in FORCES:
        tone, word = _tone(pct)
        extra = (' <span class="wf-flag" title="Readings of this force keep Clear only if they pass this test '
                 'themselves">must pass on new weeks</span>') if name in EXTRA_TESTED else ""
        rows.append(
            f'<div class="wf-frow" title="{escape(name)}: {pct}% over {n:,} big weeks">'
            f'<span class="wf-fname">{escape(name)}{extra}</span>'
            f'<span class="wf-track"><i class="wf-fill wf-{tone}" style="width:{pct}%"></i>'
            f'<i class="wf-coin" style="left:{COIN}%"></i></span>'
            f'<b>{pct}%</b><span class="wf-word wf-w-{tone}">{word}</span></div>')
    return ('<div class="wf-card"><div class="wf-head"><span class="wf-k">Clear readings, by force</span>'
            '<span class="wf-legend"><span><i class="wf-ok"></i>70%+ holds up</span><span><i class="wf-mid"></i>55-69%</span>'
            '<span><i class="wf-bad"></i>near a coin flip</span></span></div>'
            f'<div class="wf-forces">{"".join(rows)}</div>'
            '<p class="wf-note">Funds and stocks pooled; hover a bar for the number of big weeks tested. Forces near '
            'a coin flip (marked \u201cmust pass\u201d, or \u2731 on a small screen) are shown as Tentative unless a reading '
            'passes the same test on its own data.</p></div>')


def section_html() -> str:
    return ('<div class="wf">' + tiers_html() + forces_html() + '</div>'
            '<p class="wf-foot">From the walk-forward studies in the research record. They describe how past readings '
            'held up; it is not a forecast.</p>')


WF_CSS = """<style>
.wf{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:12px;margin:6px 0 4px;}
.wf-card{position:relative;padding:14px 16px 12px;border-radius:16px;border:1px solid rgba(148,180,210,.18);
  background:radial-gradient(120% 120% at 0% 0%,rgba(108,229,210,.07),transparent 55%),rgba(255,255,255,.025);
  -webkit-backdrop-filter:blur(14px) saturate(140%);backdrop-filter:blur(14px) saturate(140%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 18px 40px -26px rgba(0,0,0,.8);}
.wf-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:6px 12px;margin-bottom:10px;}
.wf-k{font-size:var(--uar-t-micro,.74rem);font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--ux-teal,#6ce5d2);}
.wf-legend{display:flex;flex-wrap:wrap;gap:10px;font-size:var(--uar-t-micro,.74rem);color:var(--uar-ink-2,#b7c3d4);}
.wf-legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px;}
.wf-legend .wf-coin-k{width:2px;height:12px;border-radius:1px;background:var(--uar-ink-3,#8394ab);}
.wf-tiers{display:grid;gap:10px;}
.wf-tier-k{font-size:var(--uar-t-sm,.82rem);font-weight:650;color:var(--uar-ink,#e8edf5);margin-bottom:3px;}
.wf-bar-row,.wf-frow{display:grid;align-items:center;gap:8px;font-variant-numeric:tabular-nums;}
.wf-bar-row{grid-template-columns:52px 1fr 40px;font-size:var(--uar-t-micro,.74rem);color:var(--uar-ink-3,#8394ab);}
.wf-frow{grid-template-columns:minmax(150px,1.1fr) 2fr 40px 70px;font-size:var(--uar-t-sm,.82rem);color:var(--uar-ink-2,#b7c3d4);padding:3px 0;}
.wf-bar-row b,.wf-frow b{color:var(--uar-ink,#e8edf5);text-align:right;}
.wf-track{position:relative;height:10px;border-radius:999px;background:rgba(255,255,255,.06);}
.wf-fill{position:absolute;left:0;top:0;bottom:0;border-radius:999px;}
.wf-coin{position:absolute;top:-4px;bottom:-4px;width:2px;margin-left:-1px;border-radius:1px;background:var(--uar-ink-3,#8394ab);opacity:.8;}
.wfa{background:#4a8ae6;}.wfb{background:#b97d1a;}
.wf-ok{background:linear-gradient(90deg,#35c9a4,#6ce5d2);}.wf-mid{background:#d8b66a;}.wf-bad{background:#e06c75;}
.wf-word{font-size:var(--uar-t-micro,.74rem);font-weight:650;}
.wf-w-ok{color:#35c98b;}.wf-w-mid{color:#d8b66a;}.wf-w-bad{color:#e8a0a6;}
.wf-flag{display:inline-block;margin-left:6px;padding:0 6px;border-radius:999px;border:1px solid rgba(216,182,106,.5);
  font-size:var(--uar-t-micro,.74rem);color:#d8b66a;white-space:nowrap;}
.wf-na{grid-column:2/4;font-style:italic;}
.wf-note{margin:10px 0 0;font-size:var(--uar-t-micro,.74rem);color:var(--uar-ink-3,#8394ab);line-height:1.5;}
.wf-foot{margin:4px 0 8px;font-size:var(--uar-t-micro,.74rem);color:var(--uar-ink-3,#8394ab);}
html[data-ua-theme="light"] .wf-card{background:#fff;border-color:rgba(15,23,42,.1);box-shadow:0 10px 30px -18px rgba(15,23,42,.25);}
html[data-ua-theme="light"] .wf-track{background:rgba(15,23,42,.07);}
html[data-ua-theme="light"] .wfa{background:#2f6fd0;}html[data-ua-theme="light"] .wfb{background:#b9770e;}
html[data-ua-theme="light"] .wf-ok{background:linear-gradient(90deg,#0b6f64,#14a38b);}
html[data-ua-theme="light"] .wf-w-ok{color:#0b7a55;}html[data-ua-theme="light"] .wf-w-mid{color:#8a6a12;}html[data-ua-theme="light"] .wf-w-bad{color:#b3323d;}
html[data-ua-theme="light"] .wf-flag{color:#8a6a12;border-color:rgba(138,106,18,.45);}
@media (max-width:900px){.wf{grid-template-columns:1fr;}.wf-frow{grid-template-columns:minmax(110px,1fr) 1.4fr 36px;}.wf-word{display:none;}
  .wf-flag{font-size:0;padding:0;border:0;margin-left:4px;}.wf-flag::after{content:"✱";font-size:var(--uar-t-micro,.74rem);}}
</style>"""
