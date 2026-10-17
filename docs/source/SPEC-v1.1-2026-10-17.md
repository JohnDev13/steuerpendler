# Steuerpendler — Build Spec v1.1

Amended: 16 Oct 2026 (UTC) · Owner: John · Tax year: 2026
Supplied v1 stated status: 17 Oct 2026 (source metadata, not verified chronology).

**Reconstruction status:** The original implementation/commit is unrecovered. Reconstruction from real upstream is now authorized; this is not recovery of the lost implementation. The original `docs/prototype.html` is unavailable. This amendment certifies no implementation, official reference, licence clearance, owner approval or launch. Source lineage and F01–F15 mapping: `docs/spec-amendments-v1.1.md`.

## 0. How to use this file (agents read first)

- This file is the single source of truth. Read it fully before starting any task.
- Tasks are in section 10. A task is done only when all of its acceptance tests pass and its required CI stage is green. T1 scaffold acceptance is not feature acceptance; T8 preview readiness is not production launch (§10, §12–13).
- Data formats in section 6 are contracts between tasks. Do not change them without updating this file in the same pull request.
- Items in section 14 (open decisions) belong to the owner. Use the stated default, and do not decide them yourself.
- Rules:
  - One branch and one pull request per task. Never push to `main` directly.
  - No backend, database, user accounts, cookies or tracking in v1. The site is static files only.
  - Do not edit `vendor/swisstaxcalculator/` except for patches recorded in its `STEUERPENDLER-PATCHES.md`.
  - Never commit secrets. Use GitHub Actions secrets.
  - Never invent reference values (tax amounts, SBB travel times). Look them up in the official source or leave the cell empty and report it.
  - Track `pending`, `passed`, `failed` and `quarantined` explicitly. Empty/skipped suites, placeholders, synthetic fixtures and local success are not official or CI approval.
  - Technical defaults below guide implementation. Owner-dependent proposals (§14 and amendment register) remain pending until recorded approval; a default grants no legal/product approval.

## 1. Goal

A website where a person picks the town they work in and how long they are willing to commute by public transport, and gets every Gemeinde within that commute ranked by their total yearly income tax (Bund + Kanton + Gemeinde + Kirche), on a map and as a list.

Example: "I work in Zürich and accept at most 25 minutes by train or bus, plus up to 10 minutes' walk to the station. Where do I pay the least tax?"

## 2. Scope

**In v1**
- Workplace: any of the 2,110 Swiss Gemeinden.
- Commute filter: max travel time, max walk to the station, and a toggle that counts the walk inside the travel time.
- Tax profile: gross income, single or married, 0–3+ children, church (none, reformed, catholic).
- Results: ranked list, Switzerland map coloured by tax, and a breakdown per Gemeinde.
- Real 2026 tax data and the real Swiss timetable.
- Hosted on Cloudflare Pages, rebuilt from GitHub.

**Not in v1:** rent, health insurance premiums, wealth tax, two-earner couples (see O1), door-to-door routing, user accounts, saved searches, ads or payments.

## 3. Decisions already made (do not revisit)

| Topic | Decision |
| --- | --- |
| Hosting | Cloudflare Pages, deployed from the GitHub repo. Static files only. |
| Data | Precomputed once a year and committed to the repo as JSON. All filtering and tax maths run in the browser. |
| Tax source | ESTV 2026 tariffs and Steuerfüsse via the vendored open-source engine `swisstaxcalculator` (MIT), with three documented patches. |
| Travel source | Swiss GTFS timetable (opentransportdata.swiss) + OpenStreetMap footpaths, routed with r5py. |
| Map | Gemeinde boundaries 2026 from the `swiss-maps` npm package (4.7.0), drawn with d3-geo. No tile server, no map API key. |
| Frontend | Vite + TypeScript, vanilla DOM (no UI framework), d3-geo and topojson-client. Unit tests: Vitest. E2E tests: Playwright. |
| Lovable / Supabase | Not used. |

## 4. Current state and reconstruction lineage

The supplied v1 described a local `steuerpendler/` repository with one commit and no GitHub publication. That original state is **unrecovered**, not the verified state of this reconstruction repository. The baseline here contains requirements/review documents only. The following are historical claims and required reconstruction targets, not recovered files or passed tests:

- `vendor/swisstaxcalculator/`: reconstruct the engine and genuine 2026 data from real upstream, recording exact revision, inputs, licences and all modifications in `STEUERPENDLER-PATCHES.md`. Required historical patches:
  1. Export internal functions.
  2. Federal per-child deduction CHF 263 (2025/2026; formerly 251), federal tax floored at 0. Verify against genuine applicable inputs, not this statement alone.
  3. Fribourg: no crash above the top tariff step; top-rate assumption still needs official verification.
- `scripts/tax/build.ts`: reconstruct generation of `site/data/tax-2026-{s|m}-{0..3}.json` and `gemeinden-2026.json`.
- `scripts/tax/selftest.ts` (`npm run tax:test`): v1 reported 500 on-grid cases, max error CHF 5.19, and 300 between-grid cases, max error CHF 9.38. These are unreproduced historical claims, not §7.1 passes. The on-grid maximum alone does not establish a pass; rebuild and test without loosening the gates.
- `scripts/tax/reference.ts`: reconstruct independent engine execution for §11.1 scenarios; preserve supplied historical rounded values separately.
- `docs/prototype.html`: unavailable. Never invent its contents or claim visual/pixel fidelity. Reconstruct layout/interactions from §9, with owner UX review pending. If recovered later, use it for UX only, never numbers.

Real upstream locator: https://github.com/devbrains-com/swisstaxcalculator . Read-only HEAD lookup on 2026-10-16 returned `43064402b1e52dbbc34dded6a305d7d536737c73`: a discovery observation, not the lost commit or approved vendor/data snapshot. Pin and inspect the selected upstream revision before vendoring; never substitute plausible ESTV/SBB values for missing evidence.

## 5. Architecture

```
ESTV data (vendored) ──► scripts/tax ──────► site/data/tax-*.json, gemeinden-*.json ─┐
GTFS + OSM + STATPOP ──► scripts/travel ───► site/data/travel/**                    ├─► Vite build ─► dist/ ─► Cloudflare Pages
swiss-maps 4.7.0 ──────► scripts/map ──────► site/data/map/switzerland-2026.json ────┘
                         (GitHub Actions, manual run, yearly)        (staged CI every push/PR; gated launch on main)
```

Target repo layout:

```
SPEC.md  README.md  package.json  vite.config.ts  index.html
src/                 # TypeScript, vanilla DOM; no UI framework
  main.ts state.ts tax.ts filter.ts map.ts list.ts detail.ts format.ts strings.ts styles.css
  *.test.ts          # Vitest beside code
site/                # Vite publicDir: 'site'; contents copied to dist/
  _headers  404.html
site/data/           # generated, committed; copied to dist/data/
  manifest.json      # coherent release identity and frozen inputs (§6.7)
  tax-2026-s-0.json … tax-2026-m-3.json  gemeinden-2026.json
  travel/meta.json  travel/access.json  travel/to/<bfs>.json
  map/switzerland-2026.json
scripts/tax/  scripts/travel/  scripts/map/
tests/e2e/  tests/reference/
pages/               # impressum.html datenschutz.html methode.html; explicit Vite inputs
vendor/swisstaxcalculator/
docs/                # prototype.html unavailable; review/amendment register retained
.github/workflows/ci.yml  build-tax.yml  build-travel.yml
```

