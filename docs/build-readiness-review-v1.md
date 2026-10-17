# Steuerpendler — Build-readiness review v1

**Prepared for:** John  
**Reviewed:** 16 October 2026 (UTC)  
**Status:** Review and proposed amendments; not an approved replacement spec  
**Source:** `SPEC.md`, Build Spec v1; stated status 17 October 2026; tax year 2026  
**Source SHA-256:** `1e42772fc4062d47c6b538e0c38a55ebd90257fe17a7f2d887251a856bde39d4`

## Verdict

**Keep the architecture and chosen stack. Amend the acceptance and data-release contracts before treating the spec as an executable delivery agreement.** The static-site approach is not the problem. The main risks are building the wrong travel-time metric, validating the engine rather than the shipped calculation, and allowing production to precede independent verification.

Work can begin on scaffolding and isolated modules once their gates are clarified. A nationwide routing run should wait for a small metric-conformance experiment. Public launch must wait for real-data verification, complete quarantine behavior, licence clarification, and the owner's existing approval gates.

### Scope and evidence

- Read the complete supplied spec. Section and line references below refer to that exact source version.
- Checked r5py, Vite, Cloudflare Pages and GitHub documentation directly, and inspected the published `swiss-maps@4.7.0` archive after verifying its registry SHA-1.
- Ran three **synthetic logical counterexamples**, not Swiss tax or timetable reference cases.
- Did **not** inspect the existing application repository, execute its tax engine, obtain official ESTV/SBB values, approve the golden snapshot, or validate legal compliance. Statements about existing code remain claims in the spec, not verified implementation findings.
- Settled hosting, frontend, map and routing technologies are not reopened. O1–O6 retain their specified defaults; recommendations below require amendments, not unilateral decisions.

**Severity:** High = blocks a named implementation/validation/release milestone; Medium = should be resolved in the relevant task, without blocking all parallel work.

## Findings and proposed amendments

### F01 — T1 needs an explicit, honest CI bootstrap stage

**High — delivery sequencing.** References: §0 L8, T1 L224–230, T6 L285–298, §12 L406–417.

**Observation:** T1 must run Vitest, a production build and Playwright and be green on `main`, while the real application and its acceptance scenarios arrive later. T1's command list also omits `map:test` and `travel:test`, which §12 says run in CI.

**Impact:** An agent can either block on features outside T1, or produce misleading green CI through absent/skipped suites. T3 depends on T1, making this a critical-path ambiguity.

**Proposed amendment:** Define T1 as a working Vite/TypeScript scaffold with real smoke tests, lockfile, browser installation and an exercised production build. Keep feature acceptance distinct from scaffold acceptance. Add map/travel validation as explicit required checks when those artifacts land; thereafter run them on every push/PR. Document which gates are pending rather than reporting them as passed. Do not accept empty placeholder tests as evidence of feature completion.

Also clarify how the existing initial commit is published while preserving §0's no-direct-`main`-push rule—for example, an owner-created remote baseline followed by a T1 branch and PR.

### F02 — T3 and T9 contain a completion dependency cycle

**High — travel acceptance.** References: §0 L8, T3 L243–261, T9 L319–326.

**Observation:** T3 is done only when its manual 30-pair SBB checks pass. T9 depends on T3 and is tasked with obtaining the SBB reference values.

**Impact:** Strict task-level completion cannot follow the stated order.

**Options:**
1. Obtain and store the SBB fixtures during T3, then have T9 revalidate the integrated release against them.
2. Make T3's completion gate scripted/structural, with independent SBB acceptance belonging solely to T9.

**Recommendation:** Option 1. It catches a wrong routing metric before UI integration. This brings manual reference work forward but leaves the final go/no-go in T9. Define T9's travel step as release revalidation, not first fixture creation.

### F03 — T8 can publish before real travel data and official verification

**High — production launch.** References: T6 L286, T8 L307–317, T9 L319–327, §13 L419–429.

**Observation:** T6 permits travel stubs. T8 depends on T1, T6 and T7, but not T3 or T9. Pages deploys `main` by design.

**Impact:** The task graph permits a publicly served, production-designated site with development travel data or unchecked taxes. The launch checklist catches this conceptually, but does not prevent deployment.

