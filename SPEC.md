# Steuerpendler — Build Spec v1.4

Active scope clarification: 17 Oct 2026 (§19). Workplace destinations are narrowed; all 2,110 residential/tax Gemeinden and all 26 cantons remain in scope. The v1.3 source is preserved byte-for-byte at `docs/source/SPEC-v1.3-2026-10-22.md`; §20 describes the existing narrow Aarau preview and §21 records the owner's all-routes requirement. Earlier v1.2/v1.1 versions remain in `docs/source/`.

Amended: 22 Oct 2026 (UTC), v1.4 all-routes clarification · Owner: John · Tax year: 2026
Supplied v1 stated status: 17 Oct 2026 (source metadata, not verified chronology).

**Reconstruction status:** The original implementation/commit is unrecovered; this repository contains a new reconstruction, not the lost implementation. The original `docs/prototype.html` remains unavailable. Historical v1 statements were not implementation, official-reference, licence or launch certifications; the current narrow preview in §20 is separate. Source lineage and F01–F15 mapping: `docs/spec-amendments-v1.1.md`.

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
- Workplace: the selected 19 German-speaking cantonal capitals/government seats only. Residential/tax candidates remain all 2,110 Swiss Gemeinden in all 26 cantons.
- Commute filter: max first-board-to-arrival transit time, max external walk to a served stop/station entrance, and a toggle that counts the walk inside the time cap.
- Tax profile: gross income, single or married, 0–3+ children, church (none, reformed, catholic).
- Results: ranked list, Switzerland map coloured by tax, and a breakdown per Gemeinde.
- Real 2026 tax data and the real Swiss timetable.
- Hosted on Cloudflare Pages, rebuilt from GitHub.

**Not in v1:** rent, health insurance premiums, wealth tax, two-earner couples (see O1), address-level door-to-door routing, user accounts, saved searches, ads or payments. §8's representative residential point is an indicative Gemeinde proxy, not an address lookup.

## 3. Decisions already made (do not revisit)

| Topic | Decision |
| --- | --- |
| Hosting | Cloudflare Pages, deployed from the GitHub repo. Static files only. |
| Data | Precomputed once a year and committed to the repo as JSON. All filtering and tax maths run in the browser. |
| Tax source | ESTV 2026 tariffs and Steuerfüsse via the vendored open-source engine `swisstaxcalculator` (MIT), with three documented patches. |
| Travel source | Swiss GTFS timetable (opentransportdata.swiss) + OpenStreetMap footpaths. The conditional exact-event fallback of §8 replaces the r5py/R5 timetable path where that path cannot prove the required exact metric; pedestrian access still requires verified OSM routing. |
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

Schema v2 (current): `meta.schemaVersion: 2` adds a `precision` object with one declarative program per canton (deductions, tariff tables, splitting, personal tax). The complete contract is `docs/tax/schema-v2.md`. Grid rows stay authoritative at exact grid incomes; the program is evaluated between them.

### 6.2 Gemeinden: `site/data/gemeinden-2026.json` (reconstruct)

```json
{ "meta": {...}, "gemeinden": { "261": ["Zürich", "ZH", 95, 119, 10, 10], ... 2110 entries } }
```

Columns: name, canton, rateCanton, rateGemeinde, rateReformed, rateCatholic. Rates are % of `base`.

### 6.3 Travel metadata: `site/data/travel/meta.json` (task T3)

Target travel schema **v2** records `schemaVersion:2`, the frozen GTFS and OSM filenames/hashes, STATPOP/map vintages, approved `referenceDate`, `timezone:"Europe/Zurich"`, inclusive first-board window `06:30:00–08:30:00`, seconds-to-minute rounding rules, build-code revision and source/override hashes. It also has `targetGroups`, keyed by every selected workplace BFS, each a verified set of qualifying GTFS terminal stop IDs or `null` for explicit no-target-access. An option's destination ID must belong to its workplace's target group. The old illustrative 2027 date is **not** an approved reference day. The committed v1 frontend/data interfaces remain deliberately unavailable until every v2 consumer and validation gate is migrated together; never mix v1 access arrays with v2 route options in a release.

### 6.4 Access: `site/data/travel/access.json` (target schema v2)

Every one of the 2,110 tax BFS IDs has an object with `placeLabel` (municipal/civic label with source if not just the Gemeinde name), `referenceStop` (`[stopId,stopName]` or `null` for display), `centreLV95` (`[E,N,source]`, `source=statpop|polygon-fallback`), and `candidates` (zero or more `[parentStopId,stopName,externalWalkSeconds]`). Candidate IDs are actual GTFS parent/stop IDs, with their station entrances and routed OSM external walks independently evidenced. The local reference stop is **not** a mandatory first-boarding stop; a nearby hub in another Gemeinde can be a candidate. An empty `candidates` list is a legitimate selectable no-access state, not a missing/corrupt asset. Sort candidates deterministically by walk seconds then stable ID; never invent a walk or station membership. The source provenance records candidate rejection reasons. The reference place (e.g. civic Rathaus), population centre and GTFS stop are distinct concepts and coordinates.