Set Vite `publicDir: 'site'`, not `site/data`. Use explicit multi-page inputs for root `index.html` and the three `pages/*.html`, with served URLs `/pages/impressum.html`, `/pages/datenschutz.html`, `/pages/methode.html`. Assert `dist/data/*`, `dist/_headers`, `dist/404.html` and all three page outputs after the production build. No implicit page copying or SPA fallback is accepted as wiring.

## 6. Data contracts

All JSON is UTF-8 and minified. BFS ids are Gemeinde numbers as of 1 Jan 2026. Object keys are canonical decimal strings; travel row IDs are integers. Serialize keys deterministically; sort travel rows by minutes then numeric BFS ID. Reject duplicates, unknown IDs, non-finite numbers and schema/hash mismatches. §6.7 records release metadata in deterministic manifests without requiring metadata inside every original payload. Explanatory ellipses are not literal JSON. Files below are reconstruction targets, not assumed present.

### 6.1 Tax profile files: `site/data/tax-2026-{civ}-{kids}.json` (reconstruct)

`civ` is `s` (single) or `m` (married, one earner); `kids` is 0–3 (3 means "3 or more").

```json
{
  "meta": { "year": 2026, "incomes": { "from": 40000, "step": 1000, "count": 461 }, "...": "..." },
  "cantons": { "ZH": [[bund, base, personal], ...461 rows], "BE": [...], ... 26 cantons }
}
```

Row `i` is for gross income `from + i × step`. `bund` is the Bundessteuer in CHF, `base` the cantonal simple tax ("einfache Steuer", before Steuerfüsse), and `personal` the Personal-/Kopfsteuer in CHF.

### 6.2 Gemeinden: `site/data/gemeinden-2026.json` (reconstruct)

```json
{ "meta": {...}, "gemeinden": { "261": ["Zürich", "ZH", 95, 119, 10, 10], ... 2110 entries } }
```

Columns: name, canton, rateCanton, rateGemeinde, rateReformed, rateCatholic. Rates are % of `base`.

### 6.3 Travel metadata: `site/data/travel/meta.json` (task T3)

```json
{ "timetable": "2027", "referenceDate": "2027-01-12", "window": "06:30-08:30", "maxMinutes": 60,
  "gtfsFile": "<name of zip used>", "built": "<ISO date>" }
```

### 6.4 Access: `site/data/travel/access.json` (task T3)

```json
{ "gemeinden": { "261": ["8503000", "Zürich HB", 6], "9999": null, ... } }
```

Value: main stop id (parent station), main stop name, walk minutes from the population centre. `null` means no usable stop under §8. Every tax BFS ID must occur, including null entries. Check access before fetching a workplace file; null is a legitimate selectable no-main-stop state, not an asset failure (§9).

### 6.5 Travel times per workplace: `site/data/travel/to/<bfs>.json` (task T3)

```json
{ "to": 261, "rows": [[261, 0], [3, 7], [191, 9], ...] }
```

Each row is `[homeBfs, minutes]`, sorted by minutes then numeric BFS ID. Keep only rows ≤ 60 minutes. Every non-null-access workplace has exactly one file and a self-row with travel component 0; distinct Gemeinden sharing its nominated parent station also have travel component 0. No file is expected for null-access workplaces. A self-row never bypasses frontend walk/effective-time constraints. Missing/corrupt files for non-null workplaces are errors, not legitimate empty/no-stop results.

### 6.6 Map: `site/data/map/switzerland-2026.json` (task T2)

TopoJSON with these objects:
- `gemeinden`: exactly one geometry/feature per tax BFS ID plus the three source-only IDs 2391, 5391, 5394, canonical `id`, no properties. `Polygon` or `MultiPolygon` is allowed; disconnected parts are not duplicate features. `meta.noDataIds` identifies the three extras, excluded from tax/search joins, grey and labelled "no data"; no separate fourth topology object is required.
- `cantons`: canton polygons, for borders.
- `lakes`

Coordinates may remain pre-projected LV95/EPSG:2056 (reconstruction default), rendered using d3 geoIdentity with reflected Y, or be transformed to WGS84 with documented projection. Record source/output CRS, simplification and quantization in `meta`. Size: ≤ 1.5 MB raw, ≤ 500 KB gzip (decimal units), as in v1. Do not add an unvalidated displacement threshold as a hidden new requirement.

### 6.7 Reproducible inputs and coherent data releases

`site/data/manifest.json` is a committed deterministic release manifest. Freeze original inputs before rebuilding: source URLs and SHA-256/bytes of every input; GTFS filename, coverage, service date/timetable label; OSM snapshot date; STATPOP vintage or explicit representative-point fallback; tax/map BFS vintage and exact sorted ID-set hash; `swiss-maps@4.7.0` archive integrity; vendor revision and patch hash; overrides/preprocessing hashes; Python, JDK, r5py/R5 and JS lockfile versions/hashes; build-code revision, fixed seed and parameters. Preserve original and transformed GTFS hashes. Validate GTFS spatial assignment to the exact 2026 tax/map ID set; timetable labels need not equal tax years.

Default release scheme: retain §6 filenames and request every runtime data asset as `/data/<relative-path>?v=<releaseId>`. A deterministic `scripts/release/build.mjs` inventories final JSON bytes using SHA-256 and byte lengths, plus frozen provenance inputs and build-script hashes. Sort object keys recursively before JSON serialization; this application-specific encoding is documented and is not claimed to be full RFC 8785. Hash this non-recursive inventory to form releaseId. Exclude manifest/release wrappers, volatile timestamps and build output from their own preimage. The manifest and a small `site/data/release.json` wrapper record schemaVersion=1, release ID, file hashes, truthful availability and pending approval flags. Embed that wrapper in the application at build time. Loaders verify pinned served-byte hashes before using assets, avoiding a schema change to every original §6 payload. Cache by release ID and reject mismatched bytes. Frozen inputs produce byte-identical output; volatile run timestamps belong only in logs.

**Mandatory hosting gate:** query keys must participate in browser and CDN caching. Verify actual Pages/CDN responses for old/new `?v=` values, cache hits, ETags and revalidation across two deployments and a browser retaining the old bundle. Stable physical filenames may no longer serve an old release: the client must detect a release mismatch, discard the entire mixed release and offer reload, never calculate with mixed files or retry unversioned. A fresh bundle must obtain its pinned coherent release. Query versioning is not proven safe by configuration: if CDN query handling/coherence fails, block launch and amend to content-addressed paths with equivalent tests. No backend is introduced.

