# Steuerpendler vendor provenance and complete modifications

Source: https://github.com/devbrains-com/swisstaxcalculator

Pinned source commit: `43064402b1e52dbbc34dded6a305d7d536737c73` (verified against `/tmp/steuerpendler-upstream` HEAD).
License: MIT, copyright (c) 2025 devbrains-com. The upstream `LICENSE` is retained unchanged. This is a reconstruction of the described integration, not recovery of the lost original commit and not official ESTV approval.

## Engine patches (six)

1. **Internal exports** — `lib/taxes/income/index.ts`: export the existing `calculateTaxableAmount`, `calculateTaxesBase`, and `calculateTaxesBund` functions. Their original bodies are otherwise unchanged except patch 2. The generator calls these directly; it does not invert totals to derive a base tax.
2. **Federal child credit and zero floor** — same file: replace CHF 251 per child with CHF 263 per child when `includeChildrenDeduction` is true; wrap the subtraction in existing `dineroRoundMin0`. This prevents a negative federal tax. The constant is the reconstruction's 2025/2026 assumption; independent official verification remains pending.
3. **Fribourg upper tariff** — `lib/taxes/tarif/index.ts`, `calculateTaxesByTypeFreiburg`: when income exceeds the final row, apply that final row's effective percentage to the whole amount using existing `multiplyDineroPercent(..., 5)`, rather than throw. An empty tariff still throws. Holding the final effective rate is an explicit assumption, not an officially established extrapolation rule; the CHF 300,000 reference and CHF 500,000 unit case exercise this path.
4. **Second-earner eligibility** — `lib/taxes/deduction/index.ts`, the `ZweitVerdiener_EK` definition: retain the existing married/registered-partnership condition and additionally require at least two persons with `income > 0`. The input calculation remains unchanged. Exact source change: `rule: (taxInput) => ['m', 'rp'].includes(taxInput.relationship)` became that condition joined with `taxInput.persons.filter((person) => person.income > 0).length >= 2`. This prevents the table's positive federal minimum from creating a second-earner deduction for a zero-income spouse while preserving the existing positive-spouse calculation.
5. **Zug renter deduction** — `lib/taxes/typesClient.d.ts` exposes the existing general `rentExpenses` input, and `lib/taxes/deduction/index.ts` supplies 30% of positive rent to the existing `MaxAbzMiete_EK` canton table only for canton ID 25 (ZG). The parsed 2026 table applies its authentic CHF 10,800 maximum. ESTV evidence: the retained 2026 Zug capture `tests/reference/estv-2026/estv-2026-03-{budget,tax}.response.json` maps CHF 26,900 rent to CHF 8,070; `tests/reference/estv-2026/zug-renter-deduction-cap.json` records a second anonymous official check where CHF 45,030 rent is capped at CHF 10,800. No rule is inferred for other cantons.
6. **Capped percentage deduction format** — `lib/taxes/deduction/types.d.ts` admits the authentic `PERCENT,MAXIMUM` table value, and `lib/taxes/deduction/index.ts` calculates the rounded percentage capped at the table maximum. This repairs the 2026 SZ `HauptErw_EK` professional-expense deduction (20%, maximum CHF 6,900) without changing the retained source table.

## Node integration: paths and import aliases

- `lib/taxes/constants.ts`: add `fileURLToPath` from `node:url`; resolve parsed and raw data roots with `new URL('../../data/parsed/', import.meta.url)` and `new URL('../../data/raw/', import.meta.url)` instead of process-relative paths. `dataParsedRelativePath` is unchanged. This is the only additional modified vendor file.
- Upstream `~/...` imports are **not rewritten**. `scripts/tax/tsconfig.json` maps `~/*` to `vendor/swisstaxcalculator/*` for tsx/TypeScript. `scripts/tax/vitest.config.ts` supplies the matching absolute Vite alias. No root package/configuration files were edited. These two aliases are external integration changes, not hidden vendor source changes.

## Subset and exhaustive diff evidence

Before this notice was added, 125 files were retained: all 38 `lib/` files, all 84 raw/parsed **2026** data files, and upstream `LICENSE`, `README.md`, `package.json`. Exactly five source files named above now differ intentionally in bytes; every other retained source file is byte-identical to the pinned source. The upstream package manifest is provenance, not the root application's dependency manifest.

Omissions are deliberate, not additional engine patches: all raw/parsed 2022–2025 data (336 files), upstream UI/runtime/configuration files under `assets`, `components`, `inputs`, `modules`, `pages`, `server`, `utils`, `.vscode`, plus `app.vue`, `.eslintrc.js`, `.gitignore`, `.prettierrc.json`, `formkit.config.ts`, `nuxt.config.ts`, `tailwind.config.js`, `tsconfig.json`, `vitest.config.mjs`, and `yarn.lock`. Upstream `.git` metadata is not vendored.

- `docs/tax/vendor-inventory.txt` and `docs/tax/vendor-changes.patch` are the historical snapshot for the original three patches. The fourth patch is recorded exactly above; those reference artifacts are intentionally not regenerated by this focused repair.
- This `STEUERPENDLER-PATCHES.md` is the only added vendor file.

Tests: `scripts/tax/vendor.test.ts` exercises the original three patches and data paths. Focused second-earner engine and compiler regressions are in `scripts/tax/precision.test.ts`. They do not establish general official tax accuracy. Actual reconstruction results, including the failing off-grid accuracy gate, are in `docs/tax/` and `scripts/tax/README.md`. VS/Sion remains suspect until official checks pass.