### 6.5 Travel alternatives per workplace: `site/data/travel/to/<bfs>.json` (target schema v2)

Each available destination file has `schemaVersion:2`, `to:<workplaceBfs>` and `rows`, one row per residential BFS with at least one valid option. A row is `[homeBfs, options]`; each option is `[externalWalkSeconds, transitSeconds, originParentId, destinationParentId, firstBoardSeconds, arrivalSeconds]` with integers for times on the frozen local service day. `originParentId` must occur among the home's verified access candidates and `destinationParentId` in the workplace's verified `targetGroups`. Keep the exact nondominated walk/transit frontier for that home/destination within maximum supported external walk (15 minutes after ceiling) and transit (30 minutes after ceiling), sorted by stable numeric/time/ID keys. Record full dated trip/transfer/OSM path evidence in source-backed audit artifacts keyed to the option; no option may be supplied by an unverified default. No row means no *proved* permitted transit itinerary only when the workplace file's full search/coverage gate has passed; otherwise withhold the entire file/availability. A workplace with no verified target stop group has no `to/` file and an explicit no-target-access state.

The self-home/workplace option alone has transit seconds 0 by definition, but still requires an evidenced residential→target-hub access walk and obeys the walk/combined-time filters; a different-Gemeinde pure walk is not a transit option. Distinct GTFS bus and rail parents in one hub are **not** automatically zero-time endpoints; use actual terminal membership and directed transfer rules. The old single `[homeBfs,minutes]` rows and one access walk per BFS cannot represent the user's walk-versus-bus choice. Publishing v2 requires migration/tests of `src/filter.ts`, loaders/detail UI, travel primitives and manifest/release hashing together. Until then `site/data/manifest.json` truthfully keeps travel unavailable.

### 6.5a Canonical first-boarding Route artifact (owner amendment, 2026-10-21)

`docs/travel/canonical-route-v1-20261021.md` and `docs/travel/canonical-route-v1.schema.json` define one versioned authoritative stop-event→workplace route-time dataset, `data/travel/canonical-routes-v1-20261027.ndjson.gz`. For every eligible first-boarding event and each of the 19 workplace destinations, record exactly one proof status; include an evidenced dated itinerary for `fastest_proven` or `best_found_unproven`, reserving the claim **fastest** for the former. Keep exact elapsed seconds and derived ceiling minutes; retain legs and directed transfer evidence. Derive any public workplace/Gemeinde views from this file only. A positive best-found but non-optimality-proven result may be labelled indicative; an unresolved case cannot become a negative exclusion. This contract is a **new internal data schema** and does not silently turn the existing v1 `site/data/travel` files into v2. The owner's interim external residential access assumption is zero *unmeasured* seconds, not the measured OSM walk promised by §6.4 for a validated v2 release; keep the UI walking control separate and visibly identify its provisional mode. Publishing actual source-backed indicative results must not await another owner walk/date/SBB sign-off, but no missing or fabricated route rows may be released.

### 6.5b Aarau observed-direct preview (temporary, owner amendment 2026-10-22)

Before the **complete** §6.5a file exists, a separately labelled Aarau-only positive preview may be derived from the hash-pinned partial direct-route diagnostic (`routeSha256:5f9c6c8648f87ff88cf0c1dc4f158d471a6e55f57ed28cd53e649940d1d4b89e`), not described as a complete canonical file or global optimum. Its derived `site/data/travel/aarau-direct-observed-20261027.json` has SHA-256 `311420191be00d7f8b6d96f81f1e8295f801a26e34deb6d49ad5ec2e7f78b988` and uses the frozen 2026 Gemeinde polygons, a 100 m boundary quarantine and the owner-approved 2026-10-27 service day. The 59 observed stop-locality rows within 30 minutes include 36 within **exactly ≤1,200 seconds**; these are positive direct-trip observations at stops in polygons, **not proven residential access**. Unlisted Gemeinden remain unknown, not excluded. The release builder inventories the copy, while `availability.travel` and independent SBB/ESTV approvals remain false. The browser must verify release bytes and source/map/Gemeinde hashes, display unmeasured zero external access, label tax estimates as non-advisory, preserve the VS quarantine, and leave the other 18 workplace travel views pending. This limited exception does not alter the eventual single-source-of-truth Route v1 file, v2/OSM/full coverage, T9, or production gates. See §20 and `docs/spec-amendments-v1.3.md` for supersession and drift.

### 6.5c Experimental travel matrix: `site/data/travel/matrix/` (not an accepted authority)

`scripts/travel/run_matrix.py` is a candidate standard-library Connection Scan over a GTFS feed, not a replacement for the pinned §6.5a first-event×19 route authority. It has not been validated on a real national feed. Its origin-stop coverage, frequency trips, transfer precedence and walking approximations require independent checks before any new public route claim.

