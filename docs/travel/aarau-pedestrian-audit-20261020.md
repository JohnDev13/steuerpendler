# Aarau pedestrian-access audit — selected entrance, no residential walk accepted

**Recorded:** 2026-10-20 UTC. **Status:** fail closed. Contract: `SPEC.md` §§6.4, 8 and `docs/travel/hub-access-contract-20261020.md` at source `main` commit `e7891d7404cd2d889523e26c3c2e49de7eb329ad`. This is a bounded physical-access audit, not a national pedestrian router or a household recommendation.

## Source and replay

- Frozen OSM `switzerland-261018.osm.pbf`, SHA-256 `16dd2c5cedaf63205fcb21c50b723e43b1b3953a8ffef32e5683ec91c0ea84d1`; BFS 2025 inhabited-cell centres joined to 2026 polygon IDs: `/home/hermes/data/steuerpendler/2026-10-19/AARAU-HUB-ORIGIN-POINTS.json`. Their provenance is in `/home/hermes/data/steuerpendler/2026-10-19/SOURCE-SNAPSHOT.json`.
- CLI: `scripts/travel/aarau_pedestrian_audit.py`; four synthetic direction/barrier/connector tests: `PYTHONPATH=scripts/travel python3 -m unittest tests.travel.test_aarau_pedestrian_audit` (4/4). Real probe ran with Python 3.11.15, `osmium==4.3.2`, `pyproj==3.7.2` available through `PYTHONPATH=/home/hermes/.hermes/cache/scratch/osmium-probe /home/hermes/.hermes/hermes-agent/venv/bin/python scripts/travel/aarau_pedestrian_audit.py --pbf /home/hermes/data/steuerpendler/2026-10-19/switzerland-261018.osm.pbf --origins /home/hermes/data/steuerpendler/2026-10-19/AARAU-HUB-ORIGIN-POINTS.json --output /home/hermes/data/steuerpendler/2026-10-19/AARAU-PEDESTRIAN-AUDIT-20261020.json`. The scratch dependency directory may expire; reinstall these pinned libraries for Python 3.11 if needed.
- Result JSON at the above path, SHA-256 `d142bdc5d441a23e5fa6dc509ba388d8575931926f9601df9af71063864f678d`, reproduced byte-for-byte on rerun. The first three-pass attempt timed out at 260 seconds and produced no output; the successful version reads node and combined way/relation passes, without a nationwide route build. Validate the source checksum and the output's path/node/way trace before interpreting it.

## What was observed

The candidate Lenzburg station entrance is OSM node **1209130473**, `entrance=yes` on a `building=train_station` way **103394820** and a walkable bridge/path way **130894824**. OSM stop-area relation **1547389** includes the building way and has `uic_ref=8502119`; the selected Swiss GTFS slice's `Parentch:1:sloid:2119` row has `didok=8502119`. This is a strong station-identity cross-check, **not** a verified home→network connector or an extra entrance→boarding-platform walk. No entrance-to-platform duration was added.

For that **one selected entrance** and at 1.2 m/s:

- Staufen near inhabited cell: provisional connected-network portion **866.632 m**; nearest origin-network node is **12.642 m** away across an **unevidenced connector**. No accepted residential walk, even though the network portion alone is below 15 minutes.
- Staufen far inhabited cell: **1,730.051 m** connected-network portion, origin-network gap **8.012 m**. Its WGS84 geodesic straight-line lower bound to this selected entrance is **1,473.5 m / 20.47 min**, exceeding the 15-minute example even before any detour. This does not rule out another station entrance or local-bus access.
- Niederlenz population-weighted point: **1,617.887 m** network portion, origin-network gap **7.002 m**. The lower bound to this selected entrance is **1,224.6 m / 17.01 min**; it does not rule out bus boarding or another entrance.

The geodesic checks use `pyproj.Transformer(2056,4326,always_xy=True)` and `pyproj.Geod(ellps='WGS84').inv` on the source LV95 points and OSM entrance coordinates. Lower bounds apply to the selected entrance only; they are not routes. The real probe intentionally sets **all three cases `UNVERIFIED`, `accepted_walk_seconds:null`** and `NO_WALK_ACCEPTED`. In particular, the near point is not yet a verified ≤15-minute walk from a home. The graph profile's filtered edges/direction/barriers and source path IDs are in the result JSON, but origin access over the off-network gap and independent station/path QA remain open.

## Remaining acceptance gates

Source-evidence the actual origin-to-pedestrian-network connector (or select a documented residential entrance on the network) and review its barriers/crossings; independently verify the selected station entrance and any alternate entrance. Then run dated complete first-board timetable search for each valid origin candidate, including all relevant services and directed transfers, on a fully justified all-canton holiday-free reference day. The four-trip named-stop smoke and the current OSM graph do not qualify a Staufen or Niederlenz residence. Travel availability and separate ESTV approval remain withheld. Re-run this audit when OSM, STATPOP, map polygons, entrance IDs, access profile or GTFS stop mappings change.
