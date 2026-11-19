"""A shared quiz result previews as itself, with no spoilers.

What must hold:
  * the result link carries right/wrong per question and the day -- never the
    answers -- and a shared link titles the page and its card with the score;
  * only a well-formed result is read; anything else is the plain quiz page;
  * the card is a real 1200x630 PNG; nonsense is a 404; the canonical stays /quiz.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from tests.test_explore_page import client  # noqa: F401  (fixture)
from tests.test_quiz_page import _library
from utils import quiz_share as qs
from utils.quiz_page import quiz_page_html


def test_only_a_well_formed_result_is_read():
    assert qs.parse("1101", "2026-11-19", today=date(2026, 11, 19)) == ([1, 1, 0, 1], date(2026, 11, 19))
    for g, d in (("", "2026-11-19"), ("12", "2026-11-19"), ("1" * 21, "2026-11-19"), ("1101", "nope"),
                 ("1101", "2027-01-01"), ("1101", "2020-01-01"), ("<b>", "2026-11-19")):
        assert qs.parse(g, d, today=date(2026, 11, 19)) is None, (g, d)


def test_the_result_link_carries_right_and_wrong_but_never_the_answers():
    html = quiz_page_html(_library(), "https://www.x", "https://app.x", day=date(2026, 11, 19))
    assert "'?g=' + marks.map" in html and "'&d=' + box.getAttribute('data-iso')" in html
    assert 'data-iso="2026-11-19"' in html
    assert "navigator.share" in html


def test_a_shared_result_gets_its_own_title_and_card():
    plain = quiz_page_html(_library(), "https://www.x", "https://app.x", day=date(2026, 11, 19))
    shared = quiz_page_html(_library(), "https://www.x", "https://app.x", day=date(2026, 11, 19),
                            g="1101101110", d="2026-11-19")
    assert "7/10 on today" in shared and "7/10 on today" not in plain
    assert 'og:image" content="https://www.x/quiz/og.png?g=1101101110&amp;d=2026-11-19"' in shared
    assert '<link rel="canonical" href="https://www.x/quiz">' in shared
    bad = quiz_page_html(_library(), "https://www.x", "https://app.x", day=date(2026, 11, 19),
                         g="<script>", d="x")
    assert "<script>" not in bad.split("<body")[0] and "7/10" not in bad


def test_the_card_is_a_png_and_nonsense_is_a_404(client):  # noqa: F811
    c, *_ = client
    r = c.get("/quiz/og.png?g=1101101110&d=2026-11-19")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert (int.from_bytes(r.content[16:20], "big"), int.from_bytes(r.content[20:24], "big")) == (1200, 630)
    assert c.get("/quiz/og.png?g=abc&d=2026-11-19").status_code == 404
    assert c.get("/quiz/og.png").status_code == 404


def test_www_proxies_the_card():
    cfg = (Path(__file__).resolve().parents[1] / "unstructured-alpha-web" / "next.config.ts").read_text()
    assert 'source: "/quiz/og.png"' in cfg


def test_the_fingerprint_game_shares_the_same_way(client):  # noqa: F811
    from tests.test_guess_page import _library as guess_library
    from utils.guess_page import guess_page_html
    html = guess_page_html(guess_library(), "https://www.x", "https://app.x", day=date(2026, 11, 19))
    assert "'?g=' + marks.map" in html and 'data-iso="2026-11-19"' in html and "navigator.share" in html
    shared = guess_page_html(guess_library(), "https://www.x", "https://app.x", day=date(2026, 11, 19),
                             g="10110", d="2026-11-19")
    assert "3/5 on today" in shared and "“Whose fingerprint?”" in shared
    assert 'og:image" content="https://www.x/guess/og.png?g=10110&amp;d=2026-11-19"' in shared
    assert '<link rel="canonical" href="https://www.x/guess">' in shared
    c, *_ = client
    r = c.get("/guess/og.png?g=10110&d=2026-11-19")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert c.get("/guess/og.png?g=x&d=2026-11-19").status_code == 404
    cfg = (Path(__file__).resolve().parents[1] / "unstructured-alpha-web" / "next.config.ts").read_text()
    assert 'source: "/guess/og.png"' in cfg