- `meta.json`: `schema:"steuerpendler.travel-matrix.v1"`, `serviceDate`, `firstBoardWindow:["06:30:00","08:30:00"]`, `capSeconds:1800`, `absence:"unknown_unobserved"`, model assumptions and ignored-source inventories, `feed:{url,sha256,bytes}`, `codeRevision`, `workplaces:{<bfs>:{station,targetStops,rows,directRows}}`.
- `to/<workplaceBfs>.json`: `{schema,to,station,serviceDate,rows,directRows}`. All-route and independently scanned direct-only rows each use `[homeBfs, transitSeconds, transfers, firstBoardStopName, firstBoardSeconds]`, sorted by seconds then BFS; the direct-only subset has zero changes, and the workplace row is `[bfs,0,0,"",0]`.
- Missing Gemeinde/destination rows are **unknown**, not unreachable. The frontend must not prefer this experimental matrix over the observed-positive preview while `availability.travel` is false. Enabling it requires source and projection audits, exact inclusive window/cap checks, independent direct-route validation, and a release decision. The owner's unmeasured zero external access remains explicitly provisional.

Display minutes may be rounded up, but comparisons and the 30-minute limit retain exact seconds. An SBB sample within ±3 displayed minutes is a diagnostic, not proof of source completeness, global fastest routing, or a waiver of the first-event §6.5a contract. No independent SBB or ESTV approval is asserted.

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

## 7. Tax rules

Inputs: workplace-independent profile `(civ, kids, income, church)` and Gemeinde `g`. Income is clamped to CHF 40,000–500,000 with a visible note.

**Evaluation (schema v2, `src/tax.ts`).** At an exact grid income the serialized row is used. Between grid incomes the canton's precision program is evaluated exactly: gross → net, deductions, taxable income floored to CHF 100 as the tariffs require, splitting, tariff table. Linear interpolation of tax amounts is **not** permitted: the CHF 100 floor makes tax a staircase in income (steps of CHF 13–57 about every CHF 105), and a line between CHF 1,000 rows misses it by up to CHF 47, which violates §7.1. Schema-v1 profiles keep the legacy interpolation only for backwards compatibility.

```
kanton   = round_half_even(base × g.rateCanton / 100)
gemeinde = round_half_even(base × g.rateGemeinde / 100)
kirche   = round_half_even(base × rateCh / 100)        (rateCh per person for married, 2 dp, as the engine)
total    = bund + kanton + gemeinde + kirche + personal
```

Fixed assumptions, shown on the page: gross employment income, age 35, no wealth, married couples have one income, and ESTV's 2026 standard defaults (age-35 BVG pension deduction, standard household budget/estimated rent; evidence in `docs/tax/bvg-rule-evidence.md` and `docs/tax/estv-budget-defaults.md`). The page states: „Dies ist eine indikative Schätzung mit ESTV-Standardannahmen, keine individuelle oder verbindliche Steuerveranlagung und keine Steuerberatung.“

Display totals rounded to CHF 10; ranking and gates use unrounded values.

### 7.1 Numeric verification gates (inclusive; unrounded CHF)

For each case `error = abs(actual - expected)`; percentages use `abs(expected)`, not actual. Every case must independently pass; averages/maxima cannot hide failures. Compare before display rounding; at expected zero the absolute floor applies. These are fixed requirements, not permission to loosen tolerances or alter references:

| Gate | Actual / expected | Coverage | Required limit |
| --- | --- | --- | --- |
| On-grid regression | Reconstructed tables and `src/tax.ts`, each independently vs full engine | ≥ 500 deterministic on-grid cases; all 26 cantons, 8 profiles, 3 church options represented; endpoints and §11.1 scenarios | `error <= max(2, 0.0001 * abs(expected))` |
| Off-grid regression | Reconstructed tables and `src/tax.ts`, each independently vs full engine | ≥ 300 deterministic between-grid cases; all 26 cantons and 8 profiles, near tariff/deduction transitions | `error <= 10` |
| Official end-to-end | Shipped `src/tax.ts` directly vs independently retrieved ESTV | All 29 §11.1 scenarios, same frozen release and exact inputs | `error <= max(5, 0.001 * abs(expected))` |

Store seed, exact inputs and individual errors. §11.1 historical rounded engine cells are lineage, not substitutes for unrounded engine execution. At an exact grid point interpolation reproduces components to absolute error ≤ `1e-9` CHF. Intermediate tolerances cannot establish the direct official gate. Fix discrepancies or report failed gates; do not relax limits to make CI green.

Official CSV/evidence must record tax year, BFS/canton, gross income, age 35, civil/household status, partner income 0, child ages/treatment, church, no wealth, employment/deduction settings and actual ESTV input mapping/calculation steps from gross income. Proposed child-age default where unspecified: 10 years for each child; owner confirmation of comparability and deduction selections is pending before official acceptance. Record source URL/retrieval time, official result at available precision, evidence/hash, engine/frontend values, release ID and pass/fail. Never fill official gaps from the engine. Prioritize suspect VS and FR top-step checks without declaring either officially wrong/passed here.

