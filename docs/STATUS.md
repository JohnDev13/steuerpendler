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
- Withheld ("Daten in Prüfung"): VS, VD, JU for every profile, plus every canton × profile that the broad
  ESTV sample shows more than 5 % off (`src/withheld.ts`). Outside the three quarantined cantons every sampled
  profile matches, but the 650 cases cover only one Gemeinde per canton; this is not all-Gemeinde validation.

## Gates

| Gate | Result | Command |
| --- | --- | --- |
| Tax on-grid, 500 cases vs engine (`src/tax.ts`) | pass, max CHF 0 | `npm run tax:test` |
| Tax off-grid, 300 cases vs engine | pass, max CHF 0 | `npm run tax:test` |
| Tax vs official ESTV, 29 frozen cases | 27 pass, 2 fail (VD, VS; ratchet: may only improve) | `npm run tax:official` |
| Tax vs broad official sample, 650 cases (26 capitals × 6 profiles × 4 incomes + church) | 606 pass (up from 604 before #78); VD 6/25, VS 0/25, every other canton 25/25 | `npx tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/sample.ts --fail` |
| Canton × profile more than 5 % off ESTV is withheld | enforced by test (`src/withheld.ts`) | `npm test` |
| Travel vs SBB, 30 pairs, ± 3 min | pass: 29 within 3 min, Wollerau consistent (SBB 38 min > cap) | `python3 scripts/travel/compare_reference.py --require-complete` |
| Unit, release, map, content, e2e | pass | see CI |

The green `tax-accuracy` job checks engine parity, not the independently failing ESTV gate;
`npm run tax:official` still exits 1 (2/29 cases fail: VD, VS). `availability.travel` (official, audited
travel) and the approval flags stay false; the preview uses `availability.matrix`.

Tax tables were refreshed from ESTV on 29 Oct 2026 (new tariffs for JU, NW, SZ, TI, VD, VS; six data corrections
became unnecessary). The 650-case sample exposed low-income deductions, cantonal married and single-parent
deduction rules, tax reductions per child (e.g. BL), and the still-unresolved VD family quotient. Supported rules were
added canton by canton (vendor patches 20–25). Patch 25 models the VD family deduction on declaration code 650:
2026 indexed thresholds from the VD deduction table, with completed-tranche semantics from the VD 2025 instructions
and corroborating anonymous 2026 ESTV captures (see vendor patch log and `tests/reference/vd-family-2026.json`).
The frozen VD family's taxable-income stage now matches, but its total still differs by CHF 2,413; VD passes only
6/25 broad sample cases (versus 4/25 before #78). Remaining gaps are the three quarantined cantons:
JU parish rates of merged municipalities (its deductions now match), VD quotient familial plus housing/modest-income
relief, and VS rebates/coefficient rules. A passing Lausanne income stage is not all-Gemeinde acceptance.
GE left the quarantine once its 12 % cantonal reduction and 1 % home-care levy were modelled.

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
  (or manually). Pages uses GitHub Actions from `main`; the former `gh-pages` branch was deleted and its
  last tip retained as the `archive/gh-pages` tag. The Pages API may still show the old source-branch field.

## Open tasks

- Walking from home to the first stop is not measured. Frequency trips and the feed's trip-pair transfer
  rules are modelled; the matrix is still one reference day's first-board-to-arrival result, not a measured
  residential route or service reliability claim.
- Resolve VD and VS official mismatches and JU parish rates with source-backed, municipality-aware evidence;
  passing one capital's sample cases alone cannot lift a canton-wide quarantine.
- Production host (Cloudflare per SPEC §3), Impressum details (O5), commercial map rights.

## History

Dated evidence from 17–26 Oct 2026 stays in `docs/deployment/`, `docs/travel/`, `docs/tax/` and
`docs/source/` for reference; it describes earlier states and is not current status. New evidence belongs
in CI run artifacts, not in committed files.
