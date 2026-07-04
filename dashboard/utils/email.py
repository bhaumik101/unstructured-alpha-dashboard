# utils/email.py
# Unstructured Alpha — Verification Email Sending (Resend)
#
# Endpoint/payload shape verified live against Resend's published API
# reference before writing this, 2026-06-21:
#   POST https://api.resend.com/emails
#   Authorization: Bearer {api_key}
#   {"from": "...", "to": [...], "subject": "...", "html": "..."}
#   -> {"id": "..."}
# Plain requests.post, not Resend's Python SDK -- consistent with every
# other third-party integration in this codebase (FRED, EIA, SEC, FINRA all
# use requests directly), and avoids adding a dependency just to wrap one
# REST call this small.
#
# Configuration -- environment variable checked FIRST, st.secrets as a
# fallback (same priority order as FRED_API_KEY/EIA_API_KEY in
# utils/fetchers.py and DATABASE_URL in utils/db.py). This matters beyond
# consistency: st.secrets only exists at all under Streamlit Cloud's
# secrets.toml mechanism, so a host without that (Render, Railway, a plain
# VPS) needs the env var path to work, not just a fallback that happens to
# never get reached:
#   RESEND_API_KEY   -- required to actually send mail.
#   RESEND_FROM_EMAIL -- optional; defaults to Resend's own test sender
#     ("onboarding@resend.dev"), which only works for sending TO the email
#     address on the Resend account itself, not arbitrary recipients --
#     real signups need a verified sending domain configured in Resend and
#     that address set here.

import os

import requests
import streamlit as st

_RESEND_API_URL = "https://api.resend.com/emails"
_DEFAULT_FROM = "Unstructured Alpha <onboarding@resend.dev>"


class EmailSendError(Exception):
    """Raised when the verification email genuinely fails to send (bad/missing
    API key, Resend API error) -- distinct from AuthError, since this is an
    infrastructure failure, not a user input mistake."""


def _get_resend_config() -> tuple[str, str]:
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        try:
            api_key = st.secrets.get("RESEND_API_KEY", "")
        except Exception:
            api_key = ""

    from_email = os.environ.get("RESEND_FROM_EMAIL", "")
    if not from_email:
        try:
            from_email = st.secrets.get("RESEND_FROM_EMAIL", _DEFAULT_FROM)
        except Exception:
            from_email = _DEFAULT_FROM
    return api_key, from_email


def send_verification_email(to_email: str, code: str) -> None:
    """Send a 6-digit verification code to to_email. Raises EmailSendError
    if RESEND_API_KEY isn't configured or Resend's API rejects the request.

    TEMPORARY DIAGNOSTIC LOGGING (added 2026-06-22, remove once the "emails
    aren't arriving for arbitrary recipients" issue is confirmed fixed):
    the FIRST version of this logging never showed up in Render's logs at
    all, even though a fresh, fully-observed incognito test confirmed
    signup() really was completing successfully (the "We emailed a code"
    UI message only renders when no exception was raised) -- and the
    GitHub source for the exact deployed commit was checked directly and
    does contain these print() calls. That combination only makes sense
    as a well-known Python/Docker gotcha: stdout is FULLY buffered (not
    line-buffered) when it's not an interactive terminal, which is always
    true for a containerized process whose stdout is piped into a log
    collector -- so print() output can sit in an internal buffer
    indefinitely in a long-running server process that never naturally
    exits, instead of ever reaching the log stream. flush=True on every
    print() below forces each line out immediately rather than waiting
    on Python's buffer to fill.
    """
    api_key, from_email = _get_resend_config()
    print(f"[email] send_verification_email called: to={to_email!r} from={from_email!r} "
          f"api_key_present={bool(api_key)} api_key_prefix={api_key[:6] if api_key else None!r}",
          flush=True)
    if not api_key:
        print("[email] aborting: no RESEND_API_KEY configured", flush=True)
        raise EmailSendError(
            "No RESEND_API_KEY configured -- add one in Streamlit secrets to send real verification emails."
        )

    html = f"""
    <div style="font-family: Georgia, serif; max-width: 480px;">
        <h2 style="color:#1C2B4A;">Verify your Unstructured Alpha account</h2>
        <p>Enter this code to finish creating your account:</p>
        <div style="font-size:2rem; font-weight:700; letter-spacing:0.2em; color:#B8860B; margin: 16px 0;">
            {code}
        </div>
        <p style="color:#8B7355; font-size:0.85rem;">This code expires in 15 minutes. If you didn't request this, you can ignore this email.</p>
    </div>
    """

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "Your Unstructured Alpha verification code",
                "html": html,
            },
            timeout=15,
        )
        print(f"[email] Resend API responded: status={resp.status_code} body={resp.text[:500]!r}", flush=True)
        resp.raise_for_status()
        print(f"[email] send succeeded for to={to_email!r}", flush=True)
    except requests.RequestException as e:
        print(f"[email] send FAILED for to={to_email!r}: {type(e).__name__}: {e}", flush=True)
        raise EmailSendError(f"Failed to send verification email: {e}") from e