## 8. Travel-time rules (target hub/access contract; pilot before release)

This amendment replaces a single compulsory origin stop with route alternatives while keeping **all 2,110 residential Gemeinden** and only the 19 selected workplace capitals. Decision/rationale and drift record: `docs/travel/hub-access-contract-20261020.md`. A validated full-coverage release still requires the new schema, frontend and source-backed search to pass together; the owner-directed **indicative** mode below may publish honestly labelled computed positives sooner, never invented negatives.

**Owner decision, 21 October 2026:** the selectable first-board-to-arrival public-transport cap is now at most **30 minutes for every one of the 19 workplaces**, initially evaluated with Aarau. The existing external walk control remains independent at 0–15 minutes; its optional count-walk toggle still applies. Do not drop a Gemeinde merely because a direct-only or nominated-stop route is longer than 30 minutes: an eligible alternate stop, walk-accessible cross-border hub or valid transfer may still qualify. Transit-only screens may mark proven journeys as candidates, but absence from an incomplete screen is **unknown**, not outside the cap. A full evidenced residential-access and complete-route search remains necessary before publishing Gemeinde eligibility.

**Subsequent owner-directed indicative mode, 21 October 2026:** 2026-10-27 is owner-approved as the reference service date; this approval is not a claim that all 26 cantonal holiday calendars were independently checked. External residence→entrance access is assumed negligible/zero for now, explicitly labelled unmeasured; no entrance→platform penalty. The owner accepts the SBB material they reviewed without another approval request; do not relabel it as a newly completed independent comparison. Search each event→destination pair for the fastest feasible route and store its proof status in the separate canonical file defined in §6.5a; publish honest computed estimates rather than withhold them for another generic owner sign-off. The existing §6.4/§8 measured-walk and independent conformance requirements continue to apply to a *validated* full-coverage release, not to this explicitly labelled approximation. Tax, release integrity and negative-exclusion completeness remain independent gates.

- **Reference day:** freeze a GTFS-covered Tuesday. Interpret "earliest" as the first eligible service Tuesday **on or after the later of the frozen feed's publication/version date and its recorded acquisition date**; historical dates inside a feed's advertised coverage are not acceptable. Check dates in Europe/Zurich and exclude national/cantonal public holidays and compulsory-school holidays in all 26 cantons (all published regional/local calendars where applicable). Record the feed's source/version/acquisition dates, calendar URLs, retrieval dates, holiday exclusions, and dated active-service evidence. If no such date exists, require owner-approved documented exception before T3 acceptance; never silently weaken the rule. The provisional 2026-11-17 pilot and old illustrative 2027 metadata are **not** approved feed/date selections.
- **Reference place and main stop (display, not mandatory boarding):** use a sourced civic label if one is intentionally nominated (e.g. Niederlenz Rathaus) and keep its coordinates distinct from any timetable stop. Prefer a service-active **rail** parent inside the Gemeinde as the local main stop, ranking multiple rail parents by dated 06:00–09:00 boardable rail departures, then OSM/geodesic proximity to the representative point, then stable ID. Where none exists, choose the service-active **local bus/tram** stop nearest to the sourced civic point (or STATPOP centre if no civic point is sourced), then dated boardable departure count, then stable ID. A town without a usable local stop may have `referenceStop:null` yet still access a nearby hub by walking. Record sourced override `bfs,stop_id,reason` and input hashes; never derive a DIDOK/UIC from arbitrary SLOID arithmetic without an authoritative mapping. The one-stop 06:00–09:00 highest-departures nomination is no longer a compulsory origin endpoint.
- **Representative origin:** population-weighted point from BFS STATPOP inhabited hectares spatially joined to the 2026 municipality polygon; if unavailable, polygon representative point with a recorded fallback. This is **indicative municipality-level access, not an address-level promise**. Test near/far inhabited cells separately in the pilot to reveal sensitivity without replacing national Gemeinde coverage or attributing their results to the entire municipality.
- **Origin access and hub choice:** enumerate served local stops plus out-of-Gemeinde rail/interchange hubs accessible from the representative point on the frozen OSM **pedestrian network**. Walk externally to the stop or station **entrance** at 1.2 m/s, obeying access/barriers. Do **not** add entrance-to-platform distance/time or a generic platform-finding penalty. Compute seconds and ceil minutes for controls; retain candidates whose ceiled external walk ≤15 minutes, including equality. A straight line, fixed detour multiplier, network snap across an unverified barrier, or public API estimate is not an accepted route. Record unusable/no-path cases instead of inventing zero.
- **Station complexes and interchanges:** a verified complex may label physically co-located bus and rail parents (Lenzburg/Aarau) while preserving their distinct GTFS stop IDs. A direct walk to the rail station can first-board rail; a local bus first-board must arrive at its actual bus stop and obey applicable **directed** `transfers.txt` minimum/forbidden/timed, route/trip/service-specific interchange rules before boarding rail. Transfer walking constraints and subsequent waiting count within first-board→destination transit elapsed time. The documented Lenzburg bus→rail generic minimum in the selected feed is 240 seconds; it is not an extra pre-board platform walk. Never infer a zero transfer from a shared name or nearby coordinate. Destination is the verified workplace capital's main station complex: terminal membership must be evidenced; there is no arbitrary uncounted alternate-stop egress.
- **Transit metric and route selection:** enumerate exact scheduled first-board events in inclusive `[06:30:00,08:30:00]` Europe/Zurich on the approved service day. For each feasible route record separate external access-walk seconds and elapsed seconds from **first vehicle boarding** to arrival at an eligible destination terminal. Include seconds, all in-trip legs, transfer walks and waits; exclude pre-first-board waiting at home and external walk from the *transit* component. No different-Gemeinde pure-walk, car/bicycle access, unsupported approximate timepoint or invented fixed departure for `frequencies.exact_times=0`. Respect pickup/drop-off and service exceptions. Find the exact nondominated `(walkSeconds,transitSeconds)` frontier per home/destination; keep evidence for each option. Among **currently eligible** options prefer the minimum exact active time `(walkSeconds+transitSeconds)`, then transitSeconds, walkSeconds, earliest first-board and stable IDs. Only self-workplace rows have defined zero-transit without a vehicle; access still applies. Ceil each component to minutes for filtering and display; never relabel percentile/sampled or restricted-template results as an exact global optimum. Drop options above the supported 15-minute external walk or 30-minute transit bounds only after coverage has been proved.
- **Conformance before nationwide routing:** the pinned r5py/R5 path did not prove exact seconds over all events. A deterministic GTFS event/connection fallback is conditionally approved for timetable search while R5/OSM may be used for **verified** pedestrian access, subject to architecture review and a source-complete implementation. Use explicit synthetic boundary fixtures for first-board edges and seconds, rare fast vs frequent slower service, a direct walk to rail vs bus→rail, access cap/equality, minimum/forbidden transfer, pickup/drop-off, near hub across municipality border, no service, same-parent/self and `exact_times=0`. Test one complete real Aarau pilot with independent endpoint/leg checks and source/version hashes before any national compute. Fail closed when affected service classes or pedestrian paths cannot be established; do not quietly select the most convenient observed itinerary.

