# pages/38_Admin.py
# Unstructured Alpha — Admin Dashboard
#
# Gated to the admin email (ADMIN_EMAIL below). Anyone else sees a blank
# "access denied" message — no information leakage, no error stack traces.
#
# Metrics shown:
#   • Top-line KPIs: total users, verified, Pro, trial, free, digest opt-ins
#   • Acquisition: signups today / 7d / 30d
#   • Engagement: active users (login in last 7d / 30d)
#   • Conversion funnel: signup → verified → pro
#   • Daily signup chart (last 30 days)
#   • Recent signups table (last 50)
#   • Referral stats
#   • Watchlist adoption

import json

import streamlit as st

st.set_page_config(
    page_title="Admin — UA",
    layout="wide",
    initial_sidebar_state="expanded",
)

from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, text

from utils import ua_charts
from utils.conversion_measurement import (
    build_conversion_measurement,
    load_conversion_rows,
)
from utils.header import render_header, render_page_header, render_sidebar_base
from utils.db import engine, users, referrals, watchlist
from utils.theme import inject_premium_css, PLOTLY_CONFIG
from utils.billing import is_admin

render_header("Admin")
inject_premium_css()

# ── Access gate ───────────────────────────────────────────────────────────────
# Uses the centralized is_admin() allowlist (utils/billing.py) — single source
# of truth shared with the header's ADMIN badge and admin-only nav link.

if not is_admin(st.session_state.get("user")):
    st.error("Access denied.")
    st.stop()

_admin_section = render_sidebar_base(
    page_title="Admin",
    sections=("Conversion Measurement", "Operations"),
    section_key="admin_section_rail",
)

render_page_header(
    "Admin Dashboard",
    (
        "Pre/post redesign conversion evidence — live from stored records."
        if _admin_section == "Conversion Measurement"
        else "User metrics, acquisition funnel, and engagement — live from the DB."
    ),
    icon="",
)

