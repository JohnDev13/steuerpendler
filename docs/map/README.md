# T2 — Real 2026 Switzerland map

## Source and legal status — unresolved launch gate

- Published input: [`swiss-maps@4.7.0`](https://www.npmjs.com/package/swiss-maps/v/4.7.0), Interactive Things, [upstream repository](https://github.com/interactivethings/swiss-maps).
- Original archive: `https://registry.npmjs.org/swiss-maps/-/swiss-maps-4.7.0.tgz`.
- Archive SHA-256: `5302805c536eef70e2001a8893ec66615a3e9e4ccf15eafe4a2215b50d39435e`.
- Inputs: the package's `2026/{municipalities,cantons,lakes}.{shp,shx,dbf,prj}`. The package's ready-made `ch-combined.json` is **not** used.
- `source-manifest.json` records the SHA-256 of each input and the package metadata/notices. Installed inputs were verified byte-for-byte against the supplied pinned archive; build and test both enforce those hashes.
- Attribution required by the package: **Bundesamt für Statistik (BFS), GEOSTAT**. Its README also describes the data's swisstopo/FSO lineage. Do not replace the explicit BFS/GEOSTAT credit with a generic swisstopo credit.
- The upstream **code** licence is BSD-3-Clause; the unmodified notice is retained in `swiss-maps-4.7.0-LICENSE.txt`. The unmodified upstream README is retained in `swiss-maps-4.7.0-README.md`.
- **The package README explicitly states a non-commercial licence for the geodata. That issue is unresolved. The code licence is not legal clearance for the derived geography.** The owner must establish applicable data rights, redistribution conditions and launch/commercial-use permission before publication. Neither this local commit nor its technical tests approve those rights.

## Build and reproduce

The root package/lockfile is managed by the integrating task, not this branch. Required installed versions for the build: `swiss-maps@4.7.0`, `mapshaper@0.7.87`; tests/rendering also use `d3-geo`, `topojson-client`, `pngjs`, and `@resvg/resvg-wasm@2.6.2`. Node 22 was used (mapshaper requires Node >=20.11).

```sh
node scripts/map/build.mjs
node scripts/map/render.mjs
node scripts/map/test.mjs --rebuild
```

Run from the repository root. The build itself resolves paths from its script location. `--rebuild` deliberately executes two independent builds and compares their bytes to one another **and to the existing committed file**. There are no timestamps or machine-specific paths in the output.

Until the separate tax task is integrated, the final command must fail because `site/data/gemeinden-2026.json` is missing. For explicit partial verification only:

```sh
node scripts/map/test.mjs --allow-missing-tax --rebuild
```

That option skips only an **absent** tax file with a `BLOCKED` explanation; if a tax file exists, count and exact set equality are always enforced. No synthetic tax fixture is generated. The parent should wire `map:build`/`map:test` to the above commands in package.json, and rerun without the opt-out after tax integration.

## Geometry and frontend contract

- TopoJSON output: `site/data/map/switzerland-2026.json`; three named objects: `gemeinden`, `cantons`, `lakes`.
- `gemeinden` contains **2,113 geometries with unique numeric source BFS IDs**: the expected 2,110 municipalities plus the three source-only/no-tax areas **2391, 5391, 5394**. These extras remain in the geography; `meta.noDataIds` tells the UI to render them grey and label them **no data**. Do not include them in workplace search, rankings, tax totals, or reachability denominators.
- There is one geometry per source ID, not one record per disconnected island. `Polygon` and `MultiPolygon` are both intentional. All geometry properties are removed, so names and canton codes must come from tax metadata where available. Canton/lake IDs are their source IDs, not municipality IDs.
- Coordinates stay **pre-projected CH1903+ / LV95, EPSG:2056, in metres**, matching all three source PRJs. Use `d3.geoIdentity().reflectY(true).fitExtent(...)` with `d3.geoPath`. Do **not** feed these numbers to geoMercator/geoAlbers or assume longitude/latitude. TopoJSON's transform decodes quantized coordinates into LV95 metres.
- mapshaper imports all three layers with `combine-files` into **one shared arc graph before simplification**. Weighted Visvalingam simplification uses `interval=100 planar keep-shapes`; TopoJSON export uses **one** `quantization=100000` grid, `id-field=id`, `drop-table`, `bbox`. IDs are sorted numerically before serialization. No independent per-polygon simplification, reprojection, or guessed replacement geometry is used.
- Tested shared topology: **6,763** municipal neighbour arcs have opposite orientation; **1,010** arcs are reused by municipalities/cantons, **179** by municipalities/lakes, and **8** by cantons/lakes. Shared references prevent independent simplified borders drifting apart.
- Source lakes are retained, including cross-border portions. They are not clipped to an invented national mask. The layer remains 22 real source lakes; canton count is 26.
- Size: **698,284 bytes raw; 240,960 bytes gzip** (Node zlib default). Budgets use conservative decimal limits of 1,500,000 and 500,000 bytes.
- Output SHA-256: `d118a3e8b47c8d76d4fa2587911aa088573d09a934ea484f2f1a60d573aafe14` (two clean builds matched).

## Automated and visual evidence

The test verifies pinned source hashes and verbatim notices, exact map/source and map/tax ID sets, duplicates/counts/extras, no properties, finite quantized arcs and LV95 projection bounds, non-empty polygon/multipolygon rings, closure, nonzero area, no proper self-crossings, valid arc references, neighbour orientation and shared arcs, finite d3 paths, raw/gzip budgets, and evidence PNG hashes/pixels. These are cartographic integrity checks, not cadastral accuracy or an exhaustive legal/OGC certification.

`switzerland-2026.png` is a real **1400×1000** image rendered offline from the generated topology, not a placeholder. `render-report.json` binds its SHA-256 to the map's hash. Colours are geometry-only: green municipality, grey no-data extras, blue lake. White thin municipal boundaries and dark canton borders are deliberate strokes, not gaps. The grey extras are very small at national scale (5394 is subpixel in area), so the legend also lists all three IDs.

The PNG's actual pixels were loaded and visually inspected: recognizable Swiss outline, plausible lake positions, contiguous neighbouring municipality coverage, no obvious slivers/cracks, and no clipped geometry or text. This is a national-scale review only, not proof of every small island at arbitrary zoom.

Chromium was installed, but opening even a blank Playwright page failed with `V8 process OOM (Failed to reserve virtual memory for CodeRange)`. The permitted SVG-to-image alternative uses already-installed `@resvg/resvg-wasm@2.6.2` with local DejaVu Sans fonts, no network resources. On a different OS set `MAP_FONT_DIR` to a directory containing `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf`. The image test reads PNG pixels using pngjs. Browser/UI tests remain the integrating task's responsibility.

## Acceptance scope

Initial RED was observed: the first map-data test failed because the map output did not exist. Subsequent RED checks identified missing provenance/render artifacts and the missing real tax file; implemented build, notices and PNG satisfy the available checks. `test-output.tap` records the actual partial verification run, including two identical rebuilds. **Tax set integration is still blocked in this isolated map worktree** until the parent integrates the real dataset. No official, CI/PR, owner, licensing, deployment or full T2 acceptance is claimed by this branch. SPEC.md, package.json, vendor code and UI files were not changed.
