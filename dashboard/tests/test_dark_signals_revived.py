"""The three signals the public report listed as "awaiting data".

/signals/report went live in #169 naming them, which is how they were
identified without database access:

    fedspeaks_hawkishness    Fed Policy Hawkishness (FOMC AI Score)
    quantum_arxiv_velocity   Quantum Computing arXiv Paper Velocity
    retail_fear_gauge        Retail Fear Index (Google Trends)

The product advertises 47 signals and was scoring 44. Three different causes,
none of them "the API is down":

1. fedspeaks_hawkishness -- A HARDCODED SCHEDULE THAT EXPIRED
   _FOMC_DATES ended at 2025-12-10. On 2026-08-19 the "8 most recent meetings"
   were all at least eight months old. The dates are now read from the Fed's own
   calendar page, which links each statement as monetary<YYYYMMDD>a.htm, with
   the static list kept as a floor so a fetch failure degrades to the old
   behaviour rather than to nothing.

2. quantum_arxiv_velocity -- A QUERY THAT MATCHED THE WHOLE CATEGORY
   arXiv ANDs bare terms across all fields, so "qubit error correction fault
   tolerant quantum computing" matched essentially all of quant-ph: 184,786
   results. The 300 most recent papers spanned SIX DAYS and resampled to two
   weekly buckets -- far too few for a z-score. Scoped to field-qualified
   phrases it returns 1,366 results, the same 300 papers span 314 days, and the
   series has 46 weekly buckets. One request, and a signal that means what its
   name says.

3. retail_fear_gauge -- AN ARGUMENT urllib3 REMOVED
   pytrends builds a urllib3 Retry from retries=/backoff_factor= using
   method_whitelist=, which urllib3 2.x renamed to allowed_methods. With
   urllib3 2.5 installed, passing either raised TypeError BEFORE any request --
   so this was never rate-limiting, it was a deterministic failure on every
   call. Dropping the two arguments returns 93 weekly rows.

   Underneath that, Google does 429 this endpoint intermittently: it has no
   official API. A bounded retry clears most, and when it does not, an empty
   series is the honest answer -- /signals/report now says "awaiting data"
   rather than counting the signal as neutral.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_FETCHERS = (_ROOT / "utils" / "fetchers.py").read_text(encoding="utf-8")


def test_fomc_dates_are_discovered_not_only_hardcoded():
    assert "_fomc_meeting_dates" in _FETCHERS, "date discovery is gone"
    assert "fomccalendars.htm" in _FETCHERS, (
        "the Fed calendar is no longer read, so the schedule expires again "
        "the moment the static list runs out"
    )
    body = _FETCHERS[_FETCHERS.index("def _fomc_meeting_dates"):]
    body = body[: body.index("\ndef ", 1)]
    assert "set(_FOMC_DATES)" in body, (
        "the static list must remain a floor; without it a failed calendar "
        "fetch yields no dates at all"
    )
    assert "recent_dates = _fomc_meeting_dates()" in _FETCHERS, (
        "the fetcher still slices the static list directly"
    )


def test_the_static_fomc_floor_is_not_itself_stale():
    """A tripwire. If discovery breaks, the fallback should still be recent."""
    dates = sorted(re.findall(r'"(20\d{6})"', _FETCHERS))
    assert dates, "no FOMC dates found at all"
    assert dates[-1] >= "20260101", (
        f"the static FOMC list stops at {dates[-1]}. Discovery covers this, but "
        "the floor is what is left when the Fed's page moves — top it up."
    )


def test_the_arxiv_query_is_field_scoped():
    """Bare terms match the whole category and collapse the series to days."""
    from utils.config import SIGNALS
    q = SIGNALS["quantum_arxiv_velocity"]["series_id"]
    assert "abs:" in q or "ti:" in q, (
        f"arXiv query {q!r} uses bare keywords, which arXiv ANDs across all "
        "fields — that matched 184,786 papers and produced a 6-day window"
    )
    assert '"' in q, "phrases must be quoted or the words match independently"


def test_pytrends_is_not_given_the_argument_urllib3_removed():
    body = _FETCHERS[_FETCHERS.index("def fetch_google_trends_fear"):]
    body = body[: body.index("\ndef ", 1)]
    code = "\n".join(line.split("#")[0] for line in body.splitlines())
    for arg in ("retries=", "backoff_factor="):
        assert arg not in code, (
            f"TrendReq is given {arg} again; pytrends turns it into a urllib3 "
            "Retry with method_whitelist=, which raises TypeError on urllib3 2.x "
            "before any request is made"
        )


def test_a_single_429_does_not_end_the_trends_fetch():
    body = _FETCHERS[_FETCHERS.index("def fetch_google_trends_fear"):]
    body = body[: body.index("\ndef ", 1)]
    assert "for attempt in range(2)" in body, "the bounded retry is gone"
    assert "_time.sleep" in body, "the retry no longer pauses between attempts"
    assert "giving up after 2 attempts" in body, (
        "a give-up should say so; a silent empty series is indistinguishable "
        "from a signal that legitimately has no data"
    )


def test_all_three_signals_are_still_registered():
    """If one is ever retired, the advertised count must move with it."""
    from utils.config import SIGNALS
    from utils.product_metrics import ACTIVE_SIGNAL_COUNT
    for sid in ("fedspeaks_hawkishness", "quantum_arxiv_velocity", "retail_fear_gauge"):
        assert sid in SIGNALS, f"{sid} was removed without updating this test"
    assert ACTIVE_SIGNAL_COUNT == len(SIGNALS)
