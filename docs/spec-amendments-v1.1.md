# Steuerpendler — Spec amendments v1.1

**Amended:** 2026-10-16 UTC
**Canonical requirements:** `../SPEC.md`, Build Spec v1.1
**Scope:** documentation-only implementation-contract amendments for F01–F15; not implementation, official verification, legal clearance or owner approval.

## 1. Source lineage and status

| Source | Identity / evidence boundary |
| --- | --- |
| Supplied Build Spec v1 | SHA-256 `1e42772fc4062d47c6b538e0c38a55ebd90257fe17a7f2d887251a856bde39d4`; exact original available as `git show 42761e7:SPEC.md`. This 64-hex value is the supplied document checksum, **not** a recovered implementation commit. |
| Local reconstruction baseline | Commit `42761e7` (`docs: establish supplied spec and reconstruction baseline`); requirements/review/agent instructions, not the lost application. No remote was configured at amendment inspection. |
| Build-readiness review v1 | `build-readiness-review-v1.md`; SHA-256 `76ddaedbfa2e9e0af8024a388dae1e57ad81bc8487c5cb142c7cef7134feafa6`; reviewed 2026-10-16 UTC; original source references remain tied to v1, not shifted v1.1 line numbers. |
| Canonical amended spec | `../SPEC.md` v1.1; SHA-256 `05b8c095bb59b4094161ebc263ca21604172c7910e85e3c208efd90511e7b089` at this amendment. Future edits require a new traceability entry/checksum rather than retaining this identity for changed bytes. |
| Real engine upstream | https://github.com/devbrains-com/swisstaxcalculator ; read-only `git ls-remote ... HEAD` on 2026-10-16 returned `43064402b1e52dbbc34dded6a305d7d536737c73`. This verifies a live upstream locator/revision observation only, not its 2026 data, licences, patches or an approved reconstruction snapshot. |
| Original implementation/prototype | Original implementation/commit remains **unrecovered**; original `docs/prototype.html` unavailable. User authorized reconstruction from genuine upstream, not invention or a claim of recovered/pixel-identical implementation. |

The supplied v1 says **17 October 2026**, one day after the actual amendment/review date **16 October 2026 UTC**. Preserve this as supplied metadata; do not infer that the original implementation or approvals existed on either date. Historical tax totals and reported error maxima are preserved as claims, not freshly executed results.

The architecture remains static Cloudflare Pages + GitHub, Vite/TypeScript vanilla DOM, Vitest/Playwright, vendored swisstaxcalculator/ESTV, r5py/R5 with Swiss GTFS/OSM/STATPOP, and swiss-maps 4.7.0/d3-geo/topojson-client. No backend/database/accounts/cookies/tracking, extra tax dimensions or substitute map/routing provider was introduced. O1–O6 defaults and owner authority are unchanged.

## 2. Finding-to-contract map

Section references below address **v1.1**. All findings have contract amendments; none is thereby claimed implemented or validated in production.

