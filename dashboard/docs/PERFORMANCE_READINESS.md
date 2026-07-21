# Performance Readiness

## Core user loop

The product is not ready for broad acquisition until a new user can reliably:

1. Open the application.
2. Search a ticker.
3. See a useful cached result quickly.
4. Understand the score and what changed.
5. Save the ticker.
6. Return and see updated information.

## Performance targets

- Initial authenticated page usable within 3 seconds.
- Cached ticker result visible within 2 seconds.
- Uncached core analysis visible within 8 seconds.
- Optional SEC, insider, contracts, options and institutional modules must not block the core result.
- A Streamlit widget interaction must not rerun remote data collection unnecessarily.
- Every operation taking longer than 2 seconds must display a progress state.
- Optional-source failure must not hide the core score.
- Previously computed scores must display their calculation timestamp.

## Required architecture

- Load stored score snapshots before calculating fresh results.
- Cache macro inputs separately from daily market data.
- Cache third-party responses with source-appropriate TTLs.
- Keep user-specific calculations separate from shared market calculations.
- Load expensive optional sections only when opened.
- Persist selected ticker and completed results in session state.
- Never run a complete ticker calculation merely because a widget changed.
- Record execution duration for major data and scoring functions.

## Release gate

Broad marketing should remain paused until five external testers can complete:

search ticker → understand result → save ticker → return later

without founder assistance and without a major delay, crash or unexplained empty state.