Frontend filter (authoritative per workplace/home option, including workplace):

```
eligible(o) = accessCandidate(o) is verified
           && ceil(o.walkSeconds/60) <= maxWalk
           && ceil(o.transitSeconds/60) <= maxTime
           && (!countWalk || ceil(o.walkSeconds/60)+ceil(o.transitSeconds/60) <= maxTime)
reachable(g) = any eligible(o) in to[workplace].rows[g]
selected(g) = argmin eligible(o) by (o.walkSeconds+o.transitSeconds,
              o.transitSeconds,o.walkSeconds,o.firstBoardSeconds,stableIds)
```

With `countWalk` off, the transit cap and walk cap remain **separate**; the active-time comparator does not silently combine them into one threshold. Tax eligibility is a separate later restriction (§9); no workplace/self exemption is allowed.

**Geographic QA:** use each selected option's actual boarded-origin and destination-terminal coordinates, not municipality centroids or the display reference stop. Only the expressly defined self row may have zero transit without a vehicle; all other zero-time rows require exact same physical endpoint and documented service semantics or are errors. For positive-minute rows retain conservative `v = 60 * max(0, d - 0.1) / (minutes + 1)` km/h with 100 m coordinate and one minute rounding tolerance; `v > 100` requires review evidence, `v > 150` blocks acceptance without an exact pair/service/feed-scoped independently evidenced owner-approved exception. Verify the heuristic against the Aarau pilot; it is not a universal service speed bound.

## 9. UI spec

The original prototype is unavailable. Reconstruct layout/interactions from this section without claiming fidelity; owner UX review remains pending. If recovered later, the prototype guides UX only, never numeric expectations.

**Controls**

| Control | Range | Default |
| --- | --- | --- |
| Workplace | search box over the 19 supported German-speaking cantonal capitals, accent-insensitive | Zürich |
| Max travel time | 5–30 min, step 1 | 25 |
| Max external walk to stop/station entrance | 0–15 min, step 1 | 10 |
| Count the walk in the travel time | toggle | off |
| Gross income | slider CHF 40,000–500,000, step 1,000, plus a number field | 120,000 |
| Civil status | single / married | single |
| Children | 0 / 1 / 2 / 3+ | 0 |
| Church | none / reformed / catholic | none |

