# Aarau first-boarding cone probe — 2026-10-20

## Scope and limits

This is a candidate enumeration only. The candidate service day 2026-10-27 is not approved. Each origin is screened separately against child stops by WGS84 geodesic distance at the necessary-condition bound of 1,080 m (1.2 m/s × 15 minutes). The result does not establish a residence, pedestrian route, entrance-to-platform walk, destination, transfer, route eligibility, exhaustive path search, or official acceptance.

Origins from `AARAU-HUB-ORIGIN-POINTS.json` are the Staufen near inhabited-cell example and the Niederlenz and Lenzburg population-weighted centres in EPSG:2056. Lazily loaded `pyproj.Transformer(..., always_xy=True)` converts them to WGS84; `pyproj.Geod` measures each source stop independently. Real calls fail closed when this optional dependency is unavailable; synthetic tests inject deterministic geometry. Municipality reference stops are not treated as boarding stops.

## Frozen source and replay

- GTFS: `/home/hermes/data/steuerpendler/2026-10-19/gtfs_fp2026_20261017.zip`, 291,535,005 compressed bytes, SHA-256 `d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e`; provenance remains in the outside-Git `SOURCE-SNAPSHOT.json`.
- Command used a 480-second timeout and 3.5-GiB virtual-address-space limit with Python 3.11 and `pyproj==3.7.2`:
  `ulimit -v 3670016; timeout 480s env PYTHONPATH=/home/hermes/.hermes/cache/scratch/osmium-probe:scripts/travel /home/hermes/.hermes/hermes-agent/venv/bin/python scripts/travel/aarau_boarding_cone_probe.py --feed /home/hermes/data/steuerpendler/2026-10-19/gtfs_fp2026_20261017.zip --origins /home/hermes/data/steuerpendler/2026-10-19/AARAU-HUB-ORIGIN-POINTS.json --source-snapshot /home/hermes/data/steuerpendler/2026-10-19/SOURCE-SNAPSHOT.json --result /home/hermes/data/steuerpendler/2026-10-19/aarau-first-boarding-cone-20261027.json`
- Full outside-Git result: `/home/hermes/data/steuerpendler/2026-10-19/aarau-first-boarding-cone-20261027.json`, 719,727 bytes, SHA-256 `229cbab8cb2e813189bf7c6f1e21ce8fa5ab8b78024e98b6e73efc20de4781f2`.

## Measured result

Status `EXACT_SCHEDULE_CANDIDATES_ENUMERATED`: 877 exact scheduled candidate records in inclusive 06:30:00–08:30:00 Europe/Zurich, across the separate origin screens. The geometric candidate-stop set contains 79 parented source child-stop IDs. A separate scan of `location_type=0` children found zero unparented stops within 1,080 m of these three origins; that is a scoped feed observation, not a general GTFS invariant. There were 0 scoped `pickup_type=1` exclusions, 0 scoped `exact_times=0` frequency candidates, and 0 scoped `exact_times=1` frequency candidates.

Frequency trips are classified conservatively whenever an active template touches a candidate stop with boarding permitted, independent of whether that template row's clock is in the boarding window. Such unresolved rows are emitted separately as `template_only`; no headway departure is invented. Therefore the zero frequency result means none of the 1,899 scanned frequency rows belonged to an active trip with a boardable template stop in this cone, not merely that no template clock fell in the window.

The scan selected 8,596 active services and 190,163 active trips after calendar additions/removals. Rows scanned: 88,917 `calendar.txt`; 10,909,747 `calendar_dates.txt`; 104,831 `stops.txt`; 2,601,990 `trips.txt`; 1,899 `frequencies.txt`; 42,243,848 `stop_times.txt`. Wall time was 118.81 seconds and Python peak RSS was 464,388 KiB. The script retains exact clock seconds, source/parent stop IDs, names and coordinates, trip/service IDs, source CRS and origin/stop geodesic distances. Unsupported pickup rules, unreadable or incomplete required tables, inexact scoped scheduled timepoints, and source-hash mismatch fail closed.

Synthetic tests cover inclusive boundaries, base/inactive/exception-added/exception-removed services, pickup prohibition and unsupported pickup failure, an overlapping frequency interval whose template clock is outside the window, unparented-child reporting, lazy optional geometry failure, geodesic exclusion, and preservation of source/parent stop IDs. Both the default Python suite without `pyproj` and the pinned Python 3.11 plus `pyproj` suite passed all 42 travel tests. They introduce no residential acceptance or route filtering.