## 7. Tax rules (frontend must implement exactly this)

For workplace-independent tax profile `(civ, kids, income, church)` and Gemeinde `g`:

```
x       = clamp((income − 40000) / 1000, 0, 460)
i       = min(floor(x), 459);  t = x − i
row     = cantons[g.canton][i] + (cantons[g.canton][i+1] − cantons[g.canton][i]) × t     (element-wise)
rateCh  = church == reformed ? g.rateReformed : church == catholic ? g.rateCatholic : 0
kanton  = row.base × g.rateCanton / 100
gemeinde= row.base × g.rateGemeinde / 100
kirche  = row.base × rateCh / 100
total   = row.bund + kanton + gemeinde + kirche + row.personal
```

Fixed assumptions, shown on the page: gross employment income, age 35, no wealth, standard deductions, and married couples have one income.

Display totals rounded to CHF 10. Income input: CHF 40,000–500,000. Below or above that range, clamp the value and show a note.

### 7.1 Numeric verification gates (inclusive; unrounded CHF)

For each case `error = abs(actual - expected)`; percentages use `abs(expected)`, not actual. Every case must independently pass; averages/maxima cannot hide failures. Compare before display rounding; at expected zero the absolute floor applies. These are fixed requirements, not permission to loosen tolerances or alter references:

| Gate | Actual / expected | Coverage | Required limit |
| --- | --- | --- | --- |
| On-grid regression | Reconstructed tables and `src/tax.ts`, each independently vs full engine | ≥ 500 deterministic on-grid cases; all 26 cantons, 8 profiles, 3 church options represented; endpoints and §11.1 scenarios | `error <= max(2, 0.0001 * abs(expected))` |
| Off-grid regression | Reconstructed tables and `src/tax.ts`, each independently vs full engine | ≥ 300 deterministic between-grid cases; all 26 cantons and 8 profiles, near tariff/deduction transitions | `error <= 10` |
| Official end-to-end | Shipped `src/tax.ts` directly vs independently retrieved ESTV | All 29 §11.1 scenarios, same frozen release and exact inputs | `error <= max(5, 0.001 * abs(expected))` |

Store seed, exact inputs and individual errors. §11.1 historical rounded engine cells are lineage, not substitutes for unrounded engine execution. At an exact grid point interpolation reproduces components to absolute error ≤ `1e-9` CHF. Intermediate tolerances cannot establish the direct official gate. Fix discrepancies or report failed gates; do not relax limits to make CI green.

Official CSV/evidence must record tax year, BFS/canton, gross income, age 35, civil/household status, partner income 0, child ages/treatment, church, no wealth, employment/deduction settings and actual ESTV input mapping/calculation steps from gross income. Proposed child-age default where unspecified: 10 years for each child; owner confirmation of comparability and deduction selections is pending before official acceptance. Record source URL/retrieval time, official result at available precision, evidence/hash, engine/frontend values, release ID and pass/fail. Never fill official gaps from the engine. Prioritize suspect VS and FR top-step checks without declaring either officially wrong/passed here.

## 8. Travel-time rules (task T3 must implement exactly this)

- **Reference day:** freeze a GTFS-covered Tuesday. Proposed calendar rule: earliest covered Tuesday outside national/cantonal public holidays and compulsory-school holidays in all 26 cantons (all published regional calendars where applicable). Record calendar URLs, retrieval dates and coverage evidence. If no such date exists, require owner-approved documented exception before T3 acceptance; never silently weaken the rule. Illustrative §6.3 2027 metadata is not an approved feed/date selection.
- **Main stop:** rank active stops inside the Gemeinde, aggregated by parent station, by departures 06:00–09:00 inclusive on the reference day (Europe/Zurich). Count each active `(trip_id, stop_sequence)` once; stops without parent use their own ID. Ties: lexicographic station ID. If none inside has departures, choose the nearest active station within 2,000 m geodesic distance of the population centre, same tie rule; otherwise access is null. Parent coordinates are the nominated endpoint; if missing, use the arithmetic mean of child-platform coordinates and record it. Manual fixes: `scripts/travel/main-stop-overrides.csv` (`bfs,stop_id,reason`), validated and hashed.
- **Population centre:** population-weighted centre from BFS STATPOP hectares; if unavailable, use polygon representative point and explicitly record fallback in manifest/meta.
- **Walk minutes:** OSM pedestrian route from population centre to nominated station, speed 1.2 m/s, obey pedestrian access, ceil to integer minutes and cap at 60. If no walk route exists, reject candidate and try the next ranked eligible station; if none is usable access is null. Record rejection reasons, never invent a route.
- **Travel metric:** exact minimum elapsed time from **first boarding at an eligible platform of the nominated origin parent station** to arrival at an eligible platform of the nominated destination parent, among actual first-board departures in inclusive `[06:30:00, 08:30:00]` Europe/Zurich on the reference day. Include second-level departures, transfer waiting and transfer walks; exclude only pre-first-boarding waiting and external access/egress. Own-parent origin/destination platforms are endpoint equivalents with no added access/egress time; intra-journey transfers retain routed duration. Allow scheduled rail, tram, bus, ferry and cableway transit; explicitly map extended GTFS types and retain transformation provenance. No pure-walking journeys, car/bicycle access or arbitrary alternate-station access/egress. Same-parent and self cases are zero by definition. Find exact minimum in seconds, then ceil minutes and drop values > 60.
- **Conformance before nationwide routing:** keep r5py/R5, but do not assume `percentiles=[1]` or any sampled percentile is an exact minimum. Inspect itineraries on deterministic tiny feeds: rare fast vs frequent slower service, non-zero-second departures, transfer wait/walk, shared parent/platforms, no service/pure-walk exclusion, both inclusive edges and immediately-outside departures. Record pinned API/options/results. If the chosen API cannot deliver this metric, stop and document the blocker, never relabel a percentile.

Frontend filter (authoritative, including workplace):

```
reachable(g) = access[g] != null
            && rows has g
            && walk(g) <= maxWalk
            && (countWalk ? minutes(g) + walk(g) : minutes(g)) <= maxTime
```

Tax eligibility is a separate later restriction (§9); no workplace/self exemption is allowed.

**Geographic QA:** use geodesic distance `d` km between the exact nominated parent-station endpoints, not municipal centres. Same-parent/forced self zero rows are valid with coincident nominated endpoints; all other zero-time rows are errors. For positive-minute rows define conservative `v = 60 * max(0, d - 0.1) / (minutes + 1)` km/h, allowing 100 m coordinate tolerance and one minute rounding tolerance. `v > 100` requires review evidence; `v > 150` blocks acceptance unless an exact pair/service/feed-scoped exception is independently evidenced and owner-approved in a committed register. Never drop suspicious pairs to pass. Thresholds are plausibility heuristics, not proven universal service bounds; verify against actual services in the pilot. Test shared-parent, positive-distance/zero-time errors and rounding-edge cases.

## 9. UI spec