| Finding | Amended canonical sections | Binding amendment / remaining evidence |
| --- | --- | --- |
| F01 — honest CI bootstrap | §0; §10 T1; §12 | Real scaffold interaction/build/browser smoke gate; pending feature gates declared, activated tax/map/travel checks run on every push/PR; no empty/skipped-as-pass suites. Owner baseline remote and branch/PR publication. Tax automation separately requires genuine reconstruction and changed/no-change paths. |
| F02 — T3/T9 cycle | §10 T3/T9; §11.2; §12 | T3 collects all 30 genuine SBB fixtures and passes initial manual checks; T9 revalidates the integrated release. No missing official fixture is a pass. |
| F03 — premature deployment | §5; §10 T6/T8/T9; §13 | Preview/infrastructure separate from production launch. Real-data T6 integration is an explicit milestone before T9, with final golden/T6 approval afterward (no new completion cycle). Release merge/launch gates require genuine travel, official pass/quarantine evidence, actual owner approvals and no stubs. Development main suppresses recommendations and displays non-production notice. |
| F04 — routing metric | §8; §10 T3; §11.2 | Exact minimum first-boarding-to-arrival, not percentile assumption; retain transfers/waits/walks, exclude initial wait/access/egress, define modes/platforms/seconds/window/timezone/ceil. Tiny-feed itinerary conformance before nationwide run; GTFS/date/calendar evidence pending. |
| F05 — numeric gates | §4; §7.1; §10 T4/T9; §11.1; §12 | Inclusive per-case unrounded on-grid `max(2, 0.0001 * abs(expected))`, off-grid CHF 10; direct shipped frontend-to-ESTV `max(5, 0.001 * abs(expected))`. Full input/evidence mapping and zero handling; no tolerance relaxation or rounded engine-cell substitution. |
| F06 — functional quarantine | §9; §10 T5/T6/T9; §13–15 | Failed cantons fully excluded from every tax-derived recommendation/count/group/detail/rank/delta including workplace baseline, not merely greyed. Separate failed/unverified/passed states; proposed unverified withholding and limited-coverage launch approval remain owner-pending. |
| F07 — legitimate no-stop state | §6.4–6.5; §9; §10 T3/T5/T6 | Keep all Gemeinden selectable; inspect null access before fetching a known-absent file. Dedicated no-main-stop explanation, distinct from empty reachability, withheld data and asset errors. |
| F08 — self-row filter | §6.5; §8; §10 T5 | Zero travel component does not waive access/walk/effective-time constraints. Explicit walk 10 / maxWalk 10 / maxTime 5 on/off counterexample. |
| F09 — exact package rights | §10 T2/T7/T8; §13; §16 | Credit BFS/GEOSTAT, preserve package BSD notices, distinguish code and geodata/non-commercial statements. Exact upstream 2026 rights unresolved; no legal clearance inferred from package or this spec. |
| F10 — speed QA endpoints | §8; §10 T3 | Nominated parent-station coordinates, not municipal centres; self/shared-parent zero semantics. Explicit 100 m/one-minute tolerance, 100 km/h review and 150 km/h blocking rule with independently evidenced owner-approved exceptions; no silent pair deletion. |
| F11 — identity and coherence | §5; §6.7; §10 T1/T3/T4/T8; §13; §15 R6; §17 | Frozen inputs/hash/toolchain/vintage manifest; deterministic no-diff; schema/release validation. Versioned `?v=<releaseId>` on every query with bundle-pinned manifest hash; mandatory browser/CDN two-release cache/revalidation verification. Failure blocks launch; amend to content paths if required. |
| F12 — map features/topology | §6.6; §10 T2 | One feature per exact tax ID, MultiPolygon allowed, three explicit disjoint noData IDs; joint topology simplification/quantization, geometry/adjacency/shared-arc/gap/overlap tests and PNG. |
| F13 — static output/404 | §5; §9; §10 T6/T7/T8 | `publicDir: 'site'`, explicit page inputs/URLs, output `_headers`/404 assertions. Status/type/schema/hash loader checks, genuinely absent-asset tests on production-style server and Pages, not mock-only SPA success. |
| F14 — environment/automation | §10 T1/T3; §15 R3 | JDK 21/Python/engine pins, bounded heap, measured pilot/full RAM/disk/time, checkpoints and owner-controlled alternatives. Least-privilege PR job permissions, repository settings, approval-required generated-PR CI behavior and actual changed/no-change-path verification. |
| F15 — measurable UI/golden | §7; §9; §10 T5/T6/T8; §12–13; §17 | Cold transfer budget and cold loading behavior separate from warm compute/render; explicit emulation/measurements. Unrounded rank, deterministic collation/small groups, non-increasing filters and named effect cases; real-data release-bound golden requires actual owner approval/reapproval. |

## 3. Exact defaults versus unresolved owner/evidence gates

These are implementation defaults, not claims that they have been tested: schema version 1; RFC 8785 canonical JSON/SHA-256; manifest excludes its own hash inventory and app embeds final manifest hash; WGS84 output; 20 m final displacement and 100,000-per-axis quantization; explicit 1 m² topology anomaly tolerance; deterministic stop ties/coordinates, 1.2 m/s walking, ceil minutes; Europe/Zurich inclusive exact boarding window; explicit travel modes; station-speed tolerance/formula; de-CH collation plus numeric BFS final tie; up to five balanced groups; frozen seed/inputs and 50-workplace checkpoints; JDK 21/Python 3.11 environment pins; JVM headroom/resource budgets; explicit warm/cold browser profile and timeouts. Exact compatible package/runtime patch versions and official source snapshots must still be selected, pinned and verified from real releases, not invented here.

