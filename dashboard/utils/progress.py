# utils/progress.py
# Unstructured Alpha — the learning track: streaks, XP and a five-step path
#
# The daily quiz and fingerprint game, the What-if tool, the X-ray and the
# guide's playground each teach one idea. This ties them into a path a
# visitor can work through and come back to: a level, a daily streak, an
# accuracy figure, and the steps done and left.
#
# RULES
#   * Progress lives in this browser only (localStorage). Nothing is sent to
#     the server, no account is needed, and a blocked or empty store simply
#     shows a fresh start -- the pages work the same without it.
#   * Only the first play of a day's quiz or game earns XP, so replaying a
#     round you have just seen the answers to cannot farm a level.
#   * It measures the visitor's practice, never a market call: no level or
#     badge says anything about how to invest.

from __future__ import annotations

from html import escape

# (key, title, what it teaches, href)
STEPS = (
    ("learn", "Read a reading", ("Move the playground on this page: a typical move, its 90% range, and "
      "when it counts as Clear."), "/learn#evidence"),
    ("quiz", "Which way did it move?", ("Ten questions on whether a stock rose, fell, or showed no "
      "clear link when a force moved."), "/quiz"),
    ("guess", "Whose fingerprint?", "Match a stock to its five-force profile.", "/guess"),
    ("explore", "What if? Move a force", ("Drag oil, rates or the dollar and see which stocks have "
      "typically moved with it."), "/explore"),
    ("xray", "X-ray a portfolio", "Add two or more holdings and see the mix's biggest driver.", "/xray"),
)
STEP_XP = 50
# (XP needed, name). A day's two games are worth at most 240 XP.
LEVELS = ((0, "Newcomer"), (100, "Reader"), (300, "Apprentice"), (700, "Analyst"),
          (1500, "Senior analyst"), (3000, "Macro strategist"))
GAME_XP = {"quiz": (20, 10), "guess": (20, 20)}    # (for playing, per right answer)

