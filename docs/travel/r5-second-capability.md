# Pinned R5 exact-second capability inspection — 2026-10-19

**Decision at this snapshot:** no verified API path for the SPEC §8 deterministic, inclusive 06:30:00–08:30:00 first-board itinerary metric was established. This is a bounded negative result, not proof that no R5 implementation is possible. No authentic Aarau pilot can follow from it.

Pinned diagnostic environment: `scripts/travel/environment.lock.json` records R5 7.5.1 JAR SHA-256 `d50be106cadd7b636cfc0e209052767d7df570629f79fdf98ecd5cf5d2d89be7`, Azul JDK 21.0.8 archive SHA-256 `63f56bbb46958cf57352fba08f2755e0953799195e5545acc0c8a92920beff1e`; the installed Python environment imports r5py 1.1.7 and JPype 1.7.1 with that `JAVA_HOME`.

Evidence from the installed implementation:

- `r5py/r5/regional_task.py:215-223` builds `RegionalTask.fromTime` from **hour and minute only**, dropping the input departure second before invoking R5. A 06:30:01 input therefore cannot be distinguished from 06:30:00 through this setter.
- `r5py/r5/trip_planner.py:230-248` passes the regional request to `McRaptorSuboptimalPathProfileRouter.route()` and exposes `finalStatesByDepartureTime` keyed by seconds; the second-valued output key does not restore seconds lost from the input or establish exhaustive enumeration.
- Bytecode from the pinned JAR (`McRaptorSuboptimalPathProfileRouter.generateDepartureTimesToSample(ProfileRequest)`, inspected with JDK `javap -private -c`) divides the time window by `monteCarloDraws`, begins at `fromTime + MersenneTwister.nextInt(...)`, and advances by sampled offsets while time is `< toTime`. This observed implementation samples departures; it is not evidence of exhaustive inclusive-second search. Whether a seed makes repeated runs reproducible does not change this coverage gap.

The prior preflight `scripts/travel/build.py --preflight-only` returned 2 with `EXACT_METRIC_UNPROVEN`, `nationalDownloadsAttempted=false`, and `siteDataWritten=false` (see `docs/travel/aarau-authentic-pilot-triage.md`). This inspection adds no real GTFS/OSM/STATPOP input, exact fixture conformance, or route result.

**Next bounded experiment:** identify a low-level R5 itinerary/state API that accepts second-precise start/end values and supports complete timetable departure enumeration, then prove it against the saved boundary/transfer/parent/no-service fixture suite and independent walk/transit caps. If the pinned API cannot, document a deliberate adapter or engine change with source-version and licensing implications before any real Aarau run. Do not replace the contract with percentile or sampled itineraries.
