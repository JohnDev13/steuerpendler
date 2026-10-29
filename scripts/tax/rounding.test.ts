// Steuerpendler patch 20: canton-specific rounding of the taxable income around splitting, evidenced by the
// broad ESTV sample (scripts/tax/sample.ts). Synthetic table so the arithmetic is visible.
import { expect, test } from 'vitest';
import { applyTariffRounding, tariffRounding } from '../../vendor/swisstaxcalculator/lib/taxes/tarif';
import { preciseTariffTax } from '../../src/tax';

// Progressive table: 0% to 10'000, then 10% (tax = 10% of the excess)
const tax = (y: number) => Math.max(0, y - 10000) * 0.1;

test('split100: floor income to 100, divide, floor to 100, apply that rate to the floored income', () => {
  // x = 79'373, s = 2 -> X = 79'300, y = 39'600, rate(y) = 2'960/39'600, tax = 2'960/39'600 * 79'300
  expect(applyTariffRounding('split100', 79373, 2, tax)).toBeCloseTo(2960 / 39600 * 79300, 6);
  // without splitting it is the tax on the income floored to 100
  expect(applyTariffRounding('split100', 79373, 1, tax)).toBeCloseTo(tax(79300), 6);
});

test('income100: floor income to 100, divide exactly, tax times split (AG)', () => {
  expect(applyTariffRounding('income100', 79373, 2, tax)).toBeCloseTo(tax(39650) * 2, 6);
});

test('exact: no rounding (SO, GR, GE, UR, formula tariffs)', () => {
  expect(applyTariffRounding('exact', 79373, 2, tax)).toBeCloseTo(tax(39686.5) * 2, 6);
});

test('conventions per canton', () => {
  expect(tariffRounding(0, 'BUND')).toBe('split100');      // federal
  expect(tariffRounding(26, 'ZUERICH')).toBe('split100');  // ZH
  expect(tariffRounding(1, 'ZUERICH')).toBe('income100');  // AG
  for (const id of [8, 10, 18, 22]) expect(tariffRounding(id, 'BUND')).toBe('exact'); // GE, GR, SO, UR
  expect(tariffRounding(5, 'FORMEL')).toBe('exact');       // BL formula tariff
});

test('browser evaluation applies the same convention', () => {
  const table = [{ amount: 0, percent: 0, taxes: 0, formula: '' }, { amount: 10000, percent: 10, taxes: 0, formula: '' }];
  for (const rounding of ['split100', 'income100', 'exact'] as const)
    expect(preciseTariffTax({ type: 'BUND', split: 2, rounding, table }, 79373))
      .toBeCloseTo(applyTariffRounding(rounding, 79373, 2, tax), 6);
});
