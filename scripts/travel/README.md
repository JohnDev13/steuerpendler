# Travel routing: current and historical evidence

## Public preview (active)

`site/data/travel/all19-observed-routes-20261027.json` is the pinned, observed-positive
all-19 preview (SHA-256 `426e71f1a361f9b645f4f16fd121854a6955f4b19dab0268b4bed6cf3befb2bb`).
Its 806 all-route and 451 independently sourced direct-only municipality/destination
positives are indicative; missing rows are **unknown**, not unreachable. First boarding is
06:30:00–08:30:00 Europe/Zurich on the approved 2026-10-27 reference Tuesday, and the
30-minute cap is exact in seconds. External home-to-boarding-stop access is zero by interim
assumption and *unmeasured*. `availability.travel=false` and independent SBB approval remains false.

The separate pinned first-board-event×19 gzip is provisional engineering evidence, not a
public globally-fastest authority. The source-coverage audit found 78,279 candidate boarding
events without assigned-origin coverage and 65 Gemeinden without an assigned boarding stop;
neither gap authorizes a negative conclusion. See `SPEC.md` §6.5a and
`docs/travel/canonical-event-slice-decision.md` for schema/version and provenance limits.

## Experimental GTFS candidate (inactive)

`scripts/travel/matrix.py` and `run_matrix.py` are a standard-library Connection Scan candidate.
They emit bounded all-route positives and a **separate direct-only scan**, exact-second
comparisons with display minutes rounded up, and `absence:"unknown_unobserved"`.
The candidate has not been run and independently validated on a national real feed.
Frequency trips, origin completeness, route/trip-specific transfer precedence, approximate
short walks and source drift are unresolved. The frontend refuses to load this candidate while
`availability.travel=false`, even if generated files appear in the manifest.

The manual **Build travel matrix** workflow requires a feed URL **and pinned SHA-256**, records
actual bytes/hash, runs tests and diagnostic SBB comparisons, and can open a **draft** data PR.
A draft PR is not release approval; inspect every positive path and source gap before deciding
whether to merge data. An SBB sample within ±3 display minutes alone does not certify fastest
routing. `tests/travel/sbb-reference-2026.csv` currently has blank reference minutes.

```sh
python3 -m unittest discover -s tests/travel -v
python3 scripts/travel/compare_reference.py  # diagnostic only; source file must exist
```

## Historical diagnostics and drift

The earlier Aarau-only direct screen, R5 metric probes, dependency preflight, and associated
scripts/tests were retired from the current checkout during cleanup. Their dated findings remain
in `docs/travel/`, `docs/deployment/`, archived source-version documents and Git history; commands
that refer to deleted scripts are **not** current instructions. The R5 percentile diagnostic did
not meet the first-boarding metric; a successful process exit was not conformance. The all-19
observed-positive asset superseded the Aarau-only public copy, not the canonical event contract.

Before changing route claims, compare the current source/feed hash and code version to the pinned
2026-10-27 evidence, rerun exact boundary and independent direct-path checks, and update the
release manifest, methodology and this page together. Do not mark unknown origins unreachable,
change `availability.travel`, or assert official SBB acceptance from synthetic tests.