# ── Query helpers ─────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)  # refresh every minute
def load_metrics() -> dict:
    """Pull all admin metrics in one DB trip bundle. Returns a flat dict."""
    now = _now_utc()
    d1  = _iso(now - timedelta(days=1))
    d7  = _iso(now - timedelta(days=7))
    d30 = _iso(now - timedelta(days=30))

    with engine.connect() as conn:
        # ── Top-line counts ────────────────────────────────────────────────
        total        = conn.execute(select(func.count()).select_from(users)).scalar() or 0
        verified     = conn.execute(
            select(func.count()).where(users.c.email_verified == True)  # noqa: E712
        ).scalar() or 0
        pro_count    = conn.execute(
            select(func.count()).where(users.c.subscription_tier == "pro")
        ).scalar() or 0
        trial_count  = conn.execute(
            select(func.count()).where(
                (users.c.subscription_tier == "pro") &
                (users.c.trial_end_at != None)  # noqa: E711
            )
        ).scalar() or 0
        free_count   = conn.execute(
            select(func.count()).where(users.c.subscription_tier == "free")
        ).scalar() or 0
        digest_count = conn.execute(
            select(func.count()).where(users.c.digest_opted_in == True)  # noqa: E712
        ).scalar() or 0

        # ── Acquisition ───────────────────────────────────────────────────
        new_today = conn.execute(
            select(func.count()).where(users.c.created_at >= d1)
        ).scalar() or 0
        new_7d    = conn.execute(
            select(func.count()).where(users.c.created_at >= d7)
        ).scalar() or 0
        new_30d   = conn.execute(
            select(func.count()).where(users.c.created_at >= d30)
        ).scalar() or 0

        # ── Engagement ────────────────────────────────────────────────────
        active_7d  = conn.execute(
            select(func.count()).where(
                (users.c.last_login_at != None) &  # noqa: E711
                (users.c.last_login_at >= d7)
            )
        ).scalar() or 0
        active_30d = conn.execute(
            select(func.count()).where(
                (users.c.last_login_at != None) &  # noqa: E711
                (users.c.last_login_at >= d30)
            )
        ).scalar() or 0

        # ── Daily signups (last 30 days) ──────────────────────────────────
        # We can't use DATE() portably across SQLite/Postgres in SQLAlchemy
        # Core easily, so pull the raw created_at strings and bucket in Python.
        rows = conn.execute(
            select(users.c.created_at).where(users.c.created_at >= d30)
        ).fetchall()
        daily_counts: dict[str, int] = {}
        for (ts,) in rows:
            day = ts[:10] if ts else None  # first 10 chars = YYYY-MM-DD
            if day:
                daily_counts[day] = daily_counts.get(day, 0) + 1

        # ── Recent signups (last 50) ──────────────────────────────────────
        recent = conn.execute(
            select(
                users.c.email,
                users.c.created_at,
                users.c.email_verified,
                users.c.subscription_tier,
                users.c.trial_end_at,
                users.c.last_login_at,
                users.c.digest_opted_in,
            ).order_by(users.c.created_at.desc()).limit(50)
        ).fetchall()

        # ── Referrals ─────────────────────────────────────────────────────
        try:
            ref_total     = conn.execute(select(func.count()).select_from(referrals)).scalar() or 0
            ref_converted = conn.execute(
                select(func.count()).where(referrals.c.status == "converted")
            ).scalar() or 0
            ref_rewarded  = conn.execute(
                select(func.count()).where(referrals.c.status == "rewarded")
            ).scalar() or 0
        except Exception:
            ref_total = ref_converted = ref_rewarded = 0

        # ── Watchlist adoption ────────────────────────────────────────────
        users_with_watchlist = conn.execute(
            select(func.count(func.distinct(watchlist.c.user_id)))
        ).scalar() or 0

    return {
        "total": total,
        "verified": verified,
        "pro": pro_count,
        "trial": trial_count,
        "free": free_count,
        "digest": digest_count,
        "new_today": new_today,
        "new_7d": new_7d,
        "new_30d": new_30d,
        "active_7d": active_7d,
        "active_30d": active_30d,
        "daily_counts": daily_counts,
        "recent": recent,
        "ref_total": ref_total,
        "ref_converted": ref_converted,
        "ref_rewarded": ref_rewarded,
        "users_with_watchlist": users_with_watchlist,
    }


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def load_traffic() -> dict:
    """
    Traffic + engagement from the analytics_events table (page_view events are
    emitted by render_header on every navigation). All wrapped defensively so a
    missing table or empty data never breaks the page.
    """
    now = _now_utc()
    d1  = _iso(now - timedelta(days=1))
    d7  = _iso(now - timedelta(days=7))
    d30 = _iso(now - timedelta(days=30))
    out = {
        "pv_today": 0, "pv_7d": 0, "pv_30d": 0,
        "uniq_today": 0, "uniq_7d": 0, "uniq_30d": 0,
        "sessions_7d": 0, "new_visitors_7d": 0, "returning_visitors_7d": 0,
        "engaged_visitors_7d": 0, "identity_coverage_30d": 0.0,
        "anon_7d": 0, "loggedin_7d": 0,
        "top_pages": [], "daily_views": {}, "daily_visitors": {},
        "device_breakdown": [], "event_breakdown": [], "total_events": 0,
    }
    try:
        with engine.connect() as conn:
            out["total_events"] = conn.execute(
                text("SELECT COUNT(*) FROM analytics_events")
            ).scalar() or 0

            # One bounded query feeds all traffic, page, and device metrics.
            pv_rows = conn.execute(
                text(
                    "SELECT visitor_id, session_id, user_id, properties, "
                    "created_at, device_type FROM analytics_events "
                    "WHERE event_name='page_view' AND created_at >= :d"
                ),
                {"d": d30},
            ).fetchall()
            page_stats: dict[str, dict] = {}
            daily_views: dict[str, int] = {}
            daily_visitor_sets: dict[str, set] = {}
            device_stats: dict[str, dict] = {}
            visitor_views_7d: dict[str, int] = {}
            visitors_today: set[str] = set()
            visitors_7d: set[str] = set()
            visitors_30d: set[str] = set()
            sessions_7d: set[str] = set()
            identified_30d = 0

            for visitor_id, session_id, user_id, props, ts, device_type in pv_rows:
                ts = str(ts or "")
                in_7d = ts >= d7
                in_1d = ts >= d1
                out["pv_30d"] += 1
                if in_7d:
                    out["pv_7d"] += 1
                    if user_id is None:
                        out["anon_7d"] += 1
                    else:
                        out["loggedin_7d"] += 1
                    if session_id:
                        sessions_7d.add(str(session_id))
                if in_1d:
                    out["pv_today"] += 1

                if visitor_id:
                    visitor_id = str(visitor_id)
                    identified_30d += 1
                    visitors_30d.add(visitor_id)
                    if in_7d:
                        visitors_7d.add(visitor_id)
                        visitor_views_7d[visitor_id] = visitor_views_7d.get(visitor_id, 0) + 1
                    if in_1d:
                        visitors_today.add(visitor_id)

                try:
                    page = (json.loads(props) or {}).get("page", "?") if props else "?"
                except Exception:
                    page = "?"
                page = str(page or "?")
                stats = page_stats.setdefault(
                    page, {"views": 0, "visitors": set(), "logged_in": 0}
                )
                stats["views"] += 1
                if visitor_id:
                    stats["visitors"].add(visitor_id)
                if user_id is not None:
                    stats["logged_in"] += 1

                day = ts[:10] if ts else None
                if day:
                    daily_views[day] = daily_views.get(day, 0) + 1
                    if visitor_id:
                        daily_visitor_sets.setdefault(day, set()).add(visitor_id)

                device = str(device_type or "unknown").title()
                device_row = device_stats.setdefault(
                    device, {"views": 0, "visitors": set()}
                )
                device_row["views"] += 1
                if visitor_id:
                    device_row["visitors"].add(visitor_id)

            out["uniq_today"] = len(visitors_today)
            out["uniq_7d"] = len(visitors_7d)
            out["uniq_30d"] = len(visitors_30d)
            out["sessions_7d"] = len(sessions_7d)
            out["engaged_visitors_7d"] = sum(
                count >= 2 for count in visitor_views_7d.values()
            )
            out["identity_coverage_30d"] = (
                identified_30d / out["pv_30d"] * 100 if out["pv_30d"] else 0.0
            )
            out["daily_views"] = daily_views
            out["daily_visitors"] = {
                day: len(ids) for day, ids in daily_visitor_sets.items()
            }

            out["top_pages"] = [
                {
                    "Page": page,
                    "Views": stats["views"],
                    "Visitors": len(stats["visitors"]),
                    "Views / Visitor": round(
                        stats["views"] / len(stats["visitors"]), 1
                    ) if stats["visitors"] else 0.0,
                    "Traffic Share": f"{stats['views'] / out['pv_30d'] * 100:.1f}%",
                    "Signed-in Share": f"{stats['logged_in'] / stats['views'] * 100:.1f}%",
                }
                for page, stats in sorted(
                    page_stats.items(), key=lambda item: -item[1]["views"]
                )[:15]
            ]
            out["device_breakdown"] = [
                {
                    "Device": device,
                    "Visitors": len(stats["visitors"]),
                    "Views": stats["views"],
                    "Traffic Share": f"{stats['views'] / out['pv_30d'] * 100:.1f}%",
                }
                for device, stats in sorted(
                    device_stats.items(), key=lambda item: -item[1]["views"]
                )
            ]

            first_seen_rows = conn.execute(
                text(
                    "SELECT visitor_id, MIN(created_at) FROM analytics_events "
                    "WHERE event_name='page_view' AND visitor_id IS NOT NULL "
                    "GROUP BY visitor_id"
                )
            ).fetchall()
            first_seen = {str(visitor_id): str(ts) for visitor_id, ts in first_seen_rows}
            out["new_visitors_7d"] = sum(
                first_seen.get(visitor_id, "") >= d7 for visitor_id in visitors_7d
            )
            out["returning_visitors_7d"] = (
                out["uniq_7d"] - out["new_visitors_7d"]
            )

            # Event-type breakdown (last 30d) — what are users actually doing.
            ev_rows = conn.execute(
                text("SELECT event_name, COUNT(*) c FROM analytics_events "
                     "WHERE created_at >= :d GROUP BY event_name ORDER BY c DESC"), {"d": d30}
            ).fetchall()
            out["event_breakdown"] = [(r[0], r[1]) for r in ev_rows][:15]
    except Exception:
        pass
    return out


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def load_conversion_measurement() -> dict:
    """Load the five redesign-conversion questions from stored records only."""
    page_rows, signup_rows = load_conversion_rows()
    return build_conversion_measurement(page_rows, signup_rows)


