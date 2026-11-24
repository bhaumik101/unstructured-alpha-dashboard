# utils/report_ui.py
# Unstructured Alpha — presentation for the exposure report
#
# The pages stay thin: everything a user reads is built here as escaped HTML or
# plain text by pure functions, so the wording is testable without a browser.
# Numbers come only from utils/exposure.py; nothing here computes a statistic.

from __future__ import annotations

import csv
import io
import math
import re
from datetime import datetime
from html import escape
from typing import Iterable, List, Optional, Tuple

from urllib.parse import quote

import streamlit as st

from utils import exposure as ex

SAMPLE_KEYS = {
    "balanced": "Balanced ETF portfolio",
    "income": "Retirement income",
    "growth": "Concentrated growth stocks",
}
SINGLE_STOCKS = (
    ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "Nvidia"), ("JPM", "JPMorgan Chase"),
    ("XOM", "Exxon Mobil"), ("CAT", "Caterpillar"), ("KO", "Coca-Cola"), ("PG", "Procter & Gamble"),
)
FREE_MAX_HOLDINGS = 15
PRO_MAX_HOLDINGS = ex.MAX_HOLDINGS
FACTOR_BY_KEY = {f.key: f for f in ex.FACTORS}
FACTOR_COLORS = {"rates": "#3b7ddd", "inflation": "#e0664a", "dollar": "#1a9a70",
                 "oil": "#d99018", "credit": "#7c5ce0", "growth": "#1497b0"}

# The identity colours above are chosen for dots, borders and map lines, where
# only 3:1 against the background is required. Set behind WHITE TEXT they fail
# WCAG AA: measured, #3b7ddd gives 4.07:1 and #1a9a70 gives 3.54:1 against
# white, and the matrix pills are 13px, so the large-text allowance does not
# apply. These are the same hues darkened until white clears 4.5:1 in either
# theme, and the outline colour is the one that clears 4.5:1 as TEXT — which
# differs by theme, so it has to be a variable rather than an inline style.
FACTOR_FILL = {"rates": "#1f5fae", "inflation": "#b5442a", "dollar": "#0f7a54",
               "oil": "#8a5a06", "credit": "#6344c9", "growth": "#0e6f84"}
FACTOR_INK_DARK = {"rates": "#6fa4ec", "inflation": "#ef9179", "dollar": "#4fc79b",
                   "oil": "#eab54f", "credit": "#a893f0", "growth": "#55c3d8"}

GENERIC_ERROR = ("Something went wrong while measuring this portfolio. Nothing has been "
                 "estimated in its place; please try again.")

