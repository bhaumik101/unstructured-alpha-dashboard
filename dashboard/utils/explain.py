# utils/explain.py
# Unstructured Alpha — making the report readable for a first-time investor
#
# Two aids, both on top of the numbers and never changing them:
#
#   * A glossary. The words a newcomer stops at (credit spreads, the 90% range,
#     "Clear", beta) are underlined with dots; hovering or tapping one opens a
#     plain-English definition. Where the SEC's investor-education site
#     (Investor.gov) has a page on the idea, the definition links to it, so
#     regulated terms are explained by the regulator, not by us. Only pages
#     confirmed to exist are linked (checked 2026-11-25); the rest carry our
#     own one-line explanation and no link.
#
#   * Dollars. "−0.56%" means little until it is money. The report carries
#     each estimate as a percent in a data attribute; a small script in the
#     page (DOLLARS_JS, injected by scripts/inject_boot_splash.py because
#     st.markdown drops <script>) turns it into "≈ −$56 on $10,000" for an
#     amount the visitor types. The amount never leaves the browser.
#
# RULES
#   * A definition explains a word; it never characterises this portfolio.
#   * Dollar figures are the same past estimate times the amount, labelled as
#     a typical same-week move, never a forecast or a loss limit.

from __future__ import annotations

from html import escape
from typing import Dict, NamedTuple, Optional

IG = "https://www.investor.gov/introduction-investing"


class Term(NamedTuple):
    label: str
    text: str
    url: Optional[str] = None          # an Investor.gov page, only where one exists


GLOSSARY: Dict[str, Term] = {
    "etf": Term("ETF (exchange-traded fund)",
                "A fund that holds many investments and trades on a stock exchange like a single share.",
                f"{IG}/investing-basics/glossary/exchange-traded-fund-etf"),
    "mutual_fund": Term("Mutual fund",
                        "A fund that pools many people's money into stocks, bonds or both; its shares are "
                        "priced once a day, at the close.",
                        f"{IG}/investing-basics/glossary/mutual-funds"),
    "index_fund": Term("Index fund",
                       "A fund that tries to match a market index, such as the S&P 500, instead of picking investments.",
                       f"{IG}/investing-basics/glossary/index-fund"),
    "bonds": Term("Bonds",
                  "A loan to a government or company that pays interest; their prices fall when interest rates rise.",
                  f"{IG}/investing-basics/glossary/bonds"),
    "rates": Term("Interest rates (10-year Treasury yield)",
                  "The interest the U.S. government pays to borrow for ten years. It sets the tone for mortgage and "
                  "loan rates, and when it rises, existing bond prices fall.",
                  f"{IG}/general-resources/news-alerts/alerts-bulletins/investor-bulletins-86"),
    "interest_rate_risk": Term("Interest-rate risk",
                               "The chance that a bond fund's value drops because interest rates went up; "
                               "longer-dated bonds feel it more.",
                               f"{IG}/investing-basics/glossary/bond-funds-and-income-funds"),
    "credit": Term("Credit spreads",
                   "The extra interest companies pay over the U.S. government to borrow. It widens when lenders "
                   "worry more about companies not paying them back.",
                   f"{IG}/investing-basics/glossary/high-yield-bond-or-junk-bond"),
    "inflation": Term("Inflation expectations",
                      "How much prices are thought likely to rise per year over the next ten years, read here from "
                      "the gap between ordinary and inflation-protected Treasury bonds.",
                      f"{IG}/investing-basics/what-risk"),
    "dollar": Term("Trade-weighted U.S. dollar",
                   "The dollar's value against the currencies of the countries the U.S. trades with most, weighted "
                   "by how much it trades with each. A stronger dollar makes foreign holdings worth fewer dollars."),
    "oil": Term("Oil and energy",
                "The price of crude oil. It moves energy companies directly and everyone else through fuel and "
                "shipping costs."),
    "natgas": Term("Natural gas",
                   "The price of natural gas futures: heating, power plants and industry run on it."),
    "risk": Term("Risk",
                 "How uncertain an investment's return is, including the chance it returns less than you hoped.",
                 f"{IG}/investing-basics/what-risk"),
    "diversification": Term("Diversification",
                            "Spreading money across different investments so one bad outcome hurts less.",
                            f"{IG}/getting-started/asset-allocation"),
    "market": Term("Accounting for the stock market",
                   "Every estimate here is measured with the stock market's own move held fixed, so it shows what "
                   "this force adds on top of the market, not the market again."),
    "beta": Term("Moves with the market (beta)",
                 "How much the portfolio typically moves when the whole U.S. stock market moves 1%. 1.0× moves "
                 "with it; 0.5× moves half as much."),
    "range90": Term("90% range",
                    "The span the true figure most likely falls in, given how noisy the weekly data are. A narrow "
                    "range is a precise estimate; a range that crosses zero cannot rule out no effect."),
    "clear": Term("Clear",
                  "Strong enough to hold up even after allowing for testing several forces at once."),
    "tentative": Term("Tentative",
                      "Points one way, but not strongly enough to rule out chance. Treat it as a lead, not a finding."),
    "indistinct": Term("Not distinguishable",
                       "Could not be told apart from zero with this much data. That is not the same as having no "
                       "exposure: the effect may be small, or the data too short."),
    "term_premium": Term("Term premium",
                         "The extra yield investors want for tying money up in a ten-year bond instead of rolling "
                         "short-term ones. A New York Fed model estimates it."),
    "breakeven": Term("Breakeven inflation",
                      "The inflation rate at which an ordinary Treasury and an inflation-protected one would pay the "
                      "same; markets' implied inflation outlook."),
    "smb": Term("Size tilt (SMB)",
                "Small minus big: how much more the portfolio moves with small companies than with large ones."),
    "hml": Term("Value tilt (HML)",
                "High minus low: how much more the portfolio moves with cheap 'value' stocks than with fast-growing "
                "'growth' stocks."),
    "gdp": Term("Real GDP growth",
                "How fast the economy's output of goods and services grew, after removing inflation, stated as a "
                "yearly rate."),
}

