# Steuerpendler — scope and zoomable-map update

**Verified:** 17 October 2026 (UTC)

**Live non-commercial preview:** https://johndev13.github.io/steuerpendler/

**Repository:** https://github.com/JohnDev13/steuerpendler

## Delivered

- Workplace choices are the 19 supported German-speaking cantonal capitals/government seats. This is the workplace subset only; it is never substituted for residential/tax coverage.
- All **2,110 Swiss Gemeinden in all 26 cantons** remain residential candidates and tax inputs, including non-capitals and neighbouring or French-/Italian-speaking cantons. The existing municipality file and all eight tax profile files were verified byte-identical to the previous full-coverage data.
- A separate residential search selects municipalities such as Lenzburg, Olten or Genève without changing the workplace. Browser tests explicitly exercise these choices while Aarau remains selected.
- The **20-minute transport / 15-minute station-walk** controls remain separate with count-walk disabled. These control tests are not evidence of authentic qualifying train routes.
- The actual SVG map supports +/− buttons, mouse-wheel and keyboard zoom, mouse/touch dragging, two-finger pinch and reset to Switzerland. Zoom is bounded; manual navigation and municipality selection survive profile/filter/selection updates. Map viewport is not a geometric commute filter.
- The full genuine geography remains: 2,110 residential/tax municipalities plus three existing source-only no-data areas.

## Verification

The final application was exercised against real production-build files under `/steuerpendler/`:

- **26 unit tests passed.**
- **16 Playwright tests passed**, including real Chromium CDP touch events, zoom/pan/reset, ordinary selection, a held-stationary drag regression, native suggestion-list scrolling, completed touch taps, keyboard/ARIA state, cross-canton residential selection, 400px layout and stale-data rejection.
- **8 map tests passed**, including authentic IDs, shared borders, geometry and two byte-identical rebuilds.
- Release-inventory regression: **1 passed**.
- Content checks: **14 passed including browser subtests**.
- Diagnostic travel Python checks: **7 passed**. These do not generate or validate real national routes.
- Final independent precommit review passed after two reproduced interaction defects were fixed with observed RED/GREEN regressions. The staged-added-line credential/dangerous-primitive pattern scan reported no findings; this is not an exhaustive security certification.

### Real public deployment

The live HTTPS browser verification passed: capital-only workplace suggestions, all 2,110 residential candidates, cross-canton residential search, persistent zoom/reset, actual geography, withheld unverified tax amounts, responsive 400px layout, working static content, genuine missing-data HTTP 404, no browser errors, no cookies and no third-party browser requests.

All **27 current built public files** were fetched and their SHA-256 hashes matched the local deployment artifact. Previous hashed JS/CSS assets were retained on `gh-pages` for cache grace; the 27-file inventory is the current build, not a count of every historical file on that branch. Physical-phone/Safari testing and production cache coherence remain pending.

## GitHub workflow access: verified, not assumed

The cached credential originally lacked `workflow`. Following the permission refresh, a real workflow-bearing branch push was accepted and GitHub Actions executed it.

Current application source-check run: https://github.com/JohnDev13/steuerpendler/actions/runs/39025535462

- **Preview engineering job: SUCCESS**, including 26 unit tests and all 16 browser tests in the remote logs.
- **Tax accuracy job: FAILURE** on the existing numerical selftest, not an authorization failure. It remains a hard failure with no tolerance relaxation or failure masking.
- Overall source-check run is therefore **not green**. CI restoration remains **draft PR #11**, deliberately unmerged rather than represented as an all-green pipeline: https://github.com/JohnDev13/steuerpendler/pull/11
- CI head differs from the published application source only in the workflow and its contract test; the application/data tested remotely are the same. Source CI is verified in that PR, not falsely described as an active merged workflow on main.

## Source-version and documentation-drift trace

- Application feature PR: https://github.com/JohnDev13/steuerpendler/pull/12 — merged.
- Published application source: `f049afca96a3e17f34c31bd4c7c13b210b954065` (feature commit `819d1f1`).
- Static Pages deployment: `b610957d9bfaab85bf5462bfbc9f6daded261b1f`.
- CI verification head: `32a75f196f6da14ab1b081ec2ae6c736fe7e8dbe`.
- Data release identity: `02e571458ba6c8ad172f984dfc0b89b6e8e52b2b5b90c78208ccfb16799e31b9`.
- Canonical specification: **SPEC v1.2**, especially §19. Source v1.1 is preserved at `docs/source/SPEC-v1.1-2026-10-17.md`; changes are recorded in `docs/spec-amendments-v1.2.md`.
- Release inventory pins the current SPEC and workplace registry inputs. Isolated-worker map evidence is clearly marked historical and distinguished from the current integrated results.
- This report and machine-readable evidence are a documentation-only follow-up; they do not change the application, data release or deployed bytes above. Evidence: `docs/deployment/evidence/2026-10-17-scope-map/`.

## Still not a verified tax-and-commute product

The pre-existing off-grid numerical gate remains **119/300 failures against CHF 10**, maximum error **CHF 46.792**. Verified all-origin→capital timetable/access generation and official ESTV/SBB comparisons remain unfinished. Tax amounts, rankings, deltas and tax-based colouring remain withheld; no arbitrary-profile or all-municipality official approval is inferred from limited research.

Production, owner content/golden approvals, physical-device checks and commercial/geodata-rights review remain open. GitHub Pages remains the authorized non-commercial test preview; Cloudflare is still the intended production host. No synthetic routes, sampled capital-to-capital results or invented cheapest-home recommendations were substituted for the missing data.