The original prototype is unavailable. Reconstruct layout/interactions from this section without claiming fidelity; owner UX review remains pending. If recovered later, the prototype guides UX only, never numeric expectations.

**Controls**

| Control | Range | Default |
| --- | --- | --- |
| Workplace | search box over all Gemeinden, matching by name, accent-insensitive | Zürich |
| Max travel time | 5–60 min, step 1 | 25 |
| Max walk to station | 0–15 min, step 1 | 10 |
| Count the walk in the travel time | toggle | off |
| Gross income | slider CHF 40,000–500,000, step 1,000, plus a number field | 120,000 |
| Civil status | single / married | single |
| Children | 0 / 1 / 2 / 3+ | 0 |
| Church | none / reformed / catholic | none |

**Results**
- **Summary:** "N reachable Gemeinden with comparable tax data" and the cheapest eligible total. Separately label "M reachable Gemeinden: data under review"; never count withheld places as recommendations.
- **Ranked list:** rank, name, canton, travel minutes, walk minutes, CHF/year and difference to workplace. Sort by unrounded total, travel minutes, name using `Intl.Collator('de-CH', {sensitivity: 'base', numeric: true})`, then numeric BFS ID. Deltas use an eligible workplace tax baseline independently of workplace travel reachability; otherwise "comparison unavailable".
- **Map:** Switzerland, tax-eligible reachable Gemeinden in up to 5 equal-count green-to-red groups, others grey with accessible distinct labels for out of reach, no data and data under review. For N > 0, k = min(5, N); contiguous rank-ordered groups have floor(N/k) members, with one extra in the first N mod k groups; N = 0 gives no groups. Use unrounded ranking. Number eligible top 10, mark workplace, zoom to eligible reachable area with padding; empty/no-stop keeps Switzerland overview. Clicking any geographic area selects its detail.
- **Detail:** Bundes-, Kantons-, Gemeinde-, Kirchen-, Personalsteuer; Gemeinde rate %, main stop, travel/walk and rank. Tax-eligible unreachable places still show detail labelled "out of reach". Quarantined/withheld-unverified places remain geographically selectable but expose **no total, breakdown, tax rank, cheapest status, delta or colour-group membership**; show "data under review". Extra map IDs show "no data" and never join as Gemeinden.
- **Empty travel result:** "No Gemeinde in reach. Allow more time or walking."
- **No-main-stop workplace:** all Gemeinden remain searchable/selectable, including null access. Check access before fetching `to/`; show "No usable main stop for this workplace", no travel results/ranked recommendations, with map/detail still available. Do not fetch a known-absent file or fabricate a self-row.
- **All reachable taxes withheld:** "Reachable Gemeinden have data under review", not a false claim of no travel reachability. Missing/corrupt/incompatible required assets get a distinct readable error/reload state, never a legitimate empty state.
- **Footer:** tax year, fixed assumptions, "Estimate, not tax advice", sources and Impressum / Datenschutz / Methode links.

**Non-functional**
- Works at 400 px without horizontal scroll; keyboard-usable, every control labelled; light/dark themes.
- Cold first usable default render ≤ 1,000,000 gzip bytes (decimal MB): count HTML, CSS, JS, fonts, manifest, map, municipality/access, default profile/workplace data and other required response bodies. Report compressed transfer bytes and full request inventory with caches disabled; do not exclude lazy data needed for initial results.
- Warm-cache full list/map/summary/detail update < 100 ms on a mid-range phone. Reproducible automation default: pinned Playwright Chromium, 400 × 800 viewport, device scale 1, CDP 4× CPU slowdown, all needed data in memory. Measure 30 scripted changes after 5 warmups, **every** measured change < 100 ms from input-handler entry to animation frame after committed DOM/map updates. Record browser/runtime/machine and individual times; also test real phones (§13).
- Cold profile/workplace changes: loading feedback ≤ 100 ms, validated-data compute/render < 100 ms after arrival, no stale result labelled as new selection. Test CDP emulation: 150 ms latency, 1.6 Mbit/s down, 750 kbit/s up, cache disabled; record cold transfer/total latency, 10 s timeout with readable retry error. Warm-cache budget does not include network latency.
- No cookies; no third-party requests except a font host if used (self-host default). Assert this in browser tests, including content pages. No analytics by O6 default.
- Money `CHF 12'345`, totals displayed to CHF 10, visible clamp notes; German default/all strings in `src/strings.ts` per O2.

## 10. Tasks

### T1 — Repo on GitHub, CI skeleton
Depends on owner creating the repo (O4).
1. Owner creates remote and baseline `main` (e.g. initial README). Publish reconstruction through a T1 branch/PR; no implicit remote creation or agent push directly to `main`.
2. Working Vite/TypeScript scaffold, lockfile, actual Vitest smoke and actual Playwright smoke against served production build. On every push/PR: `npm ci`, `npm test`, `npm run build`, `npx playwright install --with-deps chromium`, `npx playwright test`. Smoke asserts rendered scaffold content, a functioning interaction and no runtime/console errors; this proves scaffold only.
3. Committed CI-stage register: enable `npm run tax:test` with genuine reconstructed engine/tables; `npm run map:test` with T2 artifacts; `npm run travel:test` with T3 artifacts; T4/T5 units and T6 e2e as tasks land. Once active, run on **every** push/PR, never silently disable on missing files. Pending suites are labelled pending/not yet applicable, not passed/skipped feature acceptance. Release runs all §12 automated checks including captured official comparisons and approved golden; absent fixtures/approval block release.
4. Before activating tax data checks, reconstruct the §4 engine/data/patches and tax build/selftest/reference scripts from genuine inputs as T1 tax-automation prerequisites (not scaffold acceptance). `build-tax.yml`: manual `npm run tax:build` and `npm run tax:test`, deterministic frozen-input no-diff check, changed-data PR. Data automation acceptance stays pending until genuine tax reconstruction; never fake its prerequisites for scaffold closure. Exercise changed-data PR and unchanged-data no-PR paths before automation acceptance.

**Accept (scaffold only):** real smoke/unit/build CI green on merged `main`, branch protections/stage register visible, later gates explicitly pending. Local success is not CI success. No empty suite, `--passWithNoTests`, unconditional success or invented fixtures. Tax automation acceptance is separate once real prerequisites exist; release requires it.

**PR automation contract:** CI has `contents: read`, no secrets for untrusted PRs. Only data-PR jobs get `contents: write`, `pull-requests: write`, repository approval to create PRs, pinned actions, no direct `main` push or auto-merge. Default `GITHUB_TOKEN` uses owner/manual approval for generated-PR CI runs where current policy requires it; verify opened/synchronize/reopened behavior and required checks. Do not assume token-generated events always or never run CI. Unattended checks require owner-authorized least-privilege GitHub App alternative, not unsolicited token setup. A generated PR is not accepted until required CI actually runs/passes.

