# utils/quiz_page.py
# Unstructured Alpha — "Which way did it move?": a ten-round daily quiz
#
# Hands-on and quick: a stock and a force, three buttons -- rose with it, fell
# with it, no clear link -- and the measured answer revealed after each guess.
# The point it teaches is the product's own: most stocks have no measurable
# link to most forces, and the ones that do are often not the obvious ones.
#
# RULES
#   * "Rose" and "fell" answers come only from Clear readings; "no clear link"
#     only from readings that could not be told apart from zero. Tentative
#     readings are left out: neither answer would be fair.
#   * The round is the same for everyone on a given day (seeded by the date),
#     so a score means the same thing to two people comparing it.
#   * Past, not forecast; every answer links to the stock's own page.

from __future__ import annotations

import json
import random
from datetime import date
from html import escape
from typing import Iterable, List, Optional

from utils.exposure_pages import SYMBOL_RE, _shell
from utils.force_pages import FORCE_BY_KEY

ROUNDS = 10
MIX = {"up": 4, "down": 3, "none": 3}     # how a round is split before shuffling


def _pool(stocks: Iterable[dict]) -> dict:
    pool = {"up": [], "down": [], "none": []}
    for s in stocks:
        if not SYMBOL_RE.match(s.get("ticker") or ""):
            continue
        for key, e in (s.get("exposures") or {}).items():
            f = FORCE_BY_KEY.get(key)
            if f is None:
                continue
            ev = e.get("evidence")
            if ev == "clear":
                side = "up" if e["impact"] > 0 else "down"
            elif ev == "indistinct" and e["low"] <= 0 <= e["high"]:
                side = "none"
            else:
                continue                         # tentative, or too little data to ask
            if side:
                pool[side].append([s["ticker"], s.get("name") or "", key, f.label, f.shock_phrase,
                                   round(float(e["impact"]), 3), round(float(e["low"]), 3),
                                   round(float(e["high"]), 3), side])
    return pool


def quiz_rounds(stocks: Iterable[dict], day: Optional[date] = None) -> List[list]:
    """Today's round: up to ROUNDS questions, the same for everyone today, no
    stock or force asked twice."""
    day = day or date.today()
    pool = _pool(stocks)
    rng = random.Random(day.isoformat())
    picked, seen_t, seen_f = [], set(), set()
    for side, want in MIX.items():
        items = sorted(pool[side])               # stable order before the seeded shuffle
        rng.shuffle(items)
        n = 0
        for fresh_force in (True, False):        # spread across forces, if the pool allows
            for it in items:
                if n == want:
                    break
                if it[0] in seen_t or (fresh_force and it[2] in seen_f):
                    continue
                picked.append(it)
                seen_t.add(it[0])
                seen_f.add(it[2])
                n += 1
    rng.shuffle(picked)
    return picked[:ROUNDS]


_SCRIPT = r"""
(function(){
  var Q = JSON.parse(document.getElementById('qz-data').textContent), i = 0, score = 0;
  var box = document.getElementById('qz-box'), say = document.getElementById('qz-say');
  var WORD = {up: 'Rose with it', down: 'Fell with it', none: 'No clear link'};
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function pct(v){ var a = Math.abs(v); return (v > 0 ? '+' : v < 0 ? '−' : '') + (a < 10 ? a.toFixed(1) : a.toFixed(0)) + '%'; }
  function ask(){
    if (i >= Q.length) return done();
    var q = Q[i];
    box.innerHTML = '<p class="qz-step">Question ' + (i + 1) + ' of ' + Q.length + ' · score ' + score + '</p>'
      + '<p class="qz-q">In weeks when <b>' + esc(q[4]) + '</b>, what did <b>' + esc(q[0]) + '</b>'
      + (q[1] ? ' <span class="qz-name">(' + esc(q[1]) + ')</span>' : '') + ' do, beyond the stock market?</p>'
      + '<div class="qz-btns">' + ['up', 'down', 'none'].map(function(k){
          return '<button type="button" class="btn btn-secondary" data-k="' + k + '">' + WORD[k] + '</button>'; }).join('') + '</div>';
    box.querySelectorAll('button').forEach(function(b){ b.addEventListener('click', function(){ answer(b.getAttribute('data-k')); }); });
    box.querySelector('button').focus();
  }
  function answer(k){
    var q = Q[i], right = k === q[8]; if (right) score++;
    var fig = q[8] === 'none'
      ? 'Its typical move was ' + pct(q[5]) + ', but the 90% range (' + pct(q[6]) + ' to ' + pct(q[7]) + ') includes zero: no link that stands apart from noise.'
      : 'It typically moved <b>' + pct(q[5]) + '</b> (90% range ' + pct(q[6]) + ' to ' + pct(q[7]) + '), a Clear reading.';
    box.innerHTML = '<p class="qz-step">Question ' + (i + 1) + ' of ' + Q.length + ' · score ' + score + '</p>'
      + '<p class="qz-verdict ' + (right ? 'qz-right' : 'qz-wrong') + '">' + (right ? 'Right.' : 'Not quite.') + ' ' + WORD[q[8]] + '.</p>'
      + '<p class="lead">' + fig + ' <a href="/exposure/' + encodeURIComponent(q[0]) + '">See ' + esc(q[0]) + '</a> · '
      + '<a href="/forces/' + encodeURIComponent(q[2]) + '">' + esc(q[3]) + '</a></p>'
      + '<div class="qz-btns"><button type="button" class="btn btn-primary" id="qz-next">' + (i + 1 < Q.length ? 'Next question' : 'See your score') + '</button></div>';
    say.textContent = (right ? 'Right. ' : 'Not quite. ') + WORD[q[8]] + '.';
    var n = document.getElementById('qz-next'); n.addEventListener('click', function(){ i++; ask(); }); n.focus();
  }
  function done(){
    var none = Q.filter(function(q){ return q[8] === 'none'; }).length;
    box.innerHTML = '<p class="qz-q">You scored <b>' + score + ' of ' + Q.length + '</b>.</p>'
      + '<p class="lead">' + none + ' of today&#39;s ' + Q.length + ' had no clear link at all. Across the library that is the usual answer: '
      + 'most stocks show no measurable link to most forces. A new round comes tomorrow.</p>'
      + '<div class="qz-btns"><a class="btn btn-primary" href="/explore">What if? Move a force</a>'
      + '<a class="btn btn-secondary" href="/compare">Compare two stocks</a></div>';
    say.textContent = 'You scored ' + score + ' of ' + Q.length + '.';
  }
  ask();
})();
"""