REPORT_CSS = """<style>
.uar{--uar-surface:#101824;--uar-subtle:#162131;--uar-ink:#f3f6fa;--uar-ink-2:#c3cddb;
  --uar-ink-3:#a8b5c7;--uar-line:#263448;--uar-accent:#6ce5d2;--uar-bar:#c9d6e8;--uar-bar-soft:rgba(201,214,232,.42);--uar-pos:#5a8fd4;--uar-neg:#c9822f;--uar-pos-ink:#7fb2ec;--uar-neg-ink:#e9a35a;
  --uar-sky:#11262a;--uar-shadow:rgba(0,0,0,.45);
  --uar-t-micro:.74rem;--uar-t-meta:.78rem;--uar-t-sm:.82rem;--uar-t-body:.88rem;
  --uar-t-price:1.8rem;--uar-t-lead:1.18rem;--uar-t-val:1.02rem;--uar-t-ws:1.6rem;
  font-family:Inter,"SF Pro Text","Segoe UI",system-ui,-apple-system,sans-serif;
  font-variant-numeric:tabular-nums;color:var(--uar-ink);}
html[data-ua-theme="light"] .uar{--uar-surface:#ffffff;--uar-subtle:#eef2f7;--uar-ink:#152033;
  --uar-ink-2:#3d4a5f;--uar-ink-3:#526176;--uar-line:#dce3ec;--uar-accent:#0b6f64;--uar-pos:#2563a8;
  --uar-neg:#c26a0a;--uar-pos-ink:#2563a8;--uar-neg-ink:#a8580a;--uar-sky:#e7f5f2;--uar-shadow:rgba(13,34,59,.35);
  --uar-bar:#3d5677;--uar-bar-soft:rgba(61,86,119,.38);}
/* Links inside report surfaces take the report's own accent. Left to the
   old skin they rendered #3d9df3 on the light page background — 2.64:1,
   a real AA failure on the footer of every one of these pages, and it was
   invisible until the global stylesheet was actually loading locally. */
.uar a{color:var(--uar-accent);}
.uar-strip{display:none;}
.uar-dot{display:inline-block;width:12px;height:12px;border-radius:4px;margin-right:9px;vertical-align:0;}
.uar-card{background:var(--uar-surface);border:1px solid var(--uar-line);border-radius:14px;
  overflow:hidden;margin:6px 0 18px;box-shadow:none;}
.uar-head{padding:16px 20px;border-bottom:1px solid var(--uar-line);display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 20px;}
.uar-title{font-size:1.02rem;font-weight:650;color:var(--uar-ink);}
.uar-sub{font-size:.84rem;color:var(--uar-ink-3);line-height:1.5;}
.uar-lead{font-size:1.02rem;color:var(--uar-ink-2);line-height:1.65;margin:2px 0 10px;}
.uar-body{padding:14px 20px;}
.uar-row{display:grid;grid-template-columns:minmax(150px,1.1fr) minmax(140px,1.2fr) 150px minmax(160px,1fr);
  gap:14px;align-items:center;padding:14px 20px;border-bottom:1px solid var(--uar-line);}
.uar-row:last-child{border-bottom:0;}
.uar-label{font-weight:600;font-size:.95rem;color:var(--uar-ink);}
.uar-shock{font-size:.78rem;color:var(--uar-ink-3);line-height:1.4;}
.uar-val{font-weight:650;font-size:.95rem;color:var(--uar-ink);}
.uar-range{font-size:.78rem;color:var(--uar-ink-3);}
.uar-bar{position:relative;height:22px;}
.uar-axis{position:absolute;left:50%;top:-4px;bottom:-4px;width:1px;background:var(--uar-bar-soft);}
.uar-fill{position:absolute;top:6px;height:10px;border-radius:2px;background:var(--uar-bar);}
.uar-fill-tent{background:var(--uar-bar-soft);}
.uar-fill-zero{background:transparent;box-shadow:inset 0 0 0 1px var(--uar-bar-soft);}
.uar-whisker{position:absolute;top:10.5px;height:1px;background:var(--uar-bar);opacity:.8;}
.uar-whisker::before,.uar-whisker::after{content:"";position:absolute;top:-3.5px;width:1px;height:8px;background:inherit;}
.uar-whisker::before{left:0;}.uar-whisker::after{right:0;}
.uar-chip{display:inline-flex;align-items:center;gap:6px;align-self:flex-start;font-size:.72rem;font-weight:600;padding:3px 8px;border-radius:6px;
  border:1px solid var(--uar-line);color:var(--uar-ink-2);white-space:nowrap;line-height:1.3;}
.uar-chip i{width:7px;height:7px;border-radius:50%;flex:none;box-shadow:inset 0 0 0 1px currentColor;}
.uar-chip-clear i{background:currentColor;}
.uar-chip-tentative i{background:linear-gradient(90deg,currentColor 50%,transparent 50%);}
.uar-chip-nodata{border-style:dashed;}.uar-chip-nodata i{display:none;}
.uar-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;}
.uar-chip-clear{background:rgba(108,229,210,.12);border-color:rgba(108,229,210,.4);color:#8eebdc;}
html[data-ua-theme="light"] .uar-chip-clear{background:#ddf5f1;border-color:#a6e0d6;color:#0b6458;}
.uar-chip-tentative{background:rgba(217,144,24,.16);border-color:rgba(217,144,24,.5);color:#f0bb62;}
html[data-ua-theme="light"] .uar-chip-tentative{background:#fdefd6;border-color:#f1cf95;color:#8a4f00;}
.uar-driver{font-size:.8rem;color:var(--uar-ink-3);margin-top:4px;}
.uar-held{font-size:.8rem;color:var(--uar-ink-2);margin-top:4px;}
.uar-foot{padding:12px 20px;background:var(--uar-subtle);font-size:.8rem;color:var(--uar-ink-3);line-height:1.55;}
.uar-legend{display:flex;flex-wrap:wrap;gap:14px;font-size:.78rem;color:var(--uar-ink-3);align-items:center;}
.uar-sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px;}
.uar-scroll{overflow-x:auto;}
/* Long measures are the single most common readability failure on wide screens:
   the report's own copy is capped, and so is any markdown these pages emit. */
.uar-lead,.uar-sub,.uar-note{max-width:76ch;}
.stApp [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stMarkdownContainer"] li{max-width:76ch;}
/* Section rhythm: a hairline above each section heading instead of headings
   floating in whitespace. */
.stApp [data-testid="stMarkdownContainer"] h2{border-top:1px solid var(--uar-line);
  padding-top:20px;margin-top:30px;font-size:1.02rem;letter-spacing:-0.01em;}
/* The three sample portfolios are the main thing to click on an empty report,
   and rendered as bare buttons they read as secondary chrome. */
.uar-samples{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:6px 0 4px;}
.uar-sample{background:var(--uar-surface);border:1px solid var(--uar-line);border-radius:16px;
  padding:16px 18px 14px;box-shadow:0 18px 38px -32px var(--uar-shadow);height:100%;}
.uar-sample-strip{display:none;}
.uar-sample-name{font-weight:650;font-size:.95rem;color:var(--uar-ink);}
.uar-sample-holds{font-size:.78rem;color:var(--uar-ink-3);margin-top:4px;line-height:1.5;}
@media (max-width:760px){.uar-samples{grid-template-columns:1fr;}}
@media (min-width:761px){.uar-tier{min-height:430px;}}
/* Pricing cards, as on the landing page: the Advisor pilot is the featured
   tier there, so it is the featured tier here too. */
/* .uar-card clips its children so the strip and head corners stay round;
   the badge deliberately hangs over the top edge, so this one does not. */
.uar-tier{position:relative;display:flex;flex-direction:column;overflow:visible;}
.uar-tier-name{font-weight:700;font-size:var(--uar-t-sm);color:var(--uar-accent);
  text-transform:uppercase;letter-spacing:.04em;}
.uar-tier-price{font-size:var(--uar-t-price);font-weight:750;letter-spacing:-0.02em;
  margin:6px 0 2px;color:var(--uar-ink);}
.uar-tier-list{margin:14px 0 0;padding:0;list-style:none;}
.uar-tier-list li{font-size:var(--uar-t-body);color:var(--uar-ink-2);padding:5px 0 5px 20px;
  position:relative;line-height:1.5;}
.uar-tier-list li::before{content:"";position:absolute;left:2px;top:12px;width:8px;height:8px;
  border-radius:50%;background:#0f7a54;}
.uar-tier-kicker{margin-top:12px;font-weight:700;letter-spacing:.04em;}
.uar-tier-later li{color:var(--uar-ink-3);}
.uar-tier-feature{background:linear-gradient(160deg,#0d223b,#15375d);border-color:transparent;
  color:#eef3fa;margin-top:16px;}
.uar-tier-feature .uar-body{padding-top:20px;}
.uar-tier-feature .uar-tier-name{color:#ffc24b!important;}
.uar-tier-feature .uar-tier-price{color:#ffffff!important;}
.uar-tier-feature .uar-sub,.uar-tier-feature .uar-tier-list li{color:rgba(238,243,250,.88)!important;}
.uar-tier-feature .uar-tier-list li::before{background:#ffc24b;}
.uar-tier-badge{position:absolute;top:-11px;left:24px;background:#ffc24b;color:#13213a;
  font-size:var(--uar-t-micro);font-weight:750;padding:4px 12px;border-radius:999px;}
.uar-table{width:100%;border-collapse:collapse;font-size:.88rem;}
.uar-table th{text-align:left;font-weight:600;color:var(--uar-ink-3);font-size:.74rem;padding:8px 12px;border-bottom:1px solid var(--uar-line);white-space:nowrap;}
.uar-table td{padding:9px 12px;border-bottom:1px solid var(--uar-line);color:var(--uar-ink-2);}
.uar-table tr:last-child td{border-bottom:0;}
/* Search results and the draft list. Rows are 44px tall so the Add and Remove
   buttons beside them line up without a wrapper grid. */
.uar-hit{display:flex;align-items:center;gap:10px;min-height:44px;padding:4px 2px;
  border-bottom:1px solid var(--uar-line);}
.uar-hit-row{border-bottom:0;}
.uar-hit-tick{font-weight:700;color:var(--uar-ink);min-width:66px;}
.uar-hit-kind{font-size:var(--uar-t-micro);font-weight:700;color:#fff;border-radius:999px;
  padding:2px 8px;white-space:nowrap;}
.uar-hit-name{color:var(--uar-ink-2);font-size:var(--uar-t-body);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;}
.uar-hit-where{color:var(--uar-ink-3);font-size:var(--uar-t-meta);margin-left:auto;
  white-space:nowrap;}
.uar-hold-head{display:grid;grid-template-columns:3.4fr 1.5fr 1.5fr .9fr;gap:8px;
  font-size:var(--uar-t-micro);font-weight:650;color:var(--uar-ink-3);text-transform:uppercase;
  letter-spacing:.05em;padding:14px 2px 6px;border-bottom:1px solid var(--uar-line);
  margin-top:8px;}
.uar-hold-val{min-height:44px;display:flex;flex-direction:column;justify-content:center;
  font-size:var(--uar-t-body);color:var(--uar-ink-2);}
.uar-hold-sub{font-size:var(--uar-t-meta);color:var(--uar-ink-3);}
.uar-hold-muted{color:var(--uar-ink-3);}
.uar-hold-warn{color:var(--uar-neg-ink);font-weight:600;}
.uar-hold-total{margin-top:10px;padding-top:10px;border-top:1px solid var(--uar-line);
  font-size:var(--uar-t-meta);color:var(--uar-ink-3);}
@media (max-width:760px){.uar-hold-head{display:none;}}
.uar-draft-head{font-weight:650;color:var(--uar-ink);margin:16px 0 2px;
  padding-top:14px;border-top:1px solid var(--uar-line);}
/* Every holding on one grid: the old per-stock research pages, rebuilt around
   what we can actually measure. One row per holding, one column per force. */
.uar-matrix{width:100%;border-collapse:separate;border-spacing:0;font-size:var(--uar-t-body);}
.uar-matrix th{text-align:center;font-weight:650;font-size:var(--uar-t-micro);padding:9px 10px;
  border-bottom:1px solid var(--uar-line);white-space:nowrap;color:var(--uar-ink-2);}
.uar-matrix th.uar-m-name,.uar-matrix td.uar-m-name{text-align:left;position:sticky;left:0;
  background:var(--uar-surface);z-index:1;}
.uar-matrix th .uar-dot{width:9px;height:9px;border-radius:3px;margin:0 6px 0 0;}
.uar-matrix td{padding:10px;border-bottom:1px solid var(--uar-line);text-align:center;
  color:var(--uar-ink-2);}
.uar-matrix tr:last-child td{border-bottom:0;}
.uar-matrix tbody tr:hover td{background:var(--uar-sky);}
.uar-matrix tbody tr:hover td.uar-m-name{background:var(--uar-sky);}
.uar-m-tick{font-weight:700;color:var(--uar-ink);}
.uar-m-weight{font-size:var(--uar-t-meta);color:var(--uar-ink-3);margin-top:1px;}
.uar-m-val{display:inline-block;padding:3px 9px;border-radius:999px;font-weight:650;
  font-size:var(--uar-t-sm);line-height:1.35;}
.uar-m-clear{color:#fff;}
.uar-m-tent{background:transparent;}
.uar-m-zero{color:var(--uar-ink-3);font-weight:500;}
.uar-heat td.uar-hm{padding:11px 10px;border-bottom:2px solid var(--uar-surface);border-right:2px solid var(--uar-surface);}
.uar-hm-v{font-weight:650;color:var(--uar-ink);font-variant-numeric:tabular-nums;}
.uar-hm-total th,.uar-hm-total td{border-bottom:2px solid var(--uar-ink-3)!important;}
.uar-heat tbody tr:hover td.uar-hm{filter:brightness(0.97);}
.uar-hm-legend{display:flex;flex-wrap:wrap;align-items:center;gap:6px 6px;padding:10px 20px 0;
  font-size:var(--uar-t-micro);color:var(--uar-ink-3);}
.uar-hm-key{display:inline-block;width:18px;height:12px;border-radius:2px;}
.uar-hm-mid{display:inline-block;width:1px;height:14px;background:var(--uar-ink-3);margin:0 2px;}
.uar-hm-sep{display:inline-block;width:14px;}
.uar-hm-tentkey{outline:1.5px dashed var(--uar-ink-3);outline-offset:-2px;}
/* Saved-portfolio cards on the portfolios page. */
.uar-pcard{background:var(--uar-surface);border:1px solid var(--uar-line);border-radius:16px;
  padding:16px 18px 14px;box-shadow:0 18px 38px -32px var(--uar-shadow);min-height:230px;}
.uar-pcard .uar-sample-strip{margin:-16px -18px 13px;border-radius:16px 16px 0 0;}
.uar-pcard-name{font-weight:700;color:var(--uar-ink);font-size:var(--uar-t-body);}
.uar-pchips{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 8px;}
.uar-pchip{display:inline-flex;align-items:center;gap:2px;padding:3px 10px;border-radius:999px;
  border:1px solid var(--uar-line);background:var(--uar-subtle);font-size:var(--uar-t-meta);
  color:var(--uar-ink-2);}
.uar-pchip .uar-dot{width:8px;height:8px;margin-right:6px;}
.uar-pchip b{margin-left:4px;color:var(--uar-ink);}
.uar-pcard-spark{margin:6px 0 8px;}
.uar-pcard-empty{margin-top:14px;color:var(--uar-ink-3);font-size:var(--uar-t-body);}
.uar-note{border-left:3px solid var(--uar-line);padding:8px 14px;color:var(--uar-ink-2);font-size:.88rem;margin:10px 0;line-height:1.55;}
.uar-note-warn{border-left-color:var(--uar-neg);}
.uar-note-back{border-left-color:var(--uar-accent);background:var(--uar-sky);border-radius:0 10px 10px 0;}
.uar-note-back a{color:var(--uar-accent);font-weight:650;}
.uar-error{border:1px solid var(--uar-neg);border-radius:12px;padding:16px 20px;margin:8px 0 16px;color:var(--uar-ink-2);background:var(--uar-surface);}
.uar-error b{color:var(--uar-ink);}
.uar-kicker{font-size:.8rem;font-weight:600;color:var(--uar-accent);margin-bottom:4px;}
.uar-map{width:100%;max-width:520px;height:auto;display:block;margin:4px auto 10px;}
.uar-map-label{fill:var(--uar-ink);font-size:.88rem;font-weight:600;}
.uar-map-value{fill:var(--uar-ink-3);font-size:.8rem;}
.uar-map-core{fill:var(--uar-ink);font-size:1.02rem;font-weight:700;}
@media print{
  .ua-topnav,.st-key-ua_account_row,[data-testid="stButton"],[data-testid="stRadio"],
  [data-testid="stExpander"],[data-testid="stCode"],.ua-scroll-top,#ua-scroll-top{display:none!important;}
  .uar{--uar-surface:#fff;--uar-subtle:#f6f7f9;--uar-ink:#14171f;--uar-ink-2:#3a4152;
       --uar-ink-3:#596070;--uar-line:#d8dbe2;}
  .uar-card{break-inside:avoid;page-break-inside:avoid;box-shadow:none;}
  .uar-map{max-width:420px;}
  a[href]:after{content:"";}
}
@media (max-width:760px){
  .uar-row{grid-template-columns:1fr auto;gap:6px 12px;}
  .uar-row .uar-bar{grid-column:1/-1;order:3;}
  .uar-row .uar-rowdriver{grid-column:1/-1;order:4;}
}

/* ── the answer first (takeaway_html) ─────────────────────────────────── */
.uar-take{margin:20px 0 18px;}
.uar-take-lead{font-size:var(--uar-t-lead);line-height:1.5;color:var(--uar-ink);margin:0;max-width:72ch;letter-spacing:-0.005em;}
.uar-take-lead b{font-weight:650;}
.uar-take-rest{font-size:var(--uar-t-body);color:var(--uar-ink-3);margin:6px 0 0;max-width:90ch;}
/* ── the main exposure view (exposure_table_html) ─────────────────────── */
.uar-xrow{display:grid;grid-template-columns:minmax(150px,1.3fr) minmax(120px,1.45fr) 76px 132px 128px minmax(96px,.9fr);
  gap:14px;align-items:center;padding:14px 20px;border-top:1px solid var(--uar-line);}
.uar-xhead{border-top:0;padding-top:12px;padding-bottom:10px;font-size:var(--uar-t-micro);font-weight:600;
  letter-spacing:.05em;text-transform:uppercase;color:var(--uar-ink-3);}
.uar-xhead>div{white-space:nowrap;}
.uar-xaxis{display:flex;justify-content:space-between;text-transform:none;letter-spacing:0;font-variant-numeric:tabular-nums;}
.uar-xforce{display:flex;align-items:flex-start;gap:10px;min-width:0;}
.uar-xforce .uar-dot{width:8px;height:8px;border-radius:50%;margin:7px 0 0;flex:none;}
.uar-xnum{text-align:right;font-variant-numeric:tabular-nums;}
.uar-xrow .uar-val{font-size:var(--uar-t-val);font-weight:700;}
.uar-xrow .uar-range{white-space:nowrap;}
.uar-xrow .uar-driver{margin:0;}
.uar-xlab{display:none;}
.uar-xkey{display:flex;flex-wrap:wrap;gap:6px 18px;padding:12px 20px;border-top:1px solid var(--uar-line);
  font-size:var(--uar-t-meta);color:var(--uar-ink-3);}
.uar-xkey span{display:inline-flex;align-items:center;gap:7px;}
.uar-k{display:inline-block;width:16px;height:8px;border-radius:2px;}
.uar-k-clear{background:var(--uar-bar);}.uar-k-tent{background:var(--uar-bar-soft);}
.uar-k-zero{box-shadow:inset 0 0 0 1px var(--uar-bar-soft);}
.uar-k-range{height:1px;background:var(--uar-bar);position:relative;}
.uar-xheld{padding:0 20px 12px;font-size:var(--uar-t-meta);color:var(--uar-ink-3);line-height:1.55;}
.uar-xheld b{color:var(--uar-ink-2);}
@media (max-width:900px){
  .uar-xrow{grid-template-columns:minmax(0,1fr) auto;gap:6px 14px;padding:14px 16px;}
  .uar-xhead{display:none;}
  .uar-xrow .uar-xbar{grid-column:1/-1;order:3;}
  .uar-xrow .uar-range{grid-column:1;order:4;text-align:left;}
  .uar-xrow .uar-xev{grid-column:2;order:5;justify-self:end;}
  .uar-xrow .uar-xhold{grid-column:1/-1;order:6;}
  .uar-xlab{display:inline;color:var(--uar-ink-3);}
}

/* ── workspace header, skeleton, window note ───────────────────────────── */
.uar-ws{padding:4px 0 2px;}
.uar-ws-kicker{margin:0 0 4px;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:var(--uar-t-micro);
  letter-spacing:.08em;text-transform:uppercase;color:var(--uar-ink-3);}
.stApp .uar-ws h1.uar-ws-title{font-size:var(--uar-t-ws)!important;font-weight:700!important;letter-spacing:-0.02em!important;
  line-height:1.15!important;margin:0!important;padding:0!important;color:var(--uar-ink)!important;
  overflow-wrap:anywhere;}
.uar-ws-meta{margin:6px 0 0;font-size:var(--uar-t-sm);color:var(--uar-ink-3);}
.uar-ws-holdings{margin:10px 0 0;display:flex;flex-wrap:wrap;gap:6px;}
.uar-ws-holdings span{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:var(--uar-t-meta);color:var(--uar-ink-3);
  border:1px solid var(--uar-line);border-radius:6px;padding:1px 7px;}
.uar-ws-holdings b{color:var(--uar-ink);font-weight:600;margin-right:5px;}
.uar-skel .uar-sk{display:block;border-radius:6px;background:var(--uar-subtle);}
.uar-sk-msg{font-size:var(--uar-t-body);color:var(--uar-ink-3);margin:0 0 16px;}
.uar-sk-title{width:min(420px,80%);height:18px;}
.uar-sk-line{width:min(640px,95%);height:12px;margin-top:12px;}
.uar-sk-card{padding:6px 20px;margin-top:20px;}
.uar-sk-row{display:grid;grid-template-columns:1.3fr 1.6fr 64px 110px;gap:16px;align-items:center;padding:16px 0;
  border-top:1px solid var(--uar-line);}
.uar-sk-row:first-child{border-top:0;}
.uar-skel .uar-sk-row .uar-sk{height:11px;}.uar-skel .uar-sk-row .uar-sk-bar{height:8px;}
.uar-skel{animation:uar-pulse 1.6s ease-in-out infinite;}
@keyframes uar-pulse{0%,100%{opacity:1}50%{opacity:.6}}
@media (prefers-reduced-motion: reduce){.uar-skel{animation:none;}}
.uar-window{font-size:var(--uar-t-sm);color:var(--uar-ink-3);margin:-4px 0 12px;max-width:96ch;line-height:1.55;}
.uar-window-tag{display:inline-block;margin-right:10px;padding:2px 8px;border-radius:6px;border:1px solid var(--uar-line);
  color:var(--uar-ink);font-weight:600;font-size:var(--uar-t-meta);}
.uar-table-num th:nth-child(2),.uar-table-num td:nth-child(2),.uar-table-num th:nth-child(n+4),
.uar-table-num td:nth-child(n+4){text-align:right;font-variant-numeric:tabular-nums;}
.uar-table-num td:nth-child(3){white-space:nowrap;}

/* ── visuals: tiles, glyphs, flow, takeaway card ──────────────────────── */
.uar-ficon{display:inline-flex;align-items:center;justify-content:center;flex:none;border-radius:8px;
  color:var(--fc);background:color-mix(in srgb,var(--fc) 16%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--fc) 35%,transparent);}
.uar-xforce .uar-ficon{margin-top:1px;}
.uar-tiles{display:grid;grid-template-columns:1.5fr 1fr 1fr 1fr;gap:12px;margin:18px 0 4px;}
.uar-tile{border:1px solid var(--uar-line);border-radius:14px;padding:14px 16px;background:var(--uar-surface);min-width:0;}
.uar-tile-lead{display:flex;gap:14px;align-items:flex-start;position:relative;overflow:hidden;}
.uar-tile-lead::after{content:"";position:absolute;right:-60px;top:-60px;width:180px;height:180px;border-radius:50%;
  background:radial-gradient(closest-side,color-mix(in srgb,var(--uar-accent) 18%,transparent),transparent);pointer-events:none;}
.uar-tile-k{font-size:var(--uar-t-micro);text-transform:uppercase;letter-spacing:.06em;color:var(--uar-ink-3);font-weight:600;}
.uar-tile-v{font-size:var(--uar-t-lead);font-weight:700;color:var(--uar-ink);margin:4px 0 6px;letter-spacing:-.01em;font-variant-numeric:tabular-nums;}
.uar-tile-v span{color:var(--uar-ink-2);font-weight:650;margin-left:4px;}
.uar-tile-s{font-size:var(--uar-t-meta);color:var(--uar-ink-3);line-height:1.45;}
.uar-marks{display:flex;gap:6px;margin:2px 0 8px;}
.uar-mk{width:14px;height:14px;border-radius:50%;box-shadow:inset 0 0 0 1.5px var(--uar-bar);}
.uar-mk-c{background:var(--uar-bar);}
.uar-mk-t{background:linear-gradient(90deg,var(--uar-bar) 50%,transparent 50%);}
.uar-gauge{position:relative;height:8px;border-radius:4px;background:var(--uar-subtle);margin:2px 0 8px;}
.uar-gauge i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:linear-gradient(90deg,var(--uar-bar-soft),var(--uar-bar));}
.uar-gauge b{position:absolute;top:-3px;bottom:-3px;width:1.5px;background:var(--uar-ink-3);}
.uar-weeks{display:grid;grid-template-columns:repeat(39,1fr);gap:2px;margin:2px 0 8px;height:8px;}
.uar-weeks i{background:var(--uar-bar-soft);border-radius:1px;}
.uar-weeks i:nth-child(13n){background:var(--uar-bar);}
.uar-take{position:relative;padding:16px 20px;border-radius:14px;border:1px solid var(--uar-line);
  background:linear-gradient(100deg,color-mix(in srgb,var(--uar-accent) 9%,var(--uar-surface)),var(--uar-surface) 60%);}
.uar-take::before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:3px;border-radius:0 3px 3px 0;
  background:linear-gradient(180deg,var(--uar-accent),color-mix(in srgb,var(--uar-accent) 20%,transparent));}
.uar-flow{padding:16px 20px 8px;}
.uar-flow-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 16px;margin-bottom:8px;}
.uar-flow-head b{color:var(--uar-ink);font-size:var(--uar-t-body);}
.uar-flow-head span{color:var(--uar-ink-3);font-size:var(--uar-t-meta);}
.uar-flow svg{width:100%;height:auto;display:block;max-width:860px;margin:0 auto;}
.uar-rib{opacity:.55;transition:opacity .2s ease;}
.uar-ribs:hover .uar-rib{opacity:.15;}.uar-ribs .uar-rib:hover{opacity:.85;}
.uar-flow-bar{fill:var(--uar-ink-3);}
.uar-flow-t{fill:var(--uar-ink);font-weight:600;font-size:var(--uar-t-sm);font-family:ui-monospace,"SF Mono",Menlo,monospace;}
.uar-flow-l{fill:var(--uar-ink);font-size:var(--uar-t-sm);font-weight:650;}
.uar-flow-s{fill:var(--uar-ink-3);font-size:var(--uar-t-micro);}
.uar-flow-n{fill:var(--uar-ink-3);font-size:var(--uar-t-micro);font-family:inherit;}
.uar-hname{display:block;margin-top:1px;font-size:var(--uar-t-micro);font-weight:400;color:var(--uar-ink-3);line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:34ch;}
@media (prefers-reduced-motion: reduce){.uar-rib{transition:none;}}
@media (max-width:900px){.uar-tiles{grid-template-columns:1fr 1fr;}.uar-tile-lead{grid-column:1/-1;}}
@media (max-width:520px){.uar-tile{padding:12px;}.uar-tile-s{display:none;}.uar-tile-lead .uar-tile-s{display:block;}}
</style>"""


