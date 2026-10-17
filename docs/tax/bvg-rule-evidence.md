# ESTV age-35 BVG default: rule and evidence

## Decision

For an employed person aged 35, gross annual income `x` in the requested CHF 40,000–500,000 domain, ESTV's 2026 calculator native budget (`Budget: []`) returns this annual employee BVG contribution, rounded to whole CHF:

```text
round_half_up(
  0.05  * (min(x, 90_720) - 26_460)
+ 0.035 * max(x - 90_720, 0)
)
```

This is an **ESTV calculator default**, not the statutory BVG minimum as a whole. Implement it only for the fixed age-35, 2026, gross-employed profile evidenced here; do not generalize it to other ages, years, employment types, or user-entered pension contributions.

## Authentic evidence

The frozen public ESTV client contract identifies the anonymous official operations and binds the client bundle by URL and SHA-256 (`tests/reference/estv-2026/contract.json`). The collector contract documents that `Budget: []` invokes native defaults rather than zero deductions (`docs/reference/estv-2026-capture.md`; `scripts/reference/README.md`).

All 29 existing official budget captures have `Age1: 35`. Their `BEITRAG_BVG_P1` values agree exactly with the rule at captured incomes CHF 60,000–400,000. Examples: 60,000 → 1,677; 90,000 → 3,177; 95,000 → 3,363; 120,000 → 4,238; 400,000 → 14,038 (`tests/reference/estv-2026/estv-2026-16-budget.response.json`, `-07-`, `-20-`, `-01-`, and `-19-`). Repeated incomes across municipalities and household/church profiles return the same BVG value.

Five targeted anonymous POSTs to the official `API_calculateTaxBudget` endpoint on 2026-10-17 returned HTTP 200:

| Gross income | ESTV `BEITRAG_BVG_P1` | Boundary purpose |
|---:|---:|---|
| 40,000 | 677 | requested lower bound |
| 26,460 | 189 | statutory minimum coordinated-salary floor (outside requested domain) |
| 90,720 | 3,213 | upper coordinated-salary boundary |
| 90,721 | 3,213 | first franc above boundary; whole-CHF rounding |
| 500,000 | 17,538 | requested upper bound |

Raw probe responses are retained at `/tmp/estv-bvg-{income}.json` for this worker run; they are not repository fixtures or approvals.

## Statutory minimum versus ESTV assumption

BVG/LPP Article 8 defines coordinated salary, and Article 16 sets the statutory retirement-credit rate for ages 35–44 at 10% of coordinated salary. The 2025/2026 BVG key figures are entry threshold CHF 22,680, coordination deduction CHF 26,460, upper annual salary CHF 90,720, and minimum coordinated salary CHF 3,780. These explain ESTV's 5% employee-side amount through CHF 90,720 (including `0.05 × 3,780 = 189`).

The additional **3.5% of gross salary above CHF 90,720** is not part of that statutory minimum: income above the BVG upper limit is extra-mandatory. It is therefore specifically an ESTV default modelling assumption evidenced by the official calculator responses, not a universal legal or pension-plan rule.

## Boundaries and rounding

Within CHF 40,000–90,720 the first term is 5% of `x − 26,460`. Above CHF 90,720, CHF 3,213 is retained and 3.5% of excess income is added. ESTV rounds the final annual result to whole CHF; the captures and probes are consistent with half-up rounding (for example 75,000 → 2,427.00 and 95,000 → 3,362.80 → 3,363). No curve was fitted silently: the legal coordinated-salary boundaries supply the break, while official ESTV observations establish its separate excess-income assumption.

## Sources

- ESTV Swiss Tax Calculator public client: <https://swisstaxcalculator.estv.admin.ch/>
- Official anonymous budget operation: <https://swisstaxcalculator.estv.admin.ch/delegate/ost-integration/v1/lg-proxy/operation/c3b67379_ESTV/API_calculateTaxBudget>
- Federal Act on Occupational Old Age, Survivors' and Invalidity Pension Provision (BVG/LPP), Arts. 8 and 16: <https://www.fedlex.admin.ch/eli/cc/1983/797_797_797/en>
- Federal Social Insurance Office, occupational-pension key figures: <https://www.bsv.admin.ch/bsv/en/home/social-insurance/bv/grundlagen-und-gesetze/grundlagen.html>
