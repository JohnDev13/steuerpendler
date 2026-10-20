# Bounded GTFS calendar-exception streaming — Aarau smoke

Architect review decision: accept the narrow parser-memory fix for integration, **not** residential-route, date, full-feed, or travel-release acceptance. `scheduled_events` now streams `calendar_dates.txt` and retains only selected-trip service IDs on the requested date; it still materializes the other GTFS tables, notably `stop_times.txt`. No departures are inferred and approximate-frequency/timepoint rejection is unchanged.

Evidence on the provisional service date **2026-11-17** (not an approved all-canton reference day):

- Untrimmed, four-genuine-trip, **incomplete** extract SHA-256: `3f4060696d481f646e003e622b8efd92172c6314d1b8f41bf1bb6219ca8742ca`.
- Calendar-filtered derivative SHA-256: `86dd3e7c9639aa6f0c7aa22eea67d5013670559146781359d5dd2ec797a8b1f9`.
- Both yielded the same **48 canonical stop-to-stop events across 4 trips**, including exact stop IDs, seconds and clock strings. Canonical sorted JSON tuple digest: `31c87ea6bc8f745b64d7ac8b0990cf064d319ed7a8b6f1b6b3a2a1b1570b15bc` (SHA-256); byte-for-byte tuple equality was asserted.
- Sequential same-process execution observed **87,564 KiB peak RSS** and roughly **13 seconds** for the untrimmed fixture on this host. This is a smoke observation, **not** a peak/full-feed bound; RSS is process-wide high-water mark.
- TDD: new regression test with 20,000 unrelated exceptions failed before the fix (20,002 passed to service resolver instead of 2); after the fix the complete travel suite passed **30/30**. `git diff --check` passed.

This evidence eliminates only the unnecessary nationwide *calendar exception* materialization for a four-trip fixture. It does not establish complete timetable coverage, home-to-stop walking, eligible residential options, the full inclusive boarding-window fastest journey, official holiday suitability, or performance on the full selected feed. Travel remains unavailable pending separate acceptance gates.