# Emitted after the sheet above so the two colour tables cannot drift: the dark
# theme is the base, light overrides only the ink.
REPORT_CSS = REPORT_CSS.replace("</style>", "".join((
    ".uar{",
    *(f"--fd-{k}:{v};" for k, v in FACTOR_FILL.items()),
    *(f"--fh-{k}:{v};" for k, v in FACTOR_INK_DARK.items()),
    "}",
    'html[data-ua-theme="light"] .uar{',
    *(f"--fh-{k}:{v};" for k, v in FACTOR_FILL.items()),
    "}\n</style>",
)))
# Group titles in the "more forces" card (extras_html).
REPORT_CSS = REPORT_CSS.replace("</style>",
    ".uar .uar-group{padding:12px 20px 4px;font-size:var(--uar-t-micro);font-weight:700;"
    "letter-spacing:.05em;text-transform:uppercase;color:var(--uar-ink-3);}"
    ".uar .uar-why{margin-top:6px;font-style:italic;}</style>")


# ── formatting ──────────────────────────────────────────────────────────────

def fmt_pct(x: Optional[float]) -> str:
    """Signed percent with a true minus sign; two decimals below 1%."""
    if x is None or not math.isfinite(x):
        return "—"
    digits = 1 if abs(x) >= 0.95 else 2
    if round(x, digits) == 0:
        return f"{0:.{digits}f}%"
    sign = "+" if x > 0 else "−"
    return f"{sign}{abs(x):.{digits}f}%"


def fmt_date(iso: Optional[str]) -> str:
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return str(iso or "")
    return f"{d:%b} {d.day}, {d.year}"


def _join(items: List[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def evidence_chip(evidence: str) -> str:
    label = ex.EVIDENCE_LABELS.get(evidence, evidence)
    cls = {"clear": " uar-chip-clear", "tentative": " uar-chip-tentative"}.get(evidence, "")
    return f'<span class="uar-chip{cls}">{escape(label)}</span>'


def _nice_scale(values: Iterable[float]) -> float:
    peak = max((abs(v) for v in values if v is not None and math.isfinite(v)), default=0.25)
    for step in (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0):
        if peak <= step:
            return step
    return math.ceil(peak / 10.0) * 10.0


def exposure_bar(impact: float, low: float, high: float, scale: float, evidence: str = "clear") -> str:
    """A diverging bar on a shared axis: the estimate from zero, the 90% range
    as a capped line. Direction is the side of zero (and the signed figure
    beside it); the fill says how strong the evidence is -- solid, lighter, or
    an outline -- so neither colour nor shape carries meaning alone, and no
    force's identity colour is borrowed for direction. Values beyond the scale
    are clipped at its edge, and the caller prints the scale."""
    def pos(v: float) -> float:
        return 50.0 + max(-scale, min(scale, v)) / scale * 50.0
    left = min(pos(0.0), pos(impact))
    width = abs(pos(impact) - pos(0.0))
    tone = {"clear": "", "tentative": " uar-fill-tent"}.get(evidence, " uar-fill-zero")
    return (f'<div class="uar-bar" aria-hidden="true"><div class="uar-axis"></div>'
            f'<div class="uar-fill{tone}" style="left:{left:.2f}%;width:{width:.2f}%;"></div>'
            f'<div class="uar-whisker" style="left:{pos(low):.2f}%;width:{pos(high) - pos(low):.2f}%;"></div></div>')


# ── holdings input ──────────────────────────────────────────────────────────

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
_TICKER_COLS = {"ticker", "symbol", "tickers", "symbols", "holding", "security id"}
_WEIGHT_COLS = {"weight", "weight_pct", "weight %", "weight (%)", "allocation", "allocation %",
                "percent", "percentage", "% of account", "% of portfolio", "portfolio %", "pct"}
_VALUE_COLS = {"market value", "value", "amount", "position value", "current value",
               "market_value", "marketvalue", "mkt val (market value)", "mkt val"}
_NOT_HOLDINGS = {"CASH", "TOTAL", "ACCOUNT", "PENDING", "--"}


def _number(value: object) -> Optional[float]:
    s = str(value or "").strip().replace("$", "").replace(",", "").rstrip("%").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        x = float(s)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def parse_holdings_text(text: str) -> Tuple[List[dict], List[str]]:
    """'VTI 40' / 'VTI, 40%' / 'VTI' per line. Returns (rows, rejected lines)."""
    rows, rejected = [], []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p for p in re.split(r"[,\t ]+", line) if p]
        ticker = parts[0].upper().lstrip("$")
        weight = _number(parts[1]) if len(parts) > 1 else None
        if not _TICKER_RE.match(ticker) or (len(parts) > 1 and weight is None):
            rejected.append(line)
            continue
        rows.append({"ticker": ticker, "weight_pct": weight})
    return rows, rejected


def parse_holdings_csv(data: bytes) -> Tuple[List[dict], List[str]]:
    """A CSV with a ticker/symbol column and an optional weight or value column.

    Brokerage exports often put account details above the real header, so the
    header is the first row (within the first 15) that names a ticker column.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    table = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not table:
        return [], ["The file is empty."]

    header_at = next((i for i, r in enumerate(table[:15])
                      if any(c.strip().lower() in _TICKER_COLS for c in r)), None)
    if header_at is None:
        return [], ["No ticker column found. Add a header row with a column named Ticker or Symbol."]
    header = [c.strip().lower() for c in table[header_at]]

    def find(names: set) -> Optional[int]:
        return next((i for i, h in enumerate(header) if h in names), None)

    t_col = find(_TICKER_COLS)
    w_col = find(_WEIGHT_COLS)
    v_col = find(_VALUE_COLS) if w_col is None else None
    amount_col = w_col if w_col is not None else v_col

    rows, rejected = [], []
    for line_no, r in enumerate(table[header_at + 1:], start=header_at + 2):
        raw = r[t_col].strip().upper().lstrip("$") if t_col < len(r) else ""
        if not raw or any(raw.startswith(x) for x in _NOT_HOLDINGS):
            continue
        if not _TICKER_RE.match(raw):
            rejected.append(f"Row {line_no}: {raw[:24]}")
            continue
        amount = _number(r[amount_col]) if amount_col is not None and amount_col < len(r) else None
        if amount is not None and amount <= 0:
            rejected.append(f"Row {line_no}: {raw} has no positive weight or value")
            continue
        rows.append({"ticker": raw, "weight_pct": amount})
    return rows, rejected


HOLDINGS_PARAM = "h"
APP_BASE = "https://app.unstructuredalpha.com"


def holdings_param(rows: Iterable[dict]) -> str:
    """'VTI:40,BND:30' — a portfolio small enough to live in a link.

    Outreach and sharing both need one URL that opens a finished report, with
    no account and no upload. Weights are rounded to one decimal: the extra
    precision changes nothing a reader sees and makes links unreadable.
    """
    parts = []
    for r in rows or []:
        weight = r.get("weight_pct")
        parts.append(f"{r['ticker']}:{round(float(weight), 1):g}" if weight else str(r["ticker"]))
    return ",".join(parts)


def parse_holdings_param(value: str) -> List[dict]:
    """The inverse. Anything malformed is dropped, never guessed at."""
    rows: List[dict] = []
    for chunk in str(value or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        ticker, _, weight = chunk.partition(":")
        ticker = ticker.strip().upper().lstrip("$")
        if not _TICKER_RE.match(ticker):
            continue
        rows.append({"ticker": ticker, "weight_pct": _number(weight) if weight else None})
    return rows


def share_url(rows: Iterable[dict], app_base: str = APP_BASE) -> str:
    return f"{app_base}/?{HOLDINGS_PARAM}={quote(holdings_param(rows))}"


def holdings_to_text(rows: Iterable[dict]) -> str:
    out = []
    for r in rows or []:
        w = r.get("weight_pct")
        out.append(f"{r['ticker']} {round(float(w), 2):g}" if w else str(r["ticker"]))
    return "\n".join(out)


def prepare_holdings(rows: Iterable[dict], max_holdings: int):
    """(cache key, cleaning notes). The key is the normalized, sorted portfolio."""
    positions, notes = ex.normalize_positions(rows, max_holdings)
    key = tuple(sorted((p["ticker"], round(p["weight_pct"], 4)) for p in positions))
    return key, notes


# ── data (cached; errors are never cached) ──────────────────────────────────

class _NotCacheable(Exception):
    def __init__(self, payload: dict):
        super().__init__(payload.get("message", ""))
        self.payload = payload


@st.cache_data(ttl=3600, show_spinner=False, max_entries=1)
def carry_over() -> Optional[float]:
    """The published track record's carry-over slope, or None."""
    from utils import track_record as tr

    try:
        r = tr.latest()
        return float(r["shrinkage_slope"]) if r and r.get("available") and r.get("shrinkage_slope") is not None else None
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False, max_entries=1)
def held_up() -> dict:
    """How each force's readings held up out of sample, from the newest
    published track-record run ({} when there is none)."""
    from utils import track_record as tr

    try:
        return tr.persistence(tr.latest())
    except Exception:
        return {}


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=200)
def _cached_ok_report(key: tuple, max_holdings: int) -> dict:
    report = ex.build_live_report([{"ticker": t, "weight_pct": w} for t, w in key],
                                  max_holdings=max_holdings)
    if report.get("status") != "ok":
        # Raised, not returned: Streamlit does not cache exceptions, so a
        # provider outage is retried on the next request instead of being
        # served from cache for six hours.
        raise _NotCacheable(report)
    return report


def peek_report(key: tuple, max_holdings: int) -> Optional[dict]:
    """A report only if one is already stored — never a new measurement.

    The portfolios page lists every saved portfolio, and for the Advisor pilot
    that list has no limit. Measuring each one on page load would be 10-20
    seconds apiece against two providers before anything appeared, so the page
    shows what is already measured and offers a button for the rest.
    """
    try:
        from utils import report_cache

        return report_cache.get(key, max_holdings)
    except Exception:
        return None