def _pct(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:.1f}%"


def _render_conversion_measurement(data: dict) -> None:
    """Render only the five questions requested by the redesign audit."""
    import pandas as pd

    st.markdown(ua_charts.CHART_CSS, unsafe_allow_html=True)
    st.markdown(
        """
<style>
.ua-conversion-boundary {
    background:linear-gradient(135deg,rgba(var(--ua-purple-rgb),0.12),
        rgba(var(--ua-cyan-rgb),0.05));
    border:1px solid rgba(var(--ua-purple-rgb),0.30);
    border-left:3px solid var(--ua-purple);
    border-radius:12px;
    color:var(--ua-ink);
    margin:4px 0 18px;
    padding:14px 16px;
}
.ua-conversion-boundary strong {
    color:var(--ua-ink);
}
.ua-conversion-boundary span {
    color:var(--ua-ink-mut);
}
</style>
""",
        unsafe_allow_html=True,
    )

    totals = data["totals"]
    st.markdown("### Redesign conversion measurement")
    st.caption(
        f"Real stored records only · {data['window_start']} through "
        f"{data['window_end']} UTC · refreshes every 60 seconds"
    )
    st.markdown(
        f"""
<div class="ua-conversion-boundary">
  <strong>Redesign boundary: {data["redesign_start"]} → {data["redesign_end"]}</strong><br>
  <span>Weeks touching these dates are labelled “Redesign rollout overlap” rather
  than being presented as clean pre- or post-redesign evidence.</span>
</div>
""",
        unsafe_allow_html=True,
    )

    summary_cols = st.columns(4)
    summary_cols[0].metric(
        "Unique visitors (30d)",
        (
            f"{totals['unique_visitors']:,}"
            if totals["unique_visitors"] is not None
            else "Unavailable"
        ),
        help=(
            "Exact only when every stored page view carries the privacy-safe "
            "visitor identifier."
        ),
    )
    summary_cols[1].metric("Signups (30d)", f"{totals['signups']:,}")
    summary_cols[2].metric(
        "Visitor → signup (30d)", _pct(totals["conversion_rate"])
    )
    summary_cols[3].metric(
        "Visitor identity coverage", f"{totals['identity_coverage']:.1f}%"
    )

    if totals["page_views"] and totals["signups"] == 0:
        st.warning(
            "The stored traffic window contains real page views and zero signups. "
            "That points to distribution or the value proposition—not missing "
            "product features. The next move should be user conversations and "
            "funnel testing, not feature 21."
        )
    elif totals["conversion_rate"] is None:
        st.info(
            "An exact 30-day conversion rate is unavailable because "
            f"{totals['excluded_page_views']:,} page view(s) lack the visitor "
            "identity required for a defensible denominator. Those views are "
            "excluded, not treated as new visitors."
        )
    else:
        st.success(
            f"The exact observed 30-day visitor → signup rate is "
            f"{totals['conversion_rate']:.1f}% "
            f"({totals['signups']:,} signup(s) from "
            f"{totals['unique_visitors']:,} unique visitor(s))."
        )

    st.markdown("#### 1. Unique visitors per day")
    daily = data["daily"]
    visitor_rows = [
        {
            "Date (UTC)": row["date"],
            "Unique visitors": (
                row["unique_visitors"]
                if row["unique_visitors"] is not None
                else "Unavailable"
            ),
            "Identity coverage": f"{row['identity_coverage']:.1f}%",
            "Excluded page views": row["excluded_page_views"],
        }
        for row in daily
    ]
    st.dataframe(pd.DataFrame(visitor_rows), width="stretch", hide_index=True)
    if any(row["excluded_page_views"] for row in daily):
        st.caption(
            "A day is marked Unavailable if even one stored page view lacks "
            "visitor identity; the view does not invent a distinct-visitor count."
        )
    else:
        labels = [
            row["date"][5:] if index % 5 == 0 or index == len(daily) - 1 else ""
            for index, row in enumerate(daily)
        ]
        st.markdown(
            ua_charts.bar_v(
                labels,
                [row["unique_visitors"] or 0 for row in daily],
                y_title="Unique visitors",
                H=230,
            ),
            unsafe_allow_html=True,
        )

    st.markdown("#### 2. Signups per day")
    signup_rows = [
        {"Date (UTC)": row["date"], "Signups": row["signups"]}
        for row in daily
    ]
    st.dataframe(pd.DataFrame(signup_rows), width="stretch", hide_index=True)
    signup_labels = [
        row["date"][5:] if index % 5 == 0 or index == len(daily) - 1 else ""
        for index, row in enumerate(daily)
    ]
    st.markdown(
        ua_charts.bar_v(
            signup_labels,
            [row["signups"] for row in daily],
            y_title="Signups",
            H=230,
        ),
        unsafe_allow_html=True,
    )

    st.markdown("#### 3. Weekly visitor → signup conversion")
    weekly_rows = [
        {
            "Week": f"{row['week_start']} → {row['week_end']}",
            "Design phase": row["phase"],
            "Unique visitors": (
                row["unique_visitors"]
                if row["unique_visitors"] is not None
                else "Unavailable"
            ),
            "Signups": row["signups"],
            "Conversion": _pct(row["conversion_rate"]),
            "Identity coverage": f"{row['identity_coverage']:.1f}%",
            "Excluded page views": row["excluded_page_views"],
        }
        for row in data["weekly"]
    ]
    st.dataframe(pd.DataFrame(weekly_rows), width="stretch", hide_index=True)
    exact_weeks = [
        row for row in data["weekly"] if row["conversion_rate"] is not None
    ]
    if exact_weeks:
        st.markdown(
            ua_charts.bar_v(
                [row["week_start"][5:] for row in exact_weeks],
                [row["conversion_rate"] for row in exact_weeks],
                max_v=max(
                    1.0,
                    max(row["conversion_rate"] for row in exact_weeks) * 1.15,
                ),
                y_title="Conversion %",
                H=230,
            ),
            unsafe_allow_html=True,
        )
    else:
        st.info(
            "No week in this window has both a non-zero visitor denominator and "
            "complete visitor identity, so a weekly conversion chart would be "
            "misleading and is not rendered."
        )

    st.markdown("#### 4. Landing-page bounce proxy")
    bounce = data["bounce"]
    bounce_cols = st.columns(3)
    bounce_cols[0].metric("Tracked landing sessions", bounce["landing_sessions"])
    bounce_cols[1].metric("Exactly one page", bounce["one_page_sessions"])
    bounce_cols[2].metric("More than one page", bounce["multi_page_sessions"])
    if bounce["landing_sessions"]:
        st.markdown(
            ua_charts.bar_h(
                ["Exactly one page", "More than one page"],
                [bounce["one_page_sessions"], bounce["multi_page_sessions"]],
                H=180,
            ),
            unsafe_allow_html=True,
        )
        st.caption(
            f"One-page rate: {_pct(bounce['one_page_rate'])}. This is a proxy "
            "for sessions whose first recorded page is Home/Landing; it does "
            "not claim to measure dwell time."
        )
    else:
        st.info("No stored session in this window starts on Home/Landing.")
    if bounce["page_views_without_session"]:
        st.caption(
            f"{bounce['page_views_without_session']:,} page view(s) without a "
            "session ID were excluded. Session coverage is "
            f"{bounce['session_coverage']:.1f}%."
        )

    st.markdown("#### 5. Last page viewed before signup")
    attribution = data["attribution"]
    attr_cols = st.columns(3)
    attr_cols[0].metric("Signups", totals["signups"])
    attr_cols[1].metric("Attributable", attribution["attributed_count"])
    attr_cols[2].metric("Unattributed", attribution["unattributed_count"])
    if attribution["pages"]:
        st.dataframe(
            pd.DataFrame(
                [
                    {"Last page before signup": row["page"], "Signups": row["signups"]}
                    for row in attribution["pages"]
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    elif totals["signups"]:
        st.info("No signup in this window can be linked to a prior page view.")
    else:
        st.info("There are no signups in this window to attribute.")
    st.warning(
        f"Stored-schema limit: {attribution['schema_gap']} "
        f"Attribution coverage is {attribution['coverage']:.1f}%. "
        f"Smallest future addition: {attribution['smallest_addition']}"
    )

    excluded = data["excluded"]
    if excluded["invalid_page_timestamps"] or excluded["invalid_signup_timestamps"]:
        st.caption(
            "Excluded malformed timestamps: "
            f"{excluded['invalid_page_timestamps']} page view(s), "
            f"{excluded['invalid_signup_timestamps']} signup(s)."
        )


# ── Load data ─────────────────────────────────────────────────────────────────

if _admin_section == "Conversion Measurement":
    try:
        with st.spinner("Measuring the redesign against stored traffic…"):
            with st.container(key="admin_conversion_measurement"):
                _render_conversion_measurement(load_conversion_measurement())
    except Exception as exc:
        st.error(
            "Conversion measurement is unavailable because the stored analytics "
            f"records could not be read ({type(exc).__name__}). "
            "No values were substituted."
        )
    st.stop()

# ── System health (rate-limiter backend; Operations view only) ────────────────
try:
    from utils.ratelimit import backend as _rl_backend
    _rlb = _rl_backend()
    if _rlb == "redis":
        st.caption(" Rate limiter: **Redis** (distributed, shared across instances)")
    else:
        st.caption(" Rate limiter: **in-process fallback** — REDIS_URL unset or Redis "
                   "unreachable. Limits are per-process only; check the Key Value service.")
except Exception:
    pass

# The timing summary is deliberately session-local: no visitor identifier,
# request metadata, or additional database record is created. An admin can open
# Home, return here, and see exactly which sequential render phase dominated.
with st.expander("Home render diagnostics (this session)", expanded=False):
    _home_perf = st.session_state.get("_ua_home_perf_last")
    if not isinstance(_home_perf, dict) or not _home_perf.get("phases"):
        st.info(
            "Open Home once in this browser session, then return to Operations. "
            "The latest render will appear here."
        )
    else:
        _home_phases = _home_perf["phases"]
        _slowest = max(
            _home_phases,
            key=lambda phase: float(phase.get("duration_ms", 0)),
        )
        _hp1, _hp2, _hp3 = st.columns(3)
        _hp1.metric("Total Home render", f"{float(_home_perf.get('total_ms', 0)) / 1000:.2f}s")
        _hp2.metric("Slowest phase", str(_slowest.get("phase", "Unknown")).replace("_", " ").title())
        _hp3.metric("Slowest duration", f"{float(_slowest.get('duration_ms', 0)) / 1000:.2f}s")
        st.caption(
            f"Captured {_home_perf.get('captured_at', 'during the latest Home render')}. "
            "Sequential timings are also emitted to application logs."
        )
        st.dataframe(
            [
                {
                    "Phase": str(phase.get("phase", "")).replace("_", " ").title(),
                    "Duration (ms)": float(phase.get("duration_ms", 0)),
                    "Status": "Complete" if phase.get("success", False) else "Failed",
                }
                for phase in sorted(
                    _home_phases,
                    key=lambda item: float(item.get("duration_ms", 0)),
                    reverse=True,
                )
            ],
            width="stretch",
            hide_index=True,
        )

with st.spinner("Loading metrics..."):
    m = load_metrics()
    tr = load_traffic()

# ── KPI cards ─────────────────────────────────────────────────────────────────

st.markdown("###  Top-Line KPIs")

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Users", m["total"])
c2.metric("Verified", m["verified"],
          delta=f"{round(m['verified']/m['total']*100)}% of total" if m["total"] else None)
c3.metric("Pro", m["pro"],
          delta=f"{round(m['pro']/m['total']*100)}% of total" if m["total"] else None)
c4.metric("On Trial", m["trial"])
c5.metric("Free", m["free"])
c6.metric("Digest Opt-in", m["digest"])

st.markdown("---")

# ── Revenue (estimated) ───────────────────────────────────────────────────────

st.markdown("###  Revenue (estimated)")

_PRO_MONTHLY = 20  # $/mo — Pro monthly list price (see billing.py)
_mrr = m["pro"] * _PRO_MONTHLY
_conv = (m["pro"] / m["total"] * 100) if m["total"] else 0
rv1, rv2, rv3, rv4 = st.columns(4)
rv1.metric("Est. MRR", f"${_mrr:,}", help="Pro subscribers × $20/mo. Annual plans pay ~$16/mo, so this is a slight over-estimate.")
rv2.metric("Est. ARR", f"${_mrr * 12:,}")
rv3.metric("Paid Conversion", f"{_conv:.1f}%", help="Pro ÷ total users")
rv4.metric("Free → Pro headroom", f"{m['free']:,}", help="Free users not yet converted")

st.markdown("---")

# ── Traffic ───────────────────────────────────────────────────────────────────

st.markdown("###  Traffic")
st.caption(
    "Unique visitors use a salted, one-way network + coarse-device identifier — "
    "not Streamlit sessions. Raw IP addresses and full user-agent strings are never "
    "stored. Corrected visitor identity applies to events collected after this deploy."
)

t1, t2, t3, t4 = st.columns(4)
t1.metric("Page Views (24h)", f"{tr['pv_today']:,}")
t2.metric("Page Views (7d)",  f"{tr['pv_7d']:,}")
t3.metric("Page Views (30d)", f"{tr['pv_30d']:,}")
t4.metric("Unique Visitors (24h)", f"{tr['uniq_today']:,}")

t5, t6, t7, t8 = st.columns(4)
_views_per_visitor = (tr["pv_7d"] / tr["uniq_7d"]) if tr["uniq_7d"] else 0
t5.metric("Unique Visitors (7d)", f"{tr['uniq_7d']:,}")
t6.metric("Unique Visitors (30d)", f"{tr['uniq_30d']:,}")
t7.metric("Views / Visitor (7d)", f"{_views_per_visitor:.1f}")
t8.metric(
    "Sessions (7d)", f"{tr['sessions_7d']:,}",
    help="Sessions remain an engagement metric, but no longer define unique visitors.",
)

t9, t10, t11, t12 = st.columns(4)
_engaged_rate = (
    tr["engaged_visitors_7d"] / tr["uniq_7d"] * 100 if tr["uniq_7d"] else 0
)
t9.metric("New Visitors (7d)", f"{tr['new_visitors_7d']:,}")
t10.metric("Returning Visitors (7d)", f"{tr['returning_visitors_7d']:,}")
t11.metric(
    "Engaged Visitors (7d)", f"{_engaged_rate:.1f}%",
    help="Identified visitors with two or more page views in the last 7 days.",
)
t12.metric(
    "Identity Coverage (30d)", f"{tr['identity_coverage_30d']:.1f}%",
    help="Share of page views carrying the new privacy-safe visitor ID.",
)

if tr["pv_30d"] == 0:
    st.info("No page-view data yet. Traffic accrues from now that page-view "
            "tracking is live — check back after users browse the app.")
else:
    # Daily page views (last 30 days)
    import plotly.graph_objects as go
    today = datetime.now(timezone.utc).date()
    all_days = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    view_counts = [tr["daily_views"].get(d, 0) for d in all_days]
    visitor_counts = [tr["daily_visitors"].get(d, 0) for d in all_days]
    figv = go.Figure()
    figv.add_bar(
        x=all_days, y=view_counts, name="Page views", marker_color="#6470F5"
    )
    figv.add_scatter(
        x=all_days, y=visitor_counts, name="Unique visitors",
        mode="lines+markers", line={"color": "#8B7BF7", "width": 2},
    )
    figv.update_layout(
        title="Daily Traffic (last 30 days)",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"showgrid": False},
        yaxis={"showgrid": True, "gridcolor": "rgba(255,255,255,0.08)"},
        margin={"t": 40, "b": 40, "l": 40, "r": 10}, height=280,
        legend={"orientation": "h", "y": 1.12},
    )
    st.plotly_chart(figv, width="stretch", config=PLOTLY_CONFIG, theme=None)

    tp_col, device_col = st.columns([2, 1])
    with tp_col:
        st.markdown("**Page Performance (30d)**")
        if tr["top_pages"]:
            import pandas as pd
            st.dataframe(
                pd.DataFrame(tr["top_pages"]),
                width="stretch", hide_index=True,
            )
        else:
            st.caption("No page data yet.")
    with device_col:
        st.markdown("**Devices (30d)**")
        if tr["device_breakdown"]:
            import pandas as pd
            st.dataframe(
                pd.DataFrame(tr["device_breakdown"]),
                width="stretch", hide_index=True,
            )
        else:
            st.caption("No device data yet.")

    mix_col, ev_col = st.columns(2)
    with mix_col:
        st.markdown("**Audience Mix (7d)**")
        import pandas as pd
        st.dataframe(
            pd.DataFrame([
                {"Audience": "Logged-in page views", "Views": tr["loggedin_7d"]},
                {"Audience": "Anonymous page views", "Views": tr["anon_7d"]},
            ]),
            width="stretch", hide_index=True,
        )
    with ev_col:
        st.markdown("**Event Breakdown (30d)**")
        if tr["event_breakdown"]:
            import pandas as pd
            st.dataframe(
                pd.DataFrame(tr["event_breakdown"], columns=["Event", "Count"]),
                width="stretch", hide_index=True,
            )
        else:
            st.caption("No events yet.")

st.markdown("---")

# ── Acquisition ───────────────────────────────────────────────────────────────

st.markdown("###  Acquisition")

a1, a2, a3 = st.columns(3)
a1.metric("New Today",    m["new_today"])
a2.metric("New (7 days)", m["new_7d"])
a3.metric("New (30 days)", m["new_30d"])

# ── Engagement ────────────────────────────────────────────────────────────────

st.markdown("###  Engagement")

e1, e2, e3 = st.columns(3)
e1.metric("Active (7d)",  m["active_7d"],
          delta=f"{round(m['active_7d']/m['total']*100)}% of users" if m["total"] else None)
e2.metric("Active (30d)", m["active_30d"],
          delta=f"{round(m['active_30d']/m['total']*100)}% of users" if m["total"] else None)
e3.metric("Have Watchlist", m["users_with_watchlist"],
          delta=f"{round(m['users_with_watchlist']/m['total']*100)}% of users" if m["total"] else None)

# ── Conversion funnel ─────────────────────────────────────────────────────────

st.markdown("###  Conversion Funnel")

if m["total"] > 0:
    import plotly.graph_objects as go

    fig = go.Figure(go.Funnel(
        y=["Signed Up", "Email Verified", "Has Watchlist", "Pro Subscriber"],
        x=[m["total"], m["verified"], m["users_with_watchlist"], m["pro"]],
        textinfo="value+percent initial",
        marker={"color": ["#4A9EFF", "#3DD68C", "#F5A623", "#A855F7"]},
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#E2E8F0",
        margin={"t": 20, "b": 20, "l": 0, "r": 0},
        height=280,
    )
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, theme=None)
else:
    st.info("No users yet — funnel will appear once signups arrive.")

# ── Daily signups chart ───────────────────────────────────────────────────────

st.markdown("###  Daily Signups (last 30 days)")

if m["daily_counts"]:
    import plotly.graph_objects as go
    from datetime import date

    # Fill in zeros for days with no signups
    today = datetime.now(timezone.utc).date()
    all_days = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    counts   = [m["daily_counts"].get(d, 0) for d in all_days]

    fig2 = go.Figure(go.Bar(
        x=all_days,
        y=counts,
        marker_color="#4A9EFF",
    ))
    fig2.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#E2E8F0",
        xaxis={"showgrid": False},
        yaxis={"showgrid": True, "gridcolor": "rgba(255,255,255,0.08)"},
        margin={"t": 10, "b": 40, "l": 40, "r": 10},
        height=240,
    )
    st.plotly_chart(fig2, width="stretch", config=PLOTLY_CONFIG, theme=None)
else:
    st.info("No signups in the last 30 days.")

# ── Referral stats ────────────────────────────────────────────────────────────

st.markdown("###  Referral Program")

r1, r2, r3 = st.columns(3)
r1.metric("Total Referrals",  m["ref_total"])
r2.metric("Converted",        m["ref_converted"],
          delta=f"{round(m['ref_converted']/m['ref_total']*100)}%" if m["ref_total"] else None)
r3.metric("Rewarded",         m["ref_rewarded"])

# ── Recent signups table ──────────────────────────────────────────────────────

st.markdown("###  Recent Signups (last 50)")

if m["recent"]:
    import pandas as pd

    rows = []
    for email, created_at, verified, tier, trial_end, last_login, digest in m["recent"]:
        rows.append({
            "Email":       email,
            "Signed Up":   created_at[:16].replace("T", " ") if created_at else "—",
            "Verified":    "" if verified else "",
            "Tier":        tier or "free",
            "Trial Ends":  trial_end[:10] if trial_end else "—",
            "Last Login":  last_login[:16].replace("T", " ") if last_login else "never",
            "Digest":      "" if digest else "—",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True)
else:
    st.info("No users yet.")

# ── Refresh note ──────────────────────────────────────────────────────────────

st.markdown(
    "<p style='color:#64748B;font-size:0.8rem;text-align:right;margin-top:1rem'>"
    f"Data refreshes every 60 seconds · Last loaded {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
    "</p>",
    unsafe_allow_html=True,
)
