# Reconstructed 2026 tax pipeline

Run from the repository root. The integrated package scripts now expose `npm run tax:build`, `npm run tax:test` and `npm run tax:reference`, explicitly selecting `scripts/tax/tsconfig.json` for vendor aliases. Local tooling was exercised with Node v22.23.2, tsx v4.23.15 and Vitest v5.0.5. Dependencies are pinned in the root lockfile; `npm ci` installs them. The temporary reconstruction worktree's `node_modules` symlink was not committed. Equivalent direct commands:

```sh
node_modules/.bin/vitest run --config scripts/tax/vitest.config.ts
node_modules/.bin/tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/build.ts
node_modules/.bin/tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/selftest.ts --report docs/tax/selftest-report.json
node_modules/.bin/tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/reference.ts --report docs/tax/reference-report.json
```

Both comparison CLIs accept `--data directory` and `--report file`, print JSON, save the report when requested, and exit 1 on an accuracy failure or execution error. Selftest currently **exits 1**; do not hide it with a success fallback. Reference's pass means table reconstruction only, never official acceptance.

## Inputs and assumptions

Authentic upstream source SHA `43064402b1e52dbbc34dded6a305d7d536737c73`; MIT notice and complete subset/patch audit in `vendor/swisstaxcalculator/STEUERPENDLER-PATCHES.md`. Uses its raw/parsed 2026 data: 2,110 unique BFS IDs and 26 cantons. No ESTV values were fabricated. All generated files and reports mark official verification pending; reference rows have `officialEstv: null`.

Gross employment income, age 35, no wealth, standard upstream deductions; married means one earner and a zero-income partner, both age 35 with the selected confession. Church maps none/reformed/catholic to other/protestant/roman. Children 0–3; 3 is the v1 3+ bucket, calculated as exactly three. Profiles use CHF 40,000–500,000 inclusive in 461 CHF 1,000 steps. Eight civil/children profiles store direct engine federal/base/personal values for one representative per canton; municipality/church factors are applied separately using SPEC §7. Linear interpolation and clamping are performed without display rounding. Cantonal shared-base separability is a model assumption tested by sampling, not proven for all municipalities/incomes.

Selftest reloads actual serialized JSON, uses deterministic uint32 LCG seed `0x2026`, stratifies across all cantons/profiles/church choices, and evaluates 500 on-grid and 300 truly off-grid inputs against the full engine. Gates are unchanged: on-grid `max(2, abs(expected)*0.0001)`; off-grid CHF 10. Reference parses exactly the 29 rows in original SPEC §11.1, preserves historical totals, and reports signed engine-minus-historical drift separately from absolute table error (CHF 10 gate).

## Actual verification in this worktree

- Unit suite: **12/12 tests passed**, 4/4 files; includes corruption-induced selftest failure. Vite emits a non-fatal config-loader warning (recorded in `docs/tax/unit-tests.txt`).
- Two complete generations: **all 9 SHA-256 hashes identical**; see `docs/tax/generation-{first,second}.sha256` and build logs.
- Selftest: **FAIL**, exit 1. On-grid **0/500 failures**, maximum absolute error **CHF 6.302667999989353** (within the relative gate). Off-grid **119/300 failures**, maximum **CHF 46.79200000000128**, exceeding CHF 10. Full inputs, expected/actual amounts, and failures are preserved in `docs/tax/selftest-report.json`.
- Reference: **PASS**, exit 0; **29/29** table comparisons pass, maximum error **CHF 0.831000000000131**. All 29 historical engine drifts are exactly zero; these are historical engine amounts, not official reference checks. See `docs/tax/reference-report.json`.

These actual sampled errors differ from the historical claims in SPEC §4. The original SPEC is retained unchanged. The off-grid acceptance gate is **not met**; it was not weakened or special-cased. Resolving interpolation/rounding accuracy and official ESTV verification (especially suspect VS and the Fribourg extrapolation) remains work before acceptance. No SBB, map, CI, deployment, or owner-approval result is asserted.

To reproduce the double-build hash comparison:

```sh
node_modules/.bin/tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/build.ts
sha256sum site/data/*2026*.json > /tmp/tax-first.sha256
node_modules/.bin/tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/build.ts
sha256sum site/data/*2026*.json > /tmp/tax-second.sha256
diff -u /tmp/tax-first.sha256 /tmp/tax-second.sha256
```
