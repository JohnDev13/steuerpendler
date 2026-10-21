# Aarau bounded feeder cone — provisional 2026-10-27 source check

**Status:** necessary same-child two-trip candidate pairs only, **not** proven transfer itineraries or qualifying Gemeinden. Different trip IDs need not mean different vehicles; linked/block trips remain unresolved. The date 2026-10-27 still lacks the all-canton public/school-holiday approval. No site travel asset or release manifest was changed.

## Pinned sources and execution

- Swiss GTFS archive SHA-256 `d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e`.
- Aarau direct-positive seed SHA-256 `0f373c32bf994f145e6b16d3ad5864017f41cb969ea7c67bc84235b9edbc9edb`: 1,754 direct pairs, 212 observed boarding children (potential second-leg hubs).
- Read-only preflight on the frozen feed: 43,832 trips touch a seed hub across the entire schedule; 2,510 are active fixed-schedule trips on the provisional service day, zero active frequency templates. This is source scope, not residential coverage.
- Bounded run: `timeout 480s`, `ulimit -v 3670016`; observed wall **201.204 s**, Python peak RSS **72,832 KiB**. It scanned all **42,243,848** stop-time rows twice and scoped dated services rather than materializing the national table.
- Outside-Git result: `/home/hermes/data/steuerpendler/2026-10-19/aarau-feeder-cone-provisional-20261027.json`, SHA-256 `6d7f5d2b1ae0aa912b31c24195748703c468f0d094b744affdd5e6e99fd50f78`, **16,975 bytes**. Counts only plus ten deterministic examples; no unbounded candidate array (the sample setting is hard-capped at 100).
- Source-backed necessary combinations: **40,302** first-leg pickup→same-child hub drop-off→direct Aarau departure combinations (first and second trip IDs differ), with first boarding 06:30:00–08:30:00 inclusive, hub arrival no later than second departure, and downstream destination arrival within 1,800 seconds of first boarding. The run skipped same-trip continuations (those are already direct positives), 39 upstream/hub combinations with pickup-type-1 at the upstream row, and zero drop-off-type-1 hub rows. All tracked malformed/chronology/frequency classes were zero for this scoped run.

## What this does not establish

These **40,302 are candidate combinations**, not reachable stops, journeys or Gemeinden. Most may fail published directed transfer minima or type-1/type-4/service-specific rules; this run deliberately did **not** assume zero interchange time. It also does not represent all possible feeders: only an arrival at the same observed child stop as a direct departure is considered. Absence from the cone is unknown. The separate external residential-to-entrance walk, workplace access, complete multi-transfer routing, approved reference Tuesday, SBB acceptance and geodata/release approvals remain open. Continue using the site's **“noch ungeprüft”** wording.

## Tests and drift

Synthetic RED/GREEN tests cover exact boarding/cap boundaries, stop permissions, dated service exceptions, malformed intermediate rows, source/result hashes, bounded output under a 3,000-combination fixture, bounded sample settings, and same-trip-continuation exclusion. Full Python travel suite: **67 passed** before integration review. Any change to the GTFS SHA, direct-result SHA, Swiss producer transfer semantics, cap or window requires a fresh bounded run and updated checksums here; a clean run is not independent itinerary acceptance.
