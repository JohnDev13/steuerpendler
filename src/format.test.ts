import { expect, it } from 'vitest';
it('formats CHF totals rounded to ten francs using Swiss grouping', async () => {
 const module = await import('./format').catch(() => ({} as Record<string, unknown>));
 expect(typeof module.formatCHF).toBe('function');
 const format = module.formatCHF as (amount:number)=>string;
 expect(format(12344)).toBe("CHF 12'340");
 expect(format(12346)).toBe("CHF 12'350");
 expect(format(0)).toBe('CHF 0');
 expect(format(-12344)).toBe("CHF -12'340");
});
