import { expect, test } from 'vitest';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
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

test('SZ deductions match the official Freienbach line items after the recorded corrections', async () => {
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
  expect(calculatedDeductions.get('HauptErw_EK')).toBe(officialInfo.get('TXT_30'));
  expect(calculatedDeductions.get('KKSparLedigMitBVGS3a_EK')).toBe(officialInfo.get('TXT_49'));
  expect(calculatedDeductions.get('SozLedig_EK')).toBe(officialInfo.get('TXT_60'));
  expect(dineroToNumber(taxable.taxableIncomeCanton)).toBe(official.TaxableIncomeCanton);
  expect(row[0]).toBe(official.IncomeTaxFed);
  // With the 29 Oct 2026 ESTV tariff refresh the simple tax matches too (ESTV shows whole francs).
  expect(Math.abs(row[1] - official.IncomeSimpleTaxCanton)).toBeLessThan(1);
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

test('two genuine generations produce matching SHA-256 hashes for all nine tax artifacts', async () => {
  const { generateTables } = await import('./build');
  const hash = (value: string) => createHash('sha256').update(value).digest('hex');
  const first = await generateTables();
  const second = await generateTables();
  expect(Object.keys(first).sort()).toEqual([
    'gemeinden-2026.json',
    ...['m', 's'].flatMap(civil => [0, 1, 2, 3].map(kids => `tax-2026-${civil}-${kids}.json`)),
  ].sort());
  expect(Object.fromEntries(Object.entries(first).map(([name, bytes]) => [name, hash(bytes)])))
    .toEqual(Object.fromEntries(Object.entries(second).map(([name, bytes]) => [name, hash(bytes)])));
});

test('generator joins all 2110 authentic BFS IDs with (corrected) income-rate columns', async () => {
  const { loadSources, buildGemeinden } = await import('./build');
  const { churchIncomeRateOnSimpleTax } = await import('../../vendor/swisstaxcalculator/lib/taxes/factor');
  const sources = await loadSources();
  const output = buildGemeinden(sources);
  expect(Object.keys(output.gemeinden)).toHaveLength(2110);
  expect(new Set(sources.locations.map(x => x.Canton)).size).toBe(26);
  for (const loc of sources.locations) {
    const f = sources.factors.get(loc.BfsID)!;
    const church = (rate: number) => churchIncomeRateOnSimpleTax(loc.CantonID, rate, f);
    expect(output.gemeinden[loc.BfsID].slice(0, 6)).toEqual([loc.BfsName, loc.Canton,
      f.IncomeRateCanton, f.IncomeRateCity, church(f.IncomeRateProtestant), church(f.IncomeRateRoman)]);
    // SO Gemeinden carry per-person personal taxes (patch 27), VS Gemeinden their communal index (patch 31).
    expect(output.gemeinden[loc.BfsID].length).toBe(loc.Canton === 'VS' ? 8 : loc.Canton === 'SO' ? 7 : 6);
  }
  expect(output.gemeinden[2473][6]).toEqual([30, 0, 0]);   // Dornach (ESTV: single reformed 30, married catholic 60)
  expect(output.gemeinden[6266].slice(6)).toEqual([null, 176]);   // Sion: no per-Gemeinde personal tax, index 176 %
  // Corrections from data/corrections/2026.json reach the output (patch 19).
  expect(output.gemeinden[4021].slice(2, 4)).toEqual([103, 89]);
  expect(output.gemeinden[2701].slice(2, 4)).toEqual([50, 50]);
  // JU church on cantonal tax, UR church per 1% of taxable income (patch 15).
  expect(output.gemeinden[6711][5]).toBeCloseTo(6.4 * 285 / 100, 6);
  expect(output.gemeinden[1206][5]).toBeCloseTo(130 / 7.1, 5);
});