_CSS = """<style>
.qz{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px;margin:10px 0}
.qz-step{font-size:.82rem;color:var(--ink3);margin:0 0 8px;font-variant-numeric:tabular-nums}
.qz-q{font-size:1.25rem;line-height:1.45;margin:0 0 14px}
.qz-name{color:var(--ink3);font-weight:400}
.qz-btns{display:flex;flex-wrap:wrap;gap:10px}
.qz-btns .btn{min-height:44px}
.qz-verdict{font-size:1.25rem;font-weight:750;margin:0 0 6px}
.qz-right{color:#1f7a4d}.qz-wrong{color:#a4501a}
@media (prefers-color-scheme:dark){.qz-right{color:#5cc28e}.qz-wrong{color:#e0965a}}
</style>"""


def quiz_page_html(stocks: Iterable[dict], base_url: str, app_url: str,
                   day: Optional[date] = None) -> str:
    rounds = quiz_rounds(stocks, day)
    canonical = f"{base_url}/quiz"
    title = "Which way did it move? A daily quiz on stocks and the economy"
    desc = ("Ten quick questions: when oil, rates, the dollar or gold moved, did a stock rise with it, "
            "fall with it, or show no clear link? Answers come from measured U.S. stock data.")
    crumb = '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Quiz</nav>'
    ld = {"@context": "https://schema.org", "@type": "Quiz", "name": title, "url": canonical,
          "description": desc, "isAccessibleForFree": True}
    if len(rounds) < 3:
        body = (crumb + '<h1>Which way did it move?</h1><p class="lead">Not enough stocks have been '
                'measured yet for a round. Readings are added each week.</p>')
        return _shell(title, desc, canonical, ld, body, app_url, robots="noindex, follow")
    payload = json.dumps(rounds, separators=(",", ":")).replace("</", "<\\/")
    body = (
        _CSS + crumb + '<h1>Which way did it move?</h1>'
        f'<p class="lead">{escape(desc)}</p>'
        '<div class="qz" id="qz-box"><noscript><p class="lead">The quiz needs JavaScript. '
        'Every answer is also on the <a href="/forces">economic force pages</a>.</p></noscript></div>'
        '<p aria-live="polite" id="qz-say" style="position:absolute;left:-9999px"></p>'
        '<p class="small">"Rose" and "fell" answers are Clear readings: a stock&#39;s typical same-week '
        'move when the force moved by the stated amount, after the stock market&#39;s own move, over '
        'three years of weekly returns. "No clear link" means the 90% range includes zero. Tentative '
        'readings are left out. Everyone gets the same ten questions today.</p>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here is a '
        'recommendation to buy, sell or hold any security.</p>'
        f'<script type="application/json" id="qz-data">{payload}</script>'
        f'<script>{_SCRIPT}</script>')
    return _shell(title, desc, canonical, ld, body, app_url)
