# Staufen → Aarau: dated transfer-positive counterexample

**Status:** A feasible scheduled itinerary is evidenced for the owner-approved reference day, **27 October 2026**. This is *not* proof that 18 minutes is the fastest possible time, nor independent SBB verification. It is not yet published in the site's direct-only preview.

## Journey (Europe/Zurich)

- Staufen, Lindenplatz, 06:47 board bus trip `.ojp-92-390.1.TA.127.j26`, route `92-390-j26-1`, stop `ch:1:sloid:78699_gen:missingSLOID_pf:B` (GTFS pickup allowed).
- Lenzburg, Bahnhof, 06:53 alight at `ch:1:sloid:78736:0:01` (drop-off allowed).
- Directed `transfers.txt` rule from that bus stop to Lenzburg rail stop `ch:1:sloid:2119:3:3`: type 2, minimum **240 seconds**. Scheduled allowance 06:53→06:58 is **300 seconds**. Project `resolve_transfer` returned `allowed`, provenance `transfers.txt row 94 (stop_pair, child_pair)`; no separate platform-walk time was imposed.
- Lenzburg, 06:58 board train trip `.ojp-91-37-E.1.TA.582.j26`, route `91-37-E-j26-1` (pickup allowed); Aarau, 07:05 alight at `ch:1:sloid:2113:3:4` (drop-off allowed). The dated direct tracer independently records this exact Lenzburg→Aarau leg.
- First boarding→arrival: **1,080 seconds = 18 minutes**, within the **1,200-second inclusive** Aarau/20 control. The first boarding lies inside Staufen (AG, BFS 4210), **161.1 m** from the simplified municipal boundary, beyond the projection's 100 m quarantine.

## Why missing

The released Aarau preview contains only observed **direct** stop-to-Aarau journeys. None of its 1,754 direct route rows board at a Staufen-named stop. The necessary-only feeder stream additionally matches transfers at the *same station parent*, so it does not include this bus-stop→rail-stop connection across different parents; it has zero Staufen-named origin candidate rows. Thus omission is a limitation of the current computation, **not** evidence that Staufen is unreachable in 20 minutes. The site's Staufen tax identity is present but its transfer-positive route is not yet represented.

## Evidence and cautions

- Frozen GTFS: `/home/hermes/data/steuerpendler/2026-10-19/gtfs_fp2026_20261017.zip`, SHA-256 `d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e`; targeted `stop_times.txt`, `stops.txt`, `trips.txt` and directed `transfers.txt` records inspected. The 2026-10-27 first-boarding cone includes Staufen Lindenplatz 06:47 and marks the bus service `TA+03w10` active for the reference day.
- Direct tracer `/home/hermes/data/steuerpendler/2026-10-19/aarau-direct-route-tracer-20261027.ndjson.gz`, SHA-256 `5f9c6c8648f87ff88cf0c1dc4f158d471a6e55f57ed28cd53e649940d1d4b89e`, includes the train 06:58→07:05 with service `TA+5kv00` in its approved-day observations.
- Boundary membership used `site/data/map/switzerland-2026.json` and the repository's `_decode_topology`, `wgs84_to_lv95`, `point_in_multipolygon` and `_boundary_distance` functions. The boarding locality is evidenced; actual access from every residence is provisionally zero and unmeasured.
- Feasibility is a positive source-backed counterexample, not a complete fastest-route search or a blanket classification of all residences. Before publication, transfer-positive observations need a separately labelled asset, tests, review and live verification without changing global travel approval.
