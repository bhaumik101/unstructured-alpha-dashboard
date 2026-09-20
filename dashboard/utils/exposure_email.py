# utils/exposure_email.py
# Unstructured Alpha — the weekly exposure summary email
#
# Retention, honestly: a saved portfolio earns one email a week that says what
# changed. Most weeks nothing measurable changes, and the email says exactly
# that rather than manufacturing news — an alert that always fires is noise,
# and the product's whole claim is that it reports uncertainty faithfully.
#
# The builder is pure: it takes a report from utils/exposure.py and returns a
# subject and HTML. Nothing here computes a statistic or sends anything.

from __future__ import annotations

from html import escape
from typing import Optional

from sqlalchemy import select, update

from utils import db
from utils import exposure as ex
from utils import report_ui as ui

APP_BASE = "https://app.unstructuredalpha.com"

_INK = "#13213a"
_INK_2 = "#3a4760"
_INK_3 = "#5b6780"
_LINE = "#dfe5ee"
_ACCENT = "#1f5fae"
_FACTOR_COLORS = ui.FACTOR_COLORS


# ── opt-in state ────────────────────────────────────────────────────────────

def get_weekly_opt_in(user_id: int) -> bool:
    try:
        with db.engine.begin() as conn:
            row = conn.execute(
                select(db.users.c.exposure_email_opted_in).where(db.users.c.id == int(user_id))
            ).first()
        return bool(row[0]) if row else False
    except Exception:
        return False


def set_weekly_opt_in(user_id: int, opted_in: bool) -> bool:
    try:
        with db.engine.begin() as conn:
            conn.execute(
                update(db.users).where(db.users.c.id == int(user_id))
                .values(exposure_email_opted_in=bool(opted_in))
            )
        return True
    except Exception as exc:
        print(f"[exposure-email] could not save the preference: {type(exc).__name__}", flush=True)
        return False


# ── the email ───────────────────────────────────────────────────────────────

def subject_for(portfolio_name: str, report: dict) -> str:
    """Says in the subject line whether anything actually changed."""
    flagged = [s for s in (report.get("shifts") or []) if s.get("significant")]
    if flagged:
        names = ui._join([ex.lower_label(s["label"]) for s in flagged[:2]])
        return f"{portfolio_name}: {names} sensitivity changed"
    return f"{portfolio_name}: no measurable change this week"


def _row(label: str, key: str, value: str, extra: str) -> str:
    colour = _FACTOR_COLORS.get(key, _ACCENT)
    return (
        f'<tr>'
        f'<td style="padding:10px 0;border-bottom:1px solid {_LINE};">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:3px;'
        f'background:{colour};margin-right:8px;"></span>'
        f'<span style="color:{_INK};font-weight:600;">{escape(label)}</span></td>'
        f'<td style="padding:10px 0;border-bottom:1px solid {_LINE};text-align:right;'
        f'color:{_INK};font-weight:700;white-space:nowrap;">{escape(value)}</td>'
        f'<td style="padding:10px 0 10px 14px;border-bottom:1px solid {_LINE};'
        f'color:{_INK_3};font-size:13px;white-space:nowrap;">{escape(extra)}</td>'
        f'</tr>'
    )