**Proposed amendment:** Distinguish **preview/infrastructure deployment** from **production launch**. Permit previews early; make production launch require real T3 outputs, T9 pass-or-quarantine evidence, the approved real-data Zürich snapshot, and approved T7 content. If `main` is publicly served during development, show an explicit non-production state and do not expose stubs as real results. CI and branch protection must gate the release-bearing merge, not merely a successful Vite build.

### F04 — The specified r5py percentile is not a proven fastest-connection metric

**High — routing semantics; resolve before a nationwide run.** References: §8 L167–172, T3 L244–261, §11.2 L369–404.

**Observation:** The spec correctly asks implementers to check equivalence, but proposes `percentiles=[1]` for a minimum with no wait at the first stop. r5py documents minute-by-minute travel-time sampling followed by a percentile; its tutorial explicitly includes the effect of waiting for the next service. A first percentile is not, by definition, an exact minimum. The documented API also permits access and egress walks, which can change the station-to-station meaning. [S1–S3]

**Impact:** A plausible-looking matrix could use a different metric from the one checked on SBB. Removing all waiting would also be wrong: transfer waiting must remain.

**Proposed amendment:** Before scaling T3, require a small deterministic fixture network proving that the chosen r5py/R5 method returns the minimum **elapsed time from first boarding at the nominated origin station to arrival at the nominated destination station**, for departures in the agreed window. Preserve transfer waiting and transfer walks; exclude only waiting before first boarding. If the parent-station/platform treatment adds walking, define and test it explicitly.

Conformance cases should cover a rare fast service, a frequent slower service, non-zero-second departures, a connection requiring a transfer, shared parent stations, and both edges of 06:30–08:30. Specify timezone (`Europe/Zurich`), endpoint inclusion, minute rounding, allowable modes, whether entirely walking connections count, and whether arbitrary access/egress to other stops is forbidden. Inspect itineraries, not only aggregate percentiles. Keep r5py; do not silently substitute a different metric.

The reference Tuesday and GTFS coverage must be verified, not copied from the illustrative 2027 metadata. Define which holiday calendars the “not a school-holiday week” rule must satisfy.

### F05 — Tax verification must test the shipped calculation with explicit numeric gates

**High — tax correctness evidence.** References: §4 L57, §7 L150–163, T4 L268–272, T9 L321–325, §11.1 L331–367, §12 L410.

**Observation:** There are three distinct comparisons: tables→engine, frontend→engine, and official ESTV verification. They have different thresholds. “CHF 2 / 0.01%” does not define AND/OR, the percentage denominator or rounding. The reported CHF 5.19 maximum alone is insufficient to establish whether that gate passes. The official table contains engine totals, whereas T4 permits frontend errors up to CHF 10.

**Impact:** An engine can pass the official comparison while an allowed frontend discrepancy makes the shipped calculator fail it. Display rounding can further obscure the comparison.

**Proposed amendment:** Name each gate and express it as a formula. Preserve separate regression and official-source checks. For T9, compare **unrounded totals from `src/tax.ts` directly to the ESTV reference**, with `abs(actual − expected) <= max(5, abs(expected) × 0.001)`. Round only for presentation. Define what happens at zero official liability. Specify on-grid and between-grid coverage independently; do not loosen any tolerance just to obtain green CI.

Record a reproducible ESTV input mapping: tax year, Gemeinde, age and household settings, child assumptions, partner income, church, wealth and the actual deduction/input choices that make the gross-income scenario comparable. Store retrieval date and source evidence with the CSV. A total alone is not a reproducible tax scenario. Give the currently suspect VS case and FR top-step case early attention without declaring either officially wrong before verification.

**Executed proof:** Synthetic values 1,000 / 1,005 / 1,015 for official / engine / frontend pass the engine→official and frontend→engine thresholds, but fail the direct frontend→official threshold. These numbers are deliberately artificial and are not reference data.

### F06 — Canton quarantine needs functional semantics, not just grey polygons

**High — launch safety.** References: §9 L201–208, T5 L274–283, T9 L324–327, §13 L422.

**Observation:** T9 says a failing canton is “hidden” and greyed out, but does not specify its presence in rankings, cheapest summaries, colour groups, detail amounts or workplace deltas. Its “every case passes” criterion also conflicts with the checklist's accepted alternative of hiding failing cantons.

