"""The learning track: streaks, XP, levels and the five-step path.

What must hold:
  * only the first play of a day's quiz or game earns XP -- replaying a round
    whose answers you have seen cannot farm a level;
  * a streak counts consecutive days played, still stands on a day not yet
    played, and breaks after a missed day;
  * levels follow LEVELS, and path steps add STEP_XP once each;
  * a blocked or corrupt store shows a fresh start instead of breaking the page;
  * every page in the path records its step, and the path is in the HTML
    (readable without JavaScript).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date

import pytest

from utils import progress as pg

NODE = shutil.which("node")

HARNESS = r"""
var store = {}, blocked = false, now = new Date(2026, 10, 17, 12);
global.window = global;
global.localStorage = {
  getItem: function(k){ if (blocked) throw new Error('blocked'); return k in store ? store[k] : null; },
  setItem: function(k, v){ if (blocked) throw new Error('blocked'); store[k] = String(v); }
};
__JS__
UAP._clock(function(){ return new Date(now.getTime()); });
function day(n){ now = new Date(2026, 10, 17 + n, 12); }
var out = {};
__STEPS__
process.stdout.write(JSON.stringify(out));
"""


def _run(steps: str) -> dict:
    js = HARNESS.replace("__JS__", pg.progress_js()).replace("__STEPS__", steps)
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=30, check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


@needs_node
def test_only_the_first_play_of_the_day_earns_xp():
    out = _run("""
      out.a = UAP.record('quiz', 7, 10);
      out.b = UAP.record('quiz', 10, 10);          // replay, now knowing the answers
      out.c = UAP.record('guess', 5, 5);
    """)
    quiz_play, quiz_right = pg.GAME_XP["quiz"]
    first = quiz_play + 7 * quiz_right + pg.STEP_XP          # the quiz step is done too
    assert out["a"]["counted"] and out["a"]["gained"] == first and out["a"]["xp"] == first
    assert not out["b"]["counted"] and out["b"]["gained"] == 0 and out["b"]["xp"] == first
    assert out["b"]["right"]["quiz"] == 7 and out["b"]["asked"]["quiz"] == 10
    g_play, g_right = pg.GAME_XP["guess"]
    assert out["c"]["xp"] == first + g_play + 5 * g_right + pg.STEP_XP


@needs_node
def test_a_streak_counts_days_in_a_row_and_breaks_on_a_missed_day():
    out = _run("""
      UAP.record('quiz', 5, 10); day(1); UAP.record('guess', 3, 5); day(2); UAP.record('quiz', 6, 10);
      out.three = UAP.summary().streak;
      day(3); out.notYet = UAP.summary().streak;     // today not played yet: still stands
      day(4); out.broken = UAP.summary().streak;     // a whole day missed
      UAP.record('quiz', 1, 10); out.fresh = UAP.summary().streak;
    """)
    assert (out["three"], out["notYet"], out["broken"], out["fresh"]) == (3, 3, 0, 1)


@needs_node
def test_levels_and_path_steps():
    out = _run("""
      out.start = UAP.summary();
      out.first = UAP.mark('learn'); out.again = UAP.mark('learn'); out.bogus = UAP.mark('nope');
      ['explore', 'xray'].forEach(UAP.mark);
      out.after = UAP.summary();
      for (var i = 0; i < 20; i++) { day(i); UAP.record('quiz', 10, 10); UAP.record('guess', 5, 5); }
      out.top = UAP.summary();
      out.line = UAP.line(UAP.record('quiz', 10, 10));
    """)
    assert out["start"]["level"] == pg.LEVELS[0][1] and out["start"]["xp"] == 0
    assert out["start"]["toNext"] == pg.LEVELS[1][0]
    assert out["first"] is True and out["again"] is False and out["bogus"] is False
    assert out["after"]["xp"] == 3 * pg.STEP_XP and out["after"]["stepsDone"] == 3
    assert out["after"]["level"] == "Reader"                    # 150 XP
    assert out["top"]["level"] == pg.LEVELS[-1][1] and out["top"]["next"] is None
    assert out["top"]["stepsDone"] == len(pg.STEPS) and out["top"]["streak"] == 20
    assert "replays are practice" in out["line"] and 'href="/learn#path"' in out["line"]


@needs_node
def test_a_blocked_or_corrupt_store_is_a_fresh_start():
    out = _run("""
      store[UAP._key] = '{not json'; out.corrupt = UAP.summary().xp;
      store[UAP._key] = 'null'; out.nul = UAP.summary().xp;
      blocked = true; out.rec = UAP.record('quiz', 4, 10); out.sum = UAP.summary();
    """)
    assert out["corrupt"] == 0 and out["nul"] == 0
    assert out["sum"]["xp"] == 0 and out["rec"]["level"] == pg.LEVELS[0][1]


def test_levels_ascend_and_the_path_matches_the_pages():
    assert [x for x, _ in pg.LEVELS] == sorted({x for x, _ in pg.LEVELS}) and pg.LEVELS[0][0] == 0
    assert [s[0] for s in pg.STEPS] == ["learn", "quiz", "guess", "explore", "xray"]


def _stocks():
    from tests.test_quiz_page import _library  # the quiz's synthetic library
    return _library()


def test_every_page_in_the_path_records_its_step():
    from utils.explore_page import explore_page_html
    from utils.guess_page import guess_page_html
    from utils.learn_page import learn_page_html
    from utils.quiz_page import quiz_page_html
    from utils.xray_page import xray_page_html
    B, A = "https://seo.example", "https://app.example"
    stocks = _stocks()
    quiz = quiz_page_html(stocks, B, A, day=date(2026, 11, 17))
    from tests.test_guess_page import _library as guess_library
    guess = guess_page_html(guess_library(), B, A, day=date(2026, 11, 17))
    assert "gs-data" in guess                                 # a real game, not the empty page
    learn = learn_page_html(B, A)
    explore = explore_page_html(stocks, B, A)
    xray = xray_page_html(stocks, B, A)
    for html in (quiz, guess, learn, explore, xray):
        assert "window.UAP = window.UAP ||" in html
        assert html.index("window.UAP = window.UAP ||") < html.rindex("UAP.")   # defined before use
    assert "UAP.record('quiz', score, Q.length)" in quiz
    assert "UAP.record('guess', score, R.length)" in guess
    assert "UAP.mark('explore')" in explore and "UAP.mark('xray')" in xray
    assert "UAP.mark('learn')" in learn
    # The path is in the HTML itself, in order, each step linking to its page.
    pos = [learn.index(f'data-step="{k}"') for k, *_ in pg.STEPS]
    assert pos == sorted(pos)
    for _, title, _, href in pg.STEPS:
        assert f'<a href="{href}"><b>{title}</b></a>' in learn
    assert "not sent anywhere" in learn and "not investing skill" in learn


@needs_node
def test_a_tool_use_is_counted_once_per_page_even_before_the_beacon_loads():
    """utils/progress queues uses that happen before the page's beacon script
    (it sits at the end of <body>); the beacon flushes them and sends later
    ones directly. Repeats on the same page are not counted again."""
    import json as _json
    from utils.exposure_pages import _TRACK_JS
    beacon = _TRACK_JS.replace("__LABEL__", _json.dumps("Quiz"))
    out = _run("""
      var sent = [];
      Object.defineProperty(global, 'navigator', {value: {sendBeacon: function(u, blob){ sent.push(blob); return true; }}, configurable: true});
      global.Blob = function(parts){ this.text = parts.join(''); };
      UAP.record('quiz', 4, 10); UAP.record('quiz', 9, 10);    // before the beacon: queued once
      out.queued = (window.uaQ || []).slice();
      eval(BEACON);
      UAP.used('quiz'); UAP.used('guess'); UAP.used('guess');  // after: direct, deduped
      out.sent = sent.map(function(b){ return JSON.parse(b.text); });
    """.replace("BEACON", _json.dumps(beacon)))
    assert out["queued"] == ["quiz"]
    assert out["sent"] == [{"event": "page_view", "page": "Quiz"},
                           {"event": "tool_used", "page": "Quiz", "tool": "quiz"},
                           {"event": "tool_used", "page": "Quiz", "tool": "guess"}]