def build_weekly_email(portfolio_name: str, report: dict, app_base: str = APP_BASE) -> dict:
    """Returns {subject, html} for one saved portfolio's weekly summary."""
    name = str(portfolio_name or "Your portfolio")
    portfolio = report.get("portfolio") or {}
    readings = portfolio.get("readings") or {}

    # What changed — the reason the email exists, so it leads.
    shifts = [s for s in (report.get("shifts") or []) if s.get("significant")]
    if shifts:
        changed = "".join(
            f'<p style="margin:0 0 10px;color:{_INK_2};font-size:15px;line-height:1.6;">'
            f'{escape(s["sentence"])}</p>' for s in shifts
        )
    else:
        changed = (
            f'<p style="margin:0;color:{_INK_2};font-size:15px;line-height:1.6;">'
            f'No measurable change in any exposure between the past year and the two years '
            f'before it. Most weeks look like this; the email says so rather than inventing '
            f'news.</p>'
        )

    # Recent weeks — what actually moved, and what it lines up with.
    rm = report.get("recent_moves") or {}
    recent = ""
    if rm.get("available"):
        counted = [m for m in rm["moves"] if m.get("counts")]
        lines = "".join(
            f'<li style="margin-bottom:6px;">{escape(m["label"])} moved {escape(m["move_text"])}, '
            f'which lines up with {escape(ui.fmt_pct(m["attributed"]))} for this portfolio.</li>'
            for m in counted
        )
        recent = (
            f'<p style="margin:0 0 8px;color:{_INK_2};font-size:15px;line-height:1.6;">'
            f'In the {rm["weeks"]} weeks to {escape(ui.fmt_date(rm["end"]))}, the portfolio '
            f'returned {escape(ui.fmt_pct(rm["portfolio_return"]))}.</p>'
            + (f'<ul style="margin:0;padding-left:20px;color:{_INK_2};font-size:15px;'
               f'line-height:1.6;">{lines}</ul>' if lines else "")
        )

    order = ui.ordered_keys(report) if readings else []
    rows = "".join(
        _row(readings[k]["label"], k, ui.fmt_pct(readings[k]["impact"]),
             ex.EVIDENCE_LABELS[readings[k]["evidence"]])
        for k in order
    )

    html = f"""\
<div style="background:#f4f6fa;padding:24px 0;font-family:Inter,Helvetica,Arial,sans-serif;">
<div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid {_LINE};border-radius:14px;overflow:hidden;">
  <div style="height:5px;background:#3b7ddd;"></div>
  <div style="padding:24px 26px;">
    <div style="font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:{_ACCENT};font-weight:700;">Weekly exposure summary</div>
    <div style="font-size:21px;font-weight:700;color:{_INK};margin-top:6px;">{escape(name)}</div>
    <div style="font-size:13px;color:{_INK_3};margin-top:4px;">Data through {escape(ui.fmt_date(report.get('as_of')))}</div>

    <h2 style="font-size:16px;color:{_INK};margin:22px 0 10px;">What changed</h2>
    {changed}

    {f'<h2 style="font-size:16px;color:{_INK};margin:22px 0 10px;">Recent weeks</h2>{recent}' if recent else ''}

    <h2 style="font-size:16px;color:{_INK};margin:22px 0 6px;">Current exposures</h2>
    <table style="width:100%;border-collapse:collapse;font-size:15px;">{rows}</table>
    <p style="margin:10px 0 0;color:{_INK_3};font-size:13px;line-height:1.55;">
      Each figure is the portfolio's typical same-week move when that force moved by its
      standard amount, after accounting for the stock market. It describes the past; it is
      not a forecast.
    </p>

    <p style="margin:24px 0 0;">
      <a href="{app_base}/?utm_source=weekly_email&amp;utm_medium=email&amp;utm_campaign=exposure_weekly"
         style="display:inline-block;background:{_ACCENT};color:#ffffff;text-decoration:none;
                padding:12px 22px;border-radius:9px;font-weight:600;font-size:15px;">Open the full report</a>
    </p>
  </div>
  <div style="padding:16px 26px;background:#f4f6fa;color:{_INK_3};font-size:12px;line-height:1.6;">
    You receive this because you saved a portfolio and turned on the weekly summary.
    Turn it off any time on the exposure report, or in your profile.<br><br>
    Unstructured Alpha is an educational and informational tool. Nothing here is personalized
    financial, investment, tax or legal advice, or a recommendation to buy, sell or hold any
    security. Exposure figures describe how portfolios have moved in the past; relationships
    change and past behaviour does not guarantee future results.
  </div>
</div>
</div>"""

    return {"subject": subject_for(name, report), "html": html}