PROGRESS_JS = r"""
window.UAP = window.UAP || (function(){
  var K = 'ua_progress_v1', KEEP = 400, STEP_XP = __STEP_XP__, STEPS = __STEPS__, LEVELS = __LEVELS__, GAME = __GAME__;
  var clock = function(){ return new Date(); };
  function pad(n){ return (n < 10 ? '0' : '') + n; }
  function iso(d){ return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
  function load(){ try { var p = JSON.parse(localStorage.getItem(K) || '{}'); return p && typeof p === 'object' ? p : {}; } catch (e) { return {}; } }
  function save(p){
    var days = Object.keys(p.d || {}).sort();
    days.slice(0, Math.max(0, days.length - KEEP)).forEach(function(k){ delete p.d[k]; });
    try { localStorage.setItem(K, JSON.stringify(p)); } catch (e) {}
  }
  function norm(p){ p.d = p.d || {}; p.l = p.l || {}; return p; }
  function streak(p){
    var d = clock(), n = 0;
    if (!p.d[iso(d)]) d.setDate(d.getDate() - 1);     // today not played yet: the streak still stands
    while (p.d[iso(d)]) { n++; d.setDate(d.getDate() - 1); }
    return n;
  }
  function summary(p){
    p = norm(p);
    var xp = 0, right = {quiz: 0, guess: 0}, asked = {quiz: 0, guess: 0};
    STEPS.forEach(function(s){ if (p.l[s]) xp += STEP_XP; });
    Object.keys(p.d).forEach(function(day){
      Object.keys(GAME).forEach(function(g){ var r = p.d[day][g];
        if (r) { xp += GAME[g][0] + GAME[g][1] * r[0]; right[g] += r[0]; asked[g] += r[1]; } });
    });
    var lv = 0; LEVELS.forEach(function(L, i){ if (xp >= L[0]) lv = i; });
    var next = LEVELS[lv + 1];
    return {xp: xp, level: LEVELS[lv][1], levelNo: lv + 1, next: next ? next[1] : null,
            toNext: next ? next[0] - xp : 0, floor: LEVELS[lv][0], ceil: next ? next[0] : xp,
            streak: streak(p), today: p.d[iso(clock())] || {}, steps: p.l, right: right, asked: asked,
            stepsDone: STEPS.filter(function(s){ return p.l[s]; }).length, stepsAll: STEPS.length};
  }
  function mark(step){
    var p = norm(load()), fresh = STEPS.indexOf(step) >= 0 && !p.l[step];
    if (fresh) { p.l[step] = 1; save(p); }
    return fresh;
  }
  // A finished daily round. Only the first of the day counts; returns the
  // summary with .gained (XP this play added) and .counted.
  function record(game, score, of){
    var p = norm(load()), day = iso(clock()), e = p.d[day] = p.d[day] || {}, before = summary(load()).xp;
    var counted = !e[game] && GAME.hasOwnProperty(game);
    if (counted) e[game] = [Math.max(0, Math.min(+score || 0, +of || 0)), +of || 0];
    else if (!Object.keys(e).length) delete p.d[day];
    p.l[game] = 1;
    save(p);
    used(game);
    var s = summary(load()); s.counted = counted; s.gained = s.xp - before; return s;
  }
  // Count the first real use of a tool on this page (seo/track_api tool_used).
  // Queued if the page's beacon script, at the end of <body>, has not run yet.
  var usedNow = {};
  function used(tool){
    if (usedNow[tool]) return; usedNow[tool] = 1;
    if (window.uaUsed) window.uaUsed(tool); else (window.uaQ = window.uaQ || []).push(tool);
  }
  // One line for the end of a round, as HTML. Links to the path.
  function line(s){
    var bits = [s.streak === 1 ? '1-day streak' : s.streak + '-day streak',
                s.level + ', ' + s.xp + ' XP' + (s.gained ? ' (+' + s.gained + ')' : '')];
    if (s.next) bits.push(s.toNext + ' XP to ' + s.next);
    return '<p class="uap-line">' + bits.join(' · ') + (s.counted ? '' : '. Today&#39;s first play already counted; replays are practice')
      + '. <a href="/learn#path">Your learning path</a></p>';
  }
  return {load: load, summary: function(){ return summary(load()); }, mark: mark, record: record, line: line, used: used,
          _clock: function(f){ clock = f; }, _key: K};
})();
"""

PROGRESS_CSS = (
    '<style>.uap-line{margin:12px 0 0;padding:10px 12px;border-radius:10px;background:var(--surface2,rgba(47,111,189,.07));'
    'font-variant-numeric:tabular-nums}</style>')


def progress_js() -> str:
    import json
    return (PROGRESS_JS.replace("__STEP_XP__", str(STEP_XP))
            .replace("__STEPS__", json.dumps([s[0] for s in STEPS]))
            .replace("__LEVELS__", json.dumps([list(x) for x in LEVELS]))
            .replace("__GAME__", json.dumps({k: list(v) for k, v in GAME_XP.items()})))


def progress_script() -> str:
    """The shared progress store and its line style, for any page that records
    or shows progress."""
    return PROGRESS_CSS + f"<script>{progress_js()}</script>"


def mark_on(element_id: str, event: str, step: str) -> str:
    """Mark a path step the first time the visitor uses a control."""
    return (f"<script>(function(){{var el=document.getElementById('{element_id}');"
            f"if(el&&window.UAP)el.addEventListener('{event}',function(){{UAP.mark('{step}');UAP.used('{step}');}},{{once:true}});}})();</script>")


