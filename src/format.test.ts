import { describe, expect, it } from 'vitest';
it('formats CHF totals rounded to ten francs using Swiss grouping', async () => {
 const module = await import('./format').catch(() => ({} as Record<string, unknown>));
 expect(typeof module.formatCHF).toBe('function');
 const format = module.formatCHF as (amount:number)=>string;
 expect(format(12344)).toBe("CHF 12'340");
 expect(format(12346)).toBe("CHF 12'350");
 expect(format(0)).toBe('CHF 0');
 expect(format(-12344)).toBe("CHF -12'340");
});

import { formatDelta } from './format';
describe('formatDelta', () => {
  it('puts the sign before the currency and uses a real minus sign', () => {
    expect(formatDelta(70)).toBe('+CHF 70');
    expect(formatDelta(-660)).toBe('−CHF 660');
    expect(formatDelta(0)).toBe('CHF 0');
    expect(formatDelta(-4)).toBe('CHF 0');
  });
});