**Results**
- **Summary:** "N reachable Gemeinden with comparable tax data" and the cheapest eligible total. Separately label "M reachable Gemeinden: data under review"; never count withheld places as recommendations.
- **Ranked list:** rank, name, canton, travel minutes, walk minutes, CHF/year and difference to workplace. Sort by unrounded total, travel minutes, name using `Intl.Collator('de-CH', {sensitivity: 'base', numeric: true})`, then numeric BFS ID. Deltas use an eligible workplace tax baseline independently of workplace travel reachability; otherwise "comparison unavailable".
- **Map:** Switzerland, tax-eligible reachable Gemeinden in up to 5 equal-count green-to-red groups, others grey with accessible distinct labels for out of reach, no data and data under review. For N > 0, k = min(5, N); contiguous rank-ordered groups have floor(N/k) members, with one extra in the first N mod k groups; N = 0 gives no groups. Use unrounded ranking. Number eligible top 10, mark workplace, zoom to eligible reachable area with padding; empty/no-stop keeps Switzerland overview. Clicking any geographic area selects its detail.
- **Detail:** Bundes-, Kantons-, Gemeinde-, Kirchen-, Personalsteuer; Gemeinde rate %, local reference stop **and selected route's actual first-boarding stop**, transit/access-walk times and rank. Label representative-location estimates as indicative, not address-specific. Tax-eligible unreachable places still show detail labelled "out of reach". Quarantined/withheld-unverified places remain geographically selectable but expose **no total, breakdown, tax rank, cheapest status, delta or colour-group membership**; show "data under review". Extra map IDs show "no data" and never join as Gemeinden.
- **Empty travel result:** "No Gemeinde in reach. Allow more time or walking."
- **No-target workplace:** all Gemeinden remain searchable/selectable, including empty access-candidate lists. Use the explicit target-group status before fetching `to/`; show "No verified destination stop for this workplace", no travel results/ranked recommendations, with map/detail still available. Do not fetch a known-absent file or fabricate a self-row. A missing/corrupt file for a verified target is an error, never a no-target state.
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
1. `scripts/travel/build.py`: pin Python 3.11, JDK 21 (exact distribution/patch in environment lock) and compatible r5py/R5 for paths that still use them, geopandas/pandas and actual exact-event search dependencies. JDK is explicit, not installed by pip; reread pinned-version compatibility docs. §8 metric fixtures must pass before nationwide run; unused timetable libraries are not claimed as the exact router.
2. Freeze/download genuine Swiss GTFS (opentransportdata.swiss / opendata.swiss), Geofabrik Switzerland OSM, BFS STATPOP hectares or recorded fallback, and swiss-maps 2026 polygons; fill §6.7 manifest and validate coverage/ID joins.
3. Implement §8 and write §6.3–6.5.
4. Manual `build-travel.yml` opens PR under T1 permissions. Preflight CPU/RAM/free disk/JDK. Pilot a default batch of 50 sorted workplaces, with manifest-keyed checkpoints; resume only matching inputs/toolchain. Default JVM heap floor(60% available RAM), capped at 9 GiB on a 16 GiB host; leave rest for Python/native/OS. Measure combined peak RAM, heap, temporary/output disk, wall time on pilot **and** full run. Require ≥ 20% RAM/disk headroom and ≤ 5 h on six-hour hosted job; otherwise use owner-approved R3 alternative before full run. Public visibility/checkpoints prove no capacity or time-limit exception. Test unchanged no-PR and changed PR with real CI.
5. `npm run travel:test` wraps pinned Python test runner if needed, exercising §8 tiny metric fixtures and structural/QA checks below on every push/PR once active.
6. **T3 collects initial official SBB references:** all 30 §11.2 named pairs at the selected representative points, actual candidate boarding stops, destination terminals, date and first-board window. Store `tests/reference/sbb-pairs.csv` with inputs, source URL/retrieval timestamp, itinerary/evidence hash, departure/arrival seconds, walk/transit components, rounding, release ID and outputs in evidence sidecars. The historical pair labels do not identify a unique residential point or boarding stop. Missing official values stay empty/pending; T3 is not complete until manual checks pass. T9 revalidates rather than owning initial collection.

