import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from 'vitest';
import { calculateTaxesIncomeAndFortune } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { cantonalRules, lateDeduction } from '../../vendor/swisstaxcalculator/lib/taxes/deduction/cantonal';
import { getTaxDecutionTable } from '../../vendor/swisstaxcalculator/lib/taxes/deduction/provider';
import { calculateTax, type TaxProfile } from '../../src/tax';
import { buildGemeinden, loadSources, makeInput } from './build';
import { compilePrecision } from './precision';

const ROOT = resolve(import.meta.dirname, '../..');

test('frozen estv-2026-12 applies the VD 2026 family deduction in the real engine', async () => {
  const responseBytes = await readFile(resolve(ROOT, 'tests/reference/estv-2026/estv-2026-12-tax.response.json'));
  expect(createHash('sha256').update(responseBytes).digest('hex')).toBe('5e8dc25de675e8cc7ba840aaaaaeab7361097eb14fbc1e32bfd14d352857b58b');
  const official = JSON.parse(responseBytes.toString()).response;
  expect(official.InfoCanton.find((line: any) => line.Entry.ID === 'TXT_462')?.Value).toBe(-3300);
  expect(official.TaxableIncomeCanton).toBe(106956);

  const sources = await loadSources();
  const lausanne = sources.locations.find(location => location.BfsID === 5586)!;
  const result = await calculateTaxesIncomeAndFortune(makeInput(lausanne, 'm', 2, 140000));
  expect(result.details.deductionsIncome.find(deduction => deduction.id === 'SozFamAbzug_EK')?.amountCanton).toBe(3300);
  expect(result.details.taxableIncomeCanton).toBe(106956);
});

test('VD completed-tranche bands cover boundary francs, every shipped household, and the zero floor', async () => {
  const table = await getTaxDecutionTable(23, 2026, 'EINKOMMENSSTEUER');
  const ruleFor = (married: boolean, kids: number) => cantonalRules({ cantonId: 23, married, kids }, table);
  const deduction = (basis: number) => lateDeduction(ruleFor(true, 2).late[0], basis);
  expect([[126400, 3300], [126401, 3300], [128499, 3300], [128500, 3200],
    [164199, 1600], [164200, 1500], [164201, 1500], [165199, 1500], [165200, 1400],
    [179199, 100], [179200, 0]]).toSatisfy((cases: number[][]) => cases.every(([basis, expected]) => deduction(basis) === expected));

  for (const married of [false, true]) for (let kids = 0; kids <= 3; kids++) {
    const rules = ruleFor(married, kids);
    expect(rules.disable).toEqual(['SozVerheiratet_EK', 'SozKindAlleinerzieher_EK', 'SozKind_EK']);
    const family = married ? 1300 + 1000 * kids : kids > 0 ? 2800 + 1000 * kids : 0;
    expect(rules.late).toHaveLength(family > 0 ? 1 : 0);
    if (family > 0) {
      expect(lateDeduction(rules.late[0], 126400)).toBe(family);
      expect(lateDeduction(rules.late[0], 500000)).toBe(0);
    }
  }
});

test('retained 160k and 161k captures exercise adjacent VD completed tranches', async () => {
  const fixture = JSON.parse(await readFile(resolve(ROOT, 'tests/reference/vd-family-2026.json'), 'utf8'));
  const expected = new Map([[160000, { basis: 128139, family: 3300, taxable: 124839, sha: '27842572d0fc27dd05717cad30dbb3f60c7afa3b4c9fa385d640cb8f43fd397f' }],
    [161000, { basis: 129051, family: 3200, taxable: 125851, sha: '29ac5ad51ef2838fe52778531ca7fa883d1e189b7a160593f178b50e929098bc' }]]);
  const sources = await loadSources();
  const lausanne = sources.locations.find(location => location.BfsID === 5586)!;
  for (const capture of fixture.captures.filter((item: any) => expected.has(item.grossIncome))) {
    const e = expected.get(capture.grossIncome)!;
    const response = capture.tax.response.response;
    expect(capture.tax.provenance.responseSha256).toBe(e.sha);
    expect(capture.tax.request.Revenue1).toBe(capture.grossIncome);
    expect(response.InfoCanton.find((line: any) => line.Entry.ID === 'TXT_462')?.Value).toBe(-e.family);
    expect(response.TaxableIncomeCanton).toBe(e.taxable);
    expect(e.basis - e.family).toBe(e.taxable);
    const result = await calculateTaxesIncomeAndFortune(makeInput(lausanne, 'm', 2, capture.grossIncome));
    expect(result.details.deductionsIncome.find(deduction => deduction.id === 'SozFamAbzug_EK')?.amountCanton).toBe(e.family);
    expect(result.details.taxableIncomeCanton).toBe(e.taxable);
  }
});

test('VD off-grid compiled/browser calculation remains identical to the real engine', async () => {
  const sources = await loadSources();
  const lausanne = sources.locations.find(location => location.BfsID === 5586)!;
  const input = makeInput(lausanne, 'm', 2, 160345);
  const precision = await compilePrecision(input);
  const profile: TaxProfile = { meta: { year: 2026, schemaVersion: 2, pensionDefault: 'ESTV2026Age35', budgetDefault: 'ESTV2026Age35', incomes: { from: 40000, step: 1000, count: 1 } },
    cantons: { VD: Array.from({ length: 461 }, () => [0, 0, 0]) }, precision: { VD: precision } };
  const actual = calculateTax(profile, buildGemeinden(sources).gemeinden[5586], 160345, 'none');
  const engine = await calculateTaxesIncomeAndFortune(input);
  expect(actual.total).toBe(engine.taxesTotal);
});