**Impact:** Incorrect taxes could still appear as the cheapest result even when map styling looks safe.

**Proposed amendment:** Make acceptance explicitly **pass or quarantine**. A failing canton remains selectable geographically but is excluded from tax-derived recommendations and equal-count colour groups; it exposes no misleading tax total or breakdown. Detail text says “data under review.” If the workplace is quarantined, tax-difference comparisons are unavailable. Define whether the displayed reachable count includes quarantined places or only places with comparable tax data, and label accordingly. Distinguish this state from out-of-reach and from the map's three no-data areas.

Add tests proving quarantine is applied consistently across list, summary, map, detail and workplace baseline. In the release evidence, distinguish failed, not-yet-verified and passed cases. The handling of **unverified** cantons before launch needs explicit owner agreement; do not imply unchecked data passed.

### F07 — A valid workplace can have no travel file

**High — travel/frontend contract.** References: scope L27, §6.4 L127, §6.5 L135, §9 L191, T3 L255, T6 L298.

**Observation:** Any Gemeinde is selectable. The data contract intentionally creates a workplace file only if a main stop exists; T3 accepts less than universal coverage.

**Impact:** A legitimate selection can trigger the generic missing-file error instead of a meaningful product state. This is not evidence of a broken deployment.

**Proposed amendment:** Check `access.json` before fetching a workplace file. Define an explicit “No usable main stop for this workplace” state, distinct from “No Gemeinde in reach” and a missing/corrupt asset. Specify whether such workplaces remain selectable with an explanation or are disabled with a reason. In either case, preserve the all-Gemeinden search requirement honestly rather than fabricating travel results.

### F08 — The workplace-inclusion test contradicts the exact filter

**High — executable acceptance contradiction.** References: §8 L176–180, §9 L192–194, T5 L280.

**Observation:** T5 says the workplace is always included when its walk filter allows it. Under §8, with count-walk on, the workplace must also fit within max travel time, even though its travel component is zero.

**Executed counterexample:** Workplace walk 10, max walk 10, max time 5, count-walk on. The walk filter passes; `0 + 10 <= 5` is false. All inputs are within the specified UI ranges.

**Proposed amendment:** Keep §8 as the exact implementation rule and change the T5 wording to “The workplace has a zero travel component and is included iff it satisfies access, walk, and effective-total-time constraints.” Test both toggle states. Do not create an undocumented workplace exception.

### F09 — Map attribution and permitted use are unresolved at the pinned version

**High — publication/licensing; does not block local module work.** References: §3 L44, T2 L233, §16 L457.

**Observation:** The spec credits swisstopo via `swiss-maps`. The actual pinned package README identifies the generalized geodata as BFS/GEOSTAT, calls the geodata licence non-commercial, and requires attribution to “Bundesamt für Statistik (BFS), GEOSTAT.” The package code itself is BSD-3-Clause; that does not settle the geodata rights. The included BSD licence also has notice-retention requirements. [S4]

**Impact:** The footer's planned attribution is not sufficient evidence of correct licensing. Although v1 has no payments or ads, non-commercial use cannot simply be presumed from that alone, including possible future reuse.

**Proposed amendment:** Record the applicable upstream dataset licence/terms for the exact 2026 source, retain package notices as required, and put the correct credit in the footer and Methode page. Resolve the apparent distinction between the package README and current upstream terms before publication. This is a rights clarification, not a recommendation to change map technology.

**Retrieval limitation:** The package's linked English BFS dataset page and an alternate German dataset URL returned HTTP 404. A BFS terms page returned only a title/client-rendered shell, not usable licence terms. Consequently, this review establishes what the package says, **not a definitive legal conclusion about upstream permissions**.

### F10 — Geographic speed QA needs defined endpoints and zero-time cases

**Medium — travel test validity.** References: §8 L168, T3 L257–258.

**Observation:** The distance used by the 100/150 km/h tests is unspecified. Different Gemeinden can share a main stop through the fallback rule and consequently have a zero station-to-station time despite distinct population centres.

**Impact:** A centroid-distance check could reject valid rows. The speed thresholds are plausibility heuristics, not independently verified physical limits for every Swiss service.

