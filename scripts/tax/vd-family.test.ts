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
  const family = (rules: ReturnType<typeof ruleFor>) => rules.late.find(rule => rule.id === 'SozFamAbzug_EK')!;
  const deduction = (basis: number) => lateDeduction(family(ruleFor(true, 2)), basis);
  // Patch 28: CHF 100 per completed CHF 2,000 above 126,400 and per CHF 1,000 above 164,200, fractions added before one
  // floor (all 280 Lausanne ESTV grid cases; #78's CHF 2,100 tranches were CHF 100 too high in 32 of them).
  expect([[126400, 3300], [126401, 3300], [128399, 3300], [128400, 3200],
    [164199, 1500], [164200, 1500], [164299, 1500], [164300, 1400],
    [178299, 100], [178300, 0]]).toSatisfy((cases: number[][]) => cases.every(([basis, expected]) => deduction(basis) === expected));

  for (const married of [false, true]) for (let kids = 0; kids <= 3; kids++) {
    const rules = ruleFor(married, kids);
    expect(rules.disable).toEqual(['SozVerheiratet_EK', 'SozKindAlleinerzieher_EK', 'SozKind_EK', 'SozminderjKinder_EK']);
    const amount = married ? 1300 + 1000 * kids : kids > 0 ? 2800 + 1000 * kids : 0;
    expect(rules.late.map(rule => rule.id)).toEqual(['VdLogement_EK', 'VdModeste_EK', ...(amount > 0 ? ['SozFamAbzug_EK'] : [])]);
    if (amount > 0) {
      expect(lateDeduction(family(rules), 126400)).toBe(amount);
      expect(lateDeduction(family(rules), 500000)).toBe(0);
    }
  }
});

test('retained 160k and 161k captures exercise adjacent VD completed tranches', async () => {
  const fixture = JSON.parse(await readFile(resolve(ROOT, 'tests/reference/vd-family-2026.json'), 'utf8'));
  expect(fixture.captures.map((capture: any) => capture.grossIncome).sort((a: number, b: number) => a - b)).toEqual([90000, 160000, 161000]);
  for (const capture of fixture.captures) for (const kind of ['budget', 'tax']) {
    const retained = capture[kind];
    for (const payload of ['request', 'response']) {
      const bytes = JSON.stringify(retained[payload]);
      const prefix = payload === 'request' ? 'request' : 'response';
      expect(Buffer.byteLength(bytes, 'utf8'), `${capture.grossIncome} ${kind} ${payload} bytes`).toBe(retained.provenance[`${prefix}Bytes`]);
      expect(createHash('sha256').update(bytes).digest('hex'), `${capture.grossIncome} ${kind} ${payload} SHA-256`).toBe(retained.provenance[`${prefix}Sha256`]);
    }
  }
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
