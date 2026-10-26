# Travel data

## Current pipeline: Gemeinde → workplace matrix

`matrix.py` computes, for every Gemeinde and each of the 19 workplaces, the shortest time from first
boarding at a stop inside the Gemeinde to arrival at the workplace station complex, for first boardings
06:30–08:30 on the reference Tuesday, with any number of changes, up to 30 minutes. It is a reverse
profile Connection Scan in standard-library Python (about 3–4 s per destination for ~700k connections).
The rules are in the module docstring and in SPEC §6.5c.

```sh
python3 scripts/travel/run_matrix.py --gtfs GTFS_FP2026_<date>.zip --date 2026-10-27 --feed-url <url>
python3 scripts/travel/compare_reference.py        # SBB pairs, SPEC 11.2, tolerance 3 min
python3 -m unittest discover -s tests/travel
```

In GitHub: Actions → **Build travel matrix** → Run workflow, with the URL of a feed from
https://data.opentransportdata.swiss/dataset/timetable-2026-gtfs2020. The workflow records the feed's
SHA-256, writes `site/data/travel/matrix/`, runs the SBB comparison and opens a data PR.

Fill `tests/travel/sbb-reference-2026.csv` from sbb.ch (fastest journey, same date and window) so the
comparison can pass; empty cells stay `pending`.

Known model limits, recorded in `meta.json`: walking from home to the first stop is not measured (0 min);
origins are stops inside the simplified Gemeinde polygon; route- or trip-specific `transfers.txt` rows
other than stay-seated continuations are not modelled; walks between stops are straight-line × 1.3.

## Earlier diagnostics

The remaining modules in this directory are the earlier bounded probes and the observed-positive
exporter that produced `site/data/travel/all19-observed-routes-20261027.json` (SPEC §6.5b). They are
kept until the matrix has been generated from a real feed and reviewed; see the history below.

## History

### T3 travel diagnostics — BLOCKED, not a national generator

Commands below run from the repository root. No accepted Swiss residential
travel JSON is generated; the direct-ride screen writes provisional, outside-Git
diagnostic JSON only.
`build.py` always exits **2**: the exact metric and national pipeline remain
incomplete. Neither a larger machine nor a supplied manifest bypasses the gates.

## Exact observed environment and usage

Linux x86_64, Python **3.11.15**, r5py **1.1.7**, R5 **7.5.1**,
geopandas **1.2.0**, pandas **3.0.6**, Azul Zulu21.44.17 CA JDK
**21.0.8+9-LTS**. `environment.lock.json` records observed archive/JAR hashes;
`requirements.txt` pins the installed runtime dependency closure. These are
observed version pins, not a hash-locked release or a fresh-install proof.
JDK is installed separately, never by pip. Existing local environment:

```sh
export JAVA_HOME=/home/hermes/.cache/steuerpendler-travel/zulu21.44.17-ca-jdk21.0.8-linux_x64
TRAVEL_PY=/home/hermes/.cache/steuerpendler-travel/venv/bin/python
"$TRAVEL_PY" -m pip check
python3 -m unittest discover -s tests/travel -v
"$TRAVEL_PY" scripts/travel/build.py --preflight-only --report docs/travel/preflight.json
# Exit 2 above is expected: a negative report, NOT a successful build.
```

For another environment, use Python 3.11.15 to create a venv and run
`<venv>/bin/python -m pip install -r scripts/travel/requirements.txt`. Install
the matching JDK separately and verify its archive SHA-256 against the lock.
Tests use only stdlib unittest; they do not import r5py or start Java.
Preflight checks installed versions without importing r5py, reports RAM/cgroup
limits, affinity CPUs, free disk and Java, and never downloads routing inputs.
The default report is `artifacts/travel/preflight.json` relative to the working
directory. `--inputs <local-manifest.json>` only records presence/hash (<=1 MB),
not validation; it still blocks. The national input validator does not exist.

## Bounded direct-ride positive screen (not a residential generator)

From the repository root, use the pinned GTFS source and actual station-parent
IDs; repeat `--destination-parent` for each selected target parent. An explicit
source hash rejects changed input before writing the result. The scan emits
scheduled direct journeys only; it does not add residential access walks,
transfer-aware journeys or workplace egress, and cannot exclude a Gemeinde.

```sh
python3 scripts/travel/gtfs_direct_cap.py \
  --feed /home/hermes/data/steuerpendler/2026-10-19/gtfs_fp2026_20261017.zip \
  --service-day 2026-10-27 \
  --destination-parent Parentch:1:sloid:2113 \
  --destination-parent Parentch:1:sloid:2996 \
  --result /home/hermes/data/steuerpendler/2026-10-19/aarau-direct-30-provisional-20261027.json \
  --expected-sha256 d5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e
```

The date remains **provisional** pending the all-canton holiday test. The 30-minute
first-boarding-to-arrival cap and 06:30–08:30 boarding window are independent of
the 0–15-minute website walking control. Use an outside-Git result path: see
`docs/travel/aarau-direct-30-screen-20261021.md` for source checks, observed
counts, a 19-workplace repeat and unresolved acceptance gates. The release
manifest must stay travel-unavailable; a positive screen must not be copied into
`site/data/travel/` as an accepted matrix.

## Evidence and failures

- `docs/travel/metric-probe.json`: actual tiny synthetic GTFS/OSM diagnostic,
  **not official Swiss data**, with **`conformancePassed: false`**. Percentile-1
  returned **3 minutes** for both SYN-B and no-service SYN-N, versus the fixture's
  exact first-boarding A-to-B minimum of **60 seconds** (08:30 inclusive).
  RegionalTask changed **07:13:17 to 07:13:00**. Recorded 90 itinerary segment
  rows, 512 MiB heap, 376,082,432-byte process peak RSS and 4.445 s: not national
  capacity evidence and not complete §8 fixture conformance.
- `docs/travel/metric-probe-initial-failure.json` and
  `docs/travel/metric-probe-serialization-failure.json`: retained failed attempts
  (tiny-network edge-store error, then GeoDataFrame serialization error).
- `docs/travel/preflight.json`: actual current local negative preflight report.

`metric_probe.py` is diagnostic only: exit 0 means execution completed, **not**
metric acceptance. Existing evidence is retained; do not run Switzerland. If
explicitly repeating only the tiny synthetic diagnostic, use the above venv/JDK
and `--r5-classpath /home/hermes/.cache/steuerpendler-travel/r5.jar --report <diagnostic.json>`.
The script owns its 512 MiB heap cap. Inspect `conformancePassed`, not exit 0.

Real Swiss **GTFS, OSM and STATPOP** (or evidenced representative-point fallback)
are missing as frozen, validated build inputs. Exact tax/map BFS joins, approved
all-canton reference-day evidence, provenance/release validation, OSM walking,
national generation/checkpoints, measured 50-workplace pilot/full run and all
30 official SBB comparisons remain pending. A sampled percentile is not an exact
first-boarding minimum. Prove the full §8 metric suite before any national run.
The approximately 4 GB local host also fails national RAM admission; passing
admission alone would not certify capacity or T3 completion.

The manual `.github/workflows/build-travel.yml` runs stdlib tests and real
preflight, preserves the report as an artifact, and fails when preflight blocks.
It is read-only diagnostic automation: no routing environment provisioning,
national downloads, site data generation, deployment or PR step. Runner Python,
JDK and dependency mismatches remain explicit blockers. This is **not** the
future T3 changed-data PR workflow and has not been exercised in GitHub CI.