def get_report(key: tuple, max_holdings: int) -> dict:
    """Shared cache, then this process's cache, then the engine.

    The database lookup comes first because it survives deploys and is shared
    across instances: without it every restart makes the next visitor wait ~25
    seconds for a measurement someone else already paid for.
    """
    if not key:
        return {"status": "error", "message": "Add at least one holding with a ticker symbol."}

    from utils import report_cache

    stored = report_cache.get(key, max_holdings)
    if stored is not None:
        return stored

    try:
        report = _cached_ok_report(key, max_holdings)
    except _NotCacheable as exc:
        return exc.payload
    except Exception:
        return {"status": "error", "message": GENERIC_ERROR, "retryable": True}

    report_cache.put(key, max_holdings, report)
    return report


# ── report sections ─────────────────────────────────────────────────────────

SAMPLE_BLURBS = {
    "Balanced ETF portfolio": "A classic stocks-and-bonds mix, U.S. and international.",
    "Retirement income": "Dividend payers, long bonds and utilities — an income shape.",
    "Concentrated growth stocks": "Six large technology names, deliberately concentrated.",
}


def sample_card_html(name: str) -> str:
    """The sample portfolios are the main thing to click on an empty report."""
    holdings = ex.SAMPLE_PORTFOLIOS.get(name, [])
    listing = " · ".join(f"{h['weight_pct']:g}% {h['ticker']}" for h in holdings)
    return (f'<div class="uar"><div class="uar-sample">'
            f'<div class="uar-sample-strip"></div>'
            f'<div class="uar-sample-name">{escape(name)}</div>'
            f'<div class="uar-sample-holds">{escape(SAMPLE_BLURBS.get(name, ""))}</div>'
            f'<div class="uar-sample-holds">{escape(listing)}</div></div></div>')


def ordered_keys(report: dict) -> List[str]:
    readings = report["portfolio"]["readings"]
    top = [k for k in report.get("top_exposures", []) if k in readings]
    return top + [f.key for f in ex.FACTORS if f.key in readings and f.key not in top]


def summary_text(report: dict) -> str:
    p = report["portfolio"]
    readings = p["readings"]
    clear = [ex.lower_label(readings[k]["label"]) for k in report["top_exposures"]
             if readings[k]["evidence"] == "clear"]
    tentative = [ex.lower_label(readings[k]["label"]) for k in report["top_exposures"]
                 if readings[k]["evidence"] == "tentative"]
    none = [ex.lower_label(r["label"]) for r in readings.values()
            if r["evidence"] in ("indistinct", "not_enough_data")]
    span = f"Over the {p['n_obs']} weeks to {fmt_date(p['end'])}"
    parts = []
    if clear:
        parts.append(f"clearly sensitive to {_join(clear)}")
    if tentative:
        parts.append(f"tentatively sensitive to {_join(tentative)}")
    if parts:
        text = f"{span}, this portfolio has been {' and '.join(parts)}."
    else:
        text = (f"{span}, this portfolio shows no clear sensitivity to any of the economic forces "
                f"measured, beyond its movement with the stock market.")
    if none:
        text += f" No measurable link to {_join(none)}."
    beta = p.get("market_beta_total")   # plain beta; market_beta is the joint fit's term
    if beta is not None and math.isfinite(beta):
        text += (f" It has typically moved {beta:.2f} times as much as the U.S. stock market, "
                 f"which is accounted for separately.")
    return text


def _driver_text(report: dict, key: str) -> str:
    reading = report["portfolio"]["readings"][key]
    rows = report["contributions"].get(key, [])
    if reading["evidence"] not in ("clear", "tentative") or not rows:
        return "No measurable link"
    top = rows[0]
    if top.get("share") is not None and top["share"] >= 0.5:
        return f"Mostly {top['ticker']}"
    return "Largest: " + ", ".join(r["ticker"] for r in rows[:2])


_MAP_NODES = {"rates": (260, 92), "dollar": (446, 152), "inflation": (414, 356),
              "oil": (106, 356), "credit": (74, 152)}


def exposure_map_html(report: dict) -> str:
    """The portfolio at the centre, each force around it.

    Line weight follows the measured size; a force with no clear link is a faint
    dashed line. It carries no information the table below does not — it is the
    shape of the answer, for a reader who takes in a picture faster than a table.
    """
    readings = report.get("portfolio", {}).get("readings") or {}
    drawable = [k for k in _MAP_NODES if k in readings]
    if len(drawable) < 3:
        return ""
    cx, cy = 260, 218
    peak = max((abs(readings[k]["impact"]) for k in drawable), default=1.0) or 1.0

    lines, nodes = [], []
    for key in drawable:
        x, y = _MAP_NODES[key]
        r = readings[key]
        clear = r["evidence"] in ("clear", "tentative")
        colour = FACTOR_COLORS.get(key, "#3b7ddd")
        width = 2 + 8 * min(1.0, abs(r["impact"]) / peak) if clear else 1.5
        lines.append(
            f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" stroke="{colour if clear else "var(--uar-ink-3)"}" '
            f'stroke-width="{width:.1f}" stroke-linecap="round"'
            + ('' if clear else ' stroke-dasharray="5 6" opacity="0.5"') + '></line>')
        above = y < cy - 80
        label_y = y - 56 if above else y + 48
        value_y = y - 38 if above else y + 66
        value = fmt_pct(r["impact"]) if clear else "no clear link"
        nodes.append(
            f'<g opacity="{1 if clear else 0.65}">'
            f'<circle cx="{x}" cy="{y}" r="26" fill="{colour}"></circle>'
            f'<text x="{x}" y="{label_y}" text-anchor="middle" class="uar-map-label">'
            f'{escape(r["label"])}</text>'
            f'<text x="{x}" y="{value_y}" text-anchor="middle" class="uar-map-value">{value}</text>'
            f'</g>')

    holdings = len(report.get("positions") or [])
    return (
        f'<div class="uar"><svg class="uar-map" viewBox="0 0 520 430" role="img" '
        f'aria-label="Diagram of this portfolio and the economic forces it is exposed to. '
        f'The table below gives the same figures.">'
        f'<circle cx="{cx}" cy="{cy}" r="150" fill="none" stroke="var(--uar-line)"></circle>'
        + "".join(lines)
        + f'<circle cx="{cx}" cy="{cy}" r="64" fill="var(--uar-subtle)" stroke="var(--uar-line)"></circle>'
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" class="uar-map-core">Portfolio</text>'
        f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" class="uar-map-value">'
        f'{holdings} holding{"" if holdings == 1 else "s"}</text>'
        + "".join(nodes)
        + '</svg></div>')


from utils import holding_names as hn  # noqa: E402  (display names only)


def _hname(ticker: str, n: int = 40) -> str:
    """The full name under a ticker, as a quiet second line; nothing if unknown."""
    name = hn.full_name(ticker)
    if not name:
        return ""
    return f'<span class="uar-hname" title="{escape(name)}">{escape(hn.short(name, n))}</span>'


def _main_holding(report: dict, key: str) -> Tuple[str, str]:
    """(short text, full sentence) naming the holding behind a reading."""
    reading = report["portfolio"]["readings"][key]
    rows = report["contributions"].get(key, [])
    if reading["evidence"] not in ("clear", "tentative") or not rows:
        return "—", "No measurable link"
    top = rows[0]
    if top.get("share") is not None and top["share"] >= 0.5:
        return (f'{top["ticker"]} {100 * top["share"]:.0f}%',
                f'Mostly {hn.with_name(top["ticker"])}: {100 * top["share"]:.0f}% of this exposure')
    shown = [r for r in rows[:2] if r.get("share") is not None]
    if not shown:
        return ", ".join(r["ticker"] for r in rows[:2]), "Largest: " + ", ".join(r["ticker"] for r in rows[:2])
    return (" · ".join(f'{r["ticker"]} {100 * r["share"]:.0f}%' for r in shown),
            "Largest: " + ", ".join(f'{hn.with_name(r["ticker"])}, {100 * r["share"]:.0f}%' for r in shown))


_EVIDENCE_SHORT = {"indistinct": "Not distinguishable"}


def _evidence_cell(evidence: str) -> str:
    """The chip, with a shorter word only where the full label is long; the
    full label is the tooltip and what a screen reader hears, so an uncertain
    reading is never presented as a zero."""
    label = ex.EVIDENCE_LABELS.get(evidence, evidence)
    short = _EVIDENCE_SHORT.get(evidence)
    cls = {"clear": " uar-chip-clear", "tentative": " uar-chip-tentative",
           "not_enough_data": " uar-chip-nodata"}.get(evidence, " uar-chip-zero")
    if not short:
        return f'<span class="uar-chip{cls}"><i aria-hidden="true"></i>{escape(label)}</span>'
    return (f'<span class="uar-chip{cls}" title="{escape(label)}"><i aria-hidden="true"></i>'
            f'<span aria-hidden="true">{escape(short)}</span><span class="uar-sr">{escape(label)}</span></span>')


def _top_name(report: dict, key: str) -> str:
    rows = report["contributions"].get(key, [])
    r = report["portfolio"]["readings"][key]
    if r["evidence"] in ("clear", "tentative") and rows and (rows[0].get("share") or 0) >= 0.5:
        return _hname(rows[0]["ticker"], 30)
    return ""


def takeaway_html(report: dict) -> str:
    """The answer, first: the clearest exposures and the holding behind them,
    then one quiet line for the rest. Built from the report only."""
    p = report["portfolio"]
    readings = p["readings"]
    order = ordered_keys(report)
    clear = [k for k in order if readings[k]["evidence"] == "clear"]
    tent = [k for k in order if readings[k]["evidence"] == "tentative"]
    none = [k for k in order if readings[k]["evidence"] in ("indistinct", "not_enough_data")]
    name = lambda k: escape(ex.lower_label(readings[k]["label"]))  # noqa: E731
    if clear:
        lead = f"Clearly sensitive to <b>{_join([name(k) for k in clear])}</b>."
    elif tent:
        lead = f"Tentatively sensitive to <b>{_join([name(k) for k in tent])}</b>; no clear exposure."
    else:
        lead = "No clear sensitivity to the forces measured, beyond the stock market."
    carriers = []
    for k in (clear or tent)[:2]:
        rows = report["contributions"].get(k, [])
        if rows and rows[0].get("share") is not None and rows[0]["share"] >= 0.5:
            carriers.append(f'{escape(hn.with_name(rows[0]["ticker"]))} carries {100 * rows[0]["share"]:.0f}% '
                            f'of the measured {name(k)} exposure')
    if carriers:
        lead += " " + "; ".join(carriers) + "."
    rest = []
    if clear and tent:
        rest.append(f"Tentative: {_join([name(k) for k in tent])}")
    if none:
        rest.append(f"No measurable link: {_join([name(k) for k in none])}")
    beta = p.get("market_beta_total")
    if beta is not None and math.isfinite(beta):
        rest.append(f"Moves {beta:.2f}× the U.S. stock market, which is accounted for separately")
    return ('<div class="uar uar-take"><div class="uar-take-lead">' + lead + '</div>'
            + (f'<div class="uar-take-rest">{" · ".join(rest)}.</div>' if rest else "") + '</div>')


def exposure_table_html(report: dict, held: Optional[dict] = None) -> str:
    """The main exposure view: one aligned row per force -- name and scenario,
    a diverging bar on one shared axis, the estimate, its 90% range, the
    evidence, and the holding behind it.

    held: utils.track_record.persistence() of the published study, or None.
    Its out-of-sample rates go in a supporting line under the table, not as a
    sentence repeated in every row."""
    from utils import track_record as tr

    held = held or {}
    p = report["portfolio"]
    readings = p["readings"]
    keys = ordered_keys(report)
    scale = _nice_scale([v for k in keys for v in (readings[k]["low"], readings[k]["high"])])
    rows = []
    for key in keys:
        r = readings[key]
        short, full = _main_holding(report, key)
        rows.append(
            f'<div class="uar-xrow" role="row">'
            f'<div class="uar-xforce" role="cell">{factor_icon(key)}'
            f'<div><div class="uar-label">{escape(r["label"])}</div>'
            f'<div class="uar-shock">In weeks when {escape(r["shock_phrase"])}</div></div></div>'
            f'<div role="cell" class="uar-xbar">{exposure_bar(r["impact"], r["low"], r["high"], scale, r["evidence"])}</div>'
            f'<div role="cell" class="uar-xnum uar-val">{fmt_pct(r["impact"])}</div>'
            f'<div role="cell" class="uar-xnum uar-range"><span class="uar-xlab">90% range </span>'
            f'{fmt_pct(r["low"])} to {fmt_pct(r["high"])}</div>'
            f'<div role="cell" class="uar-xev">{_evidence_cell(r["evidence"])}</div>'
            f'<div role="cell" class="uar-driver uar-xhold" title="{escape(full)}">'
            f'<span class="uar-xlab">Main holding </span>{escape(short)}{_top_name(report, key)}</div>'
            '</div>'
        )
    held_bits = [f'{escape(readings[k]["label"])} {100 * held[k]["rate"]:.0f}%'
                 for k in keys if tr.persistence_short(k, readings[k]["evidence"], held)]
    held_line = (
        '<div class="uar-xheld"><b>Track record.</b> How often Clear and Tentative readings like these held '
        'their direction a year later, out of sample (coin flip: 50%): ' + " · ".join(held_bits)
        + f'. <a href="{tr.EVIDENCE_URL}" target="_self">Held its direction a year later</a>, '
        'by force, in the published study.</div>'
    ) if held_bits else ""
    return (
        '<div class="uar"><div class="uar-card uar-xcard" role="table" aria-label="Exposure to economic forces">'
        '<div class="uar-xrow uar-xhead" role="row">'
        '<div role="columnheader">Economic force</div>'
        f'<div role="columnheader" class="uar-xaxis"><span>−{scale:g}%</span><span>0</span><span>+{scale:g}%</span></div>'
        '<div role="columnheader" class="uar-xnum">Estimate</div>'
        '<div role="columnheader" class="uar-xnum">90% range</div>'
        '<div role="columnheader">Evidence</div>'
        '<div role="columnheader">Main holding</div></div>'
        + "".join(rows) +
        '<div class="uar-xkey"><span><i class="uar-k uar-k-clear"></i>Solid bar: Clear</span>'
        '<span><i class="uar-k uar-k-tent"></i>Lighter: Tentative</span>'
        '<span><i class="uar-k uar-k-zero"></i>Outline: not distinguishable from zero (not the same as no exposure)</span>'
        f'<span><i class="uar-k uar-k-range"></i>Line: 90% range</span><span>One shared scale, ±{scale:g}%</span></div>'
        + held_line +
        f'<div class="uar-foot">Each figure is the portfolio&#39;s typical same-week move when that force '
        f'moved by the stated amount, after accounting for the stock market. Measured over '
        f'{p["n_obs"]} weeks, {escape(fmt_date(p["start"]))} to {escape(fmt_date(p["end"]))}. '
        f'It describes the past; it is not a forecast.</div>'
        '</div></div>'
    )


