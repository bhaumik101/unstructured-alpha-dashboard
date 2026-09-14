# utils/candidate_ledger.py
# Unstructured Alpha — the candidate signal ledger
#
# WHY THIS EXISTS
# ---------------
# "Keep trying new data until something works" is p-hacking with extra steps.
# With enough candidates one of them WILL clear p < 0.05 by chance, and the
# result will be worthless in precisely the way this product was already
# criticised for. docs/NOWCAST_RESULTS.md records ten configurations searched
# against 2011-2026; the best of them (skill +0.348, p = 0.131) is the best of
# ten tries and nothing more.
#
# But refusing to explore is also wrong. The honest version is a LEDGER:
#
#   1. Every candidate is registered IN CODE with a mechanism, written before it
#      is tested. Adding one after seeing a result requires a visible commit.
#   2. Each is evaluated exactly once. Results are write-once — a candidate that
#      disappointed cannot be quietly re-run until it behaves.
#   3. The significance threshold TIGHTENS as the ledger grows. Bonferroni over
#      the number actually tested, computed at read time, so the bar rises
#      automatically and nobody has to remember to raise it.
#
# That makes exploration cumulative instead of corrosive: the more you try, the
# more a survivor is worth, because the correction it had to clear was harder.
#
# PACING IS DELIBERATE. One candidate per monthly cron run. Testing twelve in an
# afternoon would demand p < 0.004 of all of them and produce nothing; testing
# one a month keeps the budget small and the evidence interpretable.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select

from utils import db
from utils.db import candidate_evaluations


@dataclass(frozen=True)
class Candidate:
    """A data source to test, with the reason it might work stated in advance."""
    key: str
    fred: str
    hypothesis: str
    first_print: bool = True
    safe_at_lag0: bool = True


# PRE-REGISTERED CANDIDATES.
#
# Each names a mechanism, and the mechanism was written before the candidate was
# tested. That ordering is the whole discipline: a hypothesis invented after
# seeing a result explains anything.
#
# Release timing is asserted per candidate, because the nowcast runs at lag 0
# and a series that publishes after Industrial Production would be look-ahead —
# the exact bug that inflated the first factor-model result (see
# docs/NOWCAST_RESULTS.md, 2026-09-03 correction).
CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        # Registered as "financial_stress" until 2026-09-14; that evaluation is
        # void (see VOIDED_EVALUATIONS) and the key is retired with it.
        "stlfsi4_stress", "STLFSI4",
        "St Louis Fed Financial Stress Index — a weekly composite built from a "
        "different input set than Chicago's NFCI, so it may carry stress "
        "information NFCI misses rather than duplicating it.",
    ),
    Candidate(
        "nfci_leverage", "NFCILEVERAGE",
        "The leverage subindex of NFCI. Leverage builds and unwinds on a "
        "different clock than the risk and credit subindices, and the headline "
        "NFCI averages that distinction away.",
    ),
    Candidate(
        "term_spread_3m", "T10Y3M",
        "10-year minus 3-month. Estrella-Mishkin found the 3-month leg a better "
        "recession predictor than the 2-year the current panel uses, because the "
        "short end tracks policy more directly.",
    ),
    Candidate(
        "broad_dollar", "DTWEXBGS",
        "Trade-weighted broad dollar. The panel's existing DXY is 58% euro; a "
        "broad index tracks the trade exposure US manufacturers actually face.",
    ),
    Candidate(
        "bank_credit", "TOTBKCR",
        "Total bank credit, H.8. Industrial working capital is bank-financed, so "
        "contraction should precede production cuts.",
    ),
    Candidate(
        "rail_carloads", "RAILFRTCARLOADSD11",
        "Carloads are the industrial half of rail freight; the panel's "
        "intermodal series is consumer-goods weighted.",
        # Rail publishes ~2 months late — the same trap that contaminated the
        # first lag-0 result. Testable at lag 1 only.
        safe_at_lag0=False,
    ),
)


# EVALUATIONS DECLARED VOID.
#
# Write-once cuts both ways: a row that did not actually test its candidate
# cannot be repaired in place either. A void is declared HERE, in a visible
# commit carrying the evidence — never by editing or deleting the row.
#
# A voided row is excluded from the Bonferroni count, because it tested nothing
# and so spent no search budget. Its key is retired: the retest must be
# registered under a new key, so the original row and its void stay readable
# side by side.
VOIDED_EVALUATIONS: dict[str, str] = {
    "financial_stress": (
        "2026-09-14 cron run recorded skill 0.3483 with the candidate against a "
        "baseline of 0.3483 — identical. Adding a column always moves the factor "
        "loadings; on the same code path run locally, STLFSI4 moved skill "
        "0.2784 -> 0.2883. The series never entered the trial design, so the "
        "row is the baseline under another name. Retested as stlfsi4_stress."
    ),
}