**Proposed amendment:** Use the nominated main-stop endpoints for this QA, explicitly handle same-station zero-time rows and the forced workplace self-row, and define tolerance for coordinate and minute rounding. Do not silently delete suspicious pairs to make tests pass. Require review evidence for genuine exceptions, and independently verify that the chosen hard threshold does not reject valid services.

**Executed proof:** A synthetic pair sharing a station has zero station separation and zero travel time, while a municipal-centre separation of 1 km would incorrectly fail the stated 150 km/h bound if used as the distance.

### F11 — Reproducible rebuilds and cache-coherent releases need a dataset identity

**High — data release integrity.** References: §6 L91–144, T1 L228–230, §15 R6 L449, §17 L462–466, T8 L317.

**Observation:** Travel metadata stores a filename and build date, but no input checksums, source vintages or toolchain identity. “Current timetable” and changing download URLs are not reproducible input identifiers. The map and tax use 2026 BFS IDs while the travel example uses a 2027 timetable. T8 requires browser-cacheable data at stable URLs.

**Impact:** Unchanged code can rebuild different results; ID drift can break joins; a browser can temporarily combine cached old JSON with newly deployed assets. A new build timestamp can create a diff even when underlying data is unchanged, depending on implementation.

**Proposed amendment:** Add a small versioned data manifest recording input URLs and checksums, GTFS coverage, chosen service day, OSM snapshot, STATPOP vintage or fallback, municipality-ID vintage, overrides hash, package/R5 versions and build-code revision. Make the rebuild no-diff check use frozen identical inputs and distinguish substantive data from volatile build metadata.

Keep tax and map IDs consistent, and explicitly map/check GTFS spatial assignments into that municipality vintage. A timetable label need not equal the tax year; **the joins must be validated**, not coerced by changing a year string.

Choose a static cache-coherence scheme: preferably a content-derived release identity in data URLs while retaining the relative filenames in §6, or a documented versioned query-key approach with verified browser/CDN behavior. Declare this interface amendment in the same PR as the spec update. No backend is needed.

### F12 — Map acceptance needs a feature/topology definition

**Medium — map contract.** References: §6.6 L139–144, T2 L236–240.

**Observation:** §6.6 says “one feature per polygon”; T2 requires exactly one feature per BFS ID. A Gemeinde can have multiple geographic parts. The three additional IDs must be retained, but their placement/classification is not explicit. A PNG alone cannot prove topological correctness.

**Proposed amendment:** Specify one geometry/feature per BFS ID, with `MultiPolygon` permitted. Keep the extra IDs in an explicitly documented no-tax-data class or object. Use the tax dataset's exact ID set as the join authority rather than relying only on counts. Simplify/quantize shared topology jointly; add scripted validity and shared-boundary checks at the selected tolerance, preserving legitimate enclaves and lake boundaries. Keep the PNG as a visual sanity check.

**Verified, not a blocker:** `swiss-maps@4.7.0` really includes 2026 municipality/canton/lake shapefiles. The municipality PRJ declares EPSG:2056 (LV95). The municipality DBF and bundled TopoJSON have 2,113 records/geometries, including 2391, 5391 and 5394; the bundled topology has 26 canton geometries. This confirms packaging/count assumptions, **not exact agreement with the uninspected tax ID file**. [S4]

### F13 — Static build paths, content pages and missing-data behavior need explicit wiring

**Medium — build/deployment integration.** References: §5 L73–85, T7 L300–305, T8 L309–317, T6 L298.

**Observation:** Vite copies the **contents** of `publicDir` into the output root. Setting it to `site/data` would produce `dist/tax-…json`, not `dist/data/tax-…json`. Pages under the repository's `pages/` directory also need explicit build inputs or copying. Cloudflare documents SPA fallback when no top-level `404.html` exists, potentially returning HTML for a nonexistent JSON URL. Its default documented cache header does not satisfy the requested one-day policy. [S5–S7]

**Proposed amendment:** Specify `publicDir: 'site'` for the stated layout, or an equivalent tested copying rule. Explicitly build/copy the legal/method pages and test their served paths. Put `_headers` where it reaches `dist/`; a proposed `/data/*` value is `Cache-Control: public, max-age=86400, must-revalidate`, paired with F11's coherent data-version strategy. Verify actual headers after deployment, including ETag/revalidation.

