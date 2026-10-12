# utils/guess_page.py
# Unstructured Alpha — "Whose fingerprint?": a daily five-round guessing game
#
# Each round shows one stock's five core readings, drawn as on its page -- a
# dot, a 90% range, the zero line -- with the name hidden, and four stocks to
# choose from. It teaches reading the chart: a big oil bar points to energy,
# a deep rates dip to utilities or real estate, a flat profile to almost
# anything.
#
# RULES
#   * A mystery stock is measured on all five core forces with at least two
#     readings that held up: a flat profile would be a coin toss.
#   * Decoys are drawn from stocks whose profiles are far from the answer's
#     (scaled by how much stocks differ on each force), preferring other
#     sectors, so a round is fair rather than a trick.
#   * Same rounds for everyone on a day (seeded by the date); no stock appears
#     twice in a day's rounds.
#   * Past, not forecast; every answer links to the stock's own page.

from __future__ import annotations

import json
import random
from datetime import date
from html import escape
from typing import Iterable, List, Optional

from utils import exposure as ex
from utils.explore_page import JS_PCT
from utils.exposure_pages import _RC_CSS, STANDS_UP, SYMBOL_RE, _shell

ROUNDS = 5
CHOICES = 4
MIN_HELD = 2
CORE = tuple(f.key for f in ex.FACTORS)


def _pool(stocks: Iterable[dict]) -> List[dict]:
    out = []
    for s in stocks:
        exps = s.get("exposures") or {}
        if not SYMBOL_RE.match(s.get("ticker") or "") or not all(k in exps for k in CORE):
            continue
        if sum(1 for k in CORE if exps[k].get("evidence") in STANDS_UP) < MIN_HELD:
            continue
        out.append(s)
    return sorted(out, key=lambda s: s["ticker"])


def _everyone(stocks: Iterable[dict]) -> List[dict]:
    return sorted((s for s in stocks if SYMBOL_RE.match(s.get("ticker") or "")
                   and all(k in (s.get("exposures") or {}) for k in CORE)), key=lambda s: s["ticker"])