### T2 — Map data
1. `scripts/map/build.*` reads `swiss-maps@4.7.0` 2026 municipalities/cantons/lakes LV95 shapefiles. Retain integrity and notices; publication rights remain §16-gated.
2. Jointly simplify/quantize shared topology into §6.6 without independently simplifying neighbours. Record actual simplification method/interval and common quantization grid; retain source multipart shapes. The reconstructed default uses LV95 and a quantization grid of 100,000 per axis, subject to size, geometric and visual checks.

**Accept (`npm run map:test`):**
- Exactly one feature for each of the 2,110 tax BFS IDs; subtract `meta.noDataIds` from the complete map ID set and require exact equality to the tax set, not just a count. MultiPolygon supported, all parts retained.
- Exactly extra polygons 2391, 5391, 5394 retained in `gemeinden` and identified by `meta.noDataIds`, grey and labelled "no data"; no unexpected IDs.
- Size §6.6. Test finite coordinates, non-empty polygon/multipolygon rings, closure, nonzero area, proper self-crossings, valid arc references, neighbour orientation, shared arcs and finite rendered paths. Preserve legitimate enclaves/lake boundaries and record known source anomalies. National-scale PNG inspection is not exhaustive sub-metre topology or cadastral certification; no unrequested 1 m² coverage threshold is imposed.
- Attach rendered Switzerland PNG as visual sanity check, supplementary to topology tests.

### T3 — Travel-time data
Depends on T1 scaffold, genuine 2026 tax ID authority and usable map polygons; do not treat an absent reconstruction input as present.
1. `scripts/travel/build.py`: pin Python 3.11, JDK 21 (exact distribution/patch in environment lock), compatible r5py/R5, geopandas/pandas and all dependencies. JDK is explicit, not installed by pip; reread pinned-version compatibility docs. §8 metric fixtures must pass before nationwide run.
2. Freeze/download genuine Swiss GTFS (opentransportdata.swiss / opendata.swiss), Geofabrik Switzerland OSM, BFS STATPOP hectares or recorded fallback, and swiss-maps 2026 polygons; fill §6.7 manifest and validate coverage/ID joins.
3. Implement §8 and write §6.3–6.5.
4. Manual `build-travel.yml` opens PR under T1 permissions. Preflight CPU/RAM/free disk/JDK. Pilot a default batch of 50 sorted workplaces, with manifest-keyed checkpoints; resume only matching inputs/toolchain. Default JVM heap floor(60% available RAM), capped at 9 GiB on a 16 GiB host; leave rest for Python/native/OS. Measure combined peak RAM, heap, temporary/output disk, wall time on pilot **and** full run. Require ≥ 20% RAM/disk headroom and ≤ 5 h on six-hour hosted job; otherwise use owner-approved R3 alternative before full run. Public visibility/checkpoints prove no capacity or time-limit exception. Test unchanged no-PR and changed PR with real CI.
5. `npm run travel:test` wraps pinned Python test runner if needed, exercising §8 tiny metric fixtures and structural/QA checks below on every push/PR once active.
6. **T3 collects initial official SBB references:** all 30 §11.2 named pairs at actual nominated stops/date/window. Store `tests/reference/sbb-pairs.csv` with inputs, source URL/retrieval timestamp, itinerary/evidence hash, departure/arrival seconds, rounding, release ID and outputs in evidence sidecars. Missing official values stay empty/pending; T3 is not complete until manual checks pass. T9 revalidates rather than owning initial collection.

**Accept (scripted):**
- ≥ 95% main-stop coverage; attach no-stop list with reasons.
- Main stops: Zürich → Zürich HB; Bern → Bern; Basel → Basel SBB; Genève → Genève (Cornavin); Lausanne → Lausanne; Luzern → Luzern; Winterthur → Winterthur; St. Gallen → St. Gallen; Lugano → Lugano. Correct via documented overrides.
- Every non-null workplace file exists, contains self 0, unique known home IDs, sorted by minutes/BFS, rows ≤ 60. Null-access workplaces have no required file. Shared-parent zeros/endpoint QA follow §8.
- Apply §8 speed 100/150 km/h review/blocking policy, tolerances and independently evidenced exceptions; never delete suspicious pairs to pass.
- Total `travel/` ≤ 25 MB; each file ≤ 100 KB (decimal); metadata included.
- Deterministic frozen-input rebuild, validated schemas/hashes/release identity; measured resource evidence and no-diff/changed-PR paths.

**Accept (manual):** all 30 pairs have `abs(oursMinutes - sbbMinutes) <= 3`, same exact metric/date/endpoints/ceil rounding, with inspected unrounded durations. If > 60 minutes, retain full routing QA result for reference comparison outside shipped truncated rows. Inaccessible official evidence is pending, never a pass.

### T4 — Tax module
1. `src/tax.ts` loads municipality file once, chosen civil/children profile on demand; cache by §6.7 release ID, validate response/schema/hash/release before use, never mix releases.
2. Implement §7 exactly.

**Accept (Vitest):**
- All §11.1 scenarios plus ≥ 500 on-grid/≥ 300 off-grid cases obey separate §7.1 frontend-to-engine limits: on-grid `max(2, 0.0001 * abs(expected))`, off-grid CHF 10. Execute unrounded engine, not rounded historical cells. Direct frontend-to-ESTV is additionally T9, not implied by regression.
- Exact grid interpolation component error ≤ `1e-9` CHF; boundary clamping below 40,000/above 500,000; correct none/reformed/catholic rate.

### T5 — Filter and ranking
Implement exact §8 filter and §9 sorting/colour groups in `src/filter.ts`.

**Accept (Vitest):**
- Walk toggle membership as formula; null access excluded.
- Workplace travel component 0 is included **iff** access, walk and effective-time constraints all pass. Walk 10/maxWalk 10/maxTime 5: excluded with countWalk on, included off; null workplace never inserted.
- Unrounded ties by minutes, explicit de-CH collation, numeric BFS ID; up to 5 balanced groups with N = 0, 1–4 and non-divisible cases.
- Lower-time result is a subset; empty, all-data-withheld and no-stop states distinct.
- Full failed-canton and withheld-unverified exclusion from tax-derived list, summary/count, groups, detail, rank/delta and workplace baseline; wrong-release/corrupt/absent asset is an error, not no-stop.

### T6 — App UI
Depends on T2/T4/T5; explicitly labelled development travel fixtures allowed until T3 lands, never in release. Feature/stub integration is not T3/T9/golden acceptance.
1. Build §9, reconstructing layout without unavailable prototype/fidelity claims; actual owner UX approval pending.
2. All UI strings in `src/strings.ts`.
3. Record a **real-data integration milestone** once executable UI/modules consume genuine T3 outputs with quarantine status support. T9 depends on this milestone, not full T6/golden acceptance. Finish T9, then owner golden approval and final T6 acceptance; never create a T6↔T9 completion cycle.