# The force keys used by the report map straight onto glossary entries.
FORCE_TERM = {"rates": "rates", "inflation": "inflation", "dollar": "dollar", "oil": "oil",
              "credit": "credit", "natgas": "natgas"}
# How each force reads as the subject of a sentence: "the weeks the U.S. dollar moved most".
FORCE_SUBJECT = {"rates": "interest rates", "inflation": "inflation expectations", "dollar": "the U.S. dollar",
                 "oil": "oil prices", "credit": "credit spreads", "natgas": "natural gas prices"}
EVIDENCE_TERM = {"clear": "clear", "tentative": "tentative", "indistinct": "indistinct",
                 "not_enough_data": "indistinct"}


def term(key: str, text: Optional[str] = None) -> str:
    """`text` (default: the term's label), dotted-underlined, with its definition
    on hover, focus or tap. Unknown keys return the plain escaped text."""
    t = GLOSSARY.get(key)
    shown = escape(text if text is not None else (t.label if t else key))
    if not t:
        return shown
    link = (f' <a href="{escape(t.url)}" target="_blank" rel="noopener">More on Investor.gov ↗</a>'
            if t.url else "")
    return (f'<span class="ugl" tabindex="0">{shown}<span class="ugl-tip" role="tooltip">'
            f'<b>{escape(t.label)}</b>{escape(t.text)}{link}</span></span>')


def tip(shown: str, title: str, body: str, cls: str = "") -> str:
    """Like term(), for a one-off explanation that is not a glossary word."""
    return (f'<span class="ugl{(" " + cls) if cls else ""}" tabindex="0">{escape(shown)}<span class="ugl-tip" role="tooltip">'
            f'<b>{escape(title)}</b>{escape(body)}</span></span>')


def downgrade_note(reading: dict) -> str:
    """The "was Clear" marker for a reading that failed the new-weeks test."""
    d = reading.get("downgraded")
    if not d:
        return ""
    if d.get("reason") == "failed":
        body = (f"This reading passed the usual test, but readings of this force must also hold up on weeks "
                f"the estimate never saw, because across our tests they often did not. Re-measured on earlier weeks and checked on later ones, it matched "
                f"{d['hits']} of {d['big_weeks']} big weeks, so it is shown as Tentative.")
    else:
        body = ("This reading passed the usual test, but readings of this force must also hold up on weeks "
                "the estimate never saw, and there were too few weeks to check. It is shown as Tentative until it can be.")
    return tip("was Clear", "Downgraded after a stricter test", body, "uar-down")


def confirmed_note(reading: dict) -> str:
    """The "5-yr confirmed" marker for a Clear reading that is also Clear, the same
    way, on five years of data (exposure._confirm_long_window)."""
    if not reading.get("confirmed_5y"):
        return ""
    weeks = reading.get("confirm_weeks") or 260
    return tip("5-yr confirmed", "Confirmed on five years of data",
               f"Re-measured on {weeks} weeks instead of three years, this reading is Clear again and points the "
               "same way. In our walk-forward test across 35 funds, readings confirmed like this held their "
               "direction in 75% of the next year's big weeks, against 65% for Clear readings that were not.",
               "uar-conf")