def extras_html(report: dict, subject: str = "portfolio") -> str:
    """The extra forces: each measured beyond the market and the core five.

    Grouped as in exposure.EXTRA_GROUPS. A report cached before extras existed
    has no "extras" key and renders nothing; a force whose data failed is
    named, never filled in.
    """
    x = report.get("extras")
    if not x:
        return ""
    readings = x.get("readings") or {}
    unavailable = x.get("unavailable") or []
    if not readings:
        if not unavailable:
            return ""
        return (f'<div class="uar"><div class="uar-note">More forces couldn&#39;t be measured: data '
                f'for {escape(_join(unavailable))} was unavailable. Nothing was estimated in its '
                f'place.</div></div>')
    scale = _nice_scale([v for r in readings.values() for v in (r["low"], r["high"])])
    body = []
    for group, title in ex.EXTRA_GROUPS.items():
        keys = [f.key for f in ex.EXTRA_FACTORS if f.group == group and f.key in readings]
        if not keys:
            continue
        body.append(f'<div class="uar-group" role="heading" aria-level="3">{escape(title)}</div>')
        for key in keys:
            r = readings[key]
            body.append(
                '<div class="uar-row">'
                f'<div><div class="uar-label">{escape(r["label"])}</div>'
                f'<div class="uar-shock">In weeks when {escape(r["shock_phrase"])}</div>'
                f'<div class="uar-shock uar-why">{escape(r["why"])}</div></div>'
                f'{exposure_bar(r["impact"], r["low"], r["high"], scale)}'
                f'<div><div class="uar-val">{fmt_pct(r["impact"])}</div>'
                f'<div class="uar-range">range {fmt_pct(r["low"])} to {fmt_pct(r["high"])}</div></div>'
                f'<div class="uar-rowdriver">{evidence_chip(r["evidence"])}</div>'
                '</div>')
    missing = (f' Data for {escape(_join(unavailable))} was unavailable, so it is not shown; '
               'nothing was estimated in its place.' if unavailable else "")
    return (
        '<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
        '<div class="uar-title">More forces, beyond the core five</div>'
        f'<div class="uar-sub">Each measured with the stock market and the five forces above held '
        f'fixed, so it shows only what they don&#39;t already explain.</div></div></div>'
        + "".join(body) +
        f'<div class="uar-foot">Each figure is the {escape(subject)}&#39;s typical same-week move when '
        f'that force moved by the stated amount, after accounting for {escape(x.get("control") or ex.CORE_CONTROL)}. '
        f'The evidence bar is stricter than for the core five: Clear needs |t| ≥ '
        f'{float(x.get("clear_t") or ex.EXTRA_CLEAR_T):.2f}, shared across every force tested, so '
        f'measuring more forces cannot manufacture more findings.{missing} It describes the past; '
        f'it is not a forecast.</div>'
        '</div></div>')


def factor_detail_html(report: dict, key: str, held: Optional[dict] = None) -> str:
    from utils import track_record as tr

    readings = report["portfolio"]["readings"]
    if key not in readings:
        return ""
    r = readings[key]
    parts = [
        f'<div class="uar"><div class="uar-card" style="border-top:4px solid {FACTOR_COLORS.get(key, "#3b7ddd")}"><div class="uar-head"><div>'
        f'<div class="uar-title"><span class="uar-dot" style="background:{FACTOR_COLORS.get(key, "#3b7ddd")}"></span>{escape(r["label"])}</div>'
        f'<div class="uar-sub">{escape(r["why"])}</div></div>{evidence_chip(r["evidence"])}</div>'
        f'<div class="uar-body"><p class="uar-lead">{escape(r["sentence"])}</p>'
        f'<div class="uar-sub">{escape(ex.EVIDENCE_EXPLAINED[r["evidence"]])} '
        f'Based on {r["n_obs"]} weeks of data.</div>'
    ]
    sentence = tr.persistence_sentence(key, r["evidence"], held or {})
    if sentence:
        parts.append(f'<div class="uar-note">{escape(sentence)} '
                     f'<a href="{tr.EVIDENCE_URL}" target="_blank" rel="noopener">How this was '
                     'measured</a></div>')
    if r.get("hard_to_separate_from"):
        parts.append(
            f'<div class="uar-note uar-note-warn">Over this period {escape(ex.lower_label(r["label"]))} moved '
            f'closely with {escape(ex.lower_label(r["hard_to_separate_from"]))}, so the two are hard to separate. '
            f'Read them together.</div>')

    rows = report["contributions"].get(key, [])
    if rows:
        body = "".join(
            f'<tr><td><b>{escape(c["ticker"])}</b>{_hname(c["ticker"])}</td><td>{c["weight_pct"]:.1f}%</td>'
            f'<td>{fmt_pct(c["impact"])} {evidence_chip(c["evidence"])}</td>'
            f'<td>{fmt_pct(c["contribution"])}</td>'
            f'<td>{"—" if c["share"] is None else f"{100 * c["share"]:.0f}%"}</td></tr>'
            for c in rows
        )
        parts.append(
            '<div class="uar-scroll" tabindex="0" role="region" aria-label="Table, scrolls sideways" style="margin-top:12px"><table class="uar-table uar-table-num">'
            '<thead><tr><th>Holding</th><th>Weight</th><th>Its own sensitivity</th>'
            '<th>Contribution</th><th>Share of total</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>'
            '<div class="uar-sub" style="margin-top:8px">A holding&#39;s contribution is its weight times '
            'its own sensitivity, and contributions add up to the portfolio figure. Holdings can offset '
            'each other, so a share can be above 100% or negative.</div>'
        )
    parts.append('</div></div></div>')
    return "".join(parts)


# ── the search-and-add builder ──────────────────────────────────────────────
# Typing tickers was the front door, and it is a real barrier: people know they
# own "the Vanguard total bond fund", not BND, and a workplace-plan statement
# lists fund names with no symbol at all. These are the pure parts of the
# builder, kept here so the weight arithmetic is testable without a browser.

def equalize(draft: List[dict]) -> List[dict]:
    """Split 100% evenly, putting the rounding remainder on the first holding.

    Weights that do not add to 100 are normalised downstream anyway, but a list
    that visibly sums to 99.9% reads as a bug on a page whose whole argument is
    that its numbers are careful.
    """
    if not draft:
        return draft
    share = round(100.0 / len(draft), 1)
    for row in draft:
        row["weight_pct"] = share
    draft[0]["weight_pct"] = round(share + (100.0 - share * len(draft)), 1)
    return draft


def add_to_draft(draft: List[dict], row: dict, max_holdings: int,
                 *, equal: bool = True) -> Tuple[List[dict], str]:
    """Add one search result. Returns (draft, message); message is "" on success.

    `equal=False` once the visitor has edited a weight: re-splitting the list
    evenly would throw away numbers they had just typed.
    """
    ticker = str(row.get("ticker") or "").strip().upper()
    if not ticker:
        return draft, "That result has no ticker symbol."
    if any(r["ticker"] == ticker for r in draft):
        return draft, f"{ticker} is already in the list."
    if len(draft) >= max_holdings:
        return draft, (f"That is the limit of {max_holdings} holdings. Remove one first, "
                       f"or measure what you have.")
    if equal:
        draft = draft + [{"ticker": ticker, "name": str(row.get("name") or ""), "weight_pct": 0.0}]
        return equalize(draft), ""

    # Weights someone typed are theirs to keep, so the rest are left exactly as
    # they are -- but arriving at 0.0 made "add a holding" do nothing at all:
    # a zero weight is dropped before measuring, and the only sign was a line
    # of small print. A new holding gets the average of what is already there,
    # which changes none of the existing PROPORTIONS, since everything is
    # rescaled to 100% before it is measured.
    existing = [float(r.get("weight_pct") or 0) for r in draft]
    positive = [w for w in existing if w > 0]
    default = round(sum(positive) / len(positive), 2) if positive else 1.0
    return draft + [{"ticker": ticker, "name": str(row.get("name") or ""),
                     "weight_pct": default}], ""


def remove_from_draft(draft: List[dict], ticker: str, *, equal: bool = True) -> List[dict]:
    kept = [r for r in draft if r["ticker"] != str(ticker).upper()]
    return equalize(kept) if equal else kept


def report_csv(report: dict, name: str = "portfolio") -> bytes:
    """The report's numbers, as a spreadsheet.

    An adviser does not read a web page into a client review; they put the
    figures next to their own. Everything here is already on the page — the
    portfolio's reading per force, then each holding's own reading and its
    contribution — so this adds no claim, only a format. The evidence label
    travels with every row on purpose: a number lifted out of here without it
    is exactly the misuse the whole report is built to prevent.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Unstructured Alpha — exposure report"])
    writer.writerow(["Portfolio", name])
    writer.writerow(["Measured through", fmt_date(report.get("as_of"))])
    portfolio = report["portfolio"]
    writer.writerow(["Window", f"{portfolio.get('n_obs', '')} weeks of weekly returns, "
                               f"{fmt_date(portfolio.get('start'))} to {fmt_date(portfolio.get('end'))}"])
    writer.writerow(["Market control", str(report.get("method", {}).get("market_control", ""))])
    writer.writerow(["Note", "Describes how this portfolio has moved. Not a forecast, "
                             "not investment advice."])
    writer.writerow([])
    writer.writerow(["Scope", "Economic force", "Holding", "Weight %", "Impact %",
                     "90% low", "90% high", "Evidence", "Contribution %", "Share of total %"])

    readings = portfolio["readings"]
    contributions = report.get("contributions") or {}
    for key in ordered_keys(report):
        reading = readings[key]
        writer.writerow(["Portfolio", reading["label"], "", 100.0,
                         _csv_num(reading.get("impact")), _csv_num(reading.get("low")),
                         _csv_num(reading.get("high")), reading.get("evidence_label", ""), "", ""])
        for row in contributions.get(key, []):
            writer.writerow(["Holding", reading["label"], row["ticker"],
                             _csv_num(row.get("weight_pct")), _csv_num(row.get("impact")),
                             "", "", ex.EVIDENCE_LABELS.get(row.get("evidence"), ""),
                             _csv_num(row.get("contribution")),
                             _csv_num(None if row.get("share") is None else 100 * row["share"])])
    return buffer.getvalue().encode("utf-8")


def _csv_num(value) -> str:
    """Plain decimals for a spreadsheet: no minus-sign typography, no percent
    sign, and an empty cell rather than the em dash the page uses."""
    if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
        return ""
    return f"{value:.4f}"


def holdings_csv(draft: List[dict], mode: str = "percent") -> bytes:
    """Just the list of holdings, in the units it was entered in.

    Not gated: someone's own holdings are their own data, and the paid part is
    the measurement, not the list. It reads back through parse_holdings_csv, so
    a portfolio can leave and come back without being retyped.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    header = ["Ticker", "Name"]
    column = {"percent": "Weight %", "amount": "Value", "shares": "Shares"}.get(mode, "Weight %")
    field = {"percent": "weight_pct", "amount": "amount", "shares": "shares"}.get(mode, "weight_pct")
    writer.writerow(header + [column])
    for row in draft or []:
        value = row.get(field)
        writer.writerow([
            str(row.get("ticker", "")).upper(),
            str(row.get("name", "") or ""),
            _csv_num(value if isinstance(value, (int, float)) else None),
        ])
    return buffer.getvalue().encode("utf-8")


def csv_filename(name: str, as_of: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "portfolio").lower()).strip("-") or "portfolio"
    return f"unstructured-alpha-{slug}-{str(as_of)[:10]}.csv"


def reopened_html() -> str:
    """Shown when the browser reopened the last portfolio by itself.

    Two things have to be said, because neither is obvious and one is about
    the visitor's data: this is YOUR last portfolio rather than a saved
    account, and it lives only in this browser. The escape hatch is a plain
    link because the forgetting happens in localStorage, which Streamlit
    cannot reach — scripts/inject_boot_splash.py handles ?fresh=1.
    """
    return ('<div class="uar"><div class="uar-note uar-note-back">'
            '<b>Reopened the portfolio you measured last time</b>, and measured it again just now. '
            'It is remembered in this browser only — nothing was sent anywhere, and no account was '
            'created. <a href="/?fresh=1" target="_self">Start fresh</a>'
            '</div></div>')


KIND_HUES = {"Stock": "#1f5fae", "ETF": "#0f7a54", "Fund": "#6344c9"}