**Accept (Playwright, `tests/e2e`):**
- Default: list > 0 on genuine eligible dataset, first row cheapest, map drawn, no console errors; otherwise correct explicit withheld/no-stop states, not fake results.
- **Golden:** Zürich, maxTime 25, maxWalk 10, countWalk off, single, 0 children, 120,000, no church. Only after real T3 and T9 pass/quarantine integration, owner independently reviews actual top 10. Store `tests/e2e/golden-zurich.json` with release ID, scenario, IDs/values and actual owner approval/date. Development-generated snapshot stays pending. Release/results changes require transparent diff/reapproval; tests cannot approve their own output.
- Lower maxTime yields subset, not necessarily strictly fewer. Control effects use named independently established fixtures; no universal married/children/church strict tax-direction assertions. Verify church rate and both walk toggle cases, visible clamp notes.
- Bern workplace gives correct actual Bern-area results; 400 px no horizontal scroll/all controls reachable; keyboard operation of all controls; light/dark themes.
- Null-access selection, all taxes withheld, quarantine detail/workplace baseline, empty results, release mismatch and genuine asset failure distinct and readable.
- Loader checks HTTP status, JSON content type/schema/hash/release. In addition to mocked failure, request genuinely absent `/data/...json?v=...` from production-style server and later Pages preview: HTTP 404, not HTML 200, readable UI handling.
- §9 warm/cold timing and cold compressed budget, no-cookie/no-unapproved-third-party checks including content pages.

### T7 — Content pages
1. `pages/impressum.html`: owner data O5; placeholder blocks launch.
2. `pages/datenschutz.html`: Swiss Data Protection Act, no cookies, Cloudflare hosting, analytics per O6; review not legal certification by this spec.
3. `pages/methode.html`: plain-language §7/§8, assumptions/years, sources/licences/credits §16 and coverage/quarantine limitations.
4. Explicit §5 Vite multi-page inputs; correct footer paths; `site/404.html` and `site/_headers` copied to `dist/`. Test direct URLs and footer navigation against built output; retain required package/data notices.

**Accept:** owner actually approved texts; served links/pages work. Rights/content approval stays pending until evidenced.

### T8 — Deploy (preview infrastructure vs production launch)
Preview setup depends on T1; integrated preview acceptance on T6/T7. Production launch additionally requires genuine T2/T3/T4/T5 outputs, T9, all §13 and actual owner approvals. Preview closure is not launch closure.
1. Owner-authorized Cloudflare Pages project/repo link: `npm run build`, `dist`, production branch `main`, PR previews.
2. Domain O3; analytics O6 defaults unchanged.

**Accept (preview):** HTTPS previews, expected pages/assets, deliberate static 404. If `main` is publicly served during development, unmistakable non-production banner and **no stub/unchecked values exposed as real recommendations**; default suppress recommendation output until launch gates pass.

**Accept (production launch):**
- Required release CI and owner release approval gate the release-bearing merge to `main`. If branch protection cannot enforce human approval, retain non-production state until documented owner authorization. Build green/main deployment alone is not launch; required release-stage check fails on stubs, missing references, unapproved snapshot/content and unresolved rights/policy gates.
- Genuine coherent release on HTTPS production URL; PR previews continue working.
- Live Lighthouse mobile performance/accessibility/best-practices ≥ 90 each (pinned version/default mobile profile, reports/environment recorded); separate §9 warm/cold budgets also pass.
- `site/_headers`: `/data/*` → `Cache-Control: public, max-age=86400, must-revalidate`; root HTML and `/pages/*` → `Cache-Control: no-cache`. Verify actual headers, ETags/conditional 304, JSON types, gzip transfer, genuine missing-asset 404 and §6.7 browser/CDN query-version coherence; configuration alone is not a pass.

### T9 — Official verification and go/no-go
Depends on T3 and the explicitly staged T6 real-data integration milestone, not T6 final golden acceptance. ESTV retrieval may start earlier without claiming T9 completion; T9 evidence then supports final T6/golden approval.
1. Fill genuinely retrieved §11.1 ESTV amounts from official calculator; commit `tests/reference/estv-2026.csv` and §7.1 full input/evidence mapping. Run **shipped frontend directly vs ESTV**; engine-only checks are supplementary.
2. Revalidate T3's existing `tests/reference/sbb-pairs.csv` against integrated release, independently rechecking all 30 same stops/day/window/metric. Changed feed/stops/date require refreshed evidence, not mismatched references.
3. Commit release-linked individual results and per-canton `passed`/`failed`/`unverified` status and reasons in `src/config.ts`. Passed requires all required cases complete/pass; any failure means failed, missing evidence means unverified.

**Accept:**
- Every tax case directly satisfies §7.1 `abs(frontend - ESTV) <= max(5, 0.001 * abs(ESTV))`, **or its entire failed canton is quarantined**. Intended coverage remains all 29 cases/all 26 cantons. Quarantine is a limited-coverage release exception, not completed official validation; missing evidence never passes.
- All 30 travel cases within 3 minutes with real evidence; no unverified travel bypass.
- **Failed cantons fully excluded** by `src/config.ts` from tax recommendations: ranked list, cheapest/comparable count, groups, rank, total/breakdown, deltas including workplace baseline. Geographically selectable, grey/labelled "data under review" until fixed/directly reverified. End-to-end tests cover every consumer.
- **Unverified-canton launch policy is owner-pending:** proposed safe default is identical full withholding, never treating unchecked amounts as passed. Launch blocked until owner expressly approves unverified/limited-coverage policy and release status (or every case is evidenced/passed). VS is suspect/unverified pending evidence, not a fabricated confirmed failure. Technical pass-or-quarantine is not owner launch authorization.

## 11. Reference values

### 11.1 Tax: engine totals (2026, gross employment income, no wealth)

Supplied v1 attributes the "Engine" column to `scripts/tax/reference.ts`; historical rounded values below are preserved verbatim, not rerun or officially verified. "ESTV" is to be filled from https://swisstaxcalculator.estv.admin.ch (T9) with §7.1 evidence. Married = one earner (partner income 0). Empty official cells remain pending, never implicitly zero.

