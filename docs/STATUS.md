# Status

Current state of the non-production preview. This page replaces `PREVIEW-STATUS.md` and `ci-stages.md`;
keep it short and update it in the same PR that changes what it describes.

## What the preview shows

- All 19 workplaces, all 2,110 Gemeinden as homes. Tax-first ranking of Gemeinden with a public-transport
  connection to the workplace, with indicative tax totals and the difference to the workplace.
- Travel: full timetable matrix (`site/data/travel/matrix/`, SPEC §6.5c) from the official GTFS feed
  `gtfs_fp2026_20261028.zip` (SHA-256 `f4d87e84…a782`) for Tuesday 27 Oct 2026, all 19 workplaces,
  any number of changes, up to 30 minutes. Frequency-based trips (cable cars, funiculars, boats) and the feed's trip-pair
  transfer rules (with their service days) are modelled; a Gemeinde without a row has no connection
  within the selected time in this timetable (access walk to the first stop: 0 min, unmeasured). The old observed-positive export and its probes are removed.
- Walking from home to the first stop is not measured (0 min); the walk controls are disabled and say so.
- Withheld ("Daten in Prüfung"): VS, VD, GE, JU for every profile, plus every canton × profile that the broad
  ESTV sample shows more than 5 % off (`src/withheld.ts`). Single without children is shown everywhere except
  LU, VS, VD, GE, JU; most other profiles are withheld in many cantons until their rules are modelled.

## Gates

| Gate | Result | Command |
| --- | --- | --- |
| Tax on-grid, 500 cases vs engine (`src/tax.ts`) | pass, max CHF 0 | `npm run tax:test` |
| Tax off-grid, 300 cases vs engine | pass, max CHF 0 | `npm run tax:test` |
| Tax vs official ESTV, 29 frozen cases | 23 pass, 6 fail (ratchet: may only improve) | `npm run tax:official` |
| Tax vs broad official sample, 650 cases (26 capitals × 6 profiles × 4 incomes + church) | 340 pass (ratchet) | `npx tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/sample.ts --fail` |
| Canton × profile more than 5 % off ESTV is withheld | enforced by test (`src/withheld.ts`) | `npm test` |
| Cantons > 5 % off ESTV are withheld | enforced by test | `npm test` |
| Travel vs SBB, 30 pairs, ± 3 min | pass: 29 within 3 min, Wollerau consistent (SBB 38 min > cap) | `python3 scripts/travel/compare_reference.py --require-complete` |
| Unit, release, map, content, e2e | pass | see CI |

The green `tax-accuracy` job checks engine parity, not the independently failing ESTV gate;
`npm run tax:official` still exits 1 (8/29 cases fail). `availability.travel` (official, audited
travel) and the approval flags stay false; the preview uses `availability.matrix`.

Tax tables were refreshed from ESTV on 29 Oct 2026 (new tariffs for JU, NW, SZ, TI, VD, VS; six data corrections
became unnecessary). The 650-case sample shows what the engine still lacks: low-income deductions, cantonal
married and single-parent deduction rules, tax reductions per child (e.g. BL) and the VD family quotient.
These are being added canton by canton; each fix lowers the sample ratchet and un-withholds combinations.

## CI and deployment

- `.github/workflows/ci.yml` on every PR and push to main: `web` (types, unit, release, map, build, manifest
  current, content, e2e), `travel` (Python), `tax-accuracy` (engine parity only). All three are required on
  `main` with strict checks and admin enforcement; this does not make `tax:official` green.
- `.github/workflows/estv-refresh.yml` (manual, on a `claude/estv-refresh*` branch): refreshes the ESTV tables,
  re-asks ESTV for the 29 cases and captures a new broad sample.
- `.github/workflows/travel-evidence.yml` (manual): downloads the newest GTFS feed, pins its hash, builds the
  matrix, fetches the 30 SBB reference journeys, runs the gate and opens a data PR. The `travel` CI job
  re-runs the gate on every PR.
- `.github/workflows/deploy-pages.yml` builds with `PAGES_BASE=/steuerpendler/` and deploys on each main push
  (or manually). Pages Source is GitHub Actions; the preserved `gh-pages` branch is not the deployment source.

## Open tasks

- Walking from home to the first stop is not measured; frequency-based trips and route-/trip-specific
  transfer rows are not modelled.
- Model the missing cantonal tax rules found by the 650-case sample (see Gates).
- Production host (Cloudflare per SPEC §3), Impressum details (O5), commercial map rights.

## History

Dated evidence from 17–26 Oct 2026 stays in `docs/deployment/`, `docs/travel/`, `docs/tax/` and
`docs/source/` for reference; it describes earlier states and is not current status. New evidence belongs
in CI run artifacts, not in committed files.