def search_result_html(row: dict) -> str:
    """One search result: ticker, what it is, and the full name."""
    kind = str(row.get("kind") or "")
    hue = KIND_HUES.get(kind, "#5b6780")
    where = str(row.get("exchange") or "")
    return (f'<div class="uar"><div class="uar-hit">'
            f'<span class="uar-hit-tick">{escape(str(row.get("ticker", "")))}</span>'
            + (f'<span class="uar-hit-kind" style="background:{hue}">{escape(kind)}</span>' if kind else "")
            + f'<span class="uar-hit-name">{escape(str(row.get("name", "")))}</span>'
            + (f'<span class="uar-hit-where">{escape(where)}</span>' if where else "")
            + '</div></div>')


def holdings_head_html(draft: List[dict], mode: str) -> str:
    """Column headings for the holdings panel, named after the unit in use."""
    from utils import holdings as hold

    n = len(draft)
    return (f'<div class="uar"><div class="uar-hold-head">'
            f'<span>{n} holding{"" if n == 1 else "s"}</span>'
            f'<span>{escape(hold.MODE_COLUMN.get(mode, "Weight %"))}</span>'
            f'<span>{"Weight" if mode == "percent" else "Last close · value"}</span>'
            f'<span></span></div></div>')


def holding_value_html(row: dict, mode: str, prices: dict, draft: List[dict] = ()) -> str:
    """What one holding is worth, and where that number came from.

    In percent mode there is nothing to price, so it says so rather than
    printing a total the percentages cannot support. A share count with no
    price says "no recent price" — never a zero.
    """
    from utils import holdings as hold

    if mode == "percent":
        # What this row BECOMES, which is not what was typed unless the column
        # happens to add to 100. Saying "share of the portfolio" was filler.
        total = sum(float(r.get("weight_pct") or 0) for r in (draft or []))
        typed = float(row.get("weight_pct") or 0)
        if total <= 0:
            share = "—"
        else:
            share = f"{100.0 * typed / total:.1f}% of the portfolio"
        return (f'<div class="uar"><div class="uar-hold-val uar-hold-muted">'
                f'{escape(share)}</div></div>')
    ticker = str(row.get("ticker", "")).upper()
    quote = prices.get(ticker)
    value = hold.row_value(row, mode, prices)
    if mode == "shares" and not quote:
        return ('<div class="uar"><div class="uar-hold-val uar-hold-warn">'
                'no recent price</div></div>')
    detail = ""
    if mode == "shares" and quote:
        detail = (f'<span class="uar-hold-sub">{hold.fmt_money(quote["close"])} close · '
                  f'{escape(fmt_date(quote["date"]))}</span>')
    return (f'<div class="uar"><div class="uar-hold-val">{escape(hold.fmt_money(value))}'
            f'{detail}</div></div>')


def holdings_total_html(draft: List[dict], mode: str, prices: dict,
                        weights: List[dict]) -> str:
    """The line under the table: what it adds up to, and what that means."""
    from utils import holdings as hold

    total = hold.portfolio_value(draft, mode, prices)
    if mode == "percent":
        entered = draft_total(draft)
        body = (f'Weights total {entered:g}%. They are rescaled to 100% before measuring, '
                f'so rough shares are fine.')
    elif total is None:
        body = 'Nothing has an amount yet.'
    else:
        counted = len(weights)
        body = (f'{hold.fmt_money(total)} across {counted} holding{"" if counted == 1 else "s"}. '
                f'The report measures the proportions, not the size.')
    return f'<div class="uar"><div class="uar-hold-total">{body}</div></div>'


def draft_header_html(draft: List[dict]) -> str:
    n = len(draft)
    return (f'<div class="uar"><div class="uar-draft-head">'
            f'{n} holding{"" if n == 1 else "s"} ready to measure</div></div>')


def draft_row_html(row: dict) -> str:
    name = str(row.get("name") or "") or hn.full_name(str(row.get("ticker", "")))
    return (f'<div class="uar"><div class="uar-hit uar-hit-row">'
            f'<span class="uar-hit-tick">{escape(str(row.get("ticker", "")))}</span>'
            f'<span class="uar-hit-name">{escape(name)}</span></div></div>')


def draft_total(draft: List[dict]) -> float:
    return round(sum(float(r.get("weight_pct") or 0) for r in draft), 1)


# ── what a change would have done ───────────────────────────────────────────
# This is the honest form of "which stocks should I buy". It is not that, and
# it must never become that: testing found no way to predict returns from this
# data, so a list of names to buy is the one thing this product withdrew.
#
# What it CAN do is measure. Adding a holding changes what a portfolio is
# exposed to, and that change is measurable over the same three years with the
# same method. So: pick anything, and see what the past three years would have
# looked like with it in. Description, not advice — and the wording says so
# rather than leaving it implied.

CANDIDATE_EXAMPLES = (
    ("GLD", "Gold"),
    ("TLT", "Long Treasuries"),
    ("XLE", "Energy"),
    ("VNQ", "Real estate"),
    ("TIP", "Inflation-protected bonds"),
    ("BNDX", "International bonds"),
)


def blend_for_candidate(key: Tuple[Tuple[str, float], ...], ticker: str,
                        weight_pct: float) -> Tuple[Tuple[str, float], ...]:
    """The current portfolio at (100 - w)%, plus the candidate at w%.

    Everything already held keeps its proportions exactly; only the room made
    for the new holding changes. Re-uses prepare_holdings so the result is the
    same shape of cache key as any other report.
    """
    weight = max(0.1, min(float(weight_pct), 90.0))
    ticker = str(ticker).upper().strip()
    # The room is made from what is left AFTER removing any existing position
    # in the candidate. Scaling the whole portfolio by (100-w)/100 first gave
    # the candidate a smaller weight than asked for whenever it was already
    # held -- 10% GLD against a portfolio that already held GLD came out at
    # 15.6%, because dropping the old position shrank the base it was scaled
    # against and normalisation then stretched everything back up.
    rest = [(t, w) for t, w in key if t != ticker]
    rest_total = sum(w for _t, w in rest)
    if rest_total <= 0:
        return prepare_holdings([{"ticker": ticker, "weight_pct": 100.0}], ex.MAX_HOLDINGS)[0]
    scale = (100.0 - weight) / rest_total
    rows = [{"ticker": t, "weight_pct": w * scale} for t, w in rest]
    rows.append({"ticker": ticker, "weight_pct": weight})
    return prepare_holdings(rows, ex.MAX_HOLDINGS)[0]


def _comparison_rows(a: dict, b: dict) -> List[str]:
    """One row per force: A, B and the difference between them.

    A row is only given a difference where at least one side stands on its own
    evidence. Subtracting two numbers that are both indistinguishable from zero
    produces a third number that is also noise, and printing it would invite
    exactly the reading this report exists to prevent.
    """
    a_readings = a.get("portfolio", {}).get("readings", {})
    b_readings = b.get("portfolio", {}).get("readings", {})
    rows = []
    for key in [k for k in ordered_keys(a) if k in b_readings]:
        left, right = a_readings[key], b_readings[key]
        if {left["evidence"], right["evidence"]} & {"clear", "tentative"}:
            delta = f'<b>{fmt_pct(right["impact"] - left["impact"])}</b>'
        else:
            delta = '<span class="uar-hold-muted">no measurable link either way</span>'
        rows.append(
            f'<tr><td><span class="uar-dot" style="background:'
            f'{FACTOR_COLORS.get(key, "#3b7ddd")}"></span><b>{escape(left["label"])}</b></td>'
            f'<td>{fmt_pct(left["impact"])} {evidence_chip(left["evidence"])}</td>'
            f'<td>{fmt_pct(right["impact"])} {evidence_chip(right["evidence"])}</td>'
            f'<td>{delta}</td></tr>')
    return rows


_COMPARE_FOOT = ('<div class="uar-foot">A difference is only shown where at least one side '
                 'could be told apart from noise. Two numbers that are both indistinguishable '
                 'from zero have a difference that is also noise.</div>')