| Gemeinde | Kt | BFS | Civil | Kids | Income | Church | Engine CHF | ESTV CHF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Zürich | ZH | 261 | single | 0 | 120,000 | none | 17,407 | |
| Winterthur | ZH | 230 | married | 2 | 150,000 | reformed | 14,277 | |
| Zug | ZG | 1711 | single | 0 | 120,000 | none | 9,467 | |
| Freienbach | SZ | 1322 | single | 0 | 120,000 | none | 9,270 | |
| Baden | AG | 4021 | married | 0 | 100,000 | catholic | 8,087 | |
| Aarau | AG | 4001 | single | 1 | 80,000 | none | 4,939 | |
| Bern | BE | 351 | single | 0 | 90,000 | reformed | 15,860 | |
| Basel | BS | 2701 | married | 2 | 180,000 | none | 24,336 | |
| Riehen | BS | 2703 | single | 0 | 250,000 | none | 55,739 | |
| Luzern | LU | 1061 | married | 1 | 120,000 | catholic | 10,333 | |
| St. Gallen | SG | 3203 | single | 0 | 70,000 | catholic | 10,144 | |
| Lausanne | VD | 5586 | married | 2 | 140,000 | none | 23,651 | |
| Genève | GE | 6621 | single | 0 | 150,000 | none | 35,726 | |
| Lugano | TI | 5192 | married | 0 | 200,000 | catholic | 36,109 | |
| Fribourg | FR | 2196 | married | 0 | 300,000 | none | 78,815 | |
| Chur | GR | 3901 | single | 3 | 60,000 | reformed | 1,317 | |
| Sion | VS | 6266 | married | 3 | 110,000 | catholic | 23,933 | |
| Neuchâtel | NE | 6458 | single | 0 | 100,000 | none | 19,232 | |
| Schaffhausen | SH | 2939 | married | 0 | 400,000 | reformed | 93,308 | |
| Frauenfeld | TG | 4566 | single | 2 | 95,000 | none | 7,599 | |
| Appenzell | AI | 3101 | single | 0 | 100,000 | catholic | 12,344 | |
| Herisau | AR | 3001 | married | 2 | 120,000 | none | 13,641 | |
| Liestal | BL | 2829 | single | 0 | 100,000 | none | 17,901 | |
| Glarus | GL | 1632 | married | 1 | 90,000 | reformed | 6,130 | |
| Delémont | JU | 6711 | single | 0 | 80,000 | catholic | 12,403 | |
| Stans | NW | 1509 | married | 0 | 160,000 | none | 20,351 | |
| Sarnen | OW | 1407 | single | 0 | 100,000 | none | 13,284 | |
| Solothurn | SO | 2601 | married | 2 | 130,000 | reformed | 13,827 | |
| Altdorf (UR) | UR | 1201 | single | 0 | 75,000 | catholic | 10,892 | |

Check first: **Sion (VS)** looks too high. Kantons- plus Gemeindesteuer come to about CHF 23,600 on a taxable income of CHF 85,324, which is far above what Valais families usually pay. Treat VS as suspect until the ESTV check passes (see R1). Fribourg at CHF 300,000 tests patch 3.

### 11.2 Travel: pairs to check against the SBB timetable

Fastest connection between nominated main stops under §8 on the frozen Tuesday 06:30–08:30 inclusive. T3 initially collects "SBB min" from https://www.sbb.ch with actual stop IDs/date/itinerary evidence; T9 revalidates. Empty SBB/Ours cells stay pending. Preserve all 30 original named pairs; never substitute easier cases.

| # | From | To | SBB min | Ours min |
| --- | --- | --- | --- | --- |
| 1 | Uster | Zürich | | |
| 2 | Winterthur | Zürich | | |
| 3 | Zug | Zürich | | |
| 4 | Freienbach | Zürich | | |
| 5 | Wollerau | Zürich | | |
| 6 | Baden | Zürich | | |
| 7 | Kilchberg (ZH) | Zürich | | |
| 8 | Dübendorf | Zürich | | |
| 9 | Wetzikon (ZH) | Zürich | | |
| 10 | Affoltern am Albis | Zürich | | |
| 11 | Maur (bus) | Zürich | | |
| 12 | Stallikon (bus) | Zürich | | |
| 13 | Baar | Zug | | |
| 14 | Cham | Zug | | |
| 15 | Thun | Bern | | |
| 16 | Köniz | Bern | | |
| 17 | Burgdorf | Bern | | |
| 18 | Fribourg | Bern | | |
| 19 | Liestal | Basel | | |
| 20 | Riehen | Basel | | |
| 21 | Rheinfelden | Basel | | |
| 22 | Kriens | Luzern | | |
| 23 | Sursee | Luzern | | |
| 24 | Morges | Lausanne | | |
| 25 | Vevey | Lausanne | | |
| 26 | Nyon | Genève | | |
| 27 | Carouge (GE) | Genève | | |
| 28 | Gossau (SG) | St. Gallen | | |
| 29 | Bellinzona | Lugano | | |
| 30 | Olten | Aarau | | |

## 12. Testing summary

Stages: **scaffold** (T1 real smoke/build), **data/features** (mandatory as artifacts/tasks land), **release** (all automated rows plus genuine official/manual/owner evidence). The CI-stage register enumerates pending gates/activation milestones. Missing suite/fixture is not passed; final release cannot rely on scaffold-only green.

| Layer | Command / where | Runs in CI | Gate |
| --- | --- | --- | --- |
| Tax tables vs engine | `npm run tax:test` | once genuine inputs land; then every push/PR | ≥ 500 on-grid `max(2, 0.0001 * abs(expected))`; ≥ 300 off-grid CHF 10; §7.1 |
| Map data | `npm run map:test` | from T2; then every push/PR | T2 exact IDs, multipart/topology/size |
| Travel data | `npm run travel:test` | from T3; then every push/PR | T3 scripted/metric/endpoint QA |
| Unit | `npm test` (Vitest) | scaffold smoke, then all active feature checks | T4/T5 §7.1, exact filter/quarantine |
| E2E | `npx playwright test` | scaffold smoke, then T6; approved golden at release | T6, 400 px, actual approval |
| Official tax | ESTV, `tests/reference/estv-2026.csv`; `npm run reference:test` runs shipped module | source collection manual/yearly, captured comparisons mandatory in release CI | Direct frontend→ESTV §7.1/T9, explicit quarantine evidence |
| Official travel | SBB, `tests/reference/sbb-pairs.csv`; `npm run reference:test` | T3 manual source/T9 recheck, captured comparisons mandatory in release CI | All 30, T3/T9 |
| Production | Lighthouse mobile, HTTP/cache/404/CDN probes, §9 timings | build checks in preview, actual live reports at launch | T8/§6.7; no configuration-only pass |

## 13. Launch checklist

- [ ] T1–T9 applicable acceptance complete including T8 launch (not merely preview); all release checks green on `main`, no stubs/pending-as-pass
- [ ] All 29 direct frontend ESTV cases pass, or failed cantons fully excluded with owner-approved limited coverage; unverified policy/status explicitly resolved, never silently waived
- [ ] All 30 SBB pairs pass
- [ ] Owner actually approved current real-release golden Zürich top 10 and reconstructed UX; approval evidence/date committed
- [ ] Impressum, Datenschutz, Methode live and approved
- [ ] Disclaimer and assumptions visible next to the results
- [ ] Exact map/data rights clarified, notices retained and correct credits in footer/Methode including BFS/GEOSTAT; rights/content approval evidenced, not inferred
- [ ] Domain live over https
- [ ] Tested on a real iPhone and Android phone
- [ ] Frozen manifest, exact ID joins, deterministic rebuild, browser/CDN query-version coherence, actual headers and static 404 verified
- [ ] O1–O6 respected, owner-approved assumptions/exceptions and production authorization recorded

## 14. Open decisions (owner)