**Accept (scripted):**
- ≥ 95% verified candidate-access coverage from representative origins; separately report local-reference-stop coverage and no-access reasons, without using the reference as compulsory boarding.
- Main stops: Zürich → Zürich HB; Bern → Bern; Basel → Basel SBB; Genève → Genève (Cornavin); Lausanne → Lausanne; Luzern → Luzern; Winterthur → Winterthur; St. Gallen → St. Gallen; Lugano → Lugano. Correct via documented overrides.
- Every verified-target workplace has a schema-v2 file with unique known home IDs, exact nondominated options sorted by stable key and within §6.5 bounds; its self row has a zero-transit option **only if** verified access permits one. A no-target workplace has no required file; an ordinary empty/no-service search is distinct. Distinct co-located bus/rail parents cannot manufacture shared-parent zeros; endpoint QA follows §8.
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
- Walk toggle membership against each evidenced route alternative; empty access candidates excluded from transit results. With walking excluded from the time cap, walking still influences the least-active-time **route selection**.
- Workplace zero-transit self option is included **iff** access, walk and effective-time constraints all pass. Walk 10/maxWalk 10/maxTime 5: excluded with countWalk on, included off; no-target workplace never inserted. A shorter-walk/slower-transit option can become eligible when sliders tighten after a longer-walk/faster option was previously selected.
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
- Empty access-candidate/no-target selection, all taxes withheld, quarantine detail/workplace baseline, empty results, release mismatch and genuine asset failure distinct and readable.
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
- **R5 Reference-stop versus actual access.** One display reference/main stop per Gemeinde remains useful for orientation, but is not the compulsory first-board location. The §8 alternatives must include verified local stops and walkable cross-border hubs. The target v2 asset can exceed the unchanged 25 MB total/100 KB per-workplace budgets (§10/T3); measure compression on real pilot-scaled data and block release rather than truncate the nondominated frontier to satisfy size.
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
- Historical v0.1 authorization status: the then-current OAuth credential lacked `workflow` scope and GitHub rejected upload. The 17 Oct 2026 refresh is recorded in §19 and `docs/ci-stages.md`; do not treat the original restriction as permanent. Actual source-CI upload/run evidence is required before any CI-success claim. Branch-based `gh-pages` remains the authorized non-production deployment path, not production approval.
- `PAGES_BASE=/steuerpendler/` selects a project-prefix build. Root `/` remains the default for Cloudflare. JSON fetches, navigation and content URLs respect the selected base; e2e runs against an actual static production build under that prefix, with genuine missing-asset 404s.
- Keep the preview unmistakeably labelled. No fictional transit data is shipped. All unverified tax cantons are withheld from recommendations, totals/breakdowns, ranks, deltas and tax colours. Showing the loaded **input profile** is not showing a tax estimate or granting launch-policy approval.
- Actual reconstructed tax regression is 500/500 on-grid cases passing their individual limits, but **119/300 off-grid cases failing CHF 10** (max CHF 46.792). This must remain a failing gate; no threshold, interpolation rule or fixture is weakened. All 29 historical engine scenarios reproduce, not official ESTV checks. Full reports are committed in `docs/tax/`.
- The actual tiny r5py diagnostic fails exact metric conformance, so T3/nationwide routing remains blocked. A negative preflight and passing diagnostic-unit tests are not a finished travel generator or SBB acceptance.
- Public non-commercial map testing is supported by the current official BFS/STAC linked attributed-use terms. Preserve author, dataset title/link, adaptation notice, exact package notices and the conservative terms link. `docs/map/publication-assessment.md` records live sources and the STAC/geocat commercial-permission discrepancy; commercial/production rights are not cleared by this preview.
- Draft legal pages remain drafts and O5 still blocks production. Datenschutz names GitHub Pages as the preview host and its documented IP logging. Host-generated metadata/logging is distinguished from client-side tax calculation.
- GitHub Pages does not apply Cloudflare `_headers`. Cloudflare cache/header/CDN coherence, production Lighthouse, real-phone checks and all owner approvals remain pending. Live HTTPS/asset/header and browser probes must verify the preview before a successful-deployment claim.

## 19. Owner clarification: destinations only; all residential Gemeinden; map navigation — 17 Oct 2026

This section supersedes only the earlier workplace-selection/destination-count and map-navigation requirements. It does not reduce tax, residential, canton, origin-access, official-reference or map coverage. Full change/lineage register: `docs/spec-amendments-v1.2.md`; previous source: `docs/source/SPEC-v1.1-2026-10-17.md`.

- Workplace destinations are the 19 German-speaking cantonal capitals/government seats in `src/destinations.ts`, validated against the complete 2026 municipality authority. Bern and Chur are included; Herisau represents AR's government seat. Do not equate this selection with officially monolingual cantons.
- Residential/tax candidates remain ALL 2,110 Gemeinden across ALL 26 cantons, including non-capitals, neighbouring cantons and non-German-speaking municipalities. The workplace subset must never replace the municipality authority passed to taxes, ranking, map, residential lookup or access processing.
- The travel matrix is all candidate origins → supported capital destinations. Generate at most those 19 destination files (one for each with usable access), retaining every qualifying origin under §8. A capital-to-capital matrix is insufficient. For this scope the destination pilot has at most 19 workplaces, not 50; resource/metric and input-validation gates remain unchanged.
- Aarau example: destination BFS 4001; transit limit 20 minutes and origin-station walking limit 15 minutes, independently applied with countWalk off. With countWalk on, walking additionally counts within the transit budget. Use real timetable and pedestrian-route reachability, not a circle or capital-to-capital radius. Existing main-stop, origin-centre, transfer and transport-mode rules are unchanged.
- Workplace search is capital-only. A separate residential search covers all Gemeinden and changes the selected detail, never the workplace. Map selection also remains municipality-wide.
- The SVG map supports explicit zoom in/out/reset controls, wheel zoom, drag pan, two-finger pinch and keyboard zoom/reset. User navigation survives municipality selection and control/data updates. Reset restores the national overview. The former automatic-fit behavior must not overwrite a manually chosen viewport.
- The narrower destination list is a versioned release input. Preserve all tax files and map IDs. Tests must assert 19 workplaces, 2,110 residences, non-capital/cross-canton selection and separate time/walk controls.
- A report of newly granted GitHub permissions is not proof of a refreshed credential or successful source CI. Recheck the effective credential and actual workflow upload/run; never mark a pending/failing accuracy stage passed. Non-commercial preview publication remains authorized under §18, not production launch.
- All numerical, direct official, travel, content and owner launch gates remain in force. Until they pass, the preview continues to withhold unverified tax recommendations. Scope/navigation acceptance is not a working all-origin timetable/tax acceptance claim.

