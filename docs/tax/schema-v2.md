# Tax profile schema v2 — precision program

Status: integrated engineering contract under SPEC §20, amending §6.1/§7 only as stated there. Engineering approval does not grant independent official ESTV acceptance or production approval; both remain pending.

## Root cause and compatibility

The 461 original rows per canton/profile remain the exact CHF 40,000–500,000 grid authority. Linear interpolation between those rows cannot reproduce taxable-income CHF 100 floors, deduction thresholds, tariff steps, or engine monetary rounding. Schema v2 therefore adds a compact declarative `precision` program used only between grid points. Exact grid inputs and schema-v1 profiles retain the original interpolation/table behaviour.

All eight profiles remain present (`s|m` × children `0..3`), with all 26 cantons. `gemeinden-2026.json` remains the authentic 2,110-row authority and is unchanged.

## Profile contract

A v2 profile has `meta.schemaVersion: 2`, the unchanged `meta.incomes` and `cantons` members from schema v1, plus:

`meta.pensionDefault` is optional for backward compatibility. When absent, gross-to-net conversion retains the original behavior (no pension deduction). The only supported value is `"ESTV2026Age35"`; it selects the frozen ESTV 2026 employed age-35 BVG default. Unknown values reject the profile rather than silently changing its tax basis. The marker affects only schema-v2 off-grid precision evaluation; exact grid rows already contain the deduction used when they were generated. Newly generated profiles MUST emit this marker.

`meta.budgetDefault` is likewise optional only for backward compatibility. Its sole value is `"ESTV2026Age35"`, and new profiles emit it together with the matching pension marker. Unknown values, a budget marker without that pension marker, or `rent30` without the budget marker reject the profile. Legacy profiles with neither marker nor operation remain unchanged.

```ts
precision: Record<CantonCode, PreciseCanton>

type DeductionFormat =
  | 'ZERO' | 'STANDARDIZED' | 'MAXIMUM' | 'PERCENT' | 'PERCENT,MAXIMUM'
  | 'PERCENT,MINIMUM,MAXIMUM' | 'STANDARDIZED,PERCENT,MAXIMUM'
type TariffType = 'BUND' | 'ZUERICH' | 'FORMEL' | 'FREIBURG' | 'FLATTAX'

interface PreciseCanton {
  bund: TaxPart
  canton: TaxPart
  personal: number
  kids: 0 | 1 | 2 | 3
  persons: 1 | 2
}
interface TaxPart {
  deductions: Array<{
    source: 'net' | 'constant' | 'rent30'
    value: number
    format: DeductionFormat
    amount: number
    percent: number
    minimum: number
    maximum: number
    multiplier: number
  }>
  tariff: {
    type: TariffType
    split: number // finite and > 0
    // How the taxable income is rounded around splitting (vendor patch 20, evidenced by the broad ESTV sample):
    // 'split100'  X = floor100(income), y = floor100(X / split), tax = tax(y) / y * X  (tax(X) when split = 1)
    // 'income100' X = floor100(income), tax = tax(X / split) * split                    (AG)
    // 'exact'     tax = tax(income / split) * split                     (SO, GR, GE, UR, formula tariffs)
    rounding: 'split100' | 'income100' | 'exact'
    table: Array<{
      amount: number
      percent: number
      taxes: number
      formula: string
    }> // non-empty
  }
}
```

The `precision` key set MUST equal the 26-key `cantons` key set. Every numeric field MUST be a finite JSON number. Missing programs, extra/missing cantons, unknown enum values, malformed rows, `null`, non-numeric fields, non-positive split values, and invalid formulas reject the entire profile. There is no fallback to interpolation for a malformed v2 payload.

`ZERO` explicitly records an authentic upstream deduction-format branch whose engine contribution is zero. The compiler emits `ZERO`; the browser does not silently map unknown formats to zero.

`rent30` is emitted only for the verified ZG renter operation. At evaluation time it computes `round10(current post-BVG net income × 0.25) × 0.30`, then applies the serialized authentic format (currently `MAXIMUM`) and cap. Its serialized `value` is zero: seed-income rent is never frozen into a profile.

## Formula language and security

No `eval`, `Function`, dynamic import, or browser dependency on the full vendored engine is used. Formula input is parsed as a complete expression. After whitespace removal, every byte MUST belong to this grammar; token extraction that leaves any character rejects the profile:

```ebnf
expression = term, { ("+" | "-"), term } ;
term       = atom, { ("*" | "/"), atom } ;
atom       = "-", atom | "log", atom | "(", expression, ")"
           | "$wert$" | number ;
number     = digit, { digit }, [".", { digit }] ;
```

No identifiers other than `log` and `$wert$`, property access, commas, assignments, strings, exponent syntax, or unsupported characters are accepted. Parsing must consume the whole input and evaluation must be finite.

## §7 arithmetic amendment

For schema v2 and an income strictly between grid points:

1. Clamp gross income to CHF 40,000–500,000 and compute the frozen-profile net income. If `meta.pensionDefault` is `"ESTV2026Age35"`, subtract that BVG default during gross-to-net conversion before applying the deductions represented by the canton program. For `rent30`, derive estimated rent from this current net amount and apply 30% before the existing maximum cap.
2. Apply the serialized federal and cantonal tariff programs, including taxable-income floors/splits and formula tariffs.
3. Apply federal CHF 263-per-child handling and personal tax as represented by the frozen profile.
4. Round each final cantonal, municipal, and church money component independently with integer half-even rounding, matching the vendored engine. Church factor per-person normalization is retained.
5. Sum unrounded-for-display components. CHF 10 display rounding remains separate.

At exact grid points the original serialized row is selected, with component error no greater than `1e-9` CHF. A profile without `meta.schemaVersion: 2` continues to use the legacy §7 linear interpolation path unchanged.

## Verification contract

`npm run tax:test` compares the shipped serialized evaluator independently with the full vendored engine for the fixed 500 on-grid and 300 off-grid samples before display rounding. `scripts/tax/precision.test.ts` separately invokes `src/tax.ts` against the full engine for the same fixed sampler and records every input/result/error in `docs/tax/browser-parity-report.json`. Official direct ESTV verification remains pending and is not replaced by engine parity.

The standard-default result must be visibly qualified in German: **„Dies ist eine indikative Schätzung mit ESTV-Standardannahmen, keine individuelle oder verbindliche Steuerveranlagung und keine Steuerberatung.“**
