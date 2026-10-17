import { describe, expect, test } from 'vitest';
import { calculateBvg2026Age35 } from './bvg';

describe('calculateBvg2026Age35', () => {
  test.each([
    [40_000, 677],
    [90_720, 3_213],
    [90_721, 3_213],
    [500_000, 17_538],
  ])('applies the documented piecewise rule at gross CHF %i', (gross, expected) => {
    expect(calculateBvg2026Age35(gross)).toBe(expected);
  });

  test.each([
    [40_010, 678],
    [90_820, 3_217],
  ])('rounds exact half-franc result up at gross CHF %i', (gross, expected) => {
    expect(calculateBvg2026Age35(gross)).toBe(expected);
  });

  test.each([39_999.99, 500_000.01, Number.NaN, Number.POSITIVE_INFINITY])(
    'rejects invalid or out-of-domain gross income %s',
    gross => expect(() => calculateBvg2026Age35(gross)).toThrow(RangeError),
  );
});