def corrected_alpha(n_tested: int, family_alpha: float = 0.05) -> float:
    """The p-value a candidate must clear, given how many have been tested.

    Bonferroni over the ledger. Computed at READ time from the number of rows
    that exist, so the bar rises on its own as exploration continues and no one
    has to remember to raise it.

    A candidate evaluated when the ledger held 3 rows is not grandfathered at
    the looser threshold: `survives_correction` is recomputed against the
    current count every time the ledger is read.
    """
    return family_alpha / max(1, int(n_tested))


def untested_candidates() -> List[Candidate]:
    """Candidates with no recorded evaluation, in registration order."""
    try:
        with db.engine.begin() as conn:
            done = {r["candidate"] for r in conn.execute(
                select(candidate_evaluations.c.candidate)).mappings().all()}
    except Exception as exc:
        print(f"[candidates] could not read the ledger: {exc}", flush=True)
        return []
    return [c for c in CANDIDATES if c.key not in done]


def record_evaluation(
    candidate: str,
    hypothesis: str,
    skill: Optional[float],
    dm_p_value: Optional[float],
    n_scored: int,
    baseline_skill: Optional[float] = None,
    notes: str = "",
) -> bool:
    """Write one evaluation. Returns True if a new row was created.

    WRITE-ONCE. A second evaluation of the same candidate is refused, because a
    candidate that can be re-run until it behaves is not being tested — it is
    being auditioned.
    """
    values = {
        "candidate": candidate,
        "hypothesis": hypothesis,
        "skill": None if skill is None else float(skill),
        "dm_p_value": None if dm_p_value is None else float(dm_p_value),
        "baseline_skill": None if baseline_skill is None else float(baseline_skill),
        "n_scored": int(n_scored),
        "notes": notes or None,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if db.IS_SQLITE:
            from sqlalchemy.dialects.sqlite import insert as _ins
        else:
            from sqlalchemy.dialects.postgresql import insert as _ins
        stmt = _ins(candidate_evaluations).values(**values).on_conflict_do_nothing(
            index_elements=["candidate"]
        )
        with db.engine.begin() as conn:
            result = conn.execute(stmt)
        written = bool(getattr(result, "rowcount", 0))
        if not written:
            print(f"[candidates] {candidate} already evaluated — not re-running",
                  flush=True)
        return written
    except Exception as exc:
        print(f"[candidates] could not record {candidate}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        return False


def get_ledger() -> dict:
    """Every evaluation, with the correction applied at today's ledger size.

    `survives_correction` is recomputed on read rather than stored, so a
    candidate tested early cannot keep a threshold that later exploration has
    invalidated.
    """
    try:
        with db.engine.begin() as conn:
            rows = [dict(r) for r in conn.execute(
                select(candidate_evaluations).order_by(
                    candidate_evaluations.c.evaluated_at)).mappings().all()]
    except Exception:
        rows = []

    # Void rows tested nothing, so they neither count toward the correction
    # nor can survive it. They are still reported, not hidden.
    voided = [{"candidate": r["candidate"], "reason": VOIDED_EVALUATIONS[r["candidate"]]}
              for r in rows if r.get("candidate") in VOIDED_EVALUATIONS]
    rows = [r for r in rows if r.get("candidate") not in VOIDED_EVALUATIONS]

    n = len(rows)
    threshold = corrected_alpha(n)
    for row in rows:
        p = row.get("dm_p_value")
        skill = row.get("skill")
        row["survives_correction"] = bool(
            p is not None and skill is not None and p < threshold and skill > 0
        )

    return {
        "n_registered": len(CANDIDATES),
        "n_tested": n,
        "n_remaining": len(CANDIDATES) - n,
        "corrected_alpha": round(threshold, 6),
        "survivors": [r["candidate"] for r in rows if r["survives_correction"]],
        "evaluations": rows,
        "voided": voided,
        "note": (
            f"Bonferroni over {n} tested candidate(s): a survivor must clear "
            f"p < {threshold:.4f}. The bar tightens as exploration continues."
            if n else "no candidates evaluated yet"
        ),
    }
