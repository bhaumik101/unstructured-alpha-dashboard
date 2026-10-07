# utils/learn_page.py
# Unstructured Alpha — how to read these pages
#
# Every public page uses the same handful of ideas: a typical weekly move,
# "beyond the market", a 90% range, and three evidence labels. Each page
# explains them in a footnote; this is the one place that explains them
# properly, with a worked example, for someone who has never read a
# regression table.
#
# RULES
#   * Every number here comes from utils/exposure (window, bars, shocks), so
#     the explanation cannot drift from what the engine does.
#   * The example is labelled as an illustration, never as a real stock.

from __future__ import annotations

from html import escape

from utils import exposure as ex
from utils.exposure_pages import _chip, _shell

SECTIONS = ("move", "market", "range", "evidence", "extras", "limits")


def learn_page_html(base_url: str, app_url: str) -> str:
    canonical = f"{base_url}/learn"
    title = "How to read stock exposure: weekly moves, 90% ranges and evidence labels"
    desc = ("A plain-English guide to every figure on Unstructured Alpha: what a stock's typical "
            "weekly move with oil or interest rates means, what the 90% range tells you, and when "
            "a reading counts as Clear.")
    years = ex.WINDOW_WEEKS // 52
    min_years = ex.MIN_WEEKS // 52
    n_tests = len(ex.FACTORS) + len(ex.EXTRA_FACTORS)
    shocks = "".join(f'<li><b>{escape(f.label)}:</b> {escape(f.shock_phrase)}</li>' for f in ex.FACTORS)
    toc = "".join(f'<li><a href="#{k}">{t}</a></li>' for k, t in zip(SECTIONS, (
        "The typical weekly move", "Beyond the market", "The 90% range", "Clear, Tentative, or not",
        "Beyond the core five", "What this cannot tell you")))
    # The worked example: a range bar drawn to scale, labelled as an illustration.
    lo, mid, hi = 1.4, 2.4, 3.4
    scale = 4.0

    def pos(v: float) -> str:
        return f"{50 + 50 * v / scale:.1f}%"
    example = (
        '<figure class="lx" aria-label="Illustration: a reading of +2.4% with a 90% range of +1.4% to +3.4%">'
        '<div class="lx-axis"><span class="lx-zero" style="left:50%"></span>'
        f'<span class="lx-range" style="left:{pos(lo)};width:{50 * (hi - lo) / scale:.1f}%"></span>'
        f'<span class="lx-dot" style="left:{pos(mid)}"></span></div>'
        '<div class="lx-ticks"><span>−4%</span><span>0</span><span>+4%</span></div>'
        '<figcaption>Illustration, not a real stock: a typical move of <b>+2.4%</b> in weeks when oil rose '
        '10%, with a 90% range of +1.4% to +3.4%. The whole range sits above zero.</figcaption></figure>')
    body = (
        '<style>.lx{margin:14px 0 18px;max-width:560px}.lx-axis{position:relative;height:28px}'
        '.lx-axis::before{content:"";position:absolute;left:0;right:0;top:13px;height:2px;background:var(--line)}'
        '.lx-zero{position:absolute;top:4px;bottom:4px;width:2px;background:var(--ink3)}'
        '.lx-range{position:absolute;top:9px;height:10px;border-radius:5px;background:var(--accent);opacity:.35}'
        '.lx-dot{position:absolute;top:7px;width:14px;height:14px;margin-left:-7px;border-radius:50%;background:var(--accent)}'
        '.lx-ticks{display:flex;justify-content:space-between;font-size:.82rem;color:var(--ink3)}'
        '.lx figcaption{font-size:.92rem;color:var(--ink2);margin-top:6px}'
        '.toc{list-style:none;display:flex;flex-wrap:wrap;gap:8px 18px;margin:0 0 10px}'
        '.learn h2{scroll-margin-top:16px}.learn p,.learn ul{max-width:760px;margin-bottom:12px;color:var(--ink2)}'
        '.learn ul{padding-left:20px}</style>'
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › How to read these pages</nav>'
        '<h1>How to read these pages</h1>'
        f'<p class="lead">{escape(desc)}</p>'
        f'<ul class="toc" aria-label="On this page">{toc}</ul>'
        '<div class="learn">'
        '<h2 id="move">The typical weekly move</h2>'
        f'<p>Each reading answers one question: <b>in a week when this force moved by a set amount, how '
        f'did the stock typically move?</b> It is measured over the last {years} years of weekly returns. '
        'The set amounts are deliberately ordinary weeks, not crises:</p>'
        f'<ul>{shocks}</ul>'
        '<p>So "+2.4% with oil" means: in weeks when oil rose 10%, the stock typically rose about 2.4% more '
        'than it otherwise would have. A negative figure means it typically fell. Moves scale roughly in '
        'a straight line, so half the oil move means about half the stock move.</p>'
        '<h2 id="market">Beyond the market</h2>'
        '<p>Most stocks rise and fall with the market as a whole, and the market itself reacts to oil, '
        'rates and the rest. Each reading is measured <b>after removing the stock market&#39;s own move</b>, '
        'and the five core forces are measured together, so each shows what that one force adds on its '
        'own. A stock can rise in a week when oil rose because everything rose; that part is not counted '
        'as oil.</p>'
        '<h2 id="range">The 90% range</h2>'
        '<p>Three years of weekly data pin a reading down only so far. The 90% range is the band the true '
        'figure very likely sits in, given how noisy the weeks were. A narrow range is a precise '
        'reading; a wide one, a rough one.</p>'
        f'{example}'
        '<p>The single most useful thing to check is <b>whether the range crosses zero</b>. If it does, the '
        'data cannot rule out that the stock has no link to that force at all.</p>'
        '<h2 id="evidence">Clear, Tentative, or not</h2>'
        '<p>Every reading carries one of three labels, from how far the figure sits from zero relative to '
        'its own noise:</p><ul>'
        f'<li>{_chip("clear")} The figure is far enough from zero that chance is an unlikely explanation, '
        f'even allowing for the fact that five forces are tested at once (|t| ≥ {ex.CLEAR_T:.2f}).</li>'
        f'<li>{_chip("tentative")} The 90% range excludes zero, but the bar for Clear is not met '
        f'(|t| ≥ {ex.Z90:.2f}). Worth noting, not worth leaning on.</li>'
        f'<li>{_chip("indistinct")} The range includes zero: no link that can be told apart from noise. '
        'This is the most common answer, and it is an answer, not a gap.</li></ul>'
        f'<p>A stock with fewer than {min_years} years of weekly prices gets no label at all: too little '
        'data to say anything. Pages rank and count only Clear and Tentative readings; the rest are shown '
        'grey, never dropped and never ranked.</p>'
        '<h2 id="extras">Beyond the core five</h2>'
        f'<p>The other forces (short-term rates, gold, bitcoin, the yen and more; {n_tests} in all) are each '
        'measured with the stock market and the core five held fixed, so they show only what those do not '
        f'already explain. Because so many are tested, their bar for Clear is stricter (|t| ≥ '
        f'{ex.EXTRA_CLEAR_T:.2f}).</p>'
        '<h2 id="limits">What this cannot tell you</h2>'
        '<ul><li><b>It is the past, not a forecast.</b> A stock that moved with oil for three years may '
        'not over the next three. The <a href="/evidence">track record</a> measures how often readings '
        'held up a year later.</li>'
        '<li><b>It is not cause and effect.</b> A reading says the two moved together, not why.</li>'
        '<li><b>It is not advice.</b> Nothing here is a recommendation to buy, sell or hold any security.</li></ul>'
        '</div>'
        '<div class="actions"><a class="btn btn-primary" href="/exposure">See every stock</a>'
        '<a class="btn btn-secondary" href="/explore">Try a move</a>'
        f'<a class="btn btn-secondary" href="{escape(app_url)}/methodology">Full methodology</a></div>')
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": title,
          "description": desc, "url": canonical,
          "publisher": {"@type": "Organization", "name": "Unstructured Alpha"}}
    return _shell(title, desc, canonical, ld, body, app_url)