Add a deliberate static 404 policy and validate HTTP status, content type and JSON shape in the loader. Test a genuinely absent data asset against the production-style server, not just an intercepted mocked 404. Assert the required pages and `dist/data/*` files exist after `npm run build`.

### F14 — T3 execution environment and automated-PR CI behavior are incomplete

**Medium — automation readiness.** References: T1 L228, T3 L244–251, §15 R3 L446.

**Observation:** Python package pins alone do not describe r5py's JVM dependency or bound the native/Java memory and temporary disk footprint. The retrieved stable r5py documentation requires JDK 21+; `pip install r5py` does not install it. GitHub's published standard x64 Linux runner specs match the spec's public/private RAM claims, but also list 14 GB SSD and a six-hour hosted-job limit. None establishes that the Swiss run fits. [S8–S10]

**Proposed amendment:** Pin Python, Java and routing-engine versions alongside Python dependencies; set Java heap with headroom for Python/native memory; measure peak RAM, disk and elapsed time on a representative pilot and then the intended full run. Define batching/checkpointing and use one of R3's already allowed execution alternatives if necessary. Do not describe “public repo” as proof of sufficient capacity.

For PR-opening workflows, specify minimal token permissions, repository approval settings and how required CI runs are started. **Current retrieved GitHub docs differ from older blanket advice:** `GITHUB_TOKEN`-created/updated PR events of the documented opened/synchronize/reopened types can create approval-required workflow runs; most other token-generated events do not start runs. Either document the manual approval step or use the documented App/token alternative when unattended checks are required. Do not hard-code the stale claim that such PRs can never trigger CI. Exercise both the changed-data PR path and the unchanged-data no-PR/no-diff path. [S11]

### F15 — Performance and golden-snapshot acceptance need measurable conditions

**Medium — frontend acceptance.** References: §9 L212–220, T4 L265, T6 L291–298, §13 L424, §17.

**Observation:** “Any control change <100 ms” includes controls that fetch uncached on-demand files; no network conditions are specified. Lowering a discrete travel threshold need not strictly reduce the result count. Married/children/church effects should be asserted for defined scenarios rather than assumed universally. A stubs-based golden snapshot would not validate real Zürich results.

**Proposed amendment:** Define warm-cache computation/render latency separately from cold fetch/loading behavior, identify a target device or reproducible throttling profile, and measure the full list-and-map update. Define whether 1 MB is decimal or binary and which first-render requests count. Add a cold-load transfer-budget test, no-third-party/no-cookie checks, theme tests and visible clamp-note tests.

Use fixed test scenarios with known changes; for generic lower-time tests require a non-increasing set, not always strictly fewer rows. Rank and form colour groups using unrounded totals, then format money. Define name collation and empty/small quantile behavior. Approve the golden snapshot only after real travel data and the quarantine policy are integrated; bind it to a data release so yearly changes require a transparent reapproval. German remains the default, with all strings in `src/strings.ts`.

## Recommended amendment order and delivery sequence

1. **Before T1 sign-off:** resolve F01 and the release distinction in F03. Preserve branch-per-task and owner-controlled repository creation.
2. **Before accepting tax/filter modules:** resolve F05–F08. Implement tests directly against the chosen contracts rather than deriving expectations from the implementation under test.
3. **Before a nationwide T3 run:** resolve F02, prove F04 on small fixtures, define F10–F11, and measure F14's resource envelope. Independent SBB references come from the actual nominated stops, service day and departure window.
4. **During T2/T6 integration:** resolve F12–F13 and performance conditions in F15. T2/T4/T5 can proceed in parallel after their contract clarifications; T6 may use explicitly labelled development fixtures.
5. **Before public launch:** resolve F09, finish real-data ESTV/SBB verification, exercise quarantine end to end, approve the real-data golden snapshot and T7 texts, and pass the existing T8/§13 gates. Previews are not evidence of production approval.

These are amendments to the existing task definitions, not a new task framework or permission to bypass owner approvals.

## Owner decisions and unresolved evidence

