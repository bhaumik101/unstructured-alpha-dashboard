# utils/evidence_page.py
# Unstructured Alpha — the track record as a public, crawlable page
#
# The in-app /evidence page needs a live Streamlit session, so it cannot be
# indexed, linked from a search result or opened by an adviser's compliance
# reviewer without signing in. This renders the same published study
# (utils/track_record.py, newest run in research_results) as plain HTML on the
# SEO service, with the same rules: every number is shown against the line
# that gives it meaning, a partial run says so, nothing is a forecast, and
# when no run exists the page says that and is not indexed.

from __future__ import annotations

from html import escape
from typing import Optional

from utils import exposure as ex
from utils.exposure_pages import _date, _shell

LABELS = (("clear", "Clear"), ("tentative", "Tentative"),
          ("indistinct", "Not distinguishable from zero"))


def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{100 * x:.0f}%"


def evidence_page_html(result: Optional[dict], base_url: str, app_url: str) -> str:
    canonical = f"{base_url}/evidence"
    title = "Does it hold up? The out-of-sample track record"
    if not result or not result.get("available"):
        desc = "The out-of-sample track record of the exposure readings has not been published yet."
        body = ('<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Track record</nav>'
                f'<h1>Does it hold up?</h1><p class="lead">{escape(desc)} It runs with the weekly '
                'measurement job, and this page shows its results, whatever they are, as soon as '
                'it finishes.</p>')
        return _shell(title, desc, canonical, {"@context": "https://schema.org", "@type": "WebPage",
                                               "name": title, "url": canonical},
                      body, app_url, robots="noindex, follow")

    bl = result.get("by_label") or {}
    clear, zero = bl.get("clear") or {}, bl.get("indistinct") or {}
    stocks, universe = result.get("n_stocks", 0), result.get("universe") or result.get("n_stocks", 0)
    when = _date(str(result.get("computed_at") or "")[:10]) if result.get("computed_at") else "—"
    desc = (f"Of readings labelled Clear, {_pct(clear.get('same_direction'))} kept their direction "
            f"over the following year, against {_pct(zero.get('same_direction'))} for readings that "
            f"could not be told apart from zero — measured out of sample on {stocks:,} S&P 500 "
            "companies.")
    partial = ('<p class="caveat">This run stopped at its time limit before reaching the whole '
               'index, so these figures cover only the companies it reached.</p>'
               if result.get("stopped") else "")

    rows = "".join(
        f'<tr><th scope="row">{escape(name)}</th><td>{(bl.get(k) or {}).get("n", 0):,}</td>'
        f'<td><b>{_pct((bl.get(k) or {}).get("same_direction"))}</b></td>'
        f'<td><b>{_pct((bl.get(k) or {}).get("consistent"))}</b></td></tr>'
        for k, name in LABELS if bl.get(k))
    bf = result.get("by_factor") or {}
    force_rows = "".join(
        f'<tr><th scope="row"><a href="/forces/{f.key}">{escape(f.label)}</a></th>'
        f'<td>{(bf.get(f.key) or {}).get("n", 0):,}</td>'
        f'<td>{_pct((bf.get(f.key) or {}).get("same_direction"))}</td>'
        f'<td>{_pct((bf.get(f.key) or {}).get("consistent"))}</td></tr>'
        for f in ex.FACTORS)
    slope = result.get("shrinkage_slope")
    origins = result.get("origins") or []
    span = f"{_date(origins[0])} to {_date(origins[-1])}" if origins else "—"

    body = (
        '<nav class="crumb" aria-label="Breadcrumb"><a href="/">Home</a> › Track record</nav>'
        '<h1>Does it hold up?</h1>'
        f'<p class="meta">Latest run {escape(when)} · {stocks:,} of {universe:,} S&amp;P 500 companies</p>'
        f'<p class="lead">Every reading the product shows is measured on three years of weekly data. '
        'This is how readings measured that way held up over the year that followed — a year the '
        'first measurement never saw. It is published whatever it shows.</p>'
        + partial +
        '<h2>Did the direction and the size last?</h2>'
        '<div class="card" tabindex="0" role="region" aria-label="Results by evidence label"><table><thead><tr><th scope="col">Label the reading carried</th>'
        '<th scope="col">Readings</th><th scope="col">Same direction a year later</th>'
        '<th scope="col">Consistent within the ranges</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        '<div class="foot">Same direction: a coin flip is 50%, so readings that are only noise '
        'should land near it. Consistent: the next-year reading agreed with the first within their '
        'combined 90% range; a perfectly stable relationship would reach about 90%.</div></div>'
        + (f'<p class="small" style="margin-top:10px">Carry-over at full size: {slope:.2f} '
           '(1.00 would mean readings did not shrink at all out of sample).</p>'
           if slope is not None else "") +
        '<h2>By force (Clear and Tentative readings)</h2>'
        '<div class="card" tabindex="0" role="region" aria-label="Results by force"><table><thead><tr><th scope="col">Force</th><th scope="col">Readings</th>'
        '<th scope="col">Same direction</th><th scope="col">Consistent</th></tr></thead>'
        f'<tbody>{force_rows}</tbody></table></div>'
        '<h2>How it was measured</h2>'
        f'<p class="lead" style="font-size:.95rem">{result.get("n_pairs", 0):,} reading pairs from '
        f'{stocks:,} companies, at {len(origins)} start dates every six months ({escape(span)}). At '
        f'each start date the five core forces were measured on the {result.get("then_weeks", 156)} '
        f'weeks before it, exactly as the product measures them, and again on the '
        f'{result.get("next_weeks", 52)} weeks after it. Pairs from neighbouring start dates share '
        'data, so they are not independent; the percentages are descriptive, not a significance '
        'test. The study reruns monthly and every run is kept.</p>'
        '<p class="caveat"><b>This describes the past, and it is not a forecast.</b> Nothing here '
        'is a recommendation to buy, sell or hold any security.</p>'
        f'<div class="actions"><a class="btn btn-primary" href="{escape(app_url)}/">Measure your own '
        'portfolio</a><a class="btn btn-secondary" href="/forces">Every economic force</a></div>')
    json_ld = {"@context": "https://schema.org", "@type": "Dataset", "name": title,
               "description": desc, "url": canonical,
               "dateModified": str(result.get("computed_at") or "")[:10] or None,
               "creator": {"@type": "Organization", "name": "Unstructured Alpha"}}
    return _shell(title, desc, canonical, {k: v for k, v in json_ld.items() if v}, body, app_url)