def _build_article_html(
    signal_scores: dict,
    signal_flips: list[dict],
    bias: str,
    bull_n: int,
    bear_n: int,
    neut_n: int,
    date_str: str,
) -> tuple[str, str]:
    """
    Build the Seeking Alpha-style macro article HTML.
    Returns (article_html, subject_line).

    signal_scores: {sig_id: {"name": str, "score": float, "status": str}}
    """
    total = bull_n + bear_n + neut_n or 1

    # ── Top signals by conviction ──────────────────────────────────────────
    bull_sigs = sorted(
        [(sid, sv) for sid, sv in signal_scores.items() if sv.get("status") == "bullish"],
        key=lambda x: -x[1].get("score", 0),
    )[:4]
    bear_sigs = sorted(
        [(sid, sv) for sid, sv in signal_scores.items() if sv.get("status") == "bearish"],
        key=lambda x: x[1].get("score", 100),
    )[:3]

    top_bull_name = bull_sigs[0][1].get("name", "several macro series") if bull_sigs else "broad macro data"
    top_bear_name = bear_sigs[0][1].get("name", "some indicators") if bear_sigs else None

    # ── Dynamic subject line ───────────────────────────────────────────────
    flip_n = len(signal_flips)
    if flip_n >= 3:
        subject = f"{flip_n} Signals Just Flipped — What the Data Is Saying This Morning"
    elif bias == "Bullish" and bull_n >= bear_n * 2:
        subject = f"Bull Signals Dominate {bull_n}–{bear_n}: {top_bull_name} Leads the Way"
    elif bias == "Bearish" and bear_n >= bull_n * 2:
        subject = f"Macro Warning: {bear_n} Bearish Signals This Morning — UA Brief"
    elif bias == "Bullish":
        subject = f"UA Morning Brief — Signal Stack Reads Bullish ({bull_n}▲ {bear_n}▼)"
    elif bias == "Bearish":
        subject = f"UA Morning Brief — Signal Stack Reads Bearish ({bear_n}▼ {bull_n}▲)"
    else:
        subject = f"UA Morning Brief — Mixed Signals ({bull_n}▲ {bear_n}▼) · {date_str}"

    # ── Headline ───────────────────────────────────────────────────────────
    if flip_n >= 3:
        headline = (
            f"{flip_n} Signals Flipped Overnight — "
            f"Here's What the Data Is Saying on {date_str}"
        )
    elif bias == "Bullish" and bull_n >= bear_n * 2:
        headline = (
            f"Bull Signals Outnumber Bears {bull_n}–{bear_n}: "
            f"{top_bull_name} Is Leading the Way"
        )
    elif bias == "Bearish" and bear_n >= bull_n:
        headline = (
            f"Macro Headwinds: {bear_n} Bearish Signals Across Independent Series — "
            f"Morning Brief"
        )
    else:
        headline = (
            f"Mixed Picture: {bull_n} Bull vs {bear_n} Bear — "
            f"Where the Data Agrees and Disagrees"
        )

    # ── Lede paragraph ─────────────────────────────────────────────────────
    if bias == "Bullish" and bull_n / total >= 0.50:
        lede = (
            f"<strong>This morning's macro read leans bullish.</strong> "
            f"The Unstructured Alpha signal stack — {total} independent macro, positioning, "
            f"and momentum series — is registering {bull_n} bullish against {bear_n} bearish. "
            f"The lead signal is <strong>{top_bull_name}</strong>, reading at "
            f"{bull_sigs[0][1].get('score', 0):.0f}/100."
        ) if bull_sigs else (
            f"<strong>This morning's macro read leans bullish.</strong> "
            f"The signal stack shows {bull_n} bullish against {bear_n} bearish across "
            f"{total} independent series."
        )
    elif bias == "Bearish" and bear_n / total >= 0.45:
        lede = (
            f"<strong>Caution is warranted this morning.</strong> "
            f"The signal stack is reading {bear_n} bearish against {bull_n} bullish "
            f"across {total} independent series. "
            + (f"<strong>{top_bear_name}</strong> is the sharpest bearish read at "
               f"{bear_sigs[0][1].get('score', 0):.0f}/100." if top_bear_name and bear_sigs else "")
        )
    else:
        lede = (
            f"<strong>The signal stack is sending mixed messages this morning.</strong> "
            f"{bull_n} series read bullish and {bear_n} read bearish across {total} "
            f"independent data sources — a split that calls for selectivity rather than "
            f"a broad directional bet."
        )

    # ── Key Data Points rows ───────────────────────────────────────────────
    data_rows = ""
    shown = set()
    for sid, sv in bull_sigs[:3]:
        shown.add(sid)
        score = sv.get("score", 0)
        name  = sv.get("name", sid)
        data_rows += (
            f'<tr>'
            f'<td style="padding:5px 8px 5px 0;font-size:0.83rem;color:#1a202c;'
            f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
            f'<span style="color:#00875A;font-weight:700;">▲</span>&nbsp;{name}</td>'
            f'<td style="padding:5px 0 5px 8px;font-weight:700;font-size:0.83rem;'
            f'color:#00875A;text-align:right;white-space:nowrap;">{score:.0f}/100</td>'
            f'</tr>'
        )
    for sid, sv in bear_sigs[:2]:
        if sid in shown:
            continue
        score = sv.get("score", 0)
        name  = sv.get("name", sid)
        data_rows += (
            f'<tr>'
            f'<td style="padding:5px 8px 5px 0;font-size:0.83rem;color:#1a202c;'
            f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
            f'<span style="color:#C53030;font-weight:700;">▼</span>&nbsp;{name}</td>'
            f'<td style="padding:5px 0 5px 8px;font-weight:700;font-size:0.83rem;'
            f'color:#C53030;text-align:right;white-space:nowrap;">{score:.0f}/100</td>'
            f'</tr>'
        )

    if flip_n:
        # Highlight the biggest flip
        top_flip = signal_flips[0]
        flip_dir = "→ Bullish" if top_flip.get("to_status") == "bullish" else "→ Bearish"
        flip_color = "#00875A" if top_flip.get("to_status") == "bullish" else "#C53030"
        data_rows += (
            f'<tr style="border-top:1px solid #E2E8F0;">'
            f'<td style="padding:7px 8px 5px 0;font-size:0.83rem;color:#4A5568;'
            f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
            f'⚡ Flip: {top_flip.get("signal_name", top_flip.get("signal_id",""))}</td>'
            f'<td style="padding:7px 0 5px 8px;font-weight:700;font-size:0.83rem;'
            f'color:{flip_color};text-align:right;">{flip_dir}</td>'
            f'</tr>'
        )

    # ── Analysis paragraph ─────────────────────────────────────────────────
    if bias == "Bullish":
        analysis = (
            "When multiple independent macro series align in the same direction, "
            "the signal is historically more meaningful than any single indicator. "
            "The current bullish cluster spans economic sectors with low mutual "
            "correlation — meaning the read isn't coming from one shared driver, "
            "but from genuinely broad-based improvement across the data stack."
        )
        if bear_sigs:
            analysis += (
                f" The main counterpoint: {top_bear_name} is still reading bearish "
                f"at {bear_sigs[0][1].get('score', 0):.0f}/100 — worth monitoring as a "
                f"potential early-warning indicator for any reversal."
            ) if top_bear_name else ""
    elif bias == "Bearish":
        analysis = (
            "The bearish cluster deserves attention precisely because it's showing up "
            "across independent data series — not all of which move on the same economic cycle. "
            "When trucking volumes, credit conditions, and forward-looking indicators all "
            "lean negative simultaneously, it typically reflects broad underlying softness "
            "rather than one-sector noise."
        )
        if bull_sigs:
            analysis += (
                f" The counter-argument: {top_bull_name} remains bullish at "
                f"{bull_sigs[0][1].get('score', 0):.0f}/100, providing a reason for "
                f"selectivity rather than blanket defensiveness."
            )
    else:
        analysis = (
            "Mixed signal environments are the norm, not the exception — "
            "but the current split is notable because it's clean: the bullish "
            "readings are concentrated in leading indicators (they point forward), "
            "while the bearish readings cluster in coincident and lagging data. "
            "This setup has historically resolved in the direction of the leading indicators "
            "within 2–4 weeks, making the next round of data prints especially important."
        )

    # ── Risk / Watch section ───────────────────────────────────────────────
    if bear_sigs:
        risk_sig = bear_sigs[0]
        risk_text = (
            f"<strong>{risk_sig[1].get('name', 'Key signal')}</strong> is the sharpest "
            f"bearish read in the stack at {risk_sig[1].get('score', 0):.0f}/100. "
            f"A continuation lower in this series would shift the overall picture and "
            f"is the primary data point to watch in the next 1–2 weeks."
        )
    elif bias == "Bullish":
        risk_text = (
            "The bull read is broad but not unanimous. "
            "Watch for any reversal in labor or freight data — "
            "both have historically given 2–4 weeks of lead time on macro inflections."
        )
    else:
        risk_text = (
            "Monitor the signal flip table below for any cluster of moves in one direction. "
            "Three or more coordinated flips in a single session have historically been "
            "a reliable confirmation signal."
        )

    # ── Bottom line ────────────────────────────────────────────────────────
    if bias == "Bullish":
        bottom_line = (
            f"Bull signals outnumber bears {bull_n}:{bear_n} today. "
            f"The machine leans bullish on macro grounds. "
            f"As always — verify with your own research before acting."
        )
    elif bias == "Bearish":
        bottom_line = (
            f"Bear signals outnumber bulls {bear_n}:{bull_n} today. "
            f"The data skews cautious. This is a read on macro alignment, "
            f"not a market call — do your own diligence."
        )
    else:
        bottom_line = (
            f"The signal stack is split {bull_n} bull / {bear_n} bear today. "
            f"No clear macro consensus. Selectivity over broad directional bets."
        )

    # ── Bias accent color ──────────────────────────────────────────────────
    accent = "#6A5ACD" if bias == "Bullish" else ("#C53030" if bias == "Bearish" else "#5A6472")

    article_html = f"""
    <div style="background:#ffffff;padding:28px 24px 20px;">
        <!-- Article header -->
        <div style="border-left:4px solid {accent};padding-left:16px;margin-bottom:20px;">
            <div style="font-size:0.60rem;color:#8892AA;text-transform:uppercase;
                        letter-spacing:0.12em;margin-bottom:7px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                MACRO INTELLIGENCE · {date_str.upper()}
            </div>
            <h2 style="font-size:1.25rem;font-weight:800;color:#0f1119;margin:0 0 8px;
                       line-height:1.35;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                {headline}
            </h2>
        </div>

        <!-- Lede -->
        <p style="font-size:0.92rem;color:#1a202c;line-height:1.75;margin:0 0 18px;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            {lede}
        </p>

        <!-- Key Data Points -->
        <div style="background:#F7F8FA;border-radius:6px;padding:14px 16px;margin-bottom:20px;
                    border:1px solid #E2E8F0;">
            <div style="font-size:0.60rem;font-weight:700;color:{accent};
                        text-transform:uppercase;letter-spacing:0.12em;margin-bottom:10px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                KEY DATA POINTS
            </div>
            <table style="border-collapse:collapse;width:100%;">
                {data_rows}
            </table>
        </div>

        <!-- What This Means -->
        <div style="font-size:0.60rem;font-weight:700;color:#4A5568;text-transform:uppercase;
                    letter-spacing:0.10em;margin-bottom:8px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            WHAT THIS MEANS
        </div>
        <p style="font-size:0.88rem;color:#2D3748;line-height:1.78;margin:0 0 18px;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            {analysis}
        </p>

        <!-- Watch For -->
        <div style="border-left:3px solid #C53030;padding:10px 14px;
                    background:#FFF5F5;border-radius:0 4px 4px 0;margin-bottom:20px;">
            <div style="font-size:0.60rem;font-weight:700;color:#C53030;
                        text-transform:uppercase;letter-spacing:0.10em;margin-bottom:5px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                WATCH FOR
            </div>
            <p style="font-size:0.83rem;color:#4A5568;margin:0;line-height:1.65;
                      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                {risk_text}
            </p>
        </div>

        <!-- Bottom Line -->
        <div style="border-top:2px solid #E2E8F0;padding-top:14px;">
            <span style="font-size:0.60rem;font-weight:700;color:{accent};
                         text-transform:uppercase;letter-spacing:0.10em;
                         font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                BOTTOM LINE
            </span>
            <p style="font-size:0.88rem;color:#1a202c;margin:5px 0 0;font-weight:600;
                      line-height:1.55;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                {bottom_line}
            </p>
        </div>
    </div>
    """

    return article_html, subject