def guess_rounds(stocks: Iterable[dict], day: Optional[date] = None) -> List[dict]:
    """Today's rounds: [{"answer": i, "choices": [[ticker, name, sector]...],
    "profile": [[label, impact, low, high, held]...]}]. Empty when the library
    is too small for a fair game."""
    from utils.sector_pages import sector_by_ticker
    stocks = list(stocks)
    pool, everyone = _pool(stocks), _everyone(stocks)
    if len(pool) < ROUNDS or len(everyone) < 4 * CHOICES:
        return []
    secs = sector_by_ticker()
    spread = {}
    for k in CORE:
        xs = [s["exposures"][k]["impact"] for s in everyone]
        m = sum(xs) / len(xs)
        spread[k] = (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5 or 1.0

    def dist(a: dict, b: dict) -> float:
        return sum(((a["exposures"][k]["impact"] - b["exposures"][k]["impact"]) / spread[k]) ** 2
                   for k in CORE) ** 0.5

    rng = random.Random("guess-" + (day or date.today()).isoformat())
    answers = rng.sample(pool, ROUNDS)
    used = {a["ticker"] for a in answers}
    rounds = []
    for a in answers:
        # Decoys: the farther half of profiles from the answer, other sectors first.
        ranked = sorted((s for s in everyone if s["ticker"] != a["ticker"]),
                        key=lambda s: (dist(a, s), s["ticker"]))
        far = [s for s in ranked[len(ranked) // 2:] if s["ticker"] not in used]
        a_sec = secs.get(a["ticker"])
        rng.shuffle(far)
        far.sort(key=lambda s: secs.get(s["ticker"]) == a_sec)   # stable: other sectors first
        decoys, seen_sec = [], {a_sec}
        for s in far:
            if len(decoys) == CHOICES - 1:
                break
            if secs.get(s["ticker"]) in seen_sec and len(far) > CHOICES * 3:
                continue
            decoys.append(s)
            seen_sec.add(secs.get(s["ticker"]))
        if len(decoys) < CHOICES - 1:
            decoys += [s for s in far if s not in decoys][:CHOICES - 1 - len(decoys)]
        used.update(s["ticker"] for s in decoys)
        choices = decoys + [a]
        rng.shuffle(choices)
        rounds.append({
            "answer": choices.index(a),
            "choices": [[c["ticker"], c.get("name") or "", secs.get(c["ticker"], "")] for c in choices],
            "profile": [[f.label, round(float(a["exposures"][f.key]["impact"]), 3),
                         round(float(a["exposures"][f.key]["low"]), 3),
                         round(float(a["exposures"][f.key]["high"]), 3),
                         1 if a["exposures"][f.key].get("evidence") in STANDS_UP else 0]
                        for f in ex.FACTORS]})
    return rounds


_SCRIPT = r"""
(function(){
  var R = JSON.parse(document.getElementById('gs-data').textContent), i = 0, score = 0, marks = [];
  var box = document.getElementById('gs-box'), say = document.getElementById('gs-say');
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
/*PCT*/
  function chart(p){
    var span = Math.max(0.5, Math.max.apply(null, p.map(function(r){ return Math.max(Math.abs(r[2]), Math.abs(r[3])); }))) * 1.05;
    function pos(v){ return (50 + 50 * v / span).toFixed(2) + '%'; }
    return '<div class="card rc" aria-hidden="true">' + p.map(function(r){
      var side = r[1] >= 0 ? 'u' : 'd', lo = Math.min(r[2], r[3]), hi = Math.max(r[2], r[3]);
      return '<div class="rc-row' + (r[4] ? '' : ' rc-f') + '"><span class="rc-l">' + esc(r[0]) + '</span>'
        + '<span class="rc-t"><span class="rc-z" style="left:50%"></span>'
        + '<span class="rc-r ' + side + '" style="left:' + pos(lo) + ';width:' + (50 * (hi - lo) / span).toFixed(2) + '%"></span>'
        + '<span class="rc-d ' + side + '" style="left:' + pos(r[1]) + '"></span></span>'
        + '<span class="rc-v">' + pct(r[1]) + '</span></div>';
    }).join('') + '<div class="rc-ax"><span></span><span><span>' + pct(-span) + '</span><span>0</span><span>' + pct(span) + '</span></span><span></span></div></div>';
  }
  function words(p){
    return p.map(function(r){ return r[0] + ' ' + pct(r[1]) + (r[4] ? ', held up' : ', no clear link'); }).join('; ');
  }
  function step(){ return '<p class="qz-step">Round ' + (i + 1) + ' of ' + R.length + ' · score ' + score + '</p>'; }
  function ask(){
    if (i >= R.length) return done();
    var r = R[i];
    box.innerHTML = step() + '<p class="qz-q">Whose profile is this?</p>' + chart(r.profile)
      + '<p class="small gs-words">' + esc(words(r.profile)) + '.</p>'
      + '<div class="gs-choices">' + r.choices.map(function(c, k){
          return '<button type="button" class="btn btn-secondary" data-k="' + k + '"><b>' + esc(c[0]) + '</b><span>' + esc(c[1])
            + (c[2] ? ' · ' + esc(c[2]) : '') + '</span></button>'; }).join('') + '</div>';
    box.querySelectorAll('[data-k]').forEach(function(b){ b.addEventListener('click', function(){ answer(+b.getAttribute('data-k')); }); });
    box.querySelector('[data-k]').focus();
  }
  function answer(k){
    var r = R[i], c = r.choices[r.answer], right = k === r.answer; if (right) score++; marks.push(right ? '🟩' : '⬜');
    var best = r.profile.filter(function(p){ return p[4]; }).sort(function(a, b){ return Math.abs(b[1]) - Math.abs(a[1]); })[0];
    box.querySelectorAll('[data-k]').forEach(function(b){ var n = +b.getAttribute('data-k'); b.disabled = true;
      if (n === r.answer) b.classList.add('gs-ans'); else if (n === k) b.classList.add('gs-miss'); });
    var v = document.createElement('div');
    v.innerHTML = '<p class="qz-verdict ' + (right ? 'qz-right' : 'qz-wrong') + '">' + (right ? 'Right.' : 'Not quite.') + ' It was ' + esc(c[0]) + (c[1] ? ' (' + esc(c[1]) + ')' : '') + '.</p>'
      + (best ? '<p class="lead">Its strongest clear link: ' + esc(best[0].toLowerCase()) + ', ' + pct(best[1]) + '. ' : '<p class="lead">')
      + '<a href="/exposure/' + encodeURIComponent(c[0]) + '">See ' + esc(c[0]) + '</a></p>'
      + '<div class="qz-btns"><button type="button" class="btn btn-primary" id="gs-next">' + (i + 1 < R.length ? 'Next round' : 'See your score') + '</button></div>';
    box.appendChild(v);
    say.textContent = (right ? 'Right. ' : 'Not quite. ') + 'It was ' + c[0] + '.';
    var n = document.getElementById('gs-next'); n.addEventListener('click', function(){ i++; ask(); }); n.focus();
  }
  function done(){
    box.innerHTML = '<p class="qz-q">You scored <b>' + score + ' of ' + R.length + '</b>.</p>'
      + '<p class="lead">A profile is a fingerprint: three years of how a stock moved with rates, inflation, the dollar, oil and credit. '
      + 'Sector is the best clue, but not a sure one. A new game comes tomorrow.</p>'
      + '<div class="qz-btns"><a class="btn btn-primary" href="/map">Explore the stock map</a>'
      + '<a class="btn btn-secondary" href="/quiz">Today&#39;s quiz</a>'
      + '<button type="button" class="btn btn-secondary" id="gs-copy">Copy your result</button></div>'
      + '<p class="small" id="gs-copied" aria-live="polite"></p>';
    say.textContent = 'You scored ' + score + ' of ' + R.length + '.';
    var text = 'Whose fingerprint? ' + box.getAttribute('data-day') + ': ' + score + '/' + R.length + '\n' + marks.join('') + '\n' + box.getAttribute('data-url');
    document.getElementById('gs-copy').addEventListener('click', function(){
      var note = document.getElementById('gs-copied');
      function show(){ note.innerHTML = '<textarea readonly rows="3" aria-label="Your result" style="width:100%;font:inherit">' + esc(text) + '</textarea>'; note.querySelector('textarea').select(); }
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(function(){ note.textContent = 'Copied. No spoilers: it shows only right and wrong.'; }, show);
      else show();
    });
  }
  ask();
})();
"""

_CSS = """<style>
.gs-choices{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:6px}
.gs-choices .btn{display:flex;flex-direction:column;align-items:flex-start;text-align:left;min-height:56px;gap:2px}
.gs-choices .btn span{font-weight:400;color:var(--ink3)}
.gs-choices .btn.gs-ans{border-color:#1f7a4d;outline:2px solid #1f7a4d}
.gs-choices .btn.gs-miss{border-color:#a4501a;outline:2px solid #a4501a}
@media (prefers-color-scheme:dark){.gs-choices .btn.gs-ans{border-color:#5cc28e;outline-color:#5cc28e}
  .gs-choices .btn.gs-miss{border-color:#e0965a;outline-color:#e0965a}}
.gs-choices .btn:disabled{cursor:default;opacity:1}
.gs-words{position:absolute;left:-9999px}
</style>"""


def guess_page_html(stocks: Iterable[dict], base_url: str, app_url: str,
                    day: Optional[date] = None) -> str:
    from utils.quiz_page import _CSS as QZ_CSS, _day_label
    day = day or date.today()
    rounds = guess_rounds(stocks, day)
    canonical = f"{base_url}/guess"
    title = "Whose fingerprint? A daily game: match the stock to its economic profile"
    desc = ("Five rounds a day: see how a mystery U.S. stock has moved with interest rates, inflation, "
            "the dollar, oil and credit, and pick it out of four.")
    crumb = '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Whose fingerprint?</nav>'
    ld = {"@context": "https://schema.org", "@type": "Game", "name": title, "url": canonical,
          "description": desc, "isAccessibleForFree": True}
    if not rounds:
        body = (crumb + '<h1>Whose fingerprint?</h1><p class="lead">Not enough stocks have been measured '
                'yet for a fair game. Readings are added each week.</p>')
        return _shell(title, desc, canonical, ld, body, app_url, robots="noindex, follow")
    payload = json.dumps(rounds, separators=(",", ":")).replace("</", "<\\/")
    body = (
        QZ_CSS + _RC_CSS + _CSS + crumb + '<h1>Whose fingerprint?</h1>'
        f'<p class="lead">{escape(desc)}</p>'
        f'<div class="qz" id="gs-box" data-day="{escape(_day_label(day))}" data-url="{escape(canonical)}">'
        '<noscript><p class="lead">The game needs JavaScript. Every profile is on its '
        '<a href="/exposure">stock page</a>.</p></noscript></div>'
        '<p aria-live="polite" id="gs-say" style="position:absolute;left:-9999px"></p>'
        '<p class="small">Each row is the stock&#39;s typical weekly move in weeks when that force moved by '
        'its standard amount, beyond the stock market&#39;s own move, with its 90% range. Coloured dots '
        'held up; hollow ones could not be told apart from zero. Every mystery stock has at least two '
        'readings that held up, and the other choices have clearly different profiles. Everyone gets the '
        'same five rounds today.</p>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here is a '
        'recommendation to buy, sell or hold any security.</p>'
        f'<script type="application/json" id="gs-data">{payload}</script>'
        f'<script>{_SCRIPT.replace("/*PCT*/", JS_PCT)}</script>')
    return _shell(title, desc, canonical, ld, body, app_url)
