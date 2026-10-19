# Aarau authentic-data direct-journey probe — partial evidence only

**Status 2026-10-19:** one real scheduled direct itinerary reproduced and cross-checked; **§8 pilot and product validation remain blocked**. This is an evidence probe, not a production router or national travel dataset. No site travel output was written.

## Frozen inputs and provisional day

- Selected timetable: opentransportdata.swiss GTFS 2026 resource `gtfs_fp2026_20261017.zip`, SHA-256 `d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e`, `feed_version=20261017`, coverage 2025-12-14–2026-12-12. Raw local copy and complete source URLs/checksums are in `/home/hermes/data/steuerpendler/2026-10-19/SOURCE-SNAPSHOT.json` (outside Git).
- Provisional service Tuesday: **2026-11-17**, Europe/Zurich. Its all-26-canton public/school holiday eligibility has **not** been evidenced and the §8 reference day is **not approved**.
- Stop parents in the GTFS: Lenzburg `Parentch:1:sloid:2119` (DIDOK `8502119`) and Aarau `Parentch:1:sloid:2113` (DIDOK `8502113`). They are real station parents but the §8 municipality-specific ranked main-stop nomination, population-centre and OSM access walk have **not** been proven.

## Observed direct itinerary

A streaming scan of **42,243,848** GTFS stop-time rows applied `calendar.txt` and `calendar_dates.txt` for the provisional Tuesday, the inclusive 06:30:00–08:30:00 *first boarding* window, platform-parent grouping, and scheduled pickup/drop-off eligibility. It found **13** eligible direct candidate itineraries between these parents; the shortest direct scheduled ride was **IR37**, trip `.ojp-91-37.1.TA.689.j26`, service `TA+t9n30`, from Lenzburg platform `ch:1:sloid:2119:3:3` at **07:29:00** to Aarau platform `ch:1:sloid:2113:3:4` at **07:35:00**: **360 seconds**. The separately fetched transport.opendata.ch connection response for the two DIDOK IDs returned that same departure and arrival, with 00d00:06:00 duration. The provider is a separate route planner but may draw on the same national timetable: this checks a concrete itinerary, not an independently published timetable. The bounded response is *not* a completeness oracle for all departures or transfers.

- Raw API response retained outside Git at `/home/hermes/data/steuerpendler/2026-10-19/lenzburg-aarau-api-0720.json`; SHA-256 `f7bb0d3570ea3f5c2bedd6eb6c1ec638223d74ac868fd5e08de46689d74f3a09`, retrieved 2026-10-19T13:07:08Z. The request URL, returned connections and exact platform/leg evidence are in `/home/hermes/data/steuerpendler/2026-10-19/AARAU-DIRECT-PROBE.json`.
- No `frequencies.txt` trip in the chosen GTFS snapshot had a stop-time row at either nominated station parent. This only limits the approximate-frequency concern for this *particular* pair; the national feed has **1,899** records with `exact_times=0`, and §8 also allows ferry/cableway services.

## Unpassed acceptance gates

1. Approve one feed-covered Tuesday with source-backed all-canton holiday/school-calendar evidence; re-run the probe on that date if different.
2. Prove actual municipality polygon membership, ranked main-stop selection, STATPOP population centre, and pedestrian-network station walks (≤15 minutes separately). The 2025 STATPOP municipality table lacks 2026 BFS IDs 2056 and 6831 and needs a documented vintage join/fallback.
3. Prove exact minimum over **all** eligible first-board itineraries, including transfers, min transfer times, intra-journey walks, extended route types, calendar exceptions, pickup/drop-off and no-service cases. The committed `exact_itinerary.py` is a synthetic one-transfer prototype and `gtfs_events.py` rejects this real national feed's non-fixed-frequency records; neither has passed the real-feed metric.
4. Independent broader itinerary checks and geographic QA; then an Aarau candidate set and measured 19-capital national run on an approved ≥15 billion-byte RAM/4-CPU environment. Current host and preflight block that run.
5. Keep `travel=false` and tax approval false; ESTV comparator still fails 20/29 cases. Do not equate engineering CI, this real direct journey, or a merged prototype with release approval.