| Item | Owner / timing | Recommendation or required confirmation |
|---|---|---|
| CI bootstrap and production-vs-preview distinction | John, before T1 closure | Approve explicit staged gates; do not imply later feature acceptance is complete. |
| SBB reference ownership | John, before T3 closure | Obtain fixtures during T3; use T9 for integrated revalidation. |
| Tax tolerances and unverified-canton treatment | John, before tax release acceptance | Approve explicit formulas, direct browser→ESTV verification, and a documented launch policy. No reference amounts were filled by this review. |
| No-main-stop workplace behavior and reachable-count wording | John, before T6 acceptance | Confirm the user-visible states; preserve exact §8 filtering. |
| Map dataset rights/credits | John or a qualified reviewer, before publication | Resolve exact upstream terms and preserve required notices. Package README evidence alone is not legal clearance. |
| Resource feasibility | T3 implementer, before nationwide run acceptance | Return measured full-run resource/output evidence; estimates are not passes. |
| Existing O1–O6 | John, at their existing gates | Defaults unchanged. O5 remains an explicit launch blocker; no personal details were invented. |

## Sources and documentation-drift traceability

All sources were retrieved on **2026-10-16 UTC**. Live documentation is evidence as retrieved, not a promise about a future build. Before implementation, reread version-sensitive API, runner, token-event and hosting behavior against the chosen pinned toolchain. Raw retrieved pages, extracted text and per-source metadata/checksums are retained beside this review in `sources/` and `source-manifest.json`.

- **[S0] Supplied Build Spec v1.** Owner-provided primary requirements. Hash at the top fixes the reviewed version. The stated status date is one day after the review's system date; it is retained as supplied rather than interpreted as independently verified chronology.
- **[S1] r5py API reference — RegionalTask/TravelTimeMatrix.** Project primary docs. Percentile, departure window, access/egress and walking settings: https://r5py.readthedocs.io/stable/reference/reference.html
- **[S2] r5py travel-time matrices tutorial.** Project primary docs; “A note about transit travel times and travel time windows” explains initial-wait effects and percentile aggregation: https://r5py.readthedocs.io/stable/user-guide/user-manual/travel-time-matrices.html
- **[S3] r5py detailed itineraries.** Project primary docs; segment travel/wait fields: https://r5py.readthedocs.io/stable/user-guide/user-manual/detailed-itineraries.html
- **[S4] swiss-maps 4.7.0 npm release and actual archive.** Primary release artifacts: https://registry.npmjs.org/swiss-maps/4.7.0 and https://registry.npmjs.org/swiss-maps/-/swiss-maps-4.7.0.tgz . Inspected `package/README.md`, `package/LICENSE`, 2026 DBF/PRJ and bundled topology. Archive SHA-1 matched registry value `a32e30afd8231a56c39cd76ff714ab60f12a006f`. The linked BFS dataset URL failed; the attempted terms page exposed no substantive terms.
- **[S5] Vite static asset handling.** Project primary docs; public-directory contents are copied to the output root: https://vite.dev/guide/assets.html
- **[S6] Cloudflare Pages custom headers.** Provider primary docs; `_headers` deployment mechanism: https://developers.cloudflare.com/pages/configuration/headers/
- **[S7] Cloudflare Pages serving behavior.** Provider primary docs; SPA fallback, cache defaults, ETag and compression: https://developers.cloudflare.com/pages/configuration/serving-pages/
- **[S8] r5py installation.** Project primary docs; JDK 21+ requirement in retrieved stable documentation: https://r5py.readthedocs.io/stable/user-guide/installation/installation.html
- **[S9] GitHub-hosted runners.** Provider primary docs; standard public/private x64 Linux CPU/RAM and SSD specifications: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- **[S10] GitHub Actions limits.** Provider primary docs; hosted-job six-hour limit: https://docs.github.com/en/actions/reference/limits
- **[S11] GitHub workflow triggering.** Provider primary docs; token-generated event behavior and approval-required PR runs: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow

### Verification record

- All reviewed-source references map to the supplied 466-line file; source hash is recorded above.
- Package integrity and actual contents were checked, not inferred from a package name.
- `check_contracts.py` completed with **3 synthetic counterexamples verified**. Its JSON output explicitly marks the values as synthetic, not Swiss references.
- No source spec, application repository, external account or deployment was modified.
- This review is complete as a **readiness assessment**. It does not mark T1–T9, official reference checks, licences, owner approvals or production readiness as passed.