TRACK_RECORD = ("Tested walk-forward on 35 funds over three held-out years, Clear readings held their direction in "
                "74% of the next year's big weeks (75% when confirmed on five years); weaker readings, 55%.")


# Walk-forward results for the extra forces (docs/RESEARCH_2026-11.md §9):
# key -> (% of next-year big weeks a Clear reading pointed the right way, big weeks tested).
EXTRA_TRACK = {"value": (82, 3552), "size": (71, 1627), "emerging": (78, 212), "copper": (72, 172),
               "euro": (85, 95), "short_rates": (97, 35), "volatility": (69, 107), "gold": (66, 541),
               "bitcoin": (64, 42), "momentum": (61, 189), "china": (56, 215), "natgas": (52, 48),
               "mortgage": (50, 26)}
EXTRA_PROVEN_MIN = (70, 150)          # held up at least 70% over at least 150 big weeks


def extra_proven(key: str) -> bool:
    held, n = EXTRA_TRACK.get(key, (0, 0))
    return held >= EXTRA_PROVEN_MIN[0] and n >= EXTRA_PROVEN_MIN[1]


def extra_verdict(key: str, reading: dict) -> str:
    """How far an extra force's Clear reading is backed by the walk-forward test."""
    held, n = EXTRA_TRACK.get(key, (0, 0))
    if extra_proven(key):
        return f"readings like this held up on new weeks {held}% of the time in our tests"
    if (reading.get("oos") or {}).get("passed"):
        o = reading["oos"]
        return f"it passed its own test on new weeks: {o['hits']} of {o['big_weeks']} big weeks matched"
    return "not yet tested enough on new weeks"


TRACK_RECORD_STOCKS = ("Tested the same way on 70 single stocks over three held-out years, Clear readings held their "
                       "direction in 71% of the next year's big weeks (74% when confirmed on five years); weaker "
                       "readings, 51-56%.")


def glossary_html(keys) -> str:
    """A compact glass card of the words used on the page: tap any to read it."""
    items = "".join(f'<li>{term(k)}</li>' for k in dict.fromkeys(keys) if k in GLOSSARY)
    if not items:
        return ""
    return ('<div class="uar"><div class="uxc ugl-card"><div class="uxc-head">'
            '<span class="uxc-k">Words used in this report</span>'
            '<span class="uxc-pill">Tap one to read it</span></div>'
            f'<ul class="ugl-list">{items}</ul>'
            '<div class="uxc-foot">Links marked Investor.gov go to the U.S. Securities and Exchange Commission\'s '
            'investor-education site.</div></div></div>')


DEFAULT_AMOUNT = 10000


def usd(pct: float) -> str:
    """A placeholder the script fills with the dollar figure for the chosen amount."""
    return f'<span class="uar-usd" data-pct="{pct:.4f}" aria-live="polite"></span>'


def usd_verb(pct: float) -> str:
    """Inline "lost about $56" / "gained about $56" for the chosen amount, with
    the dollar-free wording as the fallback text before the script runs."""
    word = "lost" if pct < 0 else "gained"
    return (f'<span class="uar-usd uar-usd-verb" data-pct="{pct:.4f}" data-mode="verb">'
            f'{word} about {abs(pct):.2f}%</span>')


def usd_abs(pct: float) -> str:
    """Inline "$56" (no sign) for the chosen amount; the percent before the script runs."""
    return (f'<span class="uar-usd uar-usd-verb" data-pct="{abs(pct):.4f}" data-mode="abs">'
            f'{abs(pct):.2f}%</span>')


def amount_input(label: str = "Amount invested") -> str:
    """An inline amount box; every box on the page stays in step (DOLLARS_JS)."""
    return (f'<label class="uusd-box uusd-inline"><span>$</span><input class="uusd-in" inputmode="numeric" '
            f'autocomplete="off" aria-label="{escape(label)}" placeholder="{DEFAULT_AMOUNT:,}"></label>')


