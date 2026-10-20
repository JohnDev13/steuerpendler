# Aarau residential-entrance probe — no connected candidate

Recorded: 2026-10-20 UTC. Status: `NO_RESIDENTIAL_ENTRANCE_CONNECTED`. This is bounded reconnaissance for a separate home-like pilot entrance. It does not verify the representative municipality origin, §8 residential access, complete transit routing, a reference day, or travel release.

## Source, bounds and replay

- Frozen Geofabrik OSM: `/home/hermes/data/steuerpendler/2026-10-19/switzerland-261018.osm.pbf`, 548,725,790 bytes, SHA-256 `16dd2c5cedaf63205fcb21c50b723e43b1b3953a8ffef32e5683ec91c0ea84d1` (also pinned in `SOURCE-SNAPSHOT.json`). No source was downloaded for this probe.
- Origin: selected Staufen near inhabited-cell centre EPSG:2056 `(2655050, 1248550)`, WGS84 `(8.16767767213561, 47.385481409159354)`. It remains a representative STATPOP cell centre, not a residence.
- Candidate rule: explicit OSM entrance node (`entrance=*`, excluding `entrance=no`) that is a vertex of a building way tagged exactly `house`, `detached`, `terrace`, `apartments`, or `residential`, within 250 m of the centre. The same node must belong to the permitted directed pedestrian graph and have a path to Lenzburg station entrance node `1209130473` within 900 seconds at 1.2 m/s. No proximity snap and no entrance-to-platform time is used.
- Graph computation remained inside the existing audit bbox `(8.14, 47.375, 8.215, 47.42)`. The extractor used one node pass and one combined building/pedestrian-way pass, not the timed-out three-pass design.
- Successful bounded CLI (from the repository root): `ulimit -v 3500000; export PYTHONPATH=/home/hermes/.hermes/cache/scratch/osmium-probe:scripts/travel; time timeout 360 /home/hermes/.hermes/hermes-agent/venv/bin/python scripts/travel/aarau_residential_entrance_probe.py --pbf /home/hermes/data/steuerpendler/2026-10-19/switzerland-261018.osm.pbf --radius-m 250 --output /home/hermes/data/steuerpendler/2026-10-19/AARAU-RESIDENTIAL-ENTRANCE-PROBE-20261020.json`. This imposed a 360-second wall limit and 3,500,000 KiB virtual-address-space limit. Observed wall time was 3m42.881s; the command exited 0.
- Output SHA-256: `51d9fd5abb3efbb6091b43eb95ca81dafc22311f6924cd362a9632a35d191a8b`.

## Objective result

The bbox contained 9,575 scanned building ways. Of those, 5,238 had nonresidential building values and 4,031 residential building ways had no explicit entrance node. There were 430 explicit entrance/building candidates on qualifying residential building ways: 428 were outside the stated 250 m radius, and the two inside the radius were not the same node as any permitted pedestrian-graph node. Consequently, no candidate supplied a source-mapped connector, no directed path was accepted, and no ≤15-minute external walk was reported. The result is `NO_RESIDENTIAL_ENTRANCE_CONNECTED`; `accepted_candidates` is empty.

The JSON preserves the counts, source hash, radius, bbox, origin coordinates, station entrance ID and walk policy. Since no candidate met every criterion, there is no building/path provenance to report as an accepted route. In particular, this result does not snap the earlier 12.642 m gap and does not turn the STATPOP cell centre into a verified home.

## Tests and limits

`PYTHONPATH=scripts/travel python3 -m unittest discover -s tests/travel -p 'test_*.py'` passed 39 tests, including six new synthetic cases covering a positive explicit residential entrance/path, missing entrance, nonresidential building, disconnected entrance, barrier and wrong-way direction, and radius rejection. The inherited pedestrian profile fails closed for explicit access restrictions and barriers. Conditional/time-dependent access and turn restrictions remain outside this bounded probe; no accepted path depends on relaxing those limitations because there is no accepted candidate.
