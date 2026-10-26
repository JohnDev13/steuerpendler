import { expect, test } from 'vitest';
import { calculateTaxableAmount } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { getTaxDecutionTable } from '../../vendor/swisstaxcalculator/lib/taxes/deduction/provider';
import type { TaxInput } from '../../vendor/swisstaxcalculator/lib/taxes/typesClient';

const zugInput: TaxInput = {
  year: 2026,
  calculationType: 'incomeAndWealth',
  relationship: 's',
  children: 0,
  cantonId: 25,
  locationId: 1711,
  fortune: 0,
  persons: [{ age: 35, income: 120000, incomeType: 'net', confession: 'other' }],
};

async function renterDeduction(input: TaxInput): Promise<number> {
  const result = await calculateTaxableAmount(input);
  return result.deductionsIncome
    .filter((item) => item.id === 'MaxAbzMiete_EK')
    .reduce((sum, item) => sum + item.amountCanton, 0);
}

test('Zug renter deduction is 30% of rent, capped by its parsed table, and otherwise zero', async () => {
  expect(await renterDeduction({ ...zugInput, deductions: { rentExpenses: 26900 } })).toBe(8070);

  const table = await getTaxDecutionTable(25, 2026, 'EINKOMMENSSTEUER');
  const authenticCap = table.itemsById.get('MaxAbzMiete_EK')?.maximum;
  expect(authenticCap).toBe(10800);
  expect(await renterDeduction({ ...zugInput, deductions: { rentExpenses: 50000 } })).toBe(authenticCap);

  expect(await renterDeduction(zugInput)).toBe(0);
  expect(await renterDeduction({ ...zugInput, deductions: { rentExpenses: 0 } })).toBe(0);
  expect(await renterDeduction({ ...zugInput, cantonId: 26, deductions: { rentExpenses: 26900 } })).toBe(0);
});
