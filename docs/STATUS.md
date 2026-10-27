# Status

Current state of the non-production preview. This page replaces `PREVIEW-STATUS.md` and `ci-stages.md`;
keep it short and update it in the same PR that changes what it describes.

## What the preview shows

- All 19 workplaces, all 2,110 Gemeinden as homes. Tax-first ranking of Gemeinden with a public-transport
  connection to the workplace, with indicative tax totals and the difference to the workplace.
- Travel: full timetable matrix (`site/data/travel/matrix/`, SPEC §6.5c) from the official GTFS feed
  `gtfs_fp2026_20261024.zip` (SHA-256 `10a8bd19…1090`) for Tuesday 27 Oct 2026, all 19 workplaces,
  any number of changes, up to 30 minutes. A Gemeinde without a row has no connection within the
  selected time in this timetable. The old observed-positive export and its probes are removed.
- Walking from home to the first stop is not measured (0 min); the walk controls are disabled and say so.
- Withheld cantons ("Daten in Prüfung"): VS, VD, GE, JU (`src/config.ts`).

## Gates

| Gate | Result | Command |
| --- | --- | --- |
| Tax on-grid, 500 cases vs engine (`src/tax.ts`) | pass, max CHF 0 | `npm run tax:test` |
| Tax off-grid, 300 cases vs engine | pass, max CHF 0 | `npm run tax:test` |
| Tax vs official ESTV, 29 frozen cases | 21 pass, 8 fail (ratchet: may only improve) | `npm run tax:official` |
| Cantons > 5 % off ESTV are withheld | enforced by test | `npm test` |
| Travel vs SBB, 30 pairs, ± 3 min | pass: 24 within 3 min, Wollerau consistent (SBB 38 min > cap); 5 pairs go to non-workplaces | `python3 scripts/travel/compare_reference.py --require-complete` |
| Unit, release, map, content, e2e | pass | see CI |

The green `tax-accuracy` job checks engine parity, not the independently failing ESTV gate;
`npm run tax:official` still exits 1 (8/29 cases fail). `availability.travel` (official, audited
travel) and the approval flags stay false; the preview uses `availability.matrix`.

Remaining ESTV differences: tariff-level differences in SZ, AG (married), NW and SO (0.2–1.5 %), a TG child
tax credit the engine has no concept of, and VS, VD, GE (withheld). Details:
`vendor/swisstaxcalculator/STEUERPENDLER-PATCHES.md`.

## CI and deployment

- `.github/workflows/ci.yml` on every PR and push to main: `web` (types, unit, release, map, build, manifest
  current, content, e2e), `travel` (Python), `tax-accuracy` (engine parity only). All three are required on
  `main` with strict checks and admin enforcement; this does not make `tax:official` green.
- `.github/workflows/travel-evidence.yml` (manual): downloads the newest GTFS feed, pins its hash, builds the
  matrix, fetches the 30 SBB reference journeys, runs the gate and opens a data PR. The `travel` CI job
  re-runs the gate on every PR.
- `.github/workflows/deploy-pages.yml` builds with `PAGES_BASE=/steuerpendler/` and deploys on each main push
  (or manually). Pages Source is GitHub Actions; the preserved `gh-pages` branch is not the deployment source.

## Open tasks

- Five §11.2 pairs (Morges, Vevey → Lausanne; Nyon, Carouge → Genève; Bellinzona → Lugano) go to towns
  that are not workplaces in this preview, so they can never be checked. Owner decision: replace them
  with pairs to German-speaking capitals, or add those workplaces.
- Walking from home to the first stop is not measured; frequency-based trips and route-/trip-specific
  transfer rows are not modelled.
- Refresh the vendored 2026 ESTV data (`importdata 2026 --download` upstream) and re-check
  `vendor/swisstaxcalculator/data/corrections/2026.json` (8 ESTV cases still fail).
- Production host (Cloudflare per SPEC §3), Impressum details (O5), commercial map rights.

## History

Dated evidence from 17–26 Oct 2026 stays in `docs/deployment/`, `docs/travel/`, `docs/tax/` and
`docs/source/` for reference; it describes earlier states and is not current status. New evidence belongs
in CI run artifacts, not in committed files.
