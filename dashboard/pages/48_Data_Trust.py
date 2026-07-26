"""Public data lineage, freshness, and provider-health transparency."""

from datetime import datetime

import pandas as pd
import streamlit as st

from utils.header import render_footer, render_header, render_page_header, render_sidebar_base
from utils.provider_health import (
    canonical_provider,
    freshness_for_signal,
    provider_health_snapshot,
    provider_label,
    summarize_signal_quality,
)
from utils.resilience import circuit_states
from utils.signals_cache import get_all_signal_scores


st.set_page_config(page_title="Data Trust Center — UA", layout="wide")
render_header("Data Trust Center")
section = render_sidebar_base(
    page_title="Data Trust Center",
    sections=("Coverage Overview", "Provider Health", "Signal Freshness", "Revision Bias", "Methodology"),
    section_key="data_trust_section_rail",
)
render_page_header(
    "Data Trust Center",
    "See which real-world sources are available, how current each observation is, and how provider failures are handled.",
    live_stat="No synthetic data",
)


def _status_label(state: str) -> str:
    return {
        "fresh": "Fresh",
        "cached_live": "Cached live",
        "delayed": "Delayed",
        "unavailable": "Unavailable",
        "operational": "Operational",
        "degraded": "Degraded",
        "not_checked": "Not checked",
    }.get(state, state.replace("_", " ").title())