_TRACK_SCRIPT = r"""
(function(){
  if (!window.UAP) return;
  var s = UAP.summary(), box = document.getElementById('trk-me');
  var pct = s.next ? Math.round(100 * (s.xp - s.floor) / (s.ceil - s.floor)) : 100;
  var acc = function(g, what){ return s.asked[g] ? Math.round(100 * s.right[g] / s.asked[g]) + '% right over ' + s.asked[g] + ' ' + what : 'not played yet'; };
  var today = function(g, name, href){ var r = s.today[g];
    return r ? '<li class="trk-done"><span aria-hidden="true">✓</span> ' + name + ': ' + r[0] + ' of ' + r[1] + '</li>'
             : '<li><a href="' + href + '">' + name + '</a>: not played today</li>'; };
  box.innerHTML = '<div class="trk-top"><div><p class="trk-k small">Level ' + s.levelNo + '</p><p class="trk-v">' + s.level + '</p></div>'
    + '<div><p class="trk-k small">Streak</p><p class="trk-v">' + (s.streak ? s.streak + (s.streak === 1 ? ' day' : ' days') : 'Start today') + '</p></div>'
    + '<div><p class="trk-k small">Path</p><p class="trk-v">' + s.stepsDone + ' of ' + s.stepsAll + '</p></div></div>'
    + '<div class="trk-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pct + '" aria-label="Progress to the next level">'
    + '<i style="width:' + pct + '%"></i></div>'
    + '<p class="small">' + s.xp + ' XP' + (s.next ? ' · ' + s.toNext + ' to ' + s.next : ' · top level') + '. Quiz: ' + acc('quiz', 'questions')
    + '. Fingerprint: ' + acc('guess', 'rounds') + '.</p>'
    + '<ul class="trk-today" aria-label="Today">' + today('quiz', 'Daily quiz', '/quiz') + today('guess', 'Fingerprint game', '/guess') + '</ul>';
  document.querySelectorAll('[data-step]').forEach(function(li){
    if (s.steps[li.getAttribute('data-step')]) { li.classList.add('trk-ok'); li.querySelector('.trk-st').textContent = 'Done'; }
  });
})();
"""

TRACK_CSS = (
    '.trk{padding:16px 18px;margin:10px 0 18px}.trk h2{margin:0 0 4px}'
    '.trk-top{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:8px 0 10px}'
    '.trk-k{margin:0;color:var(--ink3)}.trk-v{margin:0;font-weight:750;color:var(--ink)}'
    '.trk-bar{height:8px;border-radius:4px;background:var(--line);overflow:hidden}'
    '.trk-bar i{display:block;height:100%;background:var(--accent)}'
    '.trk-today{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 0}'
    '.trk-done{color:var(--ink2)}'
    '.trk-path{list-style:none;padding:0;margin:14px 0 0;counter-reset:st;display:grid;gap:8px}'
    '.trk-path li{display:grid;grid-template-columns:28px minmax(0,1fr) auto;gap:10px;align-items:start}'
    '.trk-path li::before{counter-increment:st;content:counter(st);display:grid;place-items:center;width:26px;height:26px;'
    'border-radius:50%;border:1px solid var(--line);color:var(--ink3);font-variant-numeric:tabular-nums}'
    '.trk-path li.trk-ok::before{content:"\\2713";background:var(--accent);border-color:var(--accent);color:#fff}'
    '.trk-path p{margin:0;color:var(--ink2)}.trk-st{color:var(--ink3);white-space:nowrap}'
)


def track_html() -> str:
    """The learning path card for /learn: the visitor's level, streak and
    accuracy (filled in the browser) over the five steps (in the HTML, so
    the path reads the same without JavaScript)."""
    steps = "".join(
        f'<li data-step="{k}"><div><a href="{href}"><b>{escape(title)}</b></a>'
        f'<p>{escape(what)}</p></div><span class="trk-st small">+{STEP_XP} XP</span></li>'
        for k, title, what, href in STEPS)
    return (
        f'<style>{TRACK_CSS}</style>'
        '<section class="card trk" id="path" aria-labelledby="trk-h">'
        '<h2 id="trk-h">Your learning path</h2>'
        '<div id="trk-me" aria-live="polite"></div>'
        f'<ol class="trk-path">{steps}</ol>'
        '<p class="small">Play the daily quiz and fingerprint game to build a streak; a day&#39;s first play '
        'earns XP for each right answer. Your progress stays in this browser and is not sent anywhere. '
        'Levels measure practice reading the data, not investing skill.</p></section>'
        + progress_script() + f"<script>{_TRACK_SCRIPT}</script>")