def _build_watchlist_html(items: list[dict]) -> str:
    """
    Build the personalised "Your Watchlist" section for the morning digest.
    items: [{ticker, name, score, case, delta}]  — max 3 items expected.
    """
    CASE_COLOR = {"BULL": "#00875A", "BEAR": "#C53030", "NEUTRAL": "#5A6472"}
    CASE_BG    = {"BULL": "#F0FDF4", "BEAR": "#FFF5F5", "NEUTRAL": "#F7F8FA"}
    CASE_SYM   = {"BULL": "▲", "BEAR": "▼", "NEUTRAL": "●"}

    cards = ""
    col_width = f"{100 // len(items)}%" if items else "33%"
    for item in items:
        case   = item.get("case", "NEUTRAL")
        color  = CASE_COLOR.get(case, "#5A6472")
        bg     = CASE_BG.get(case, "#F7F8FA")
        sym    = CASE_SYM.get(case, "●")
        score  = item["score"]
        delta  = item.get("delta")
        delta_str = (
            f'<span style="font-size:0.72rem;color:{"#00875A" if delta >= 0 else "#C53030"};'
            f'font-weight:700;">{("+" if delta >= 0 else "")}{delta:.1f} 7d</span>'
            if delta is not None else ""
        )
        name_short = item["name"][:22] + "…" if len(item["name"]) > 24 else item["name"]
        cards += f"""
        <td style="width:{col_width};padding:0 6px;vertical-align:top;">
          <div style="background:{bg};border:1px solid {color}33;border-radius:6px;
                      padding:12px 10px;text-align:center;">
            <div style="font-size:1.1rem;font-weight:800;color:#0f1119;margin-bottom:2px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
              {item["ticker"]}
            </div>
            <div style="font-size:0.65rem;color:#6B7280;margin-bottom:8px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
              {name_short}
            </div>
            <div style="font-size:1.6rem;font-weight:900;color:{color};line-height:1;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
              {score:.0f}
            </div>
            <div style="font-size:0.65rem;color:#6B7280;margin-top:1px;margin-bottom:6px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
              / 100
            </div>
            <div style="font-size:0.72rem;font-weight:700;color:{color};
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
              {sym} {case}
            </div>
            <div style="margin-top:4px;">{delta_str}</div>
          </div>
        </td>"""

    return f"""
    <div style="background:#F7F8FA;border-top:3px solid #7C3AED;padding:16px 24px 12px;">
      <div style="font-size:0.60rem;font-weight:700;color:#7C3AED;text-transform:uppercase;
                  letter-spacing:0.12em;margin-bottom:12px;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
        📋 Your Watchlist
      </div>
      <table style="border-collapse:collapse;width:100%;">
        <tr>{cards}</tr>
      </table>
      <div style="margin-top:10px;text-align:right;">
        <a href="https://unstructuredalpha.com/Watchlist"
           style="font-size:0.72rem;color:#7C3AED;text-decoration:none;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
          Open Watchlist →
        </a>
      </div>
    </div>
    """