| Gate | Proposed/default handling | Who / what closes it |
| --- | --- | --- |
| O1–O6 | One earner; German/strings; no custom domain/pages.dev; public repo default but owner creates it; Impressum placeholder blocks launch; no analytics | John at original gates. No external account/repo/domain side effects from this amendment. |
| Unverified/failed limited coverage | Failed cantons fully quarantined; propose identical withholding for unverified, clearly labelled. Never show unchecked taxes as verified. | John explicitly approves unverified policy/limited-coverage release status, or complete all real checks; final launch still needs approval. |
| Selectable no-stop and counts | Propose all-Gemeinden selection with dedicated no-stop state and comparable count plus separate under-review count | John confirms wording/UX before final T6 acceptance; exact filter cannot be bypassed. |
| Reconstructed UX and real golden | No prototype fidelity claim; real-release scenario/top 10 only, no self-approval | Actual John approval evidence/date, after T3/T9 integration; reapprove changed releases/results. |
| Comparable ESTV inputs | Fixed assumptions retained; proposed child-age 10 where unspecified, explicit deductions/input mapping | John confirms comparability; implementer retrieves all official evidence and passes direct frontend gates. No amounts filled here. |
| Reference Tuesday/calendar | Propose earliest covered Tuesday outside all specified national/cantonal/regional school calendars | Genuine GTFS/calendar evidence; owner approves any exception before T3 acceptance. |
| Speed QA exceptions | Explicit conservative station-distance checks, no silent deletions | Independently evidenced pair/service/feed-specific exception and John approval, or resolve offending route/coordinates. |
| Full-run resources | Measured pilot/full headroom/time/disk; existing local/larger-runner alternatives only | Implementer records measurements; owner authorizes paid/external execution as needed. No successful nationwide run claimed. |
| Licence/terms/content | BFS/GEOSTAT/package notices retained; exact upstream data rights unresolved, O5 placeholder remains | John/qualified reviewer resolves applicable rights and approves real Impressum/Datenschutz/Methode before publication. Not legal advice or clearance. |
| CDN/browser cache coherence | Versioned queries plus release/hash checks; no mixed results, stale clients reload | Actual two-deployment Pages/CDN/browser evidence including ETag/304/cache hits. If not coherent, block and amend scheme, not claim a pass. |
| Production launch | Preview/main deployment is not approval; release CI, official evidence, real golden, content, rights, device/performance gates required | Actual owner authorization and §13 evidence; all launch checkboxes remain unchecked in this amendment. |

## 4. Sources and documentation-drift rule

The review reports retrieval on **2026-10-16 UTC** for S1–S11 below. This amendment relies on that dated report and did **not** independently refetch all provider documentation or inspect the package archive. The review refers to `sources/` and `source-manifest.json`, but those raw evidence files were not present in the supplied local baseline; do not claim they were recovered or invent their checksums. Obtain/preserve the evidence or reread the primary sources before the dependent build/release gate. The live engine HEAD observation above was executed separately during this amendment.

| ID | Primary URL(s) / purpose |
| --- | --- |
| S0 | Supplied local `SPEC.md` v1, checksum in §1; review remains immutable with original section/line references. |
| S1 | https://r5py.readthedocs.io/stable/reference/reference.html — routing API/options |
| S2 | https://r5py.readthedocs.io/stable/user-guide/user-manual/travel-time-matrices.html — sampling/initial-wait/percentiles |
| S3 | https://r5py.readthedocs.io/stable/user-guide/user-manual/detailed-itineraries.html — segment/itinerary semantics |
| S4 | https://registry.npmjs.org/swiss-maps/4.7.0 and https://registry.npmjs.org/swiss-maps/-/swiss-maps-4.7.0.tgz — exact package, README/licence/shapefiles; review reports registry/archive SHA-1 `a32e30afd8231a56c39cd76ff714ab60f12a006f`, not fresh verification here |
| S5 | https://vite.dev/guide/assets.html — publicDir output behavior |
| S6 | https://developers.cloudflare.com/pages/configuration/headers/ — deployed `_headers` |
| S7 | https://developers.cloudflare.com/pages/configuration/serving-pages/ — static 404/cache/ETag/SPA behavior |
| S8 | https://r5py.readthedocs.io/stable/user-guide/installation/installation.html — Java/runtime prerequisites |
| S9 | https://docs.github.com/en/actions/reference/runners/github-hosted-runners — runner CPU/RAM/disk |
| S10 | https://docs.github.com/en/actions/reference/limits — execution limits |
| S11 | https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow — token/PR event and approval behavior |
| Official evidence still needed | https://swisstaxcalculator.estv.admin.ch ; https://www.sbb.ch ; https://opentransportdata.swiss ; https://opendata.swiss ; https://download.geofabrik.de/europe/switzerland.html ; exact BFS STATPOP/boundary/calendar dataset/version URLs must be recorded when genuinely retrieved, not guessed from failed links. |

**Drift rule:** before implementing a version-sensitive contract and before every annual release, reread primary documentation against the pinned versions, record retrieval date/URL/content hash and relevant excerpt, and compare with this dated baseline. Revalidate API semantics, JDK compatibility, runner/storage/time limits, generated-PR permissions/events, hosting/query/cache/404 behavior and applicable data terms. A changed page/provider behavior is not permission to silently change scope, metric, tolerances or owner policy: update SPEC and this traceability record in the same PR, keeping unresolved evidence/approval gates pending. Keep historical source dates/hashes; do not relabel an old retrieval as current. Never fill inaccessible ESTV/SBB values or legal terms from memory.

## 5. Documentation verification boundary

Validate against the baseline Git object, not a reconstructed copy: ordered sections 0–17 and task IDs T1–T9 present; original scope/stack decisions and tax/filter formula retained; all **29 tax rows**, **30 travel rows**, control defaults, **O1–O6** rows/defaults and yearly-maintenance table rows byte-identical. All official reference blanks must remain blank. Check F01–F15 map coverage, Markdown code-fence/section structure, local document links, documented spec checksum and `git diff --check` before committing. These are documentation checks only; no app/unit/CI/routing/official/CDN/legal acceptance is implied.