## 20. Narrow owner-approved non-production preview — 22 Oct 2026

The owner directed publication of **indicative** tax-first Aarau results rather than withholding them pending another walk/date/SBB sign-off. For this preview **only**, the §18–19 blanket withholding of all unverified tax estimates is superseded for the positive stop-localities evidenced under §6.5b, except quarantined/known-failed cantons (currently VS). Annual tax, selected-workplace difference and transit minutes can appear with a conspicuous non-advisory warning; the lowest amount is lowest **among observed positives**, not a proven cheapest reachable residence. Other 18 workplaces retain the pending state. At Aarau, missing/longer routes and unlisted Gemeinden remain unknown; no residential, transfer-complete, fastest or negative-reachability claim follows. The walking control remains separate: external residence→entrance access is assumed zero *unmeasured*, and there is no entrance→platform walk. No independent ESTV/SBB approval flag or T9/full-travel release gate changes. Public release remains the existing non-commercial GitHub Pages **test preview**, never the Cloudflare production launch; versioned source/bytes, attribution and site verification must accompany it.

## 21. Owner clarification: all journeys within the selected time, with optional direct filter — 22 Oct 2026

The default travel leaderboard must consider **all evidenced feasible public-transport journeys** within the selected first-boarding→workplace-arrival time limit: nonstop/direct services, services with intermediate stops, and journeys with one, two, three **or more** changes. Neither stop count nor transfer count is an eligibility cap. Search all relevant dated departures and transfer paths under §6.5a; do not replace an exhaustive search with a direct-only or same-station-only candidate stream. Compare exact elapsed seconds against the selected time limit *inclusive*, then apply presentation rounding. The separate external-walk control and the approved zero-*unmeasured* access approximation remain unchanged. Do not add an entrance→platform walk; count actual interchange minima and waiting inside the boarding→arrival elapsed time. Retain all 2,110 residential Gemeinden and the 19 selected workplace destinations.

An optional **Direct only** control may restrict displayed, evidenced results to itineraries without a vehicle change; a direct vehicle may itself call at intermediate stops. Its default is **off**. It must not be a prerequisite for finding a Gemeinde and must never make partial direct-only data appear to be a complete all-routes search. Switching the control must recompute reachability and tax-first ranking from real route evidence without converting unsearched alternatives into negative claims. Route evidence records legs, transfer count and stop endpoints; where exact intermediate-stop counts are exposed in the UI, derive them from the dated itinerary rather than conflating them with transfers. An unresolved faster route may keep an evidenced feasible journey provisional, never “fastest proven.”

**Staufen regression:** On the approved 2026-10-27 timetable, a source-backed 06:47 Staufen, Lindenplatz bus reaches Lenzburg, Bahnhof at 06:53; a directed type-2 transfer requires 240 seconds, while the 06:58 train departure allows 300 seconds, arriving Aarau 07:05. The observed 1,080-second journey qualifies for Aarau/20 and the boarding stop is inside Staufen beyond the 100 m boundary quarantine. This proves a feasible positive, *not* an exhaustive fastest time or measured access from every home. The current 36-row direct-only Aarau preview omits it and must not be described as the requested all-routes leaderboard. Tests for the eventual all-routes release must include this two-leg positive, a direct-only exclusion of the same itinerary, seconds-boundary cases, journeys with at least two and three transfers, and a qualifying itinerary with more than three changes so no hidden transfer cap slips in. Source audit: `docs/travel/staufen-transfer-regression-20261022.md` (portable identifiers and source hashes; the local scratch audit is not a second numerical authority).

This clarification changes the **target product**, not the accuracy or publication status of the existing preview. No national all-19 route file or transfer-complete release is claimed by this amendment. Do not publish invented times, classify absent municipalities as over-limit from a partial search, silently flip `availability.travel` or independent approval flags, or assume unapproved paid national compute. Lineage: `docs/spec-amendments-v1.4.md`.
