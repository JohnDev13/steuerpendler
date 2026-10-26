# T7 content approval register — German drafts

**Review date:** 2026-10-16 UTC (actual local review date, not the supplied v1's 2026-10-17 metadata).  
**Status:** Draft implementation and local checks complete; **owner/legal/content approval pending; production launch blocked**. This is not legal advice, a compliance certificate, CI acceptance, or full T7 acceptance under SPEC §10.

## Delivered content and evidence boundary

- [`../pages/impressum.html`](../pages/impressum.html): explicit O5 launch blocker; `[BETREIBERNAME – AUSSTEHEND]`, `[POSTANSCHRIFT – AUSSTEHEND]`, `[KONTAKT-E-MAIL – AUSSTEHEND]`. No invented owner identity, address, email, or working mailto link.
- [`../pages/datenschutz.html`](../pages/datenschutz.html): browser-only calculation inputs distinguished from server/CDN connection metadata and potentially revealing static profile/workplace request paths. No accounts/cookies/analytics (O6); Cloudflare Pages is prospective, not an asserted live deployment. IP processing, unresolved retention/overseas processing/contracts, rights and missing contact are explicit. No blanket claim that personal data never exists.
- [`../pages/methode.html`](../pages/methode.html): actual `src/tax.ts` interpolation, component formula and `src/format.ts` display rounding; one-earner assumptions and excluded costs; required exact-minimum station-to-station travel pipeline clearly separated from absent real travel data. Initial waiting excluded, transfer waiting/walks included; walk toggle and self-row constraints explained. ESTV 29/SBB 30, VS suspicion, unverified-canton policy, version/year differences, map contract drift and rights remain open.
- Pages are self-contained HTML with inline CSS and system font names only (no font files/downloads). Semantic landmarks, skip link, focus styles, wrapping navigation, responsive text and light/dark styles. No scripts, forms, embedded media, cookies, analytics, stylesheet/font loads or external requests on page load. Source URLs are ordinary, explicitly activated hyperlinks, not embeds.
- The genuine swiss-maps BSD notice is reproduced verbatim inside the method page and checked against the retained original. The package README's non-commercial geodata statement and **Bundesamt für Statistik (BFS), GEOSTAT** credit are visible. BSD code rights are not presented as data-rights clearance. Other source-specific notices still require release evidence.

## Source/version lineage and documentation drift

Reviewed local baseline: `0dfa6af2fa81517d3eb58b2d4b0794c23dab5faf`. Requirements: [`../SPEC.md`](../SPEC.md), Build Spec v1.1, SHA-256 `05b8c095bb59b4094161ebc263ca21604172c7910e85e3c208efd90511e7b089`; [`spec-amendments-v1.1.md`](spec-amendments-v1.1.md) records the supplied v1 identity and source/review boundaries. Formula and rounding were read from the actual local code, not inferred from historical engine totals. The upstream engine HEAD observation `43064402b1e52dbbc34dded6a305d7d536737c73` is labelled as an observation, not a shipped engine/data version.

Map sources: [`map/README.md`](map/README.md), [`map/swiss-maps-4.7.0-README.md`](map/swiss-maps-4.7.0-README.md), [`map/swiss-maps-4.7.0-LICENSE.txt`](map/swiss-maps-4.7.0-LICENSE.txt). Existing map documentation describes LV95 coordinates and 2,113 municipality geometries with metadata-marked extras 2391/5391/5394, whereas v1.1 requires WGS84 and separate `noData` geometry. This branch records the discrepancy; it does not alter SPEC, the map, or claim full T2 acceptance.

No primary provider documentation, official calculator/fahrplan values or new legal terms were fetched or certified in this content task. Before launch and yearly updates, reread the pinned-version primary documentation/terms, preserve retrieval dates and content evidence, resolve drift through the appropriate specification/release review, and never relabel old evidence as current. Tax/map target 2026 does not force the timetable year; actual travel metadata must establish the selected feed/date. The illustrative 2027 metadata is not an approved real feed.

## Approval gates

| Gate | Status | Required evidence / owner action |
| --- | --- | --- |
| O5 actual operator details and publication permission | **pending — blocks launch** | Owner supplies and approves real name, full postal address and email; replace every named placeholder consistently. No identity inferred from spec owner metadata. |
| Current German Impressum / Datenschutz / Methode texts | **pending** | Actual owner approval with date and exact content/release identity; qualified legal review where appropriate. This register cannot self-approve. |
| Privacy/Swiss DSG and hosting configuration | **pending** | Confirm actual host/CDN, contract, recipients, logs, retention, foreign processing/safeguards, contact and real full-app request/cookie behavior. Update the prospective text accordingly. |
| O6 no analytics | **default respected; owner acceptance pending** | Retain no analytics; any change requires explicit owner decision, technical/privacy review and revised texts. |
| Exact map/data redistribution and use rights | **pending — blocks launch** | Resolve non-commercial geodata statement and exact 2026 source terms; retain BFS/GEOSTAT attribution and genuine notices. Code BSD-3-Clause is not data permission. |
| Other source notices and frozen release identity | **pending** | Genuine ESTV/engine revision/patch notices, GTFS terms, OSM/ODbL and STATPOP vintage/terms or documented fallback; coherent version/hash manifest. |
| Travel availability and official comparisons | **pending** | Real nationwide pipeline outputs with metric evidence; all 30 SBB cases and all 29 direct frontend-to-ESTV cases or spec-compliant failed-canton quarantine. No fabricated values. |
| VS / unverified-canton policy and implementation | **pending** | Independent evidence, full withholding across all consumers, explicit owner limited-coverage/unverified release policy. Suspicion is not an official failed result. |
| Map/spec discrepancy | **pending** | Integrator brings artifact into v1.1 conformance or obtains a documented spec amendment and reruns affected gates. |
| Vite production pages, root footer, 404/headers and CI wiring | **pending — parent integration** | Add explicit multi-page inputs and CI commands, assert all `dist/pages/*.html` outputs; test direct production URLs and root footer navigation, copied notices/404/headers and Pages behavior. Source-server success below is not this acceptance. |
| Final release / launch | **pending — blocked** | All applicable SPEC §13 gates and actual owner authorization; local tests/commit do not grant release approval. |

## Executed tests (2026-10-16 UTC)

Environment: Node `v22.23.2`; Playwright Chromium `156.0.8078.4`, headless on this Linux host, using the supplied shared dependencies. No dependency/config/source/vendor changes were made by this task.

1. **RED → GREEN per page:** the Impressum contract failed first on missing `pages/impressum.html`, then passed after implementation. Next the Datenschutz contract failed on its missing file, then passed. Finally the Methode contract failed on its missing file, then passed. Each page was written only after its own observed missing-feature failure. A case-sensitive assertion typo in the first draft test was corrected before the initial green.
2. `node --test tests/content/pages.test.mjs` → **6 tests passed, 0 failed, 0 skipped**. Checks German language/title/draft status, viewport/landmarks/focus/wrapping hooks, banned scripts/embedded resources/external resource directives, named operator placeholders, privacy boundaries, formula/metric/source/version essentials, genuine verbatim licence, every relative hyperlink target and fragment, descriptive links and current-page navigation.
3. `node --test tests/content/browser.test.mjs` → **7 tests passed, 0 failed, 0 skipped** (one parent plus six browser subtests). A real ephemeral HTTP source server serves the three draft documents. Every page was checked at 400×800/light and 320×800/dark: HTTP 200, exactly **one HTML request**, **zero cookies**, **zero page/console errors**, no horizontal scroll, keyboard skip navigation; method licence details also open by keyboard without overflow. This is source-page verification, not a Vite/Pages test, screen-reader audit, or legal certification.
4. Combined evidence run:

   ```sh
   node --test tests/content/*.test.mjs
   ```

   Run in CI (`ci.yml`, job `web`); results are in the run log, not committed.
5. `npm test` → **4 test files passed, 9 tests passed** (existing Vitest regression suite). `git diff --check` → exit 0.

`package.json`, `vite.config.ts`, `SPEC.md`, `src/` and other branches are intentionally untouched. The new node:test suites are explicit commands, not silently claimed to be covered by the existing Vitest include pattern. Production build/CI/remote/Pages verification is **not run or claimed** by this task; parent wiring and actual owner approval remain necessary for T7 acceptance.