def dollars_bar_html() -> str:
    """The amount box over the exposure table. The script reads and fills it.

    No value attribute: Streamlit renders this HTML as React elements, and an
    input with a value but no handler is "controlled" -- React would put the
    old value back after every keystroke. Left empty, the script fills it."""
    chips = "".join(f'<button type="button" class="uusd-chip" data-amt="{a}">${a // 1000}k</button>'
                    for a in (1000, 10000, 100000))
    return ('<div class="uusd" role="group" aria-label="Show estimates in dollars">'
            '<span class="uusd-k">See it in dollars</span>'
            f'<label class="uusd-box"><span>$</span><input class="uusd-in" inputmode="numeric" '
            f'autocomplete="off" aria-label="Amount invested" placeholder="{DEFAULT_AMOUNT:,}"></label>'
            f'{chips}<span class="uusd-note">Each estimate times this amount: a typical move in a week like that; '
            'it is not a forecast. Stays in your browser.</span></div>')


EXPLAIN_CSS = """<style>
:root{--ux-teal:#6ce5d2;}html[data-ua-theme="light"]{--ux-teal:#0b6f64;}
.ugl{position:relative;display:inline;cursor:help;border-bottom:1px dotted color-mix(in srgb,currentColor 55%,transparent);outline:none;}
.ugl:focus-visible{border-bottom-style:solid;border-bottom-color:var(--ux-teal);}
.ugl-tip{position:absolute;left:0;top:calc(100% + 8px);z-index:60;width:min(300px,78vw);padding:10px 12px;border-radius:12px;
  background:rgba(14,22,34,.94);border:1px solid rgba(108,229,210,.28);box-shadow:0 14px 40px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.06);
  -webkit-backdrop-filter:blur(14px) saturate(140%);backdrop-filter:blur(14px) saturate(140%);
  color:#d8e1ec;font-size:var(--uar-t-sm,.82rem);font-weight:400;line-height:1.45;letter-spacing:0;text-transform:none;white-space:normal;text-align:left;
  opacity:0;visibility:hidden;transform:translateY(-4px);transition:opacity .14s ease,transform .14s ease,visibility .14s;pointer-events:none;}
.ugl-tip b{display:block;margin-bottom:3px;color:#fff;font-weight:700;}
.ugl-tip a{display:inline-block;margin-top:6px;color:var(--ux-teal);font-weight:600;text-decoration:none;}
.ugl:hover>.ugl-tip,.ugl:focus>.ugl-tip,.ugl:focus-within>.ugl-tip{opacity:1;visibility:visible;transform:none;pointer-events:auto;}
html[data-ua-theme="light"] .ugl-tip{background:rgba(255,255,255,.97);border-color:rgba(11,111,100,.25);color:#334155;box-shadow:0 14px 40px rgba(15,23,42,.18);}
html[data-ua-theme="light"] .ugl-tip b{color:#0f172a;}
html[data-ua-theme="light"] .ugl-tip a{color:#0b6f64;}
.ugl-list{list-style:none;margin:8px 0 0 !important;padding:0 !important;display:flex;flex-wrap:wrap;gap:8px;}
.ugl-list li{margin:0 !important;padding:5px 11px;border-radius:999px;border:1px solid var(--uar-line);background:rgba(255,255,255,.03);font-size:var(--uar-t-sm,.82rem);color:var(--uar-ink-2);}
html[data-ua-theme="light"] .ugl-list li{background:#f8fafc;}
.ugl-card::before{background:linear-gradient(180deg,#6ce5d2,#4a8ae6);}
.ugl-card,.uar-xcard,.uar-xrow,.uxc{overflow:visible;}
.uusd{display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;margin:0 0 8px;padding:10px 14px;border-radius:14px;border:1px solid var(--uar-line);
  background:linear-gradient(120deg,rgba(108,229,210,.07),rgba(74,138,230,.05));-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);}
.uusd-k{font-size:var(--uar-t-micro,.74rem);font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--uar-ink-3);}
.uusd-box{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:10px;border:1px solid rgba(108,229,210,.35);background:rgba(0,0,0,.18);}
.uusd-box span{color:var(--uar-ink-3);font-weight:700;}
.uusd-in{width:96px;border:0;outline:0;background:transparent;color:var(--uar-ink);font:inherit;font-weight:700;font-variant-numeric:tabular-nums;}
.uusd-chip{padding:4px 10px;border-radius:999px;border:1px solid var(--uar-line);background:transparent;color:var(--uar-ink-2);font:inherit;font-size:var(--uar-t-sm,.82rem);cursor:pointer;}
.uusd-chip[aria-pressed="true"]{border-color:rgba(108,229,210,.6);background:rgba(108,229,210,.12);color:var(--uar-ink);}
.uusd-note{flex-basis:100%;font-size:var(--uar-t-micro,.74rem);color:var(--uar-ink-3);}
html[data-ua-theme="light"] .uusd-box{background:#fff;border-color:rgba(11,111,100,.35);}
.uar-usd{display:block;font-size:var(--uar-t-micro,.74rem);font-weight:600;color:var(--uar-ink-3);font-variant-numeric:tabular-nums;white-space:nowrap;}
.uar-usd:empty{display:none;}
.uar-usd.uar-usd-verb{display:inline;font-size:inherit;font-weight:700;color:var(--uar-ink);white-space:normal;}
.uusd-inline{vertical-align:baseline;margin:0 2px;padding:1px 8px;}
.uusd-inline .uusd-in{width:84px;font-size:inherit;}
.upe{position:relative;margin:4px 0 14px;padding:18px 22px 14px;border-radius:20px;border:1px solid rgba(108,229,210,.22);
  background:radial-gradient(120% 140% at 0% 0%,rgba(108,229,210,.10),transparent 55%),radial-gradient(90% 120% at 100% 100%,rgba(74,138,230,.10),transparent 60%),rgba(255,255,255,.025);
  -webkit-backdrop-filter:blur(16px) saturate(140%);backdrop-filter:blur(16px) saturate(140%);box-shadow:0 18px 50px rgba(0,0,0,.28),inset 0 1px 0 rgba(255,255,255,.06);}
.upe-k{display:flex;align-items:center;gap:8px;font-size:var(--uar-t-micro,.74rem);font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--ux-teal);}
.upe-k i{width:8px;height:8px;border-radius:50%;background:#6ce5d2;box-shadow:0 0 10px #6ce5d2;}
.upe-lead{margin:8px 0 10px;font-size:var(--uar-t-lead,1.18rem);font-weight:600;color:var(--uar-ink);line-height:1.5;}
.upe-rows{list-style:none;margin:0 !important;padding:0 !important;display:grid;gap:10px 22px;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));}
.upe-rows li{margin:0 !important;max-width:none !important;display:grid;grid-template-columns:30px 1fr;gap:10px;align-items:start;font-size:var(--uar-t-body,.88rem);color:var(--uar-ink-2);line-height:1.55;}
.upe-ic{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;border:1px solid var(--uar-line);background:rgba(255,255,255,.04);color:var(--uar-ink-2);font-weight:700;}
.upf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;margin-top:8px;}
.upf-card{padding:12px 14px;border-radius:14px;border:1px solid var(--uar-line);background:rgba(255,255,255,.025);display:grid;gap:8px;align-content:start;}
.upf-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:var(--uar-ink);}
.upf-pill{margin-left:auto;font-size:var(--uar-t-micro,.74rem);font-weight:700;padding:3px 9px;border-radius:999px;border:1px solid var(--uar-line);color:var(--uar-ink);}
.upf-ok .upf-pill{border-color:rgba(53,201,139,.55);background:rgba(53,201,139,.12);}
.upf-mid .upf-pill{border-color:rgba(216,182,106,.55);background:rgba(216,182,106,.12);}
.upf-warn .upf-pill{border-color:rgba(224,108,117,.55);background:rgba(224,108,117,.12);}
.upf-strip{position:relative;height:84px;display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:5px;align-items:end;padding:0 2px;}
.upf-zero{position:absolute;left:0;right:0;top:50%;border-top:1px solid var(--uar-ink-3);opacity:.5;}
.upf-bar{position:relative;align-self:end;margin-bottom:42px;border-radius:4px 4px 0 0;cursor:help;}
.upf-bar.upf-neg{align-self:start;margin:42px 0 0;border-radius:0 0 4px 4px;}
.upf-yes{background:linear-gradient(180deg,#6ce5d2,#35c9a4);box-shadow:0 0 12px rgba(108,229,210,.25);}
.upf-no{background:linear-gradient(180deg,#e06c75,#b84a54);}
.upf-text{margin:0;font-size:var(--uar-t-sm,.82rem);color:var(--uar-ink-2);line-height:1.5;}
.upf-text b{color:var(--uar-ink);}
.upf-oos{font-size:var(--uar-t-micro,.74rem);color:var(--uar-ink-3);line-height:1.5;padding-top:6px;border-top:1px dashed var(--uar-line);}
.upf-oos b{color:var(--uar-ink);}
.upf-wrap::before{background:linear-gradient(180deg,#35c98b,#6ce5d2);}
html[data-ua-theme="light"] .upf-card{background:#f8fafc;}
html[data-ua-theme="light"] .upf-yes{background:linear-gradient(180deg,#14a38b,#0b6f64);box-shadow:none;}
.upe-ok{color:#35c98b;font-weight:600;}.upe-warn{color:#e8a0a6;font-weight:600;}
html[data-ua-theme="light"] .upe-ok{color:#0b7a55;}html[data-ua-theme="light"] .upe-warn{color:#b3323d;}
.uar-down{display:inline-block;margin-left:6px;font-size:var(--uar-t-micro,.74rem);font-weight:600;color:#d8b66a;white-space:nowrap;}
.uar-conf{display:inline-block;margin-left:6px;font-size:var(--uar-t-micro,.74rem);font-weight:700;color:var(--ux-teal);white-space:nowrap;}
html[data-ua-theme="light"] .uar-conf{color:#0b6f64;}
.upe-foot{margin-top:10px;font-size:var(--uar-t-micro,.74rem);color:var(--uar-ink-3);}
html[data-ua-theme="light"] .upe{background:radial-gradient(120% 140% at 0% 0%,rgba(11,111,100,.08),transparent 55%),#fff;border-color:rgba(11,111,100,.22);box-shadow:0 12px 34px rgba(15,23,42,.08);}
html[data-ua-theme="light"] .upe-k{color:#0b6f64;}html[data-ua-theme="light"] .upe-k i{background:#0b6f64;box-shadow:none;}
</style>"""


