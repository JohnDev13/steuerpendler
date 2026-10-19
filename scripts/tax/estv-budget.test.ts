import { describe, expect, test } from 'vitest';
import { estimateAnnualRent2026FixedProfile } from './estv-budget';

const capturedBudgets = [
  [107_602, 0, 26_900], [134_539, 0, 33_630], [107_602, 0, 26_900],
  [107_602, 0, 26_900], [89_662, 0, 22_420], [71_883, 0, 17_970],
  [80_703, 0, 20_180], [161_899, 0, 40_470], [225_739, 0, 56_430],
  [107_602, 0, 26_900], [63_063, 0, 15_770], [125_542, 0, 31_390],
  [134_539, 0, 33_630], [180_139, 0, 45_030], [271_339, 0, 67_830],
  [54_243, 0, 13_560], [98_632, 0, 24_660], [89_662, 0, 22_420],
  [362_539, 0, 90_630], [85_177, 0, 21_290], [89_662, 0, 22_420],
  [107_602, 0, 26_900], [89_662, 0, 22_420], [80_703, 0, 20_180],
  [71_883, 0, 17_970], [143_659, 0, 35_910], [89_662, 0, 22_420],
  [116_572, 0, 29_140], [67_473, 0, 16_870],
] as const;

describe('estimateAnnualRent2026FixedProfile', () => {
  test.each(capturedBudgets)(
    'matches captured 2026 ESTV budget net incomes CHF %i + %i',
    (netP1, netP2, expectedRent) => {
      expect(estimateAnnualRent2026FixedProfile(netP1, netP2)).toBe(expectedRent);
    },
  );

  test.each([
    [100_019, 0, 25_000],
    [100_020, 0, 25_010],
    [60_000.4, 40_019.6, 25_010],
  ])('rounds one quarter of combined net income to nearest CHF 10', (netP1, netP2, expected) => {
    expect(estimateAnnualRent2026FixedProfile(netP1, netP2)).toBe(expected);
  });

  test.each([
    [Number.NaN, 0],
    [Number.POSITIVE_INFINITY, 0],
    [0, Number.NEGATIVE_INFINITY],
    [-1, 50_000],
    [50_000, -1],
  ])('rejects invalid net incomes %s and %s', (netP1, netP2) => {
    expect(() => estimateAnnualRent2026FixedProfile(netP1, netP2)).toThrow(RangeError);
  });
});
