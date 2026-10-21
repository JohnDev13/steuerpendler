# Aarau direct-only 30-minute GTFS screen — 27 October 2026

## Scope and status

This is a provisional engineering screen of exact scheduled **direct rides only**. It searches first boardings in the inclusive `06:30:00–08:30:00` window and accepts arrival at either source-matched Aarau rail/bus station parent at an exact elapsed time of at most 1,800 seconds. It does not search transfers, alternative destination access, origin walking, or residential access candidates. Absence from this result is unknown, not evidence that a stop or Gemeinde is outside 30 minutes. The date `2026-10-27` remains provisional and is not the approved §8 reference day.

No `site/data/travel/` file or release manifest was changed. This result is not a qualifying-Gemeinden matrix.

## Frozen input and bounded run

- GTFS: `/home/hermes/data/steuerpendler/2026-10-19/gtfs_fp2026_20261017.zip`
- Expected and observed source SHA-256: `d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e`
- Result outside Git: `/home/hermes/data/steuerpendler/2026-10-19/aarau-direct-30-provisional-20261027.json`
- Reviewed result bytes: `1,028,542`
- Reviewed result SHA-256: `0f373c32bf994f145e6b16d3ad5864017f41cb969ea7c67bc84235b9edbc9edb`
- Bounds: `timeout 480s`; `ulimit -v 3670016`
- Reviewed rerun: `time` real `3m12.213s`, user `3m10.443s`, sys `0m0.710s`. Structured timing/report: `/home/hermes/automation/steuerpendler/aarau-direct-30-scan-20261021.log`.
- Observed Python peak RSS on reviewed rerun: `64,264 KiB`

The implementation hashes the archive before opening the output, derives destination children from `stops.txt`, scans all stop times once to identify target-reaching trips, scopes service and frequency data, then scans all stop times a second time while retaining rows only for active fixed-schedule target-reaching trips.

## Observed GTFS destination membership

The run observed exactly 17 child stops in `stops.txt`; IDs were not derived arithmetically.

- Rail `Parentch:1:sloid:2113` (10): `ch:1:sloid:2113:1:0`, `ch:1:sloid:2113:1:1`, `ch:1:sloid:2113:2:2`, `ch:1:sloid:2113:2:3`, `ch:1:sloid:2113:3:4`, `ch:1:sloid:2113:3:5`, `ch:1:sloid:2113:4:6`, `ch:1:sloid:2113:5:11`, `ch:1:sloid:2113:6:12`, `ch:1:sloid:2113:6:13`
- Bus `Parentch:1:sloid:2996` (7): `ch:1:sloid:2996`, `ch:1:sloid:2996:0:367483`, `ch:1:sloid:2996:0:604264`, `ch:1:sloid:2996::2`, `ch:1:sloid:2996::3`, `ch:1:sloid:2996::4`, `ch:1:sloid:2996::5`

No unrelated Aarau city stop was added to the target group.

## Exact result

- Status: `DIRECT_POSITIVES_ENUMERATED`
- Positive boarding→destination pairs: `1,754`
- Excluded pickup-type-1 upstream rows: `321`
- Excluded drop-off-type-1 destination rows: `0`
- Unresolved active target-reaching frequency templates: exact-times-0 `0`; exact-times-1 `0`
- Unresolved scoped stop-time rows: pickup/drop-off type 2/3 `0`; malformed `0`; timepoint 0 `0`; invalid scoped trips `0`; nonmonotonic trip clocks `0`
- Removed services are applied before trip selection; every emitted row retains either `base_calendar` or `exception_added` service provenance.

Scanned rows:

- `stops.txt`: `104,831`
- `trips.txt`: `2,601,990`
- `calendar.txt`: `88,917`
- `calendar_dates.txt`: `10,909,747`
- `frequencies.txt`: `1,899`
- `stop_times.txt` pass 1: `42,243,848`
- `stop_times.txt` pass 2: `42,243,848`

Limited evidence from the deterministic result:

1. Trip `.ojp-91-14-A.1.TA.2328.j26`: board `ch:1:sloid:2192:0:984822` at `06:30:00` (`23,400`), arrive rail child `ch:1:sloid:2113:5:11` at `06:34:00` (`23,640`), elapsed `240` seconds, base-calendar service `TA+y8k00`.
2. Trip `.ojp-92-1-J.1.TA.480.j26`: board `ch:1:sloid:72388` at `06:30:00`, arrive bus child `ch:1:sloid:2996::5` at `06:37:00`, elapsed `420` seconds, base-calendar service `TA+bvf30`.
3. The retained sample also contains an inclusive `06:30:00` boarding from rail parent `Parentch:1:sloid:2105` to rail child `ch:1:sloid:2113:3:4`, arriving `06:42:00`, elapsed `720` seconds.

Synthetic tests separately establish inclusive `06:30:00` and `08:30:00` boardings, exact 1,800-second acceptance and 1,801-second rejection, traversal over intermediate stops, ordered pickup-to-drop-off semantics, pickup/drop-off fail-closed handling, base/removal/addition service exceptions, unresolved exact-times-0 frequency templates outside the clock window, deterministic bytes, observed parent/child membership, and pre-write source-hash rejection. Architect review added RED/GREEN cases so a malformed intermediate stop or a backwards trip clock invalidates its entire trip rather than fabricating a direct ride; a supplied destination parent must actually have `location_type=1`. The reviewed full source had zero such unresolved trip anomalies, so the positive-journey count stayed `1,754`.

## Bounded direct-positive diagnostic across the 19 selected workplaces

The same script was rerun with **all 20 source-matched parent candidates** for the 19 selected capitals, using the outside-Git registry `CAPITAL-TARGET-CANDIDATES-19-20261021.json` (SHA-256 `d8a8a926d33f3e3c39be27a053409460f9b78a41faa9f5fc2d3c4af4cbd6f7fb`). The provisional raw result `all19-direct-30-provisional-20261027.json` (outside Git; SHA-256 `f570398ca8cf30e3050cfd5641e8368fc6fde0c72ac88db0c624a70731a4272d`) contains `5,577` direct pickup→arrival pairs across all 19 workplace targets, with zero unresolved scoped classes. It ran in `193.795 s` under a 500-second / 3.5-GiB memory bound, observed Python peak RSS `145,828 KiB`, and the `1,754` Aarau rows exactly matched the standalone Aarau result. The result is **not** a transfer-aware 19×2,110 residential coverage matrix and cannot reject absent destinations or Gemeinden. Neither the provisional date nor the 19 workplace-arrival-access candidates are independently approved.

A separate outside-Git GIS join assigned the `212` Aarau-positive boarding stops to `62` distinct 2026 BFS municipality polygons (all unique matches). Its 62-row CSV is `AARAU-DIRECT-STOP-LOCALITIES-30-20261021.csv` (SHA-256 `0e74e92112153253a731de6c25ec89417a56b6c4323cd8cc773686a162deae58`); the other `2,048` municipalities are **unknown**, not outside the transit limit. A stop located within a Gemeinde does not prove that any residential origin has an eligible access walk. This derived municipality list is retained outside public Git/product data while geodata rights, access and acceptance remain unresolved.