| ID | Question | Default until decided |
| --- | --- | --- |
| O1 | Married couples: one earner only, or add a second income? Needs a new tax profile dimension. | One earner |
| O2 | Languages: German only, or also French/English? | German UI; all text in `src/strings.ts` so more languages can be added later |
| O3 | Domain name | none (use `*.pages.dev`) |
| O4 | GitHub repo: public or private? Public gets 16 GB runners (needed for T3, see R3); the data is public anyway. | public |
| O5 | Impressum: name, address, email | placeholder, blocks launch |
| O6 | Analytics: none, or a cookie-free tool (which one)? | none |

O1–O6 rows/defaults are unchanged. They do not authorize remote/account creation, domain changes or publication of personal details. Additional owner-dependent proposals in `docs/spec-amendments-v1.1.md`: unverified/limited-coverage release policy; reachable-count wording/selectable no-stop UX; reconstructed UX/golden; official child/deduction mapping; calendar/speed-QA exceptions; paid/external resource alternatives; exact rights and final launch. Safe development defaults do not close these approval gates.

## 15. Risks and known issues

- **R1 Valais suspect.** See §11.1. Historical suspicion is not official proof. T9 fully quarantines failed cantons; unverified policy/release remain owner-pending.
- **R2 Unofficial engine.** It is maintained by a small open-source project and recomputes the ESTV calculator. It already needed two fixes. Every year: re-run all 29 official checks.
- **R3 Resources.** Reviewed standard x64 Linux GitHub specs: private 2 vCPU / 8 GB, public 4 vCPU / 16 GB, 14 GB SSD, six-hour hosted jobs. Recheck current runner/plan docs. Visibility is no capacity proof: T3 requires JDK 21/heap/headroom, measured RAM/temp disk/time pilot and full run. Alternatives remain larger paid runner or suitable local 16 GB+ machine committing real outputs through PR; owner approves paid/external execution, and measured capacity still governs. Never fabricate a result if routing does not fit.
- **R4 GTFS route types.** The Swiss feed uses extended route types. If r5 rejects them, map them to basic GTFS types in a preprocessing step (unverified).
- **R5 Main-stop rule.** Cities with several stations (Zürich HB vs Oerlikon) are reduced to one stop. Accepted for v1; fix individual cases via overrides.
- **R6 Gemeinde mergers on 1 Jan 2027.** Tax/map share exact BFS vintage; GTFS spatial assignment validates those IDs. Timetable year may differ with proved feed/service coverage. Release coherently under §6.7, not by merely changing year labels.
- **R7 Fribourg patch.** Applying the top rate above the table is an assumption. The Fribourg case in §11.1 verifies it.

## 16. Sources and credits (show in footer and Methode page)

- Tax tariffs and Steuerfüsse: ESTV (Eidgenössische Steuerverwaltung), via swisstaxcalculator by devbrains-com (MIT licence).
- Timetable: opentransportdata.swiss / opendata.swiss. Terms require naming the source.
- Footpaths: © OpenStreetMap contributors (ODbL).
- Boundaries: `swiss-maps@4.7.0` README credits **Bundesamt für Statistik (BFS), GEOSTAT**, describes generalized geodata as non-commercial, and separates this from code BSD-3-Clause. Preserve notices/credit; neither swisstopo attribution alone nor package code licence clears data rights. Resolve exact 2026 upstream dataset terms/permitted use before launch. The review's failed BFS URLs/client shell are an evidence gap, not legal clearance or denial. Owner/qualified review remains pending.
- Population: BFS STATPOP. Name the source.

Retain source-specific notices and captured applicable terms for tax, GTFS, OSM, boundaries/population in release evidence. Credits alone are not legal compliance certification; this spec grants no licensing/content approval.

## 17. Yearly maintenance

| When | Do |
| --- | --- |
| December (timetable change) | Run `build-travel.yml` on the new GTFS file; repeat the 30 SBB checks |
| When the new tax-year data is out | Update the vendored data (`importdata <year> --download` in the upstream project), re-apply the patches, run `build-tax.yml`; repeat the 29 ESTV checks; update the tax year in the UI |
| January | Gemeinde mergers: update the map to the new swiss-maps year, then rebuild tax and travel on the same ids |

For every update freeze/hash real inputs, reread version-sensitive docs/rights, validate exact ID joins, rerun numeric/topology/metric gates and official checks, then publish one coherent release. The retained January row means a coordinated BFS-ID vintage update, not a requirement to make the timetable label equal the tax year (§6.7/R6). Release/results changes require transparent golden diff and owner reapproval. No-diff acceptance uses identical frozen inputs/toolchain/code, never a new "current" download.

## 18. Owner-authorized GitHub Pages test preview — 17 Oct 2026

The owner explicitly requested proceeding with a public GitHub repository and GitHub Pages testing after discussing static interactivity and repository-hosted data. This authorizes a **non-commercial, non-production test preview**, not completion of T1–T9, real-data approval, personal-contact publication or a production launch. Cloudflare remains the intended production host; O1–O6 and launch gates remain unchanged.

- Public source repository: `JohnDev13/steuerpendler`. Source tasks use branches/PRs, never agent pushes directly to `main`.
- The current OAuth credential lacks `workflow` scope; GitHub rejected workflow upload. Do not claim CI green. Keep canonical workflow sources in the local source artifact; publish the test using locally built `dist/` on `gh-pages` and branch-based Pages. This is a documented least-privilege fallback, not permission to broaden credentials.
- `PAGES_BASE=/steuerpendler/` selects a project-prefix build. Root `/` remains the default for Cloudflare. JSON fetches, navigation and content URLs respect the selected base; e2e runs against an actual static production build under that prefix, with genuine missing-asset 404s.
- Keep the preview unmistakeably labelled. No fictional transit data is shipped. All unverified tax cantons are withheld from recommendations, totals/breakdowns, ranks, deltas and tax colours. Showing the loaded **input profile** is not showing a tax estimate or granting launch-policy approval.
- Actual reconstructed tax regression is 500/500 on-grid cases passing their individual limits, but **119/300 off-grid cases failing CHF 10** (max CHF 46.792). This must remain a failing gate; no threshold, interpolation rule or fixture is weakened. All 29 historical engine scenarios reproduce, not official ESTV checks. Full reports are committed in `docs/tax/`.
- The actual tiny r5py diagnostic fails exact metric conformance, so T3/nationwide routing remains blocked. A negative preflight and passing diagnostic-unit tests are not a finished travel generator or SBB acceptance.
- Public non-commercial map testing is supported by the current official BFS/STAC linked attributed-use terms. Preserve author, dataset title/link, adaptation notice, exact package notices and the conservative terms link. `docs/map/publication-assessment.md` records live sources and the STAC/geocat commercial-permission discrepancy; commercial/production rights are not cleared by this preview.
- Draft legal pages remain drafts and O5 still blocks production. Datenschutz names GitHub Pages as the preview host and its documented IP logging. Host-generated metadata/logging is distinguished from client-side tax calculation.
- GitHub Pages does not apply Cloudflare `_headers`. Cloudflare cache/header/CDN coherence, production Lighthouse, real-phone checks and all owner approvals remain pending. Live HTTPS/asset/header and browser probes must verify the preview before a successful-deployment claim.