def _comparison_card(rows: List[str], title: str, sub: str, left: str, right: str) -> str:
    if not rows:
        return ""
    return (
        '<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
        f'<div class="uar-title">{title}</div><div class="uar-sub">{sub}</div></div></div>'
        '<div class="uar-scroll" tabindex="0" role="region" aria-label="Table, scrolls sideways"><table class="uar-table"><thead><tr>'
        f'<th>Economic force</th><th>{left}</th><th>{right}</th><th>Difference</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        f'{_COMPARE_FOOT}</div></div>')


def candidate_delta_html(base: dict, after: dict, ticker: str, weight_pct: float) -> str:
    """Side by side: every force, before and after adding one holding."""
    share, tick = f"{weight_pct:g}%", escape(ticker.upper())
    return _comparison_card(
        _comparison_rows(base, after),
        f"The same three years, with {share} {tick}",
        f"Everything already held keeps its proportions; the {share} is made from the rest. "
        f"This is what the past three years would have measured with {tick} in the portfolio "
        f"— it is not a forecast, and it is not a suggestion to hold it.",
        "This portfolio", f"With {share} {tick}")


def comparison_html(a: dict, b: dict, name_a: str, name_b: str) -> str:
    """Two whole portfolios, measured the same way over the same weeks."""
    left, right = escape(name_a or "Portfolio A"), escape(name_b or "Portfolio B")
    return _comparison_card(
        _comparison_rows(a, b),
        f"{left} against {right}",
        "Both measured with the same method over the same three years of weekly returns. "
        "The difference is what separates them; it describes the past, and it is not a "
        "forecast.",
        left, right)


def holdings_diff_html(key_a: Tuple[Tuple[str, float], ...], key_b: Tuple[Tuple[str, float], ...],
                       name_a: str, name_b: str) -> str:
    """What is in one and not the other, and what moved between them.

    An adviser comparing "current" with "proposed" wants the trade list as much
    as the exposure change: the table above says what the move does, this says
    what the move is.
    """
    a, b = dict(key_a), dict(key_b)
    tickers = sorted(set(a) | set(b), key=lambda t: -(abs(b.get(t, 0) - a.get(t, 0))))
    rows = []
    for t in tickers:
        wa, wb = a.get(t), b.get(t)
        if wa is None:
            change, tag = f"+{wb:.1f} pts", '<span class="uar-chip uar-chip-clear">added</span>'
        elif wb is None:
            change, tag = f"−{wa:.1f} pts", '<span class="uar-chip uar-chip-tentative">removed</span>'
        else:
            diff = wb - wa
            if abs(diff) < 0.05:
                continue
            change = f"{'+' if diff > 0 else '−'}{abs(diff):.1f} pts"
            tag = ""
        rows.append(
            f'<tr><td><b>{escape(t)}</b> {tag}{_hname(t)}</td>'
            f'<td>{"—" if wa is None else f"{wa:.1f}%"}</td>'
            f'<td>{"—" if wb is None else f"{wb:.1f}%"}</td><td>{change}</td></tr>')
    if not rows:
        return ('<div class="uar"><div class="uar-note">The two portfolios hold the same things '
                'in the same weights.</div></div>')
    left, right = escape(name_a or "Portfolio A"), escape(name_b or "Portfolio B")
    return (
        '<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
        f'<div class="uar-title">What is different between them</div>'
        f'<div class="uar-sub">Largest changes first. Weights are each portfolio&#39;s share '
        f'after rescaling to 100%.</div></div></div>'
        '<div class="uar-scroll" tabindex="0" role="region" aria-label="Table, scrolls sideways"><table class="uar-table"><thead><tr>'
        f'<th>Holding</th><th>{left}</th><th>{right}</th><th>Change</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div></div></div>')


def portfolio_card_html(name: str, n_holdings: int, updated: str,
                        report: Optional[dict]) -> str:
    """One saved portfolio at a glance: its strongest readings and their drift.

    Only exposures that stand on their own evidence are shown as chips — a
    card that led with a "not distinguishable from zero" number would be
    headlining noise. The sparkline is the strongest exposure's rolling year,
    the same series the report charts, so the card and the report agree.
    """
    from utils import report_charts as charts

    head = (f'<div class="uar-pcard-name">{escape(name)}</div>'
            f'<div class="uar-sub">{n_holdings} holding{"" if n_holdings == 1 else "s"}'
            + (f' · saved {escape(fmt_date(updated))}' if updated else '') + '</div>')
    if not report or report.get("status") != "ok":
        return (f'<div class="uar"><div class="uar-pcard"><div class="uar-sample-strip"></div>'
                f'{head}<div class="uar-pcard-empty">Not measured in the last six hours. '
                f'Measure it to see its exposures.</div></div></div>')

    readings = report["portfolio"]["readings"]
    strong = [k for k in report.get("top_exposures", []) if k in readings][:3]
    if strong:
        chips = "".join(
            f'<span class="uar-pchip"><span class="uar-dot" style="background:'
            f'{FACTOR_COLORS.get(k, "#3b7ddd")}"></span>{escape(readings[k]["label"])} '
            f'<b>{fmt_pct(readings[k]["impact"])}</b></span>' for k in strong)
    else:
        chips = ('<span class="uar-sub">No exposure stood out from noise over the three '
                 'years.</span>')

    spark = ""
    lead = strong[0] if strong else None
    rolling = (report.get("rolling") or {}).get(lead) if lead else None
    if rolling and len(rolling) >= 3:
        words = (f"{readings[lead]['label']} sensitivity over rolling years, from "
                 f"{fmt_pct(rolling[0]['impact'])} to {fmt_pct(rolling[-1]['impact'])}.")
        spark = (f'<div class="uar-pcard-spark">'
                 f'{charts.sparkline_svg([p["impact"] for p in rolling], FACTOR_COLORS.get(lead, "#3b7ddd"), words)}'
                 f'<div class="uar-sub">{escape(readings[lead]["label"])}, rolling year</div></div>')

    return (f'<div class="uar"><div class="uar-pcard"><div class="uar-sample-strip"></div>'
            f'{head}<div class="uar-pchips">{chips}</div>{spark}'
            f'<div class="uar-sub">Measured through {escape(fmt_date(report.get("as_of")))}</div>'
            f'</div></div>')


# Heatmap intensity: four steps of the up/down pair mixed into the card, by how
# large a reading is against the largest on the grid. Text stays in body ink,
# so every step is checked for contrast in both themes (tests/test_report_ui.py).
HEAT_ALPHAS = (0.14, 0.24, 0.34, 0.44)


def _heat_step(value: float, largest: float) -> int:
    if largest <= 0:
        return 0
    return min(len(HEAT_ALPHAS) - 1, int(abs(value) / largest * len(HEAT_ALPHAS)))


def _heat_cell(impact: float, evidence: str, largest: float, say: str) -> str:
    if evidence not in ("clear", "tentative"):
        return (f'<td class="uar-hm uar-hm-zero" aria-label="{escape(say)}: not distinguishable '
                f'from zero"><span class="uar-m-zero" aria-hidden="true">—</span></td>')
    alpha = HEAT_ALPHAS[_heat_step(impact, largest)]
    if evidence == "tentative":
        alpha = HEAT_ALPHAS[0]
    hue = "var(--uar-pos)" if impact >= 0 else "var(--uar-neg)"
    cls = "uar-hm-clear" if evidence == "clear" else "uar-hm-tent"
    style = f"background:color-mix(in srgb,{hue} {alpha * 100:.0f}%,transparent);"
    if evidence == "tentative":
        style += f"outline:1.5px dashed {hue};outline-offset:-4px;"
    label = f"{say}: {fmt_pct(impact)}, {ex.EVIDENCE_LABELS[evidence]}"
    return (f'<td class="uar-hm {cls}" style="{style}" aria-label="{escape(label)}">'
            f'<span class="uar-hm-v">{fmt_pct(impact)}</span></td>')


def holdings_matrix_html(report: dict) -> str:
    """Every holding on one heatmap: rows are holdings, columns are the forces.

    The engine fits every holding separately, on exactly the same weeks and
    regressors as the portfolio, so this needs no new statistics and invents
    nothing. Each cell is shaded on the report's up/down pair, darker for a
    larger reading, so a whole book can be scanned at once: which names carry
    the rate exposure, which ones move against the rest. Clear readings are
    solid; tentative ones are the lightest shade with a dashed outline; a
    reading that cannot be told from noise is a dash, never a faint colour --
    it is an absence of evidence, not a small exposure. The whole portfolio
    sits on the top row for reference.
    """
    contributions = report.get("contributions") or {}
    if not contributions or "portfolio" not in report:
        return ""
    keys = [k for k in ordered_keys(report) if contributions.get(k)]
    if not keys:
        return ""

    cells: dict = {}
    weights: dict = {}
    for key in keys:
        for row in contributions[key]:
            cells.setdefault(row["ticker"], {})[key] = row
            weights[row["ticker"]] = row["weight_pct"]
    if len(weights) < 2:
        return ""  # a single holding IS the portfolio; the table above says it

    readings = report["portfolio"]["readings"]
    shown = [r["impact"] for t in weights for k, r in cells.get(t, {}).items()
             if r["evidence"] in ("clear", "tentative")]
    shown += [readings[k]["impact"] for k in keys if readings[k]["evidence"] in ("clear", "tentative")]
    largest = max((abs(v) for v in shown), default=0.0)

    head = "".join(
        f'<th scope="col"><span class="uar-dot" style="background:{FACTOR_COLORS.get(k, "#3b7ddd")}"></span>'
        f'{escape(readings[k]["label"])}</th>' for k in keys)

    portfolio_row = (
        '<tr class="uar-hm-total"><th scope="row" class="uar-m-name"><div class="uar-m-tick">Whole portfolio</div>'
        '<div class="uar-m-weight">for reference</div></th>'
        + "".join(_heat_cell(readings[k]["impact"], readings[k]["evidence"], largest,
                             f'Whole portfolio, {readings[k]["label"]}') for k in keys)
        + '</tr>')
    body = [portfolio_row]
    for ticker in sorted(weights, key=lambda t: -weights[t]):
        tds = []
        for key in keys:
            row = cells.get(ticker, {}).get(key)
            say = f'{ticker}, {readings[key]["label"]}'
            if row is None:
                tds.append(_heat_cell(0.0, "indistinct", largest, say))
            else:
                tds.append(_heat_cell(row["impact"], row["evidence"], largest, say))
        body.append(
            f'<tr><th scope="row" class="uar-m-name"><div class="uar-m-tick">{escape(ticker)}</div>{_hname(ticker, 30)}'
            f'<div class="uar-m-weight">{weights[ticker]:.1f}% of the portfolio</div></th>'
            + "".join(tds) + "</tr>")

    steps = "".join(
        f'<span class="uar-hm-key" style="background:color-mix(in srgb,var(--uar-neg) {a * 100:.0f}%,transparent)"></span>'
        for a in reversed(HEAT_ALPHAS)) + '<span class="uar-hm-mid"></span>' + "".join(
        f'<span class="uar-hm-key" style="background:color-mix(in srgb,var(--uar-pos) {a * 100:.0f}%,transparent)"></span>'
        for a in HEAT_ALPHAS)
    legend = (f'<div class="uar-hm-legend" aria-hidden="true"><span>Moved down</span>{steps}'
              f'<span>Moved up</span><span class="uar-hm-sep"></span>'
              f'<span class="uar-hm-key uar-hm-tentkey"></span><span>Tentative</span>'
              f'<span class="uar-m-zero">—</span><span>Not distinguishable from zero</span></div>')

    return (
        '<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
        '<div class="uar-title">Each holding, measured on its own</div>'
        '<div class="uar-sub">The same three years of weekly returns, fitted one holding at a '
        'time, with the stock market&#39;s own movement removed. Darker means a larger move; read '
        'across a row for one name, down a column for one force.</div></div></div>'
        f'{legend}'
        '<div class="uar-scroll" tabindex="0" role="region" aria-label="Holdings heatmap, scrolls sideways">'
        '<table class="uar-matrix uar-heat"><thead><tr>'
        f'<th scope="col" class="uar-m-name">Holding</th>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
        '<div class="uar-foot">Each figure is the holding&#39;s own sensitivity, before its weight is '
        'applied: its typical same-week move when that force moved by the amount in the table above. '
        'Shading is relative to the largest reading on this grid. A dash means that holding&#39;s '
        'response could not be told apart from noise — not that it has none. Each one describes how '
        'that holding has moved and is not a forecast. To look at one name on its own, enter just '
        'that ticker.</div>'
        '</div></div>')


def shifts_html(report: dict) -> str:
    shifts = report.get("shifts") or []
    if not shifts:
        return ('<div class="uar"><div class="uar-note">A before-and-after comparison needs a full '
                'three years of history, so it isn&#39;t available for this portfolio.</div></div>')
    flagged = [s for s in shifts if s["significant"]]
    if not flagged:
        body = ('<div class="uar-note">No measurable change in any exposure between the past year and '
                'the two years before it.</div>')
    else:
        body = "".join(f'<div class="uar-note uar-note-warn">{escape(s["sentence"])}</div>' for s in flagged)
    return (f'<div class="uar">{body}<div class="uar-sub">The past 52 weeks are compared with the '
            f'104 weeks before them. A change is only shown when it is larger than the combined '
            f'uncertainty of both periods.</div></div>')


def recent_moves_html(report: dict) -> str:
    rm = report.get("recent_moves") or {}
    if not rm.get("available"):
        return ""
    counted = [m for m in rm["moves"] if m["counts"]]
    head = (f'<p class="uar-lead">In the {rm["weeks"]} weeks to {escape(fmt_date(rm["end"]))}, the '
            f'portfolio returned {fmt_pct(rm["portfolio_return"])}.</p>')
    if not counted:
        return (f'<div class="uar">{head}<div class="uar-note">None of this portfolio&#39;s exposures is '
                f'strong enough to connect its recent moves to these economic forces.</div></div>')
    rows = "".join(
        f'<tr><td><b>{escape(m["label"])}</b></td><td>{escape(m["move_text"])}</td>'
        f'<td>{fmt_pct(m["attributed"])}</td>'
        f'<td>{fmt_pct(m["attributed"] - ex.Z90 * m["attributed_se"])} to '
        f'{fmt_pct(m["attributed"] + ex.Z90 * m["attributed_se"])}</td></tr>'
        for m in counted
    )
    return (
        f'<div class="uar">{head}<div class="uar-scroll" tabindex="0" role="region" aria-label="Table, scrolls sideways"><table class="uar-table"><thead><tr>'
        f'<th>Economic force</th><th>How it moved</th><th>Portfolio move that lines up with it</th>'
        f'<th>90% range</th></tr></thead><tbody>{rows}</tbody></table></div>'
        f'<div class="uar-sub" style="margin-top:8px">These apply the measured sensitivities to what '
        f'actually happened. They explain the recent past; they are not a forecast. Only exposures '
        f'labelled Clear or Tentative are shown.</div></div>'
    )


def growth_html(report: dict) -> str:
    g = report.get("growth") or {}
    if not g.get("available"):
        reason = g.get("reason") or "monthly data was unavailable"
        return (f'<div class="uar"><div class="uar-note">Economic growth couldn&#39;t be measured: '
                f'{escape(reason)}.</div></div>')
    r = g["readings"].get("growth")
    if not r:
        return ""
    return (f'<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
            f'<div class="uar-title">Economic growth · limited evidence</div>'
            f'<div class="uar-sub">{escape(r["why"])}</div></div>{evidence_chip(r["evidence"])}</div>'
            f'<div class="uar-body"><p class="uar-lead">{escape(r["sentence"])}</p>'
            f'<div class="uar-sub">{escape(g["note"])}</div></div></div></div>')


def notes_html(report: dict, cleaning_notes: Iterable[str] = ()) -> str:
    items = list(cleaning_notes) + list(report.get("notes") or [])
    for x in report.get("excluded") or []:
        items.append(f"{x['ticker']} ({x['weight_pct']:.0f}%): {x['reason']}.")
    if not items:
        return ""
    body = "".join(f"<li>{escape(i)}</li>" for i in dict.fromkeys(items))
    return (f'<div class="uar"><div class="uar-note"><b>About the data</b>'
            f'<ul style="margin:6px 0 0 18px;padding:0">{body}</ul></div></div>')


def error_html(report: dict) -> str:
    excluded = report.get("excluded") or []
    detail = ""
    if excluded:
        items = "".join(f"<li>{escape(x['ticker'])}: {escape(x['reason'])}</li>" for x in excluded)
        detail = f'<ul style="margin:8px 0 0 18px;padding:0">{items}</ul>'
    return (f'<div class="uar"><div class="uar-error"><b>We couldn&#39;t measure this portfolio.</b>'
            f'<div style="margin-top:6px">{escape(report.get("message") or GENERIC_ERROR)}</div>'
            f'{detail}</div></div>')


def portfolio_header_html(name: str, report: dict) -> str:
    positions = report.get("positions") or []
    listing = " · ".join(f"{p['weight_pct']:.0f}% {p['ticker']}"
                         for p in sorted(positions, key=lambda p: -p["weight_pct"])[:8])
    more = f" · +{len(positions) - 8} more" if len(positions) > 8 else ""
    as_of = report.get("as_of")
    return (f'<div class="uar">'
            f'<div class="uar-title" style="font-size:1.35rem">{escape(name)}</div>'
            f'<div class="uar-sub">{escape(listing + more)}'
            + (f' · data through {escape(fmt_date(as_of))}' if as_of else "")
            + '</div></div>')


# One glyph per force, the same drawings as the landing page's (page.tsx
# Glyph), so "oil" looks like oil on both. 32x32 box centred on 0,0.
_GLYPHS = {
    "rates": '<line x1="-7" y1="8" x2="7" y2="-8"/><circle cx="-6" cy="-6" r="2.6"/><circle cx="6" cy="6" r="2.6"/>',
    "inflation": '<polyline points="-9,7 -3,1 1,4 9,-5"/><polyline points="3,-5 9,-5 9,1"/>',
    "dollar": '<path d="M6,-6 C4,-9 -6,-9 -6,-4 C-6,1 6,-1 6,4 C6,9 -4,9 -6,6"/><line x1="0" y1="-11" x2="0" y2="11"/>',
    "oil": '<path d="M0,-10 C5,-3 8,1 8,4 A8,8 0 0 1 -8,4 C-8,1 -5,-3 0,-10 Z"/>',
    "credit": '<polyline points="-10,-3 0,-10 10,-3"/><line x1="-6" y1="-1" x2="-6" y2="7"/><line x1="0" y1="-1" x2="0" y2="7"/>'
              '<line x1="6" y1="-1" x2="6" y2="7"/><line x1="-10" y1="9" x2="10" y2="9"/>',
    "growth": '<line x1="-8" y1="9" x2="-8" y2="2"/><line x1="-2" y1="9" x2="-2" y2="-3"/><line x1="4" y1="9" x2="4" y2="-1"/>'
              '<line x1="10" y1="9" x2="10" y2="-8"/>',
}


def factor_icon(key: str, size: int = 28) -> str:
    """The force's glyph on a tile of its identity colour (decorative)."""
    glyph = _GLYPHS.get(key)
    if not glyph:
        return f'<span class="uar-dot" style="background:{FACTOR_COLORS.get(key, "#8794a8")}"></span>'
    return (f'<span class="uar-ficon" style="--fc:{FACTOR_COLORS.get(key, "#8794a8")};width:{size}px;height:{size}px" aria-hidden="true">'
            f'<svg viewBox="-16 -16 32 32" width="{int(size * .62)}" height="{int(size * .62)}" fill="none" stroke="currentColor" '
            f'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">{glyph}</svg></span>')


def summary_tiles_html(report: dict) -> str:
    """Four tiles that say the shape of the result at a glance: the strongest
    link, how many readings held up, the market's share, the window. Each is
    a figure from the report with a small picture of it; nothing is new."""
    p = report["portfolio"]
    readings = p["readings"]
    order = ordered_keys(report)
    if not order:
        return ""
    top = order[0]
    r = readings[top]
    marks = "".join(
        f'<i class="uar-mk uar-mk-{ {"clear": "c", "tentative": "t"}.get(readings[k]["evidence"], "z") }" '
        f'title="{escape(readings[k]["label"])}: {escape(ex.EVIDENCE_LABELS.get(readings[k]["evidence"], ""))}"></i>'
        for k in order)
    held = sum(readings[k]["evidence"] in ("clear", "tentative") for k in order)
    clear = sum(readings[k]["evidence"] == "clear" for k in order)
    beta = p.get("market_beta_total")
    beta_html = ""
    if beta is not None and math.isfinite(beta):
        w = max(0.0, min(1.5, beta)) / 1.5 * 100
        beta_html = (f'<div class="uar-tile"><div class="uar-tile-k">With the stock market</div>'
                     f'<div class="uar-tile-v">{beta:.2f}×</div>'
                     f'<div class="uar-gauge" aria-hidden="true"><i style="width:{w:.0f}%"></i><b style="left:{100 / 1.5:.1f}%"></b></div>'
                     f'<div class="uar-tile-s">its typical weekly move vs the market (1× marked), accounted for separately</div></div>')
    span = ""
    if p.get("start") and p.get("end"):
        span = (f'<div class="uar-tile"><div class="uar-tile-k">Measured over</div>'
                f'<div class="uar-tile-v">{p["n_obs"]} weeks</div>'
                f'<div class="uar-weeks" aria-hidden="true">{"<i></i>" * 39}</div>'
                f'<div class="uar-tile-s">{escape(fmt_date(p["start"]))} to {escape(fmt_date(p["end"]))}</div></div>')
    return (
        '<div class="uar uar-tiles">'
        f'<div class="uar-tile uar-tile-lead">{factor_icon(top, 34)}<div>'
        f'<div class="uar-tile-k">Largest measured exposure</div>'
        f'<div class="uar-tile-v">{escape(r["label"])} <span>{fmt_pct(r["impact"])}</span></div>'
        f'<div class="uar-tile-s">{escape(ex.EVIDENCE_LABELS.get(r["evidence"], ""))} · in weeks when {escape(r["shock_phrase"])}</div></div></div>'
        f'<div class="uar-tile"><div class="uar-tile-k">Readings that held up</div>'
        f'<div class="uar-tile-v">{held} of {len(order)}</div>'
        f'<div class="uar-marks">{marks}</div>'
        f'<div class="uar-tile-s">{clear} Clear · {held - clear} Tentative · {len(order) - held} not distinguishable from zero</div></div>'
        + beta_html + span + '</div>')


def flow_svg(report: dict) -> str:
    """Where each exposure comes from: holdings on the left, the held-up
    forces on the right, one ribbon per contribution in the same direction as
    the force's reading, its width the size of that contribution. Offsetting
    holdings are in the table below it, not drawn. Empty when nothing held up."""
    readings = report["portfolio"]["readings"]
    keys = [k for k in ordered_keys(report) if readings[k]["evidence"] in ("clear", "tentative")]
    flows = []
    for k in keys:
        for c in report.get("contributions", {}).get(k, []):
            if c["contribution"] * readings[k]["impact"] > 0 and abs(c["contribution"]) >= 0.004:
                flows.append((c["ticker"], k, abs(c["contribution"])))
    if len(flows) < 2:
        return ""
    weights = {x["ticker"]: x["weight_pct"] for x in report.get("positions") or []}
    left = sorted({t for t, _, _ in flows}, key=lambda t: -weights.get(t, 0))[:12]
    flows = [f for f in flows if f[0] in left]
    right = [k for k in keys if any(f[1] == k for f in flows)]
    # LX leaves room for each holding's full name (two lines: ticker and
    # weight, then the name) so a reader who does not know VTI still can.
    W, NODE, GAP, LX, RX = 860, 10, 14, 250, 600
    total = sum(v for _, _, v in flows)
    n = max(len(left), len(right))
    k = (300 - GAP * (n - 1)) / total          # ribbons sized for a 300-unit column...
    SLOT = 40                                  # ...then each node keeps room for its two-line label

    def column(names, size):
        return sum(max(size(x) * k, SLOT) for x in names) + GAP * (len(names) - 1)
    H = int(max(column(left, lambda t: sum(v for a, _, v in flows if a == t)),
                column(right, lambda f: sum(v for _, b, v in flows if b == f)))) + 8

    def place(names, size):
        hs = [size(n) * k for n in names]
        y = (H - (sum(max(h, SLOT) for h in hs) + GAP * (len(names) - 1))) / 2
        out = {}
        for n, h in zip(names, hs):
            out[n] = [y + max(0.0, SLOT - h) / 2, h, 0.0]
            y += max(h, SLOT) + GAP
        return out
    L = place(left, lambda t: sum(v for a, _, v in flows if a == t))
    R = place(right, lambda f: sum(v for _, b, v in flows if b == f))
    flows.sort(key=lambda f: (left.index(f[0]), right.index(f[1])))
    ribbons = []
    for t, f, v in flows:
        w = v * k
        y0, y1 = L[t][0] + L[t][2], R[f][0] + R[f][2]
        L[t][2] += w
        R[f][2] += w
        x0, x1 = LX + NODE, RX
        mx = (x0 + x1) / 2
        ribbons.append(
            f'<path d="M{x0},{y0:.1f} C{mx},{y0:.1f} {mx},{y1:.1f} {x1},{y1:.1f} L{x1},{y1 + w:.1f} '
            f'C{mx},{y1 + w:.1f} {mx},{y0 + w:.1f} {x0},{y0 + w:.1f} Z" fill="{FACTOR_COLORS[f]}" class="uar-rib">'
            f'<title>{escape(hn.with_name(t))} → {escape(readings[f]["label"])}: {v:.2f} points of {fmt_pct(readings[f]["impact"])}</title></path>')
    labels = []
    for t in left:
        y, h, _ = L[t]
        labels.append(f'<rect x="{LX}" y="{y:.1f}" width="{NODE}" height="{max(2, h):.1f}" rx="2" class="uar-flow-bar"/>'
                      f'<text x="{LX - 12}" y="{y + h / 2 - 1:.1f}" text-anchor="end" class="uar-flow-t">{escape(t)}'
                      f'<tspan class="uar-flow-s" dx="8">{weights.get(t, 0):.0f}%</tspan></text>'
                      + (f'<text x="{LX - 12}" y="{y + h / 2 + 15:.1f}" text-anchor="end" class="uar-flow-n">'
                         f'<title>{escape(hn.full_name(t))}</title>{escape(hn.short(hn.full_name(t), 32))}</text>'
                         if hn.full_name(t) else ""))
    for f in right:
        y, h, _ = R[f]
        labels.append(f'<rect x="{RX}" y="{y:.1f}" width="{NODE}" height="{max(2, h):.1f}" rx="2" fill="{FACTOR_COLORS[f]}"/>'
                      f'<text x="{RX + NODE + 12}" y="{y + h / 2 - 1:.1f}" class="uar-flow-l">{escape(readings[f]["label"])}</text>'
                      f'<text x="{RX + NODE + 12}" y="{y + h / 2 + 16:.1f}" class="uar-flow-s">{fmt_pct(readings[f]["impact"])} · '
                      f'{escape(ex.EVIDENCE_LABELS.get(readings[f]["evidence"], ""))}</text>')
    summary = "; ".join(f"{hn.with_name(t)} to {readings[f]['label']} {v:.2f} points" for t, f, v in flows)
    return (f'<div class="uar"><div class="uar-card uar-flow"><div class="uar-flow-head"><b>Where each exposure comes from</b>'
            '<span>Ribbon width: each holding&#39;s contribution, its weight times its own sensitivity. '
            'Hover a ribbon for the figure.</span></div>'
            f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{escape("Where each exposure comes from: " + summary)}">'
            f'<g class="uar-ribs">{"".join(ribbons)}</g>{"".join(labels)}</svg></div></div>')


def workspace_header_html(name: str, report: dict) -> str:
    """The report's compact header: the portfolio's identity, its holdings,
    and the measurement window and data date together on one line."""
    positions = sorted(report.get("positions") or [], key=lambda p: -p["weight_pct"])
    p = report.get("portfolio") or {}
    chips = "".join(
        f'<span role="listitem" title="{escape(hn.full_name(x["ticker"]) or x["ticker"])}">'
        f'<b>{escape(x["ticker"])}</b>{x["weight_pct"]:.0f}%'
        + (f'<span class="uar-sr"> {escape(hn.full_name(x["ticker"]))}</span>' if hn.full_name(x["ticker"]) else "")
        + '</span>' for x in positions[:10])
    if len(positions) > 10:
        chips += f'<span role="listitem">+{len(positions) - 10} more</span>'
    meta = [f'{len(positions)} holding{"" if len(positions) == 1 else "s"}']
    if p.get("n_obs") and p.get("start") and p.get("end"):
        meta.append(f'{p["n_obs"]} weeks, {fmt_date(p["start"])} to {fmt_date(p["end"])}')
    if report.get("as_of"):
        meta.append(f'data through {fmt_date(report["as_of"])}')
    return ('<div class="uar uar-ws"><div class="uar-ws-kicker">Exposure report</div>'
            f'<h1 class="uar-ws-title">{escape(name)}</h1>'
            f'<div class="uar-ws-meta">{escape(" · ".join(meta))}</div>'
            f'<div class="uar-ws-holdings" role="list" aria-label="Holdings and weights">{chips}</div></div>')


def report_skeleton_html(message: str) -> str:
    """A placeholder shaped like the report while it is measured: grey blocks,
    the plain message, no figures and no invented progress."""
    row = ('<div class="uar-sk-row"><i class="uar-sk"></i><i class="uar-sk uar-sk-bar"></i>'
           '<i class="uar-sk"></i><i class="uar-sk"></i></div>')
    return ('<div class="uar uar-skel" role="status">'
            f'<div class="uar-sk-msg">{escape(message)}</div>'
            '<div aria-hidden="true"><i class="uar-sk uar-sk-title"></i><i class="uar-sk uar-sk-line"></i>'
            f'<div class="uar-card uar-sk-card">{row * 5}</div></div></div>')


def window_note_html(report: dict) -> str:
    """The history charts use a rolling window shorter than the headline's,
    so their latest value can differ from the table's, even in sign. Said
    beside the section title, where the two numbers meet."""
    m = report.get("method") or {}
    rolling = m.get("rolling_weeks") or 52
    window = m.get("window_weeks") or (report.get("portfolio") or {}).get("n_obs") or 156
    return (f'<div class="uar"><div class="uar-window"><span class="uar-window-tag">Rolling {rolling}-week estimates</span>'
            f'Each point uses the {rolling} weeks to that date. The table above uses {window} weeks, so the '
            'latest point here can differ from it, even in sign. Each chart has its own vertical scale.</div></div>')


FOOTER_LINKS = (("Methodology", "/methodology"), ("Research record", "/research"),
                ("Pricing", "/pricing"), ("Privacy &amp; Terms", "/privacy-terms"))


def render_report_footer() -> None:
    """Footer for the redesigned pages. The shared footer still describes the
    old signal product and its data providers, which these pages do not use."""
    links = " · ".join(f'<a href="{href}" target="_self">{label}</a>' for label, href in FOOTER_LINKS)
    st.markdown(
        REPORT_CSS
        + '<div class="uar" style="margin-top:40px;padding-top:16px;border-top:1px solid var(--uar-line)">'
        f'<div class="uar-sub">{links}</div>'
        '<div class="uar-sub" style="margin-top:8px">Unstructured Alpha is an educational and informational '
        'tool. Nothing here is personalized financial, investment, tax or legal advice, or a recommendation '
        'to buy, sell or hold any security. Exposure figures describe how portfolios have moved in the past; '
        'relationships change and past behaviour does not guarantee future results. Prices from Yahoo '
        'Finance; economic series from the Federal Reserve Bank of St. Louis (FRED).</div></div>',
        unsafe_allow_html=True,
    )


HOW_TO_READ = """
**What each number means.** Take "Interest rates −0.66%". In weeks when the 10-year Treasury yield rose 0.25 percentage points, this portfolio typically moved 0.66% lower in the same week. The stock market's own movement is removed first.

**The range.** The 90% range shows how precisely the relationship was measured. A wide range means it is uncertain. A range that crosses zero means the result could be noise.

**The labels.**
- *Clear*: strong enough to hold up even after allowing for testing five factors at once.
- *Tentative*: suggestive, but could be noise.
- *Not distinguishable from zero*: no measurable relationship.
- *Not enough data*: too little history to say.

**Why the market is taken out.** Rates, oil and the dollar often move on the same days as stocks. Without removing that, nearly every stock portfolio would look sensitive to everything.

**What this is not.** It describes the past three years. Relationships change. It is not a forecast, and it is not advice.
"""
