import { expect, test } from 'vitest';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { calculateTaxesIncomeAndFortune, calculateTaxesBase, calculateTaxableAmount } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { dineroToNumber } from '../../vendor/swisstaxcalculator/lib/utils/dinero';
import { calculateBvg2026Age35 } from './bvg';

interface OfficialTaxResponse {
  IncomeTaxFed: number;
  IncomeSimpleTaxCanton: number;
  TaxableIncomeCanton: number;
  TotalTax: number;
  InfoCanton: { Entry: { ID: string }; Value: number }[];
}

test('profile rows use unrounded internal simple tax, actual federal credit and personnel tax', async () => {
  const { loadSources, makeInput, buildRow } = await import('./build');
  const { locations } = await loadSources();
  const loc = locations.find(x => x.BfsID === 261)!;
  const input = makeInput(loc, 'm', 2, 150000, 'reformed');
  expect(input.persons).toHaveLength(2);
  expect(input.persons.map(x => x.income)).toEqual([150000, 0]);
  expect(input.persons.map(x => x.pkDeduction)).toEqual([calculateBvg2026Age35(150000), 0]);
  expect(input.persons.every(x => x.age === 35 && x.confession === 'protestant')).toBe(true);
  const taxable = await calculateTaxableAmount(input);
  const base = await calculateTaxesBase(input, taxable.taxableIncomeCanton, taxable.taxableFortuneCanton);
  const engine = await calculateTaxesIncomeAndFortune(input);
  expect(await buildRow(input)).toEqual([engine.taxesIncomeBund, dineroToNumber(base.taxesIncomeBase), engine.taxesPersonnel]);
});

test('SZ generation applies the official Freienbach expense cap and exposes the two remaining table differences', async () => {
  const { loadSources, makeInput, buildRow } = await import('./build');
  const sources = await loadSources();
  const loc = sources.locations.find(x => x.BfsID === 1322)!;
  const official = (JSON.parse(await readFile(
    join(process.cwd(), 'tests/reference/estv-2026/estv-2026-04-tax.response.json'),
    'utf8',
  )) as { response: OfficialTaxResponse }).response;
  const input = makeInput(loc, 's', 0, 120000);
  const taxable = await calculateTaxableAmount(input);
  const row = await buildRow(input);
  const engine = await calculateTaxesIncomeAndFortune(input);
  const officialInfo = new Map(official.InfoCanton.map(item => [item.Entry.ID, Math.abs(item.Value)]));
  const calculatedDeductions = new Map(engine.details.deductionsIncome.map(item => [item.id, item.amountCanton]));

  expect(calculatedDeductions.get('HauptErw_EK')).toBe(6900);
  expect(calculatedDeductions.get('HauptErw_EK')).toBe(officialInfo.get('TXT_30'));
  const remaining = [
    ['KKSparLedigMitBVGS3a_EK', 'TXT_49'],
    ['SozLedig_EK', 'TXT_60'],
  ] as const;
  const gaps = remaining.map(([id, officialId]) => officialInfo.get(officialId)! - calculatedDeductions.get(id)!);
  expect(gaps).toEqual([1000, 1000]);
  expect(dineroToNumber(taxable.taxableIncomeCanton) - official.TaxableIncomeCanton).toBe(gaps.reduce((a, b) => a + b, 0));
  expect(row[0]).toBe(official.IncomeTaxFed);
  expect(row[1] - official.IncomeSimpleTaxCanton).toBeCloseTo(148.6, 10);
  expect(engine.taxesTotal - official.TotalTax).toBe(259);
});

test('one profile contains all 26 cantons and 461 finite rows at the specified grid', async () => {
  const { loadSources, buildProfile, buildRow, makeInput } = await import('./build');
  const sources = await loadSources();
  const profile = await buildProfile(sources, 's', 0);
  expect(profile.meta.incomes).toEqual({ from: 40000, step: 1000, count: 461 });
  expect(profile.meta.pensionDefault).toBe('ESTV2026Age35');
  expect(Object.keys(profile.cantons)).toHaveLength(26);
  for (const rows of Object.values(profile.cantons)) {
    expect(rows).toHaveLength(461);
    expect(rows.every(row => row.length === 3 && row.every(Number.isFinite))).toBe(true);
  }
  const zurich = sources.locations.find(x => x.BfsID === 261)!;
  const input = makeInput(zurich, 's', 0, 120000);
  expect(input.persons[0].pkDeduction).toBe(calculateBvg2026Age35(120000));
  expect(profile.cantons.ZH[80]).toEqual(await buildRow(input));
});

test('writer emits exactly eight minified profiles and a 2110-ID municipality file', async () => {
  const { writeTables } = await import('./build');
  const dir = await mkdtemp(join(tmpdir(), 'steuerpendler-tax-'));
  try {
    await writeTables(dir, false);
    const files = (await readdir(dir)).sort();
    expect(files).toHaveLength(9);
    for (const file of files) {
      const raw = await readFile(join(dir, file), 'utf8');
      const data = JSON.parse(raw);
      expect(raw).toBe(JSON.stringify(data));
      if (file.startsWith('tax-')) {
        expect(Object.keys(data.cantons)).toHaveLength(26);
        expect(Object.values(data.cantons).every((r: any) => r.length === 461)).toBe(true);
      } else expect(Object.keys(data.gemeinden)).toHaveLength(2110);
    }
    for (const civ of ['s', 'm']) for (let kids = 0; kids < 4; kids++) expect(files).toContain(`tax-2026-${civ}-${kids}.json`);
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('generator joins all 2110 authentic BFS IDs with original income-rate columns', async () => {
  const { loadSources, buildGemeinden } = await import('./build');
  const sources = await loadSources();
  const output = buildGemeinden(sources);
  expect(Object.keys(output.gemeinden)).toHaveLength(2110);
  expect(new Set(sources.locations.map(x => x.Canton)).size).toBe(26);
  for (const loc of sources.locations) {
    const f = sources.factors.get(loc.BfsID)!;
    expect(output.gemeinden[loc.BfsID]).toEqual([loc.BfsName, loc.Canton,
      f.IncomeRateCanton, f.IncomeRateCity, f.IncomeRateProtestant, f.IncomeRateRoman]);
  }
});
