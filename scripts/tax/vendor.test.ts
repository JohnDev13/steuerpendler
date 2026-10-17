import { expect, test } from 'vitest';
import { existsSync } from 'node:fs';
import { dataParsedBasePath } from '../../vendor/swisstaxcalculator/lib/taxes/constants';
import { dineroChf, dineroToNumber } from '../../vendor/swisstaxcalculator/lib/utils/dinero';
import type { TaxInput } from '../../vendor/swisstaxcalculator/lib/taxes/typesClient';
import * as income from '../../vendor/swisstaxcalculator/lib/taxes/income';

const input: TaxInput = {
  year: 2026, calculationType: 'incomeAndWealth', relationship: 'm', children: 2,
  cantonId: 26, locationId: 261, fortune: 0,
  persons: [
    { age: 35, income: 150000, incomeType: 'gross', confession: 'other' },
    { age: 35, income: 0, incomeType: 'gross', confession: 'other' },
  ],
};

test('patch 2 deducts CHF 263 per child from actual federal tariff', async () => {
  const before = await income.calculateTaxesBund(input, dineroChf(150000), false);
  const after = await income.calculateTaxesBund(input, dineroChf(150000), true);
  expect(dineroToNumber(before.taxesIncomeBund) - dineroToNumber(after.taxesIncomeBund)).toBe(526);
});

test('patch 2 floors federal child tax credit at zero', async () => {
  const result = await income.calculateTaxesBund(input, dineroChf(10000), true);
  expect(dineroToNumber(result.taxesIncomeBund)).toBe(0);
});

test('patch 3 Fribourg high income returns a finite nonnegative actual engine total', async () => {
  const result = await income.calculateTaxesIncomeAndFortune({ ...input, cantonId: 7, locationId: 2196,
    persons: input.persons.map((p, i) => ({ ...p, income: i === 0 ? 500000 : 0 })) });
  expect(Number.isFinite(result.taxesTotal)).toBe(true);
  expect(result.taxesIncomeCanton).toBeGreaterThan(0);
});

test('patch 1 exports the real taxable/base/federal calculation functions', () => {
  for (const name of ['calculateTaxableAmount', 'calculateTaxesBase', 'calculateTaxesBund']) {
    expect((income as Record<string, unknown>)[name], name).toBeTypeOf('function');
  }
});

test('vendored data paths resolve independently of process working directory', () => {
  expect(existsSync(`${dataParsedBasePath}2026/tarifs/0.json`)).toBe(true);
});
