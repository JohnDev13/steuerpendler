# Sion (`estv-2026-17`) reconciliation

## Finding

This case is **not explained by frontend input mapping**. The captured ESTV request and the input passed to the vendored engine describe the same frozen household, and both produce the same gross-to-net result. The CHF 20,315 difference is downstream: the vendored 2026 VS deduction/tariff/factor sources produce CHF 22,670, while the captured ESTV calculation produces CHF 2,355. This is evidence of an engine/source-model defect for this case, not a basis for fitting a correction.

VS remains quarantined. No approval or comparability state changes follow from this one-case diagnosis.

## Like-for-like inputs

- `tests/reference/estv-2026/estv-2026-17-tax.request.json` has `TaxYear: 2026`, `TaxLocationID: 195000000`, `Relationship: 2`, `Children: [{Age:10},{Age:10},{Age:10}]`, `Age1: 35`, `RevenueType1: 1`, `Revenue1: 110000`, `Age2: 35`, `RevenueType2: 0`, `Revenue2: 0`, both confessions `2`, `Fortune: 0`, and `Budget: []`.
- The response resolves that request to `Location.{TaxLocationID:195000000,BfsID:6266,City:"Sion",Canton:"VS"}` in `tests/reference/estv-2026/estv-2026-17-tax.response.json`.
- `scripts/tax/build.ts:22-27` maps the comparison case to year 2026, BFS `locationId`, canton ID, married status, three children, zero fortune, Roman Catholic confession, one gross-income earner and a zero-income spouse. With Sion, the exact `makeInput` is `locationId:6266`, `cantonId:24`, `relationship:"m"`, `children:3`, and persons `(age 35, roman, gross 110000, pkDeduction 3888)` plus `(age 35, roman, gross 0, pkDeduction 0)`.
- The captured budget confirms `BRUTTOLOHN_P1:110000`, `BEITRAG_AIO_P1:5830`, `BEITRAG_ALV_P1:1210`, `BEITRAG_NBU_P1:440`, `BEITRAG_BVG_P1:3888`, `NETTOLOHN_P1:98632`, and zero partner secondary earnings (`NEBENERWERB_P2`) in `tests/reference/estv-2026/estv-2026-17-budget.response.json`.
- Running `calculateTaxesIncomeAndFortune(makeInput(...))` locally produced the identical gross-net chain: 110000 − 5830 − 1210 − 440 − 3888 = 98632. Thus location, civil status, children, income basis, age, pension default, confession, spouse income and wealth mapping all agree at the point deductions begin.

## Deduction and taxable-income divergence

The captured official response (`InfoFed`, `InfoCanton`, `TaxableIncome*`) and the vendored result (`details.deductionsIncome`, `details.taxableIncome*`) differ as follows:

| Item | Captured ESTV | Vendored engine with same `makeInput` |
|---|---:|---:|
| Net employment income | 98,632 | 98,632 |
| Federal employment expense | 2,958 | 2,959 (`HauptErw_EK`) |
| Federal insurance/savings | 5,800 | 5,800: 3,700 + 3 × 700 (`KKSparzVerhMitBVGS3a_EK`, `KKSparProKind_EK`) |
| Federal married deduction | 2,800 | 2,800 (`SozVerheiratet_EK`) |
| Federal child deduction | 20,400 | 20,400 (`SozKind_EK`) |
| Federal second-earner deduction | absent | **8,600** (`ZweitVerdiener_EK`) despite zero spouse income |
| **Federal taxable income** | **66,674** | **58,073** |
| VS employment expense | 2,958 | 2,959 (`HauptErw_EK`) |
| VS insurance/savings | 10,990 | 10,990: 7,600 + 3 × 1,130 |
| VS own-childcare deduction | 9,390 | 3,130 (`EigenBetr_EK`) |
| VS children age 7–16 | 26,820 (`TXT_455`) | absent |
| VS more-than-two-children | 1,240 (`TXT_453`) | absent |
| **VS taxable income** | **47,234** | **81,553** |

The serialized frontend precision program exposes the same vendored deductions under `site/data/tax-2026-m-3.json` → `precision.VS.canton.deductions`: 2,959 at this net income, 7,600, three 1,130 entries, and 3,130, but no operations corresponding to official `TXT_455` or `TXT_453`. `scripts/tax/precision.ts:19-35` compiles those operations and tariff directly from vendored deduction/tariff providers. The taxable-income gap therefore exists in the vendored source/program before frontend municipality multiplication.

## Tariff, factors and components

- Official response keys are `IncomeSimpleTaxCanton:2403`, `IncomeSimpleTaxCity:2265`, `IncomeTaxFed:0`, `IncomeTaxCanton:662`, `IncomeTaxCity:1620`, `IncomeTaxChurch:49`, `PersonalTax:24`, `TotalTax:2355`.
- Vendored `vendor/swisstaxcalculator/data/parsed/2026/tarifs/24.json` selects `taxType:"EINKOMMENSSTEUER"`, `group:"ALLE"`, `tableType:"FREIBURG"`, `splitting:0`; the 80,000/90,000 rows have 13%/13.3%. Applied to taxable CHF 81,553, the engine returns base CHF 10,631.675 (serialized `site/data/tax-2026-m-3.json` → `cantons.VS[70]`), rounded to CHF 10,632.
- Vendored `vendor/swisstaxcalculator/data/parsed/2026/factors/24.json` for `Location.BfsID:6266` supplies `IncomeRateCanton:100`, `IncomeRateCity:110`, `IncomeRateRoman:3`. `scripts/tax/build.ts:71-79` copies these to the municipality tuple; `site/data/gemeinden-2026.json` → `gemeinden["6266"]` is `["Sion","VS",100,110,0,3]`.
- `src/tax.ts:75-90` applies the shared base to those factors. The reproduced components are federal 0, canton 10,632, city 11,695, church 319, personal 24, total **22,670**, exactly the current `docs/tax/official-comparison-report.json:302-316` actual.

The official response does not use the vendored shared-base result: its distinct `IncomeSimpleTaxCanton` and `IncomeSimpleTaxCity`, together with components 662/1,620/49, cannot be reconciled to the vendored CHF 10,631.675 base and 100/110/3 factors. Combined with the deduction omissions, this localizes the mismatch to vendored VS source/engine assumptions, not the official-comparison row-to-frontend mapping. The evidence does not identify an authoritative replacement table or factor rule, so no fix is proposed or inferred.