# Runs once per page load (scripts/inject_boot_splash.py). Delegated listeners
# and a MutationObserver, because Streamlit re-renders the report's HTML on
# every rerun and replaces the nodes these touch.
DOLLARS_JS = r"""
(function(){
  if (window.__uaUsd) return; window.__uaUsd = 1;
  var KEY = 'ua-usd', amt = 10000;
  try { var s = parseFloat(localStorage.getItem(KEY)); if (s > 0) amt = s; } catch (e) {}
  function money(v){
    var a = Math.abs(v), d = a < 10 ? 2 : 0;
    return (v < 0 ? '−' : '+') + '$' + a.toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d});
  }
  function paint(root){
    (root || document).querySelectorAll('.uar-usd[data-pct]').forEach(function(el){
      var v = parseFloat(el.getAttribute('data-pct')) / 100 * amt, t;
      var mode = el.getAttribute('data-mode');
      if (mode === 'verb')                                   // "lost about $56" / "gained about $56"
        t = (v < 0 ? 'lost about ' : 'gained about ') + money(v).slice(1);
      else if (mode === 'abs') t = money(v).slice(1);       // a plain "$56"
      else t = '≈ ' + money(v);
      if (el.textContent !== t) el.textContent = t;
    });
    (root || document).querySelectorAll('.uusd-in').forEach(function(i){
      if (document.activeElement !== i) i.value = Math.round(amt).toLocaleString('en-US');
    });
    (root || document).querySelectorAll('.uusd-chip').forEach(function(c){
      c.setAttribute('aria-pressed', String(+c.getAttribute('data-amt') === Math.round(amt)));
    });
  }
  function set(v){
    if (!(v > 0) || v > 1e12) return; amt = v;
    try { localStorage.setItem(KEY, String(v)); } catch (e) {}
    paint();
  }
  document.addEventListener('input', function(e){
    if (e.target && e.target.classList && e.target.classList.contains('uusd-in'))
      set(parseFloat(String(e.target.value).replace(/[^0-9.]/g, '')));
  }, true);
  document.addEventListener('click', function(e){
    var c = e.target && e.target.closest && e.target.closest('.uusd-chip');
    if (c) { e.preventDefault(); set(+c.getAttribute('data-amt')); }
  }, true);
  // Keep a definition on screen: nudge it left when it would run off the right edge.
  function fit(e){
    var g = e.target && e.target.closest && e.target.closest('.ugl'); if (!g) return;
    var tip = g.querySelector('.ugl-tip'); if (!tip) return;
    tip.style.left = '0px';
    var r = tip.getBoundingClientRect(), over = r.right - (window.innerWidth - 8);
    if (over > 0) tip.style.left = (-Math.min(over, Math.max(0, r.left - 8))) + 'px';
  }
  document.addEventListener('mouseover', fit, true);
  document.addEventListener('focusin', fit, true);
  var pending = 0;
  new MutationObserver(function(){
    if (pending) return; pending = 1;
    requestAnimationFrame(function(){ pending = 0; paint(); });
  }).observe(document.documentElement, {childList: true, subtree: true});
  paint();
})();
"""
