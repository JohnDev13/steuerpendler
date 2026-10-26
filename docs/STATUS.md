# Status

Current state of the non-production preview. This page replaces `PREVIEW-STATUS.md` and `ci-stages.md`;
keep it short and update it in the same PR that changes what it describes.

## What the preview shows

- All 19 workplaces, all 2,110 Gemeinden as homes. Tax-first ranking of Gemeinden with a public-transport
  connection to the workplace, with indicative tax totals and the difference to the workplace.
- Travel: until a matrix built from a real feed is merged, the page uses the observed-positive export
  (`site/data/travel/all19-observed-routes-20261027.json`, 806 of 40,090 pairs). Gemeinden not listed are
  *unknown*. Once `site/data/travel/matrix/` exists, the page uses it instead and a missing Gemeinde means
  *no journey within 30 minutes* (SPEC §6.5c).
- Walking from home to the first stop is not measured (0 min); the walk controls are disabled and say so.
- Withheld cantons ("Daten in Prüfung"): VS, VD, GE, JU (`src/config.ts`).

## Gates

| Gate | Result | Command |
| --- | --- | --- |
| Tax on-grid, 500 cases vs engine (`src/tax.ts`) | pass, max CHF 0 | `npm run tax:test` |
| Tax off-grid, 300 cases vs engine | pass, max CHF 0 | `npm run tax:test` |
| Tax vs official ESTV, 29 frozen cases | 21 pass, 8 fail (ratchet: may only improve) | `npm run tax:official` |
| Cantons > 5 % off ESTV are withheld | enforced by test | `npm test` |
| Travel vs SBB, 30 pairs, ± 3 min | pending: reference minutes not yet entered | `python3 scripts/travel/compare_reference.py` |
| Unit, release, map, content, e2e | pass | see CI |

Remaining ESTV differences: tariff-level differences in SZ, AG (married), NW and SO (0.2–1.5 %), a TG child
tax credit the engine has no concept of, and VS, VD, GE (withheld). Details:
`vendor/swisstaxcalculator/STEUERPENDLER-PATCHES.md`.

## CI and deployment

- `.github/workflows/ci.yml` on every PR and push to main: `web` (types, unit, release, map, build, manifest
  current, content, e2e), `travel` (Python), `tax-accuracy` (SPEC 7.1 gates). Make all three required on main.
- `.github/workflows/build-travel.yml` (manual): builds the travel matrix from a GTFS URL and opens a data PR.
- `.github/workflows/deploy-pages.yml` (manual): builds with `PAGES_BASE=/steuerpendler/` and deploys to
  GitHub Pages. Requires Settings → Pages → Source = "GitHub Actions"; the `gh-pages` branch is then unused.

## Open owner decisions

- Fill `tests/travel/sbb-reference-2026.csv` from sbb.ch (30 pairs).
- Run "Build travel matrix" with a feed URL from https://data.opentransportdata.swiss/dataset/timetable-2026-gtfs2020.
- Refresh the vendored 2026 ESTV data (`importdata 2026 --download` upstream) and re-check
  `vendor/swisstaxcalculator/data/corrections/2026.json`.
- Production host (Cloudflare per SPEC §3), Impressum details (O5), commercial map rights.

## History

Dated evidence from 17–26 Oct 2026 stays in `docs/deployment/`, `docs/travel/`, `docs/tax/` and
`docs/source/` for reference; it describes earlier states and is not current status. New evidence belongs
in CI run artifacts, not in committed files.
