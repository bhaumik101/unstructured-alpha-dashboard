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

import streamlit as st

st.set_page_config(
    page_title="Admin — UA",
    layout="wide",
    initial_sidebar_state="expanded",
)

from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, text

from utils.header import render_header, render_page_header, render_sidebar_base
from utils.db import engine, users, referrals, watchlist
from utils.theme import inject_premium_css, PLOTLY_CONFIG
from utils.billing import is_admin

render_header("Admin")
render_sidebar_base()
inject_premium_css()

# ── Access gate ───────────────────────────────────────────────────────────────
# Uses the centralized is_admin() allowlist (utils/billing.py) — single source
# of truth shared with the header's ADMIN badge and admin-only nav link.

if not is_admin(st.session_state.get("user")):
    st.error("Access denied.")
    st.stop()

render_page_header(
    "Admin Dashboard",
    "User metrics, acquisition funnel, and engagement — live from the DB.",
    icon="",
)

# ── System health (rate-limiter backend) ──────────────────────────────────────
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
        "uniq_7d": 0, "uniq_30d": 0,
        "anon_7d": 0, "loggedin_7d": 0,
        "top_pages": [], "daily_views": {}, "event_breakdown": [],
        "total_events": 0,
    }
    try:
        with engine.connect() as conn:
            def _cnt(where_sql: str, params: dict) -> int:
                return conn.execute(
                    text(f"SELECT COUNT(*) FROM analytics_events WHERE {where_sql}"),
                    params,
                ).scalar() or 0

            out["pv_today"] = _cnt("event_name='page_view' AND created_at >= :d", {"d": d1})
            out["pv_7d"]    = _cnt("event_name='page_view' AND created_at >= :d", {"d": d7})
            out["pv_30d"]   = _cnt("event_name='page_view' AND created_at >= :d", {"d": d30})

            out["uniq_7d"] = conn.execute(
                text("SELECT COUNT(DISTINCT session_id) FROM analytics_events "
                     "WHERE event_name='page_view' AND created_at >= :d"), {"d": d7}
            ).scalar() or 0
            out["uniq_30d"] = conn.execute(
                text("SELECT COUNT(DISTINCT session_id) FROM analytics_events "
                     "WHERE event_name='page_view' AND created_at >= :d"), {"d": d30}
            ).scalar() or 0

            out["loggedin_7d"] = _cnt(
                "event_name='page_view' AND created_at >= :d AND user_id IS NOT NULL", {"d": d7})
            out["anon_7d"] = _cnt(
                "event_name='page_view' AND created_at >= :d AND user_id IS NULL", {"d": d7})

            out["total_events"] = conn.execute(
                text("SELECT COUNT(*) FROM analytics_events")
            ).scalar() or 0

            # Top pages (last 30d) — parse page label out of the properties JSON.
            pv_rows = conn.execute(
                text("SELECT properties FROM analytics_events "
                     "WHERE event_name='page_view' AND created_at >= :d"), {"d": d30}
            ).fetchall()
            page_counts: dict[str, int] = {}
            for (props,) in pv_rows:
                try:
                    page = (json.loads(props) or {}).get("page", "?") if props else "?"
                except Exception:
                    page = "?"
                page_counts[page] = page_counts.get(page, 0) + 1
            out["top_pages"] = sorted(page_counts.items(), key=lambda kv: -kv[1])[:15]

            # Daily page views (last 30d), bucketed in Python (portable).
            day_rows = conn.execute(
                text("SELECT created_at FROM analytics_events "
                     "WHERE event_name='page_view' AND created_at >= :d"), {"d": d30}
            ).fetchall()
            dv: dict[str, int] = {}
            for (ts,) in day_rows:
                day = ts[:10] if ts else None
                if day:
                    dv[day] = dv.get(day, 0) + 1
            out["daily_views"] = dv

            # Event-type breakdown (last 30d) — what are users actually doing.
            ev_rows = conn.execute(
                text("SELECT event_name, COUNT(*) c FROM analytics_events "
                     "WHERE created_at >= :d GROUP BY event_name ORDER BY c DESC"), {"d": d30}
            ).fetchall()
            out["event_breakdown"] = [(r[0], r[1]) for r in ev_rows][:15]
    except Exception:
        pass
    return out


# ── Load data ─────────────────────────────────────────────────────────────────

import json  # for parsing analytics properties JSON

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
st.caption("Page views are logged on every navigation (deduped per session). "
           "Unique visitors = distinct sessions.")

t1, t2, t3, t4 = st.columns(4)
t1.metric("Page Views Today", f"{tr['pv_today']:,}")
t2.metric("Page Views (7d)",  f"{tr['pv_7d']:,}")
t3.metric("Unique Visitors (7d)", f"{tr['uniq_7d']:,}")
t4.metric("Unique Visitors (30d)", f"{tr['uniq_30d']:,}")

t5, t6, t7 = st.columns(3)
_views_per_visitor = (tr["pv_7d"] / tr["uniq_7d"]) if tr["uniq_7d"] else 0
t5.metric("Views / Visitor (7d)", f"{_views_per_visitor:.1f}")
t6.metric("Logged-in Views (7d)", f"{tr['loggedin_7d']:,}")
t7.metric("Anonymous Views (7d)", f"{tr['anon_7d']:,}")

if tr["pv_30d"] == 0:
    st.info("No page-view data yet. Traffic accrues from now that page-view "
            "tracking is live — check back after users browse the app.")
else:
    # Daily page views (last 30 days)
    import plotly.graph_objects as go
    today = datetime.now(timezone.utc).date()
    all_days = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    view_counts = [tr["daily_views"].get(d, 0) for d in all_days]
    figv = go.Figure(go.Bar(x=all_days, y=view_counts, marker_color="#3DD68C"))
    figv.update_layout(
        title="Daily Page Views (last 30 days)",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#E2E8F0", xaxis={"showgrid": False},
        yaxis={"showgrid": True, "gridcolor": "rgba(255,255,255,0.08)"},
        margin={"t": 40, "b": 40, "l": 40, "r": 10}, height=260,
    )
    st.plotly_chart(figv, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

    tp_col, ev_col = st.columns(2)
    with tp_col:
        st.markdown("**Top Pages (30d)**")
        if tr["top_pages"]:
            import pandas as pd
            st.dataframe(
                pd.DataFrame(tr["top_pages"], columns=["Page", "Views"]),
                use_container_width=True, hide_index=True,
            )
        else:
            st.caption("No page data yet.")
    with ev_col:
        st.markdown("**Event Breakdown (30d)**")
        if tr["event_breakdown"]:
            import pandas as pd
            st.dataframe(
                pd.DataFrame(tr["event_breakdown"], columns=["Event", "Count"]),
                use_container_width=True, hide_index=True,
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
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
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
    st.plotly_chart(fig2, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
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
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No users yet.")

# ── Refresh note ──────────────────────────────────────────────────────────────

st.markdown(
    "<p style='color:#64748B;font-size:0.8rem;text-align:right;margin-top:1rem'>"
    f"Data refreshes every 60 seconds · Last loaded {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
    "</p>",
    unsafe_allow_html=True,
)
