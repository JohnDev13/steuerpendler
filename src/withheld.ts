// Cantons whose estimates are withheld for every profile. scripts/tax/official.test.ts fails if any canton
// deviates from its ESTV reference case by more than 5% without being listed here.
// VS: cantonal rebates/coefficients not modelled (ESTV case off by ~270%).
// VD: quotient familial not modelled (~19%). GE: cantonal reduction not modelled (~8%).
// JU: official 2026 parish rates disagree with the factor table for merged municipalities (#58).
export const QUARANTINED_CANTONS: ReadonlySet<string> = new Set(['VS','JU','VD','GE']);

// Canton x profile combinations withheld because the engine is more than 5% off ESTV in the broad official
// sample (tests/reference/estv-2026-sample.jsonl). Key: civil status (s/m) and children (0-3; 3 = 3+).
// scripts/tax/sample.test.ts fails if a combination is more than 5% off without being listed here. Single
// parents are sampled with 2 children; their 1 and 3+ entries follow that sample.
export const TAX_WITHHELD: Readonly<Record<string, readonly string[]>> = {
  s0: [],
  s1: ['AG', 'BS', 'FR', 'NE', 'UR', 'ZG'],
  s2: ['AG', 'BS', 'FR', 'NE', 'UR', 'ZG'],
  s3: ['AG', 'BS', 'FR', 'NE', 'UR', 'ZG'],
  m0: ['FR', 'NE', 'SH'],
  m1: ['AG', 'FR', 'NE', 'SH'],
  m2: ['AG', 'FR', 'NE'],
  m3: ['FR', 'NE'],
};

export function withheldFor(civil: 's' | 'm', kids: number): ReadonlySet<string> {
  return new Set([...QUARANTINED_CANTONS, ...(TAX_WITHHELD[`${civil}${Math.min(kids, 3)}`] ?? [])]);
}
