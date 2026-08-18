"""Consolidated signal evidence, validation, outcomes, quality, and methodology."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.config import SIGNALS
from utils.header import (
    render_footer,
    render_header,
    render_page_header,
    render_sidebar_base,
)
from utils.model_validation import (
    build_validation_table,
    render_composites_html,
    validation_summary,
)
from utils.theme import inject_all_css
from utils.validation_status import get_static_validation_summary


st.set_page_config(page_title="Signal Research Center — UA", layout="wide")

_SECTIONS = (
    "Trust Overview",
    "Validation",
    "Track Record",
    "Data Quality",
    "Methodology",
)
_SECTION_SLUGS = {
    "overview": "Trust Overview",
    "validation": "Validation",
    "track-record": "Track Record",
    "data-quality": "Data Quality",
    "methodology": "Methodology",
}
_pending_section = st.session_state.pop("_signal_research_pending_section", None)
if _pending_section in _SECTIONS:
    st.session_state["signal_research_section_rail"] = _pending_section

render_header("Signal Research Center")
_section = render_sidebar_base(
    page_title="Signal Research Center",
    sections=_SECTIONS,
    section_key="signal_research_section_rail",
    section_aliases=_SECTION_SLUGS,
)
inject_all_css()
render_page_header(
    "Signal Research Center",
    "One place for methodology, model validation, real outcomes, and live data quality.",
    icon="",
    live_stat="No synthetic evidence",
)


def _fmt_percent(value: object) -> str:
    return "—" if value is None else f"{float(value):.1f}%"


def _open_section(label: str, *, key: str) -> None:
    if st.button(label, key=key, width="stretch"):
        # The rail widget already exists by the time these overview cards render.
        # Queue the selection for the next run instead of mutating its state late.
        st.session_state["_signal_research_pending_section"] = label
        st.query_params["section"] = next(
            slug for slug, section_label in _SECTION_SLUGS.items()
            if section_label == label
        )
        st.rerun()


if _section == "Trust Overview":
    from utils.prediction_log import get_track_record

    _records = build_validation_table(SIGNALS)
    _validation = validation_summary(_records)
    _track = get_track_record()

    st.markdown("## The evidence behind the signal stack")
    st.caption(
        "This view separates four different questions that used to live on four "
        "different pages: what the model uses, how it was tested, what happened "
        "after logged calls, and whether the underlying data is currently available."
    )

    _metrics = st.columns(5)
    _metrics[0].metric("Signals documented", _validation["total"])
    _metrics[1].metric("Core signals", _validation["core"])
    _metrics[2].metric("Measured validations", _validation["measured"])
    _metrics[3].metric("Calls logged", _track["total"])
    _metrics[4].metric("Calls resolved", _track["resolved"])

    st.info(
        "Validation confidence is not a promise of future performance. A signal can "
        "be statistically useful and still fail in a new regime. Missing provider "
        "data is excluded rather than replaced with a neutral or synthetic value."
    )

    _cards = st.columns(4, gap="medium")
    with _cards[0]:
        st.markdown("### Validation")
        st.write("See relative weights, measured reliability, and known limitations for every signal.")
        _open_section("Validation", key="src_open_validation")
    with _cards[1]:
        st.markdown("### Track Record")
        st.write("Compare timestamped calls with the actual 4-, 8-, and 12-week outcomes.")
        _open_section("Track Record", key="src_open_track")
    with _cards[2]:
        st.markdown("### Data Quality")
        st.write("Inspect provider health, observation freshness, and unavailable coverage.")
        _open_section("Data Quality", key="src_open_quality")
    with _cards[3]:
        st.markdown("### Methodology")
        st.write("Understand percentile scoring, confluence weighting, and model limitations.")
        _open_section("Methodology", key="src_open_method")

    st.markdown("## Composite-model status")
    st.html(render_composites_html(get_static_validation_summary()))


elif _section == "Validation":
    _reliabilities = st.session_state.get("_signal_research_reliabilities")
    _cta_copy, _cta_button = st.columns([3, 1])
    with _cta_button:
        if st.button(
            "Run measured validation",
            key="signal_research_run_validation",
            width="stretch",
            help=(
                "Runs the real out-of-sample lag scan with multiple-comparison "
                "correction. The first run can take about a minute."
            ),
        ):
            try:
                from utils.validation_status import validate_all_macro_signals

                with st.spinner("Validating the signal library out of sample…"):
                    _reliabilities = validate_all_macro_signals()
                    st.session_state["_signal_research_reliabilities"] = _reliabilities
            except Exception as exc:
                st.warning(f"Measured validation is unavailable right now: {exc}")

    _records = build_validation_table(SIGNALS, reliabilities=_reliabilities)
    _summary = validation_summary(_records)
    with _cta_copy:
        st.markdown("## Signal-level validation")
        st.caption(
            f'{_summary["core"]} core, {_summary["supporting"]} supporting, and '
            f'{_summary["experimental"]} limited or experimental signals. '
            f'{_summary["measured"]} currently have measured reliability in this session.'
        )

    _validation_frame = pd.DataFrame(
        [
            {
                "Signal": row["name"],
                "Weight": row["weight_label"],
                "Factor": row["category_name"],
                "Source": row["source"] or "—",
                "Update": (row["frequency"] or "—").title(),
                "Lead (wks)": row["lag_weeks"] if row["lag_weeks"] is not None else "—",
                "Confidence": row["confidence"],
                "Validation status": row["validation_status"],
                "Known limitation": row["known_limitation"],
            }
            for row in _records
        ]
    )
    st.dataframe(
        _validation_frame,
        width="stretch",
        hide_index=True,
        column_config={
            "Signal": st.column_config.TextColumn("Signal", width="medium"),
            "Validation status": st.column_config.TextColumn(
                "Validation status", width="large"
            ),
            "Known limitation": st.column_config.TextColumn(
                "Known limitation", width="large"
            ),
        },
    )
    st.caption(
        "Point-in-time validation uses first-print macro data where vintages are "
        "available. Confidence describes evidence quality, not guaranteed accuracy."
    )
    st.html(render_composites_html(get_static_validation_summary()))


elif _section == "Track Record":
    from utils.prediction_log import get_predictions_feed, get_track_record

    _track = get_track_record()
    st.markdown("## Timestamped calls and realized outcomes")
    st.caption(
        "Calls are recorded before outcomes are known. Forward returns are populated "
        "only after each window expires and real price data is available."
    )
    _track_metrics = st.columns(6)
    _track_metrics[0].metric("Logged", _track["total"])
    _track_metrics[1].metric("Resolved", _track["resolved"])
    _track_metrics[2].metric("Pending", _track["pending"])
    _track_metrics[3].metric("4-week accuracy", _fmt_percent(_track["accuracy_4w"]))
    _track_metrics[4].metric("8-week accuracy", _fmt_percent(_track["accuracy_8w"]))
    _track_metrics[5].metric("12-week accuracy", _fmt_percent(_track["accuracy_12w"]))

    if _track["resolved"] < 20:
        st.warning(
            f'Only {_track["resolved"]} calls are fully resolved. Treat accuracy as '
            "descriptive until the sample is materially larger."
        )

    _status_filter = st.radio(
        "Outcome status",
        ("All", "Pending", "Resolved"),
        index=0,
        horizontal=True,
        key="signal_research_track_status",
    )
    _feed = get_predictions_feed(
        limit=100,
        status_filter=str(_status_filter or "All").lower(),
    )
    if not _feed:
        st.info("No calls match this view yet. The public log builds automatically.")
    else:
        def _entry(row: dict) -> str:
            """Entry price, marked when it was reconstructed rather than observed.

            This table is the auditable public log, and it was the one column it
            did not show -- a reader could see that a call was made and how it
            resolved, but not the price it was measured from, which is the
            number the whole claim rests on.
            """
            px = row.get("price_at_event")
            if px is None:
                return "—"
            suffix = " est." if row.get("price_source") == "backfilled" else ""
            return f"${px:,.2f}{suffix}"

        def _ret(value) -> str:
            """A pending return is unknown, not the string "None".

            st.dataframe renders a Python None in an object column as the literal
            text None, which read as a value rather than an absence.
            """
            return "—" if value is None else f"{value:+.1f}%"

        _track_frame = pd.DataFrame(
            [
                {
                    "Date": row.get("event_date"),
                    "Ticker": row.get("ticker"),
                    "Direction": str(row.get("direction") or "").title(),
                    "Trigger": str(row.get("event_type") or "").replace("_", " ").title(),
                    "Score": row.get("score_at_event"),
                    "Entry": _entry(row),
                    "Status": str(row.get("status") or "").title(),
                    "4w return": _ret(row.get("return_4w")),
                    "8w return": _ret(row.get("return_8w")),
                    "12w return": _ret(row.get("return_12w")),
                }
                for row in _feed
            ]
        )
        st.dataframe(_track_frame, width="stretch", hide_index=True)
        if any(r.get("price_source") == "backfilled" for r in _feed):
            st.caption(
                "“est.” marks an entry price reconstructed from the official close "
                "on the call date, because the live price fetch failed when the "
                "call was logged."
            )

    st.caption(
        "Correct means a bullish call was followed by a positive return or a bearish "
        "call by a negative return. Every qualifying logged call is included."
    )
    st.page_link(
        "pages/30_Track_Record_Live.py",
        label="Open advanced earnings and signal attribution",
    )


elif _section == "Data Quality":
    from utils.provider_health import (
        freshness_for_signal,
        provider_health_snapshot,
        provider_label,
        summarize_signal_quality,
    )
    from utils.resilience import circuit_states
    from utils.signals_cache import get_all_signal_scores

    with st.spinner("Checking the shared real-data snapshot…"):
        _signals = get_all_signal_scores()
    _quality = summarize_signal_quality(_signals)
    _quality_metrics = st.columns(4)
    _quality_metrics[0].metric(
        "Available", _quality["total"] - _quality["unavailable"]
    )
    _quality_metrics[1].metric("Fresh", _quality["fresh"])
    _quality_metrics[2].metric("Cached live", _quality["cached_live"])
    _quality_metrics[3].metric("Unavailable", _quality["unavailable"])

    st.markdown("## Signal freshness")
    _freshness_rows = []
    for _signal_id, _signal in _signals.items():
        _fresh = freshness_for_signal(_signal)
        _config = _signal.get("config") or {}
        _freshness_rows.append(
            {
                "Signal": _signal.get("name") or _config.get("name") or _signal_id,
                "Provider": provider_label(_fresh["provider"]),
                "Frequency": str(_config.get("frequency") or "Provider dependent").title(),
                "Last observation": _fresh["last_observation"] or "—",
                "State": _fresh["state"].replace("_", " ").title(),
                "Score": (
                    None
                    if _fresh["state"] == "unavailable"
                    else round(float(_signal.get("score", 50)), 1)
                ),
            }
        )
    st.dataframe(pd.DataFrame(_freshness_rows), width="stretch", hide_index=True)

    with st.expander("Provider health", expanded=False):
        _provider_rows = [
            {
                "Provider": row["label"],
                "State": row["state"].replace("_", " ").title(),
                "Expected cadence": row["expected_cadence"],
                "Checks": row["requests"],
                "Last success": row["last_success"] or "—",
                "Last error": row["last_error"] or "—",
            }
            for row in provider_health_snapshot(circuit_states())
        ]
        st.dataframe(pd.DataFrame(_provider_rows), width="stretch", hide_index=True)

    st.info(
        "Unavailable observations are excluded. Cached-live values are genuine prior "
        "provider results and remain labeled with their age."
    )
    st.page_link(
        "pages/48_Data_Trust.py",
        label="Open revision-bias and provider diagnostics",
    )


else:
    st.markdown("## How the signal stack works")
    _method_steps = (
        (
            "1. Collect real observations",
            "Public and licensed provider series are fetched on their natural cadence. Missing observations are not fabricated.",
        ),
        (
            "2. Normalize each series",
            "A raw observation becomes a 0–100 percentile rank inside its own trailing two-year history.",
        ),
        (
            "3. Apply direction",
            "Historically inverse indicators are reversed before classification. Scores above 65 are supportive and below 35 are challenging.",
        ),
        (
            "4. Build ticker confluence",
            "Only relevant signals with sufficient historical relationship to a ticker contribute to its recorded score.",
        ),
        (
            "5. Preserve uncertainty",
            "Coverage, freshness, sample size, and validation state stay visible. The system does not convert uncertainty into a recommendation.",
        ),
    )
    for _title, _body in _method_steps:
        with st.container(border=True):
            st.markdown(f"**{_title}**")
            st.write(_body)

    st.markdown("## What the scores do not mean")
    st.write(
        "A score is not a price target, probability of a gain, or instruction to "
        "trade. Macro relationships change across regimes, low-frequency data can "
        "remain extreme for months, and statistical significance does not eliminate "
        "market risk."
    )
    st.page_link(
        "pages/39_How_Signals_Work.py",
        label="Open the complete methodology and FAQ reference",
    )


render_footer(page="signals")
