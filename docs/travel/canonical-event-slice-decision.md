# First-board-event Aarau source slice — decision record (2026-10-26)

**Decision:** keep this as a *source-scale observed-positive and unknown* engineering file. It is not a globally fastest journey authority, national municipality reachability certificate, residential walk measurement, or SBB approval. Do not wire it into the public site or set `availability.travel=true` on this evidence.

## Exact input and output

- Reference service date: 2026-10-27, Europe/Zurich; first boarding at 06:30:00–08:30:00 inclusive (`23,400..30,600` seconds), ≤1,800 seconds from first boarding to target. Entrance-to-platform walking is not added; home-to-boarding access remains zero/unmeasured. Normal transfers and waits count. `directOnly` is independently routed, not filtered from all-route output.
- Input SHA-256: ride connections `fc98b4195f0275dca6e0443c1fdcb63158f9127b30f5f13583ed285f9b6600fb`; dated transfer scope `6e2d6869ac4b731e96069b6ce35a20253aa704c92512d7b820bc1d6303e0819b`; board-stop municipality `53380d7c232074d6097148a7c29a08fe6e3f06213a2301b91a6fb281714f36bb`; provisional target registry `d8a8a926d33f3e3c39be27a053409460f9b78a41faa9f5fc2d3c4af4cbd6f7fb`.
- Separate gzip NDJSON authority (outside Git): `/home/hermes/data/steuerpendler/2026-10-19/canonical-event-slice-aarau-final-20261027.ndjson.gz`; SHA-256 `eb923167e57cd21bae6a21a20bd2e2b400c6cb3a81d869bc5e720d5a14b1364d`; 8,259,657 bytes. The manifest is first, then one record per assigned first-boarding connection, then a summary. The companion `.run.json` has timing/RSS/output digest. It is **not** the 19-workplace canonical file.

## Measured run and cross-check

- Source first-board candidate connections: 373,344; assigned-origin first-board rows emitted: **295,065**; **78,279 excluded** because no assigned boarding-stop municipality evidence. These are not negative route results. Each emitted event has both all-route and independent direct-only statuses.
- All-route: **3,761** `best_found_unproven`, **291,304** `unknown`; direct-only: **1,527** `best_found_unproven`, **293,538** `unknown`. Zero `fastest_proven` or `unreachable_proven`.
- Staufen BFS 4210, 06:47 first boarding → Aarau 07:05: **1,080 seconds**, bus→rail with one change; direct-only unknown for that event.
- Capped source run: **33.05 s wall; 1,089,224 KiB max RSS** reported by the producing Python process; under the stated 600s/1.5-GiB limits. `/usr/bin/time` was unavailable on this host, so metrics were obtained with `time.monotonic()`/`resource.getrusage()` in the exporter and externally capped using `timeout 600s`; do not claim GNU time results.
- Six new focused tests and **215** travel tests passed. An independent read-only SQLite verifier checked all 295,065 emitted event identities/statuses and every positive variant (3,761 all-route + 1,527 direct-only), reconstructing **295,699 distinct connection edges** and **176 distinct transfer rules** without inconsistency. The cross-check validates the *found* paths against indexed source, not completeness or global optimality.

## Outstanding proof and drift gates

- In-seat candidate transfers (19,170), non-exact frequencies (278 excluded adjacent pairs), 3,565 boundary-quarantined and 7,841 unassigned stops, provisional destination groups, parent-station fallback, and zero unmeasured residential access remain unresolved. Some entries of the source are excluded; a missing path is unknown, not unreachable. The route profile's selected path is `best_found_unproven`, not a global fastest proof.
- Scale to 19 only after a review of the exact event-source semantics and bounded resource profile. Preserve independent direct-only computation, all unresolved reasons and explicit excluded-event coverage; run an independent source-edge/transfer validation and pinned manifest for every destination. A national event×19 file on the same incomplete source still would **not** clear completeness or residential-access acceptance.
- Source-version drift: any reissued GTFS, service calendar, stop assignment, transfer-scope or target registry needs new SHA pins, rerun diagnostics and independent approval; do not silently re-label the 2026-10-27 file as current. Tax acceptance and JU/VS quarantine are separate.