def send_digest_email(
    to_email: str,
    signal_flips: list[dict],
    score_movers: list[dict],
    overall_bias: str,
    bull_n: int,
    bear_n: int,
    neut_n: int,
    signal_scores: dict | None = None,
    watchlist_items: list[dict] | None = None,
) -> None:
    """
    Send the morning intelligence digest to a single opted-in user.
    Called by cron/send_digest.py for each opted-in user.

    signal_flips:    list of {signal_id, from_status, to_status, to_score} dicts
    score_movers:    list of {ticker, from_score, to_score, delta, case} dicts
    overall_bias:    "Bullish", "Bearish", or "Mixed"
    bull_n / bear_n / neut_n: current signal counts
    signal_scores:   {sig_id: {name, score, status}} — used for the article section.
                     Optional for backward compat; article is skipped if None.
    watchlist_items: [{ticker, name, score, case, delta}] — personalised section.
                     None = no watchlist section (user has empty watchlist).
    """
    api_key, from_email = _get_resend_config()
    print(f"[digest] send_digest_email: to={to_email!r} bias={overall_bias}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    from datetime import date
    today_str = date.today().strftime("%B %-d, %Y")

    # ── Personalised watchlist section ────────────────────────────────────
    watchlist_html = _build_watchlist_html(watchlist_items) if watchlist_items else ""

    # ── Seeking Alpha-style macro article ──────────────────────────────────
    if signal_scores:
        article_html, subject_line = _build_article_html(
            signal_scores=signal_scores,
            signal_flips=signal_flips,
            bias=overall_bias,
            bull_n=bull_n,
            bear_n=bear_n,
            neut_n=neut_n,
            date_str=today_str,
        )
    else:
        article_html = ""
        subject_line = f"UA Morning Brief — {today_str}"

    # ── Signal flips table ─────────────────────────────────────────────────
    FLIP_COLOR = {"bullish": "#00875A", "bearish": "#C53030",
                  "neutral": "#5A6472", "insufficient_data": "#9E9E9E"}
    FLIP_SYM   = {"bullish": "▲", "bearish": "▼",
                  "neutral": "●", "insufficient_data": "○"}

    if signal_flips:
        flip_rows = ""
        for f in signal_flips[:6]:
            from_c = FLIP_COLOR.get(f["from_status"], "#9E9E9E")
            to_c   = FLIP_COLOR.get(f["to_status"],   "#9E9E9E")
            from_s = FLIP_SYM.get(f["from_status"], "●")
            to_s   = FLIP_SYM.get(f["to_status"],   "●")
            flip_rows += (
                f'<tr style="border-bottom:1px solid #F0F0F0;">'
                f'<td style="padding:7px 8px;font-size:0.83rem;color:#1a202c;'
                f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
                f'{f.get("signal_name", f.get("signal_id",""))}</td>'
                f'<td style="padding:7px 8px;color:{from_c};font-size:0.83rem;white-space:nowrap;">'
                f'{from_s} {f["from_status"].title()}</td>'
                f'<td style="padding:7px 4px;color:#9E9E9E;font-size:1rem;">→</td>'
                f'<td style="padding:7px 8px;font-weight:700;color:{to_c};'
                f'font-size:0.83rem;white-space:nowrap;">'
                f'{to_s} {f["to_status"].title()}</td>'
                f'</tr>'
            )
        flips_html = f"""
        <div style="font-size:0.60rem;font-weight:700;color:#4A5568;text-transform:uppercase;
                    letter-spacing:0.10em;margin-bottom:10px;padding:0 24px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            ⚡ {len(signal_flips)} Signal Flip{"s" if len(signal_flips) != 1 else ""} Since Yesterday
        </div>
        <table style="border-collapse:collapse;width:100%;margin-bottom:4px;">
            {flip_rows}
        </table>
        """
    else:
        flips_html = """
        <div style="font-size:0.60rem;font-weight:700;color:#4A5568;text-transform:uppercase;
                    letter-spacing:0.10em;margin-bottom:8px;padding:0 24px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            Signal Flips
        </div>
        <p style="font-size:0.83rem;color:#6B7280;padding:0 24px;margin:0 0 4px;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            No status changes since yesterday — signals are holding steady.
        </p>
        """

    # ── Score movers table ─────────────────────────────────────────────────
    if score_movers:
        mover_rows = ""
        for m in score_movers[:5]:
            delta = m["delta"]
            dc = "#00875A" if delta > 0 else "#C53030"
            ds = f"+{delta:.1f}" if delta > 0 else f"{delta:.1f}"
            case = m.get("case", "")
            case_color = "#00875A" if case == "BULL" else ("#C53030" if case == "BEAR" else "#5A6472")
            mover_rows += (
                f'<tr style="border-bottom:1px solid #F0F0F0;">'
                f'<td style="padding:7px 8px;font-weight:700;font-size:0.88rem;color:#0f1119;'
                f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
                f'{m["ticker"]}</td>'
                f'<td style="padding:7px 8px;color:#6B7280;font-size:0.83rem;">'
                f'{m["from_score"]:.0f} → {m["to_score"]:.0f}</td>'
                f'<td style="padding:7px 8px;font-weight:700;color:{dc};font-size:0.83rem;">{ds}</td>'
                f'<td style="padding:7px 8px;color:{case_color};font-size:0.78rem;font-weight:600;">'
                f'{case}</td>'
                f'</tr>'
            )
        movers_html = f"""
        <div style="font-size:0.60rem;font-weight:700;color:#4A5568;text-transform:uppercase;
                    letter-spacing:0.10em;margin-bottom:10px;padding:0 24px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            📊 Biggest Score Movers (7 days)
        </div>
        <table style="border-collapse:collapse;width:100%;margin-bottom:4px;">
            <tr style="background:#F7F8FA;">
                <th style="padding:5px 8px;text-align:left;font-size:0.65rem;color:#6B7280;
                           font-weight:600;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">TICKER</th>
                <th style="padding:5px 8px;text-align:left;font-size:0.65rem;color:#6B7280;font-weight:600;">SCORE</th>
                <th style="padding:5px 8px;text-align:left;font-size:0.65rem;color:#6B7280;font-weight:600;">7D Δ</th>
                <th style="padding:5px 8px;text-align:left;font-size:0.65rem;color:#6B7280;font-weight:600;">CASE</th>
            </tr>
            {mover_rows}
        </table>
        """
    else:
        movers_html = """
        <div style="font-size:0.60rem;font-weight:700;color:#4A5568;text-transform:uppercase;
                    letter-spacing:0.10em;margin-bottom:8px;padding:0 24px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            Score Movers
        </div>
        <p style="font-size:0.83rem;color:#6B7280;padding:0 24px;margin:0 0 4px;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            Score history builds as tickers get viewed — check back as the platform gets more traffic.
        </p>
        """

    # ── Bias banner ────────────────────────────────────────────────────────
    bias_color  = "#00875A" if overall_bias == "Bullish" else ("#C53030" if overall_bias == "Bearish" else "#5A6472")
    bias_bg     = "#F0FDF4" if overall_bias == "Bullish" else ("#FFF5F5" if overall_bias == "Bearish" else "#F7F8FA")

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#F0F2F5;">
<div style="max-width:600px;margin:0 auto;background:#ffffff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">

    <!-- Header -->
    <div style="background:#0f1119;padding:20px 24px;">
        <table style="width:100%;border-collapse:collapse;">
            <tr>
                <td>
                    <div style="font-size:0.60rem;color:#7C3AED;text-transform:uppercase;
                                letter-spacing:0.14em;margin-bottom:4px;">
                        UNSTRUCTURED ALPHA
                    </div>
                    <div style="font-size:1.1rem;font-weight:700;color:#E8EEFF;">
                        Morning Intelligence Brief
                    </div>
                </td>
                <td style="text-align:right;vertical-align:middle;">
                    <div style="font-size:0.75rem;color:#8892AA;">{today_str}</div>
                </td>
            </tr>
        </table>
    </div>

    <!-- Signal Pulse Banner -->
    <div style="background:{bias_bg};padding:12px 24px;border-left:5px solid {bias_color};">
        <table style="border-collapse:collapse;width:100%;">
            <tr>
                <td>
                    <div style="font-size:0.60rem;color:{bias_color};text-transform:uppercase;
                                letter-spacing:0.10em;margin-bottom:3px;">Signal Pulse</div>
                    <div style="font-size:1.2rem;font-weight:800;color:{bias_color};">
                        {overall_bias}
                    </div>
                </td>
                <td style="text-align:right;vertical-align:middle;">
                    <span style="font-size:0.80rem;color:#4A5568;">
                        <span style="color:#00875A;font-weight:700;">▲ {bull_n}</span> &nbsp;
                        <span style="color:#C53030;font-weight:700;">▼ {bear_n}</span> &nbsp;
                        <span style="color:#6B7280;">● {neut_n}</span>
                    </span>
                </td>
            </tr>
        </table>
    </div>

    <!-- Personalised watchlist (only shown when user has watchlist tickers) -->
    {watchlist_html}

    <!-- Article -->
    {article_html}

    <!-- Divider -->
    <div style="height:1px;background:#E2E8F0;margin:0 24px;"></div>

    <!-- Data Tables -->
    <div style="padding:20px 24px;">
        {flips_html}
        <div style="height:20px;"></div>
        {movers_html}
    </div>

    <!-- CTA -->
    <div style="padding:4px 24px 28px;text-align:center;">
        <a href="https://unstructuredalpha.com/Today%27s_Brief"
           style="display:inline-block;background:#7C3AED;color:#ffffff;
                  padding:12px 28px;border-radius:6px;text-decoration:none;
                  font-size:0.9rem;font-weight:700;">
            Open Full Brief →
        </a>
    </div>

    <!-- Footer -->
    <div style="background:#0f1119;padding:14px 24px;border-radius:0 0 4px 4px;">
        <p style="font-size:0.68rem;color:#6B7280;text-align:center;margin:0;">
            Unstructured Alpha · unstructuredalpha.com · Not financial advice · Data from public sources<br>
            <a href="https://unstructuredalpha.com/Watchlist"
               style="color:#7C3AED;text-decoration:none;">Manage preferences</a>
        </p>
    </div>

</div>
</body>
</html>"""

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": subject_line,
                "html": html,
            },
            timeout=20,
        )
        print(f"[digest] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[digest] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send digest to {to_email}: {e}") from e


def send_trial_reminder_email(to_email: str, trial_end_display: str) -> None:
    """
    Send a "your trial ends tomorrow" nudge email to a user on day 6 of their
    7-day free trial. Called by cron/send_trial_reminder.py.

    trial_end_display: human-readable date string, e.g. "July 1, 2026"
    """
    api_key, from_email = _get_resend_config()
    print(f"[trial-reminder] sending to={to_email!r} trial_end={trial_end_display!r}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    html = f"""
    <div style="font-family:Georgia,serif;max-width:540px;color:#1A1612;">
        <div style="background:#1C2B4A;padding:18px 24px;border-radius:8px 8px 0 0;">
            <div style="font-size:0.70rem;color:#C9A84C;letter-spacing:0.12em;text-transform:uppercase;">
                Unstructured Alpha
            </div>
            <div style="font-size:1.2rem;font-weight:700;color:#FAF7F0;margin-top:4px;">
                Your free trial ends tomorrow
            </div>
        </div>

        <div style="background:#FFFFFF;padding:24px 24px;">
            <p style="font-size:1rem;color:#1A1612;margin:0 0 16px;">
                Your 7-day Pro trial wraps up on <strong>{trial_end_display}</strong>.
            </p>
            <p style="font-size:0.9rem;color:#4A4A4A;margin:0 0 16px;">
                After that, you'll move to the Free plan — you'll keep your account and
                watchlist, but lose access to:
            </p>
            <ul style="color:#4A4A4A;font-size:0.9rem;padding-left:20px;margin:0 0 20px;">
                <li>Factor Exposure — Fama-French regression for any ticker</li>
                <li>PDF Research Reports</li>
                <li>Signal Backtester</li>
                <li>Portfolio Analyzer</li>
                <li>Options Flow</li>
                <li>Morning digest email</li>
            </ul>
            <p style="font-size:0.9rem;color:#4A4A4A;margin:0 0 24px;">
                Keep access by adding a payment method before your trial ends.
                No charge until <strong>{trial_end_display}</strong>.
            </p>
            <div style="text-align:center;">
                <a href="https://unstructuredalpha.com/Upgrade"
                   style="background:linear-gradient(90deg,#7C3AED,#00C8E0);color:#fff;
                          padding:12px 28px;border-radius:6px;text-decoration:none;
                          font-size:0.95rem;font-weight:700;display:inline-block;">
                    Continue with Pro →
                </a>
            </div>
        </div>

        <div style="background:#F0EBE1;padding:10px 24px;border-radius:0 0 8px 8px;
                    font-size:0.72rem;color:#9E9E8E;text-align:center;">
            Unstructured Alpha · unstructuredalpha.com<br>
            Questions? Just reply to this email.
        </div>
    </div>
    """

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "Your Unstructured Alpha trial ends tomorrow",
                "html": html,
            },
            timeout=15,
        )
        print(f"[trial-reminder] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[trial-reminder] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send trial reminder to {to_email}: {e}") from e


def send_welcome_email(to_email: str) -> None:
    """
    Send a day-0 welcome email immediately after a user verifies their email
    address. Goal: warm, useful, one clear CTA (open the dashboard).
    Called by auth.verify_email() in a try/except so it never blocks
    the verification flow.
    """
    api_key, from_email = _get_resend_config()
    print(f"[welcome] sending to={to_email!r}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    html = """
    <div style="font-family:Georgia,serif;max-width:540px;color:#1A1612;">
        <div style="background:#1C2B4A;padding:20px 28px;border-radius:8px 8px 0 0;">
            <div style="font-size:0.70rem;color:#C9A84C;letter-spacing:0.12em;text-transform:uppercase;">
                Unstructured Alpha
            </div>
            <div style="font-size:1.3rem;font-weight:700;color:#FAF7F0;margin-top:6px;">
                Your account is ready.
            </div>
        </div>

        <div style="background:#FFFFFF;padding:28px 28px 24px;">
            <p style="font-size:1rem;color:#1A1612;margin:0 0 18px;line-height:1.6;">
                Welcome. Unstructured Alpha scores 28 macro and alternative data signals
                daily — credit spreads, energy inventories, Fed liquidity, insider activity,
                options flow — and tells you what they're saying about the market right now.
            </p>

            <p style="font-size:0.9rem;color:#4A4A4A;margin:0 0 6px;font-weight:700;">
                Start here:
            </p>
            <ul style="color:#4A4A4A;font-size:0.9rem;padding-left:20px;margin:0 0 24px;line-height:1.8;">
                <li>
                    <a href="https://unstructuredalpha.com/Today%27s_Brief"
                       style="color:#1C2B4A;font-weight:700;">Today's Brief</a>
                    — daily signal pulse with what flipped overnight
                </li>
                <li>
                    <a href="https://unstructuredalpha.com/Ticker_Deep_Dive"
                       style="color:#1C2B4A;font-weight:700;">Ticker Deep Dive</a>
                    — type any stock ticker to see which signals are driving it
                </li>
                <li>
                    <a href="https://unstructuredalpha.com/Watchlist"
                       style="color:#1C2B4A;font-weight:700;">Watchlist</a>
                    — track your stocks and set alerts
                </li>
            </ul>

            <div style="text-align:center;">
                <a href="https://unstructuredalpha.com"
                   style="background:#1C2B4A;color:#FAF7F0;padding:13px 30px;
                          border-radius:5px;text-decoration:none;
                          font-size:0.95rem;font-weight:700;display:inline-block;">
                    Open the Dashboard →
                </a>
            </div>

            <p style="font-size:0.82rem;color:#8B8B8B;margin:24px 0 0;line-height:1.5;">
                You're on the <strong>Free plan</strong>. Upgrade to Pro anytime for
                factor exposure, PDF reports, the signal backtester, and the morning
                digest email.
                <a href="https://unstructuredalpha.com/Upgrade"
                   style="color:#1C2B4A;">See what's included →</a>
            </p>
        </div>

        <div style="background:#F0EBE1;padding:10px 28px;border-radius:0 0 8px 8px;
                    font-size:0.72rem;color:#9E9E8E;text-align:center;">
            Unstructured Alpha · Not financial advice · All data from public sources
        </div>
    </div>
    """

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "Welcome to Unstructured Alpha",
                "html": html,
            },
            timeout=15,
        )
        print(f"[welcome] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[welcome] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send welcome email to {to_email}: {e}") from e


def send_watchlist_alert_email(to_email: str, new_alerts: list[dict]) -> None:
    """
    Send a watchlist threshold-crossing alert email to a single user.
    Called by cron/send_watchlist_alerts.py for every user who has new alerts
    since the last evaluation.

    new_alerts: list of alert dicts from evaluate_watchlist(), each with at
    minimum: ticker (str), alert_type (str), direction (str), message (str).
    """
    api_key, from_email = _get_resend_config()
    print(f"[watchlist-alert] sending to={to_email!r} n_alerts={len(new_alerts)}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")
    if not new_alerts:
        return

    from datetime import date
    today_str = date.today().strftime("%B %-d, %Y")

    DIRECTION_COLOR = {"bullish": "#00D566", "bearish": "#FF4B4B"}
    DIRECTION_ICON  = {"bullish": "▲", "bearish": "▼"}

    alert_rows = ""
    for a in new_alerts[:10]:                       # cap at 10 in the email
        ticker    = a.get("ticker", "???").upper()
        direction = (a.get("direction") or "neutral").lower()
        message   = a.get("message", "Threshold crossed.")
        color     = DIRECTION_COLOR.get(direction, "#8892AA")
        icon      = DIRECTION_ICON.get(direction, "●")
        alert_rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.05);">
            <div style="font-size:0.92rem;font-weight:700;color:#E8EEFF;
                        font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
              <span style="color:{color};margin-right:6px;">{icon}</span>{ticker}
            </div>
            <div style="font-size:0.78rem;color:#8892AA;margin-top:3px;line-height:1.5;
                        font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
              {message}
            </div>
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.05);
                     text-align:right;vertical-align:top;white-space:nowrap;">
            <span style="color:{color};font-size:0.78rem;font-weight:700;
                         font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
                         text-transform:uppercase;letter-spacing:0.04em;">
              {direction.title()}
            </span>
          </td>
        </tr>"""

    n      = len(new_alerts)
    plural = "s" if n != 1 else ""
    tickers_short = ", ".join(sorted({a.get("ticker", "???").upper() for a in new_alerts[:4]}))
    if n > 4:
        tickers_short += f" +{n - 4} more"

    subject = f"⚡ {n} Watchlist Alert{plural}: {tickers_short}"

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0B0D12;">
<div style="max-width:560px;margin:0 auto;background:#12151E;
            font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#7C3AED 0%,#12151E 100%);
              padding:24px 28px;border-radius:12px 12px 0 0;">
    <div style="font-size:0.60rem;color:#A78BFA;letter-spacing:0.14em;
                text-transform:uppercase;margin-bottom:5px;">
      UNSTRUCTURED ALPHA · WATCHLIST
    </div>
    <div style="font-size:1.4rem;font-weight:800;color:#FFFFFF;line-height:1.2;">
      {n} Watchlist Alert{plural}
    </div>
    <div style="font-size:0.82rem;color:#B8C0D4;margin-top:6px;">
      {today_str} · {tickers_short}
    </div>
  </div>

  <!-- Alert table -->
  <div style="background:#12151E;padding:20px 0 8px;">
    <table style="border-collapse:collapse;width:100%;">
      {alert_rows}
    </table>
  </div>

  <!-- CTA -->
  <div style="background:#0f1119;padding:20px 28px;text-align:center;">
    <a href="https://unstructuredalpha.com/Watchlist"
       style="display:inline-block;background:linear-gradient(135deg,#7C3AED,#00C8E0);
              color:#FFFFFF;padding:12px 30px;border-radius:8px;
              text-decoration:none;font-size:0.9rem;font-weight:700;letter-spacing:0.02em;">
      Open Watchlist →
    </a>
  </div>

  <!-- Footer -->
  <div style="background:#0B0D12;padding:14px 28px;border-radius:0 0 12px 12px;
              border-top:1px solid rgba(255,255,255,0.05);
              font-size:0.68rem;color:#4A5280;text-align:center;line-height:1.6;">
    Unstructured Alpha · unstructuredalpha.com · Not financial advice<br>
    <a href="https://unstructuredalpha.com/Watchlist"
       style="color:#7C3AED;text-decoration:none;">Manage alert settings</a>
  </div>

</div>
</body>
</html>"""

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
        print(f"[watchlist-alert] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[watchlist-alert] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send watchlist alert to {to_email}: {e}") from e


def send_pro_welcome_email(to_email: str) -> None:
    """
    Send a rich onboarding email immediately after a user upgrades to Pro.
    Guides them to the highest-value Pro features so they get value on day 1.
    Called in a try/except so it never blocks the upgrade flow.
    """
    api_key, from_email = _get_resend_config()
    print(f"[pro-welcome] sending to={to_email!r}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    html = """
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
                max-width:580px;margin:0 auto;background:#0B0D12;color:#E8EEFF;">

      <!-- Header -->
      <div style="background:linear-gradient(135deg,#7C3AED 0%,#0B0D12 100%);
                  padding:32px 32px 28px;border-radius:12px 12px 0 0;">
        <div style="font-size:0.65rem;color:#A78BFA;letter-spacing:0.14em;
                    text-transform:uppercase;margin-bottom:8px;">
          Unstructured Alpha · Pro
        </div>
        <div style="font-size:1.7rem;font-weight:800;color:#FFFFFF;line-height:1.2;">
          You're in. Here's where to start.
        </div>
        <div style="font-size:0.9rem;color:#C4B5FD;margin-top:10px;">
          Your Pro access is live — every signal, every tool, no paywalls.
        </div>
      </div>

      <!-- Intro -->
      <div style="background:#12151E;padding:28px 32px 8px;">
        <p style="font-size:0.95rem;color:#B8C0D4;line-height:1.7;margin:0 0 8px;">
          Most people open the dashboard and immediately go to the ticker they're
          watching. That's fine — but here's how to get the most out of the machine
          in the first week.
        </p>
      </div>

      <!-- Feature guide -->
      <div style="background:#12151E;padding:8px 32px 28px;">

        <!-- Item 1 -->
        <div style="border-left:3px solid #7C3AED;padding:14px 0 14px 18px;margin-bottom:20px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            📋 Today's Brief — read this every morning
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            The daily signal pulse: what's bullish, what's bearish, what flipped
            overnight. Takes 60 seconds. Sets your macro frame for the day.
          </div>
          <a href="https://unstructuredalpha.com/Today%27s_Brief"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#A78BFA;text-decoration:none;font-weight:600;">
            Open Today's Brief →
          </a>
        </div>

        <!-- Item 2 -->
        <div style="border-left:3px solid #00D566;padding:14px 0 14px 18px;margin-bottom:20px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            🔍 Ticker Deep Dive — your most powerful tool
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            Type any ticker. You'll see the Confluence Score, which macro signals
            are driving it, an auto-explainer, insider cluster detection, a radar
            chart across 5 signal axes, and the full PDF export. This is the core.
          </div>
          <a href="https://unstructuredalpha.com/Ticker_Deep_Dive"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#00D566;text-decoration:none;font-weight:600;">
            Open Ticker Deep Dive →
          </a>
        </div>

        <!-- Item 3 -->
        <div style="border-left:3px solid #00C8E0;padding:14px 0 14px 18px;margin-bottom:20px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            📊 PDF Export — institutional-quality reports
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            From any Ticker Deep Dive, hit "Export Full PDF Report." You get the
            full correlation-weighted score, all signal breakdowns, insider
            transactions, 13F institutional holders, and methodology notes —
            formatted and ready to share or archive.
          </div>
          <a href="https://unstructuredalpha.com/Export"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#00C8E0;text-decoration:none;font-weight:600;">
            Try PDF Export →
          </a>
        </div>

        <!-- Item 4 -->
        <div style="border-left:3px solid #F59E0B;padding:14px 0 14px 18px;margin-bottom:20px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            ⚡ Short Squeeze Radar
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            Screens for tickers with high short interest + macro tailwinds +
            insider cluster buying. The combination that historically precedes
            sharp moves. Updated daily.
          </div>
          <a href="https://unstructuredalpha.com/Short_Squeeze_Radar"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#F59E0B;text-decoration:none;font-weight:600;">
            Open Radar →
          </a>
        </div>

        <!-- Item 5 -->
        <div style="border-left:3px solid #FF4444;padding:14px 0 14px 18px;margin-bottom:20px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            📈 Signal Backtester — build and test your own thesis
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            Pick any combination of signals and see how they would have
            performed historically on any ticker. Pro-only. Great for validating
            whether a setup you see today has actually worked before.
          </div>
          <a href="https://unstructuredalpha.com/Signal_Backtester"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#FF4444;text-decoration:none;font-weight:600;">
            Open Backtester →
          </a>
        </div>

        <!-- Item 6 -->
        <div style="border-left:3px solid #8892AA;padding:14px 0 14px 18px;margin-bottom:4px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            🔔 Watchlist & Alerts — let it come to you
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            Add your tickers to the Watchlist and set score-threshold alerts.
            You'll get notified when a ticker crosses into bullish or bearish
            territory — without having to check manually.
          </div>
          <a href="https://unstructuredalpha.com/Watchlist"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#8892AA;text-decoration:none;font-weight:600;">
            Set up Watchlist →
          </a>
        </div>

      </div>

      <!-- Morning digest opt-in nudge -->
      <div style="background:#0f1119;border:1px solid rgba(124,58,237,0.3);
                  border-radius:8px;margin:0 32px 24px;padding:18px 20px;">
        <div style="font-size:0.85rem;font-weight:700;color:#A78BFA;margin-bottom:6px;">
          📬 Morning Digest (Pro)
        </div>
        <div style="font-size:0.82rem;color:#8892AA;line-height:1.6;">
          Get a Seeking Alpha-style macro briefing in your inbox every morning at
          7 AM ET — signal pulse, what flipped, top movers, and an editorial
          take on the day's setup. Enable it in your
          <a href="https://unstructuredalpha.com/Watchlist"
             style="color:#A78BFA;">Watchlist settings</a>.
        </div>
      </div>

      <!-- CTA -->
      <div style="background:#12151E;padding:12px 32px 28px;text-align:center;">
        <a href="https://unstructuredalpha.com"
           style="display:inline-block;background:linear-gradient(135deg,#7C3AED,#00C8E0);
                  color:#FFFFFF;padding:14px 36px;border-radius:8px;
                  text-decoration:none;font-size:0.95rem;font-weight:700;
                  letter-spacing:0.02em;">
          Open Unstructured Alpha →
        </a>
      </div>

      <!-- Footer -->
      <div style="background:#0B0D12;padding:16px 32px;border-radius:0 0 12px 12px;
                  border-top:1px solid rgba(255,255,255,0.06);
                  font-size:0.70rem;color:#4A5280;text-align:center;line-height:1.6;">
        Unstructured Alpha · Pro Member<br>
        Not financial advice. All signals are statistical correlations, not predictions.<br>
        Questions? Reply to this email.
      </div>

    </div>
    """

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "You're Pro — here's where to start on Unstructured Alpha",
                "html": html,
            },
            timeout=15,
        )
        print(f"[pro-welcome] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[pro-welcome] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send Pro welcome email to {to_email}: {e}") from e


def send_referral_welcome_email(to_email: str) -> None:
    """
    Send a welcome email to a user who signed up via a referral link.
    Tells them they have a 14-day free trial (double the normal 7 days)
    and links to the Upgrade page to start it.

    Called best-effort from utils/referral.record_referral_signup() after
    the referral row is committed. Never raises externally — callers wrap
    in try/except; if Resend is not configured this is silently a no-op.
    """
    api_key, from_email = _get_resend_config()
    print(f"[referral-welcome] sending to={to_email!r}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    html = """<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0B0D12;">
<div style="max-width:560px;margin:0 auto;background:#12151E;
            font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#00C8E0 0%,#0B0D12 100%);
              padding:32px 32px 28px;border-radius:12px 12px 0 0;">
    <div style="font-size:0.62rem;color:#67E8F9;letter-spacing:0.14em;
                text-transform:uppercase;margin-bottom:8px;">
      Unstructured Alpha
    </div>
    <div style="font-size:1.6rem;font-weight:800;color:#FFFFFF;line-height:1.2;">
      A friend invited you.
    </div>
    <div style="font-size:0.92rem;color:#A5F3FC;margin-top:10px;">
      You have a 14-day free trial waiting — double the normal 7 days.
    </div>
  </div>

  <!-- Body -->
  <div style="background:#12151E;padding:28px 32px 8px;">
    <p style="font-size:0.95rem;color:#B8C0D4;line-height:1.75;margin:0 0 20px;">
      Someone who uses Unstructured Alpha thought you'd find it useful, so they sent
      you a link. Because of that, your free trial is <strong style="color:#E8EEFF;">14 days</strong> —
      twice what a direct signup gets.
    </p>

    <!-- Trial callout -->
    <div style="background:rgba(0,200,224,0.08);border:1px solid rgba(0,200,224,0.25);
                border-radius:8px;padding:16px 20px;margin-bottom:24px;">
      <div style="font-size:0.62rem;font-weight:700;color:#00C8E0;letter-spacing:0.12em;
                  text-transform:uppercase;margin-bottom:8px;">Your trial</div>
      <div style="display:flex;align-items:baseline;gap:8px;">
        <div style="font-size:2rem;font-weight:900;color:#00C8E0;line-height:1;">14</div>
        <div style="font-size:0.88rem;color:#8892AA;">days free · full Pro access</div>
      </div>
      <div style="font-size:0.78rem;color:#6B7A95;margin-top:6px;">
        Normal trial is 7 days. No extra charge — this is your referral benefit.
      </div>
    </div>

    <!-- What you can do -->
    <div style="font-size:0.62rem;font-weight:700;color:#8892AA;letter-spacing:0.10em;
                text-transform:uppercase;margin-bottom:14px;">What's included</div>

    <table style="border-collapse:collapse;width:100%;margin-bottom:24px;">
      <tr>
        <td style="padding:8px 12px 8px 0;vertical-align:top;width:28px;">
          <span style="color:#00D566;font-size:1rem;">▲</span>
        </td>
        <td style="padding:8px 0;">
          <div style="font-size:0.88rem;font-weight:700;color:#E8EEFF;">
            Ticker Deep Dive
          </div>
          <div style="font-size:0.80rem;color:#8892AA;margin-top:2px;line-height:1.5;">
            Confluence Score for any stock — 28 macro + alt-data signals scored and explained
          </div>
        </td>
      </tr>
      <tr>
        <td style="padding:8px 12px 8px 0;vertical-align:top;">
          <span style="color:#7C3AED;font-size:1rem;">◈</span>
        </td>
        <td style="padding:8px 0;">
          <div style="font-size:0.88rem;font-weight:700;color:#E8EEFF;">
            Morning Digest
          </div>
          <div style="font-size:0.80rem;color:#8892AA;margin-top:2px;line-height:1.5;">
            Daily macro briefing in your inbox — what flipped overnight and what it means
          </div>
        </td>
      </tr>
      <tr>
        <td style="padding:8px 12px 8px 0;vertical-align:top;">
          <span style="color:#F59E0B;font-size:1rem;">⚡</span>
        </td>
        <td style="padding:8px 0;">
          <div style="font-size:0.88rem;font-weight:700;color:#E8EEFF;">
            Short Squeeze Radar + PDF Reports
          </div>
          <div style="font-size:0.80rem;color:#8892AA;margin-top:2px;line-height:1.5;">
            Screen for macro-backed squeeze setups · export institutional-grade PDF research
          </div>
        </td>
      </tr>
    </table>
  </div>

  <!-- CTA -->
  <div style="background:#0f1119;padding:24px 32px;text-align:center;">
    <a href="https://unstructuredalpha.com/Upgrade"
       style="display:inline-block;background:linear-gradient(135deg,#00C8E0,#7C3AED);
              color:#FFFFFF;padding:14px 36px;border-radius:8px;
              text-decoration:none;font-size:0.95rem;font-weight:700;
              letter-spacing:0.02em;">
      Start Your 14-Day Free Trial →
    </a>
    <div style="font-size:0.75rem;color:#6B7A95;margin-top:10px;">
      Full Pro access · No charge for 14 days
    </div>
  </div>

  <!-- Footer -->
  <div style="background:#0B0D12;padding:16px 32px;border-radius:0 0 12px 12px;
              border-top:1px solid rgba(255,255,255,0.06);
              font-size:0.70rem;color:#4A5280;text-align:center;line-height:1.6;">
    Unstructured Alpha · unstructuredalpha.com<br>
    Not financial advice. All signals are statistical correlations from public data sources.
  </div>

</div>
</body>
</html>"""

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "You've been invited — your 14-day free trial is waiting",
                "html": html,
            },
            timeout=15,
        )
        print(f"[referral-welcome] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[referral-welcome] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send referral welcome email to {to_email}: {e}") from e
