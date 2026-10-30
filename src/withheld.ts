// Cantons whose estimates are withheld for every profile. scripts/tax/official.test.ts fails if any canton
// deviates from its ESTV reference case by more than 5% without being listed here.
// VS left the quarantine once its index, family rebates, communal tariffs and church base were modelled
// (vendor patch 31; every VS Gemeinde and all Sion profiles match ESTV).
// VD: rules modelled and matching Lausanne (patches 28-30); withheld until the other VD Gemeinden are checked.
// GE left the quarantine once its 12% cantonal reduction and 1% home-care levy were modelled (data correction; frozen case and 25/25 sample cases match).
// JU: official 2026 parish rates disagree with the factor table for merged municipalities (#58). Its
// deductions now match ESTV (sample 25/25 for Delémont); the parish reconciliation is still open.
export const QUARANTINED_CANTONS: ReadonlySet<string> = new Set(['JU','VD']);

// Canton x profile combinations withheld because the engine is more than 5% off ESTV in the broad official
// sample (tests/reference/estv-2026-sample.jsonl). Key: civil status (s/m) and children (0-3; 3 = 3+).
// scripts/tax/sample.test.ts fails if a combination is more than 5% off without being listed here. Single
// parents are sampled with 2 children; their 1 and 3+ entries follow that sample.
export const TAX_WITHHELD: Readonly<Record<string, readonly string[]>> = {
  s0: [],
  s1: [],
  s2: [],
  s3: [],
  m0: [],
  m1: [],
  m2: [],
  m3: [],
};

export function withheldFor(civil: 's' | 'm', kids: number): ReadonlySet<string> {
  return new Set([...QUARANTINED_CANTONS, ...(TAX_WITHHELD[`${civil}${Math.min(kids, 3)}`] ?? [])]);
}
