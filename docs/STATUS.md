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
  profile matches. Every Gemeinde the site can show (726, all within 30 minutes of a workplace) matches ESTV for
  four profiles (single 90k reformed; married with 2 children 150k catholic; single parent with 2 children 60k
  without church; married without children 220k reformed); the remaining profiles are checked at the capitals only.

## Gates

| Gate | Result | Command |
| --- | --- | --- |
| Tax on-grid, 500 cases vs engine (`src/tax.ts`) | pass, max CHF 0 | `npm run tax:test` |
| Tax off-grid, 300 cases vs engine | pass, max CHF 0 | `npm run tax:test` |
| Tax vs official ESTV, 29 frozen cases | 28 pass, 1 fail (VS; ratchet: may only improve) | `npm run tax:official` |
| Tax vs broad official sample, 650 cases (26 capitals × 6 profiles × 4 incomes + church) | 625 pass; VS 0/25, every other canton 25/25 | `npx tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/sample.ts --fail` |
| Tax vs ESTV in every Gemeinde the site can show: 726 reachable Gemeinden × 4 profiles, plus all 104 SO Gemeinden and BL cross-checks (3,286 cases) | 3,286 pass | `npx tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/gemeinden.ts --fail` (`scripts/tax/gemeinden.test.ts`) |
| Canton × profile more than 5 % off ESTV is withheld | enforced by test (`src/withheld.ts`) | `npm test` |
| Travel vs SBB, 30 pairs, ± 3 min | pass: 29 within 3 min, Wollerau consistent (SBB 38 min > cap) | `python3 scripts/travel/compare_reference.py --require-complete` |
| Unit, release, map, content, e2e | pass | see CI |

The green `tax-accuracy` job checks engine parity, not the independently failing ESTV gate;
`npm run tax:official` still exits 1 (1/29 cases fail: VS). `availability.travel` (official, audited
travel) and the approval flags stay false; the preview uses `availability.matrix`.

Tax tables were refreshed from ESTV on 29 Oct 2026 (new tariffs for JU, NW, SZ, TI, VD, VS; six data corrections
became unnecessary). The 650-case sample exposed low-income deductions, cantonal married and single-parent
deduction rules, tax reductions per child (e.g. BL), and the still-unresolved VD family quotient. Supported rules were
added canton by canton (vendor patches 20–25; 26–27 fix BL reformed church tax and SO personal tax by Gemeinde; 28–30 complete VD). Patch 25 models the VD family deduction on declaration code 650:
2026 indexed thresholds from the VD deduction table, with completed-tranche semantics from the VD 2025 instructions
and corroborating anonymous 2026 ESTV captures (see vendor patch log and `tests/reference/vd-family-2026.json`).
Patches 28–30 complete VD against the 2026 ESTV reference (family deduction in CHF 2,000 steps, housing and
modest-income deductions, the family quotient with its cap, half-up social contributions): all 592 Lausanne
captures from CHF 40,000, 25/25 sample cases and the frozen case match. VD stays withheld until its other
Gemeinden are checked. Remaining gaps: VS rebates/coefficient rules, VD Gemeinden beyond Lausanne, and JU parish
rates of merged municipalities (out of scope while unreachable; its deductions match).
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

## Owner decisions (30 Oct 2026)

- **Reference for 2026 tax rules:** where a canton has not yet published its 2026 rules or instructions, the
  official ESTV tax calculator (2026) is the reference. Rules are modelled from captured ESTV results
  (`tests/reference/estv-2026-probes/`) and must reproduce them within max(CHF 5, 0.1 %); no residual fitting
  of totals. Earlier-year documents may explain a mechanism but do not set 2026 amounts.
- **VD and VS:** model them against that reference so the frozen gate can reach 29/29. They stay withheld
  until a canton-wide check passes; today no VD/VS Gemeinde is within 30 minutes of a workplace.
- **JU:** out of scope while no JU Gemeinde is reachable within the 30-minute cap. JU stays quarantined
  (fail-closed); the parish-rate representation is only needed if the cap or workplaces change.
- **Walking from home to the first stop:** not measured, by decision. The site keeps stating that the
  access walk is 0 min and unmeasured; the measured-access pilot (Aarau) is closed as out of scope.
- **Release** (owner sign-off, Impressum O5, commercial map rights, production host): deferred, unchanged.

## Open tasks

- Frequency trips and the feed's trip-pair transfer rules are modelled; the matrix is one reference day's
  first-board-to-arrival result, not a service-reliability claim.
- VS against the ESTV 2026 reference (see Owner decisions); VD Gemeinden beyond Lausanne; broader profile
  coverage per Gemeinde.
- Production host (Cloudflare per SPEC §3), Impressum details (O5), commercial map rights — deferred.

## History

Dated evidence from 17–26 Oct 2026 stays in `docs/deployment/`, `docs/travel/`, `docs/tax/` and
`docs/source/` for reference; it describes earlier states and is not current status. New evidence belongs
in CI run artifacts, not in committed files.
