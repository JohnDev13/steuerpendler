// VD against the official 2026 ESTV results for Lausanne (vendor patches 28-30): housing, modest-income and family
// deductions, the family quotient with its cap and the half-up social contributions. Incomes below the site's
// CHF 40,000 minimum are clamped by the site and not compared.
import { expect, test } from 'vitest';
import { runGemeinden } from './gemeinden';

test('every Lausanne ESTV capture from CHF 40,000 matches within max(CHF 5, 0.1%)', async () => {
  const results = (await runGemeinden(undefined, ['vd-vs-grid', 'vd-edges', 'vd-modest'])).filter(r => r.canton === 'VD' && r.income >= 40000);
  expect(results).toHaveLength(592);
  expect(results.filter(r => !r.passed).map(r => `${r.profile} ${r.income}: ${r.ours} vs ${r.official}`)).toEqual([]);
}, 120000);
