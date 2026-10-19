# Zürich reconciliation: `estv-2026-01`

## Frozen inputs and mapping

The official tax and budget requests both send gross employed income: `RevenueType1: 1`, `Revenue1: 120000`, `Age1: 35`, `Relationship: 1`, no children/wealth/partner income, and `Budget: []` (`tests/reference/estv-2026/estv-2026-01-{tax,budget}.request.json`). The frozen frontend contract maps `BRUTTO` to `EMPLOYED` and emits `Revenue1` from `income1`; its approvals keep `default_budget_comparability` and `official_frontend_gate` pending (`tests/reference/estv-2026/contract.json`, keys `snippets[2].text`, `snippets[5].text`, `approvals`).

`scripts/tax/build.ts:21-26` maps the same CHF 120,000 to `persons[0].incomeType: "gross"` and `persons[0].income`, but supplies no `pkDeduction` or other deduction overrides.

## Gross-to-net and deductions

Official `response.IncomeP1` reports gross 120,000 less `AIOContribution` 6,360, `ALVContribution` 1,320, `NBUContribution` 480, and **`BVGContribution` 4,238**, yielding `NetIncome` 107,602 (`estv-2026-01-tax.response.json`). The budget response confirms the same under `BEITRAG_*_P1` and `NETTOLOHN_P1`; despite request `Budget: []`, it also exposes native default `KKPRAEMIEN: 4560` (`estv-2026-01-budget.response.json`, `response[].Ident`).

The vendored gross conversion computes AHV/IV/EO 5.3%, ALV 1.1%, and NBU 0.4%, but sets pension deduction from `person.pkDeduction ?? 0` (`vendor/swisstaxcalculator/lib/taxes/deduction/index.ts:244-278`). Thus `makeInput` yields net 111,840, omitting exactly CHF 4,238 BVG. Its table deductions are professional expenses 3,355 and insurance 1,800 federal/2,900 cantonal, producing taxable income 106,685 federal and 105,585 cantonal. Official `response.InfoFed`/`InfoCanton` instead show professional expense 3,228 and insurance 1,800/2,900, with `TaxableIncomeFed: 102574` and `TaxableIncomeCanton: 101474`. Both taxable gaps are exactly 4,111 = 4,238 omitted BVG minus 127 excess professional deduction.

## Tax-component reconciliation

The shipped row is `[bund, base, personal] = [3120, 6665, 24]` at CHF 120,000 (`site/data/tax-2026-s-0.json`, `cantons.ZH[80]`). Zürich factors are canton 95% and city 119% (`site/data/gemeinden-2026.json`, `gemeinden["261"]`), yielding 3,120 federal + 6,332 canton + 7,931 city + 24 personal = 17,407. Official keys are 2,849 + 5,981 + 7,492 + 24 = 16,346 (`estv-2026-01-tax.response.json`): differences are +271, +351, +439, +0 = **+1,061**, matching `docs/tax/official-comparison-report.json`, `results[0]`.

## Finding

For this case, the numeric mismatch is explained by different gross-to-net assumptions: ESTV injects a CHF 4,238 native BVG contribution while `makeInput` leaves `pkDeduction` absent and the vendored engine defaults it to zero. This is evidence-supported for `estv-2026-01`; whether ESTV's generated BVG is the approved cross-case comparison assumption remains precisely unresolved because `contract.json` keeps `approvals.default_budget_comparability` owner-pending.
