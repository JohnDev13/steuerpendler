# Independent ESTV 2026 capture (not an acceptance pass)

This catalogue covers **all 29 SPEC §11.1 cases / all 26 cantons**, not the 19 workplace destinations and not the older fixed-income capital sample. The governing specification is revision `4361c1ca8b4f0ba9ea13285b04719cf15cc89992`; its bytes and the current official client bundle are hash-bound in `tests/reference/estv-2026/contract.json`.

## Reproduction

Run from the repository root, using Python 3.11 stdlib only:

```sh
python3 -m unittest discover -s scripts/reference -v
python3 scripts/reference/estv_collector.py --offline
```

Live collection uses `python3 scripts/reference/estv_collector.py`. It caches immutable evidence, with no automatic refresh/retries; use a separate output directory for a separately reviewed source refresh, and retain the actual historical replay-baseline response there. Never delete existing raw evidence to conceal drift. The current public HTML explicitly links the client bundle; only relevant literal contract excerpts and its digest are committed. The entire bundle remains in the private discovery artifact directory because unrelated client configuration is unnecessary for this reference catalogue.

Each operation has exact UTF-8 request bytes, original response bytes, URL, UTC time, HTTP status, content type and SHA-256 sidecars. Response headers are not persisted; no authentication, outgoing cookies, tokens or browser profiles are used. Requests are serial, at least 0.4 seconds apart, timeout 25 seconds, maximum response 16 MB, with no retries. Redirects are blocked. HTTP barriers, non-JSON responses, diagnostics and mismatched input/location/arithmetic fail closed. Source-year availability and API version are retained separately: an API version's build date is not the tax year. `validate_catalogue` additionally checks all 87 case operations, all 29 CSV rows, source/year/version/replay sidecars, sanitized metadata and every entry in `tests/reference/SHA256SUMS`. The readable evidence report is `docs/reference/estv-2026-capture.md`.

## Frozen input contract

- Year 2026, gross **employment** earnings, primary age 35, net wealth 0.
- Relationship 1=single, 2=married. Partner earns 0; for married households partner age 35 and the same confession as primary are explicit **owner-pending proposals**. No partner fields for singles.
- Church uses the exact §11.1 value: 4=none, 1=reformed, 2=Roman Catholic. Married partners have the same selected church, not an invented church exemption.
- Each child is `{Age:10}`. Age 10 for every child, dependent-child treatment and the resulting deduction comparability remain **owner pending**, not approved.
- RevenueType1=1 is EMPLOYED and receives the unchanged gross income. The client maps BRUTTO to this enum; NETTO maps to SELF_EMPLOYED=2, **not employee take-home pay**. This collector never changes income basis to improve agreement.
- `Budget:[]` means ESTV native default deductions, **not zero deductions**. Per-case `*-budget.response.json` captures actual native budget entries. No custom commuting, meals, pillar 3a, childcare, property or interest overrides are selected. Gross-to-net contributions and all federal/cantonal deduction lines are retained in the raw detailed-tax response.
- Municipality lookup is matched by the exact requested BFS and canton, preferring the exact city name then lowest official TaxLocationID. No BFS-to-TaxLocationID arithmetic is assumed. Tax results must return the requested BFS/canton.

## Parent integration: native defaults versus existing engine

At source revision 4361c1c, `scripts/tax/build.ts:makeInput` supplies age35, gross income, child **count**, zero fortune, and for married couples a same-age/same-confession zero-income second person. It supplies no explicit deduction overrides. That does not establish equivalence to the public calculator's age-specific children and default budget.

The vendored deduction module uses insurance fallback CHF4,560 per adult and CHF1,400 per child. It has no active renter-expense deduction definition (rent input is commented out in its constants). The official native budget contains household/location-dependent rent and insurance assumptions. For Zug single/120000, the returned native model uses rent26,900, insurance4,560 and a renter deduction8,070 plus single-person deduction12,000. The detailed tax response shows federal professional expenses3,228, federal insurance1,800, gross120,000 → AHV/IV/EO6,360 + ALV1,320 + NBU480 + BVG4,238 → net107,602 → federal taxable102,574; federal income tax2,849, official total7,927. Winterthur married/two children/gross150000 has native insurance budget11,520 and rent33,630; net employment income134,539. Preserve those details rather than forcing the official model to an engine assumption or switching to self-employed income.

These are integration diagnostics, not a complete cause attribution or a tax-engine repair. Compare each raw `InfoFed`, `InfoCanton`, `IncomeP1`, `IncomeP2`, taxable-income field and native budget before interpreting frontend differences. Preserve unexpected official splits (including Basel) and credits as returned. TotalNetTax is TotalTax **plus the signed** TaxCredit; personal tax is included separately; wealth components must be zero. Frauenfeld single/two children/gross95000 establishes the sign: TotalTax4,571 + TaxCredit(-200) = TotalNetTax4,371. The first capture stopped on the old incorrect subtraction assumption; a real-response RED/GREEN regression fixed only the verifier, never the official bytes.

## Status and boundaries

The CSV leaves engine/frontend values and release identity **empty**. All official-gate fields remain **pending**. Capture verifies source provenance, exact case coverage and official response arithmetic, not shipped frontend accuracy, owner comparability, tax-engine parity, CI, quarantine status, redistribution rights or release approval. The parent owns §7.1/T9 direct frontend comparisons and any SPEC/config/launch changes. No tax implementation, release config or approval document is edited by this collector.

The older genuine Zürich response is retained only as a replay baseline. A new independent anonymous request must match its exact raw digest before scaling. Old nineteen-capital results are not reused as mixed-profile coverage. `verification.json` records every live request and all captured case totals; `SHA256SUMS` binds the committed evidence files.
