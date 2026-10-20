# Bounded GTFS selected-stop-time streaming — Aarau smoke

Architect review scope: this change streams `stop_times.txt`, checks every row for explicit `timepoint=0`, and retains/parses stop times only for active trip IDs. It does not approve a reference date, residential access, complete nationwide routing, or travel release.

Evidence on provisional service date **2026-11-17** (not an approved all-canton reference day):

- Untrimmed four-genuine-trip **incomplete** extract SHA-256: `3f4060696d481f646e003e622b8efd92172c6314d1b8f41bf1bb6219ca8742ca`.
- Calendar-filtered derivative SHA-256: `86dd3e7c9639aa6f0c7aa22eea67d5013670559146781359d5dd2ec797a8b1f9`.
- Both produced byte-for-byte equal sorted canonical tuples: **48 stop-to-stop events across 4 trips**. Canonical compact-JSON tuple SHA-256: `31c87ea6bc8f745b64d7ac8b0990cf064d319ed7a8b6f1b6b3a2a1b1570b15bc`, matching the pinned calendar-stream evidence.
- Sequential same-process execution observed **87,568 KiB peak RSS**. This is a process-wide high-water smoke measurement on this host, not a full-feed memory bound.
- TDD RED: the 10,000-unrelated-row regression test observed `stop_times.txt` passed through the materializing `_table` reader. GREEN: the complete travel suite passed **33/33**; instrumentation confirmed only the two active rows reached clock parsing, including second precision, preserved string stop IDs, and a beyond-24h clock. Separate tests confirm an inactive trip's `timepoint=0` still fails closed and no active trip returns no events.

This removes unnecessary materialization of unrelated stop-time rows after active trips are selected. `trips.txt`, `calendar.txt`, `frequencies.txt`, and other tables are not generally streamed; exact-frequency expansion remains unsupported; approximate frequencies remain rejected. The compared fixtures contain only four selected genuine trips and are incomplete. They do not establish complete timetable coverage, full-feed memory behavior, route qualification, residential walking access, transfer completeness, or release readiness.
