# T3 travel diagnostics — BLOCKED, not a national generator

Commands below run from the repository root. No Swiss travel JSON is generated.
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