def _time_label(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%b %d, %H:%M UTC")
    except Exception:
        return str(value)[:19].replace("T", " ")


signals = {} if section in ("Methodology", "Revision Bias") else get_all_signal_scores()

if section == "Coverage Overview":
    quality = summarize_signal_quality(signals)
    available = quality["total"] - quality["unavailable"]
    cols = st.columns(4)
    cols[0].metric("Available signals", f"{available} / {quality['total']}")
    cols[1].metric("Fresh", quality["fresh"])
    cols[2].metric("Cached live", quality["cached_live"])
    cols[3].metric("Unavailable", quality["unavailable"])

    st.markdown(
        """
        <div style="background:#0F141C;border:1px solid rgba(var(--ua-cyan-rgb),.18);border-radius:9px;
                    padding:16px 18px;margin:14px 0 22px;font-family:Inter,sans-serif;">
          <div style="font-size:.68rem;color:#8ECAD3;text-transform:uppercase;letter-spacing:.10em;
                      font-weight:750;">Integrity standard</div>
          <div style="font-size:.86rem;color:#D9E0EC;line-height:1.6;margin-top:6px;">
            Unstructured Alpha never fills a missing observation with a fabricated value. A live-source
            failure is excluded, or—when this service has already fetched a genuine result—the last
            successful observation may remain visible as <strong style="color:#B7DCE2;">cached live</strong>
            with its age disclosed.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    coverage: dict[str, dict] = {}
    for signal in signals.values():
        fresh = freshness_for_signal(signal)
        key = canonical_provider(fresh["provider"])
        row = coverage.setdefault(key, {"Provider": provider_label(key), "Signals": 0, "Available": 0,
                                        "Fresh": 0, "Cached live": 0, "Delayed": 0, "Unavailable": 0})
        row["Signals"] += 1
        if fresh["state"] != "unavailable":
            row["Available"] += 1
        row[_status_label(fresh["state"])] += 1
    frame = pd.DataFrame(coverage.values()).sort_values(["Unavailable", "Provider"], ascending=[False, True])
    st.markdown("### Coverage by provider")
    st.caption("Availability reflects the current shared signal snapshot; delayed data can still be valid for weekly or monthly releases.")
    st.dataframe(frame, hide_index=True, width="stretch")

elif section == "Provider Health":
    rows = []
    for provider in provider_health_snapshot(circuit_states()):
        rows.append({
            "Provider": provider["label"],
            "Status": _status_label(provider["state"]),
            "Circuit": provider["circuit"].replace("_", " ").title(),
            "Expected cadence": provider["expected_cadence"],
            "Checks": provider["requests"],
            "Avg latency": f'{provider["latency_ms"]:.0f} ms' if provider["latency_ms"] is not None else "—",
            "Last success": _time_label(provider["last_success"]),
            "Last error": provider["last_error"] or "—",
        })
    st.markdown("### Current provider health")
    st.caption(
        "This is a privacy-safe view of outbound calls made by the current web service process. "
        "Not checked means no call has been observed since the service last started; it does not mean the provider is down."
    )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.info("Circuit breakers pause repeated calls to an unhealthy provider, reducing page delays and unnecessary API usage.")

elif section == "Signal Freshness":
    rows = []
    for signal_id, signal in signals.items():
        fresh = freshness_for_signal(signal)
        cfg = signal.get("config") or {}
        fallback_age = fresh.get("cache_age_seconds")
        rows.append({
            "Signal": signal.get("name") or cfg.get("name") or signal_id,
            "Category": str(signal.get("category") or cfg.get("category") or "Other").replace("_", " ").title(),
            "Provider": provider_label(fresh["provider"]),
            "Frequency": str(cfg.get("frequency") or "Provider dependent").replace("_", " ").title(),
            "Last observation": fresh["last_observation"] or "—",
            "Fallback age": f"{fallback_age / 3600:.1f} hr" if fallback_age is not None else "—",
            "State": _status_label(fresh["state"]),
            "Score": None if fresh["state"] == "unavailable" else round(float(signal.get("score", 50)), 1),
        })
    state_filter = st.segmented_control(
        "Show",
        ["All", "Fresh", "Cached live", "Delayed", "Unavailable"],
        default="All",
        key="data_trust_state_filter",
    )
    if state_filter and state_filter != "All":
        rows = [row for row in rows if row["State"] == state_filter]
    st.caption("Freshness thresholds respect each signal's release frequency; a monthly series is not judged like a daily market price.")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

elif section == "Revision Bias":
    st.markdown("### Revision bias — are we scoring on hindsight?")
    st.markdown(
        "Government macro data gets **revised** after its first release. A backtest "
        "that uses today's revised numbers gives a signal credit for values nobody "
        "actually had at the time — look-ahead bias. Our validation runs on "
        "**first-print** data (the value published at the time) precisely to avoid "
        "that. This page measures how much each FRED-backed signal is actually "
        "revised, so the size of the problem is out in the open rather than assumed "
        "away."
    )
    st.caption(
        "Method: for each FRED-backed signal we compare every observation's initial "
        "release (ALFRED first print) with its latest-revised value over a multi-year "
        "window, and report the average absolute revision. Series that are never "
        "revised (e.g. market rates) correctly show ~0%. Nothing is imputed — a signal "
        "whose vintage can't be read is reported as unavailable, not as zero revision."
    )

    _audit = st.session_state.get("_revision_audit")
    if st.button("Run revision audit", key="run_revision_audit",
                 help="Compares first-print vs revised data across every FRED signal. "
                      "Makes a couple of network calls per signal; slow the first time, "
                      "then cached."):
        try:
            from datetime import timedelta
            from utils.fetchers import _get_fred_key
            from utils.vintage_audit import audit_all_fred_signals
            _end = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            _start = (datetime.now() - timedelta(days=365 * 7)).strftime("%Y-%m-%d")
            with st.spinner("Auditing first-print vs revised data across FRED signals…"):
                _audit = audit_all_fred_signals(_start, _end, api_key=_get_fred_key())
                st.session_state["_revision_audit"] = _audit
        except Exception as _e:
            st.warning(f"Revision audit unavailable right now: {_e}")

    if _audit:
        _s = _audit["summary"]
        cols = st.columns(4)
        cols[0].metric("FRED signals", _s["n_signals"])
        cols[1].metric("Measured", _s["n_measured"])
        cols[2].metric("Materially revised", _s["n_revised"])
        cols[3].metric("Avg revision", f"{_s['mean_abs_pct']:.2f}%")
        if _s["worst_series"]:
            st.caption(
                f"Most-revised signal: **{_s.get('worst_signal_name') or _s['worst_series']}** "
                f"({_s['worst_series']}) at {_s['max_abs_pct']:.2f}% average absolute revision. "
                f"Our backtests never see these revisions — they run on the first print."
            )
        _rows = [{
            "Signal": r.get("signal_name", r.get("series_id")),
            "Series": r.get("series_id"),
            "Avg revision %": (f"{r['mean_abs_pct']:.2f}" if not r.get("error") else "—"),
            "Max revision %": (f"{r['max_abs_pct']:.2f}" if not r.get("error") else "—"),
            "Obs compared": (r.get("n_compared", 0) if not r.get("error") else "—"),
            "Status": ("revised" if r.get("is_revised") else "stable") if not r.get("error") else "unavailable",
        } for r in _audit["per_signal"]]
        st.dataframe(pd.DataFrame(_rows), hide_index=True, width="stretch")
        if _s["n_unavailable"]:
            st.caption(
                f"{_s['n_unavailable']} signal(s) could not be read this run and are shown as "
                f"unavailable — excluded from the averages, never counted as zero revision."
            )
    else:
        st.info("Click **Run revision audit** to measure how much each FRED signal is revised.")

else:
    st.markdown("### What each state means")
    definitions = [
        ("Fresh", "The latest real observation is within the expected window for that signal's release frequency."),
        ("Cached live", "A provider call failed, so the service is showing a labeled copy of a genuine result fetched earlier by this running service."),
        ("Delayed", "Real data exists, but the latest observation is older than expected for its configured cadence."),
        ("Unavailable", "No trustworthy observation is available. The signal is excluded rather than assigned a placeholder value."),
        ("Degraded provider", "A recent call failed or a circuit breaker is testing recovery. Other providers continue independently."),
    ]
    for title, body in definitions:
        st.markdown(f"**{title}**")
        st.write(body)

    st.markdown("### Reliability safeguards")
    st.write(
        "Provider requests use pooled connections, bounded retries for safe idempotent calls, timeouts, and independent circuit breakers. "
        "Telemetry records only provider name, outcome, latency, status class, and time—never API keys, request URLs, or response payloads."
    )
    st.markdown("### Scoring contract")
    st.write(
        "Unavailable signals do not receive a synthetic neutral observation. Coverage warnings appear wherever a partial source set could affect interpretation, "
        "and the Data Trust Center exposes that coverage in one place."
    )

render_footer(page="signals")
