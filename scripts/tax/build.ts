import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { calculateTaxableAmount, calculateTaxesBase, calculateTaxesBund } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { calculateTaxesPersonnel } from '../../vendor/swisstaxcalculator/lib/taxes/personnel';
import { dineroToNumber } from '../../vendor/swisstaxcalculator/lib/utils/dinero';
import type { TaxLocation, TaxInput, TaxConfession } from '../../vendor/swisstaxcalculator/lib/taxes/typesClient';
import type { TaxFactors } from '../../vendor/swisstaxcalculator/lib/taxes/factor/types';
import { calculateBvg2026Age35 } from './bvg';
import { calculateGrossNetDetails } from '../../vendor/swisstaxcalculator/lib/taxes/deduction';
import { estimateAnnualRent2026FixedProfile } from './estv-budget';

export const ROOT = fileURLToPath(new URL('../../', import.meta.url));
export const SOURCE = { repository: 'https://github.com/devbrains-com/swisstaxcalculator', commit: '43064402b1e52dbbc34dded6a305d7d536737c73', year: 2026 } as const;
export type Gemeinde = [name: string, canton: string, rateCanton: number, rateGemeinde: number, rateReformed: number, rateCatholic: number];
export interface Sources { locations: TaxLocation[]; factors: Map<number, TaxFactors> }
export const metadata = () => ({ year: 2026, source: SOURCE, officialVerification: 'pending', assumptions: 'scripts/tax/README.md' });

export type Civil = 's' | 'm';
export type Church = 'none' | 'reformed' | 'catholic';
export type TaxRow = [bund: number, base: number, personal: number];
export const INCOMES = { from: 40000, step: 1000, count: 461 } as const;

export function makeInput(loc: TaxLocation, civil: Civil, kids: number, income: number, church: Church = 'none'): TaxInput {
  const confession: TaxConfession = { none: 'other', reformed: 'protestant', catholic: 'roman' }[church] as TaxConfession;
  const person = { age: 35, confession, incomeType: 'gross' as const, income, pkDeduction: calculateBvg2026Age35(income) };
  const input: TaxInput = { calculationType: 'incomeAndWealth', year: 2026, locationId: loc.BfsID, cantonId: loc.CantonID,
    relationship: civil, children: kids, fortune: 0,
    persons: civil === 'm' ? [person, { ...person, income: 0, pkDeduction: 0 }] : [person] };
  if (loc.Canton === 'ZG') {
    const net = calculateGrossNetDetails(input).map(detail => detail.netIncome);
    input.deductions = { rentExpenses: estimateAnnualRent2026FixedProfile(net[0] ?? 0, net[1] ?? 0) };
  }
  return input;
}

export async function buildRow(input: TaxInput): Promise<TaxRow> {
  const taxable = await calculateTaxableAmount(input);
  const { taxesIncomeBase } = await calculateTaxesBase(input, taxable.taxableIncomeCanton, taxable.taxableFortuneCanton);
  const { taxesIncomeBund } = await calculateTaxesBund(input, taxable.taxableIncomeBund, true);
  const row: TaxRow = [dineroToNumber(taxesIncomeBund), dineroToNumber(taxesIncomeBase), dineroToNumber(calculateTaxesPersonnel(input))];
  if (!row.every(x => Number.isFinite(x) && x >= 0)) throw new Error(`Invalid row: ${JSON.stringify(input)}`);
  return row;
}

export async function loadSources(): Promise<Sources> {
  const base = `${ROOT}vendor/swisstaxcalculator/data/parsed/2026/`;
  const locations: TaxLocation[] = JSON.parse(await readFile(`${base}locations.json`, 'utf8'));
  locations.sort((a, b) => a.BfsID - b.BfsID);
  if (locations.length !== 2110 || new Set(locations.map(x => x.BfsID)).size !== 2110) throw new Error('Expected 2110 unique 2026 BFS IDs');
  const factors = new Map<number, TaxFactors>();
  for (const id of [...new Set(locations.map(x => x.CantonID))].sort((a, b) => a - b)) {
    const rows: TaxFactors[] = JSON.parse(await readFile(`${base}factors/${id}.json`, 'utf8'));
    for (const row of rows) {
      if (factors.has(row.Location.BfsID)) throw new Error(`Duplicate factor: ${row.Location.BfsID}`);
      factors.set(row.Location.BfsID, row);
    }
  }
  if (factors.size !== locations.length) throw new Error('Location/factor count mismatch');
  return { locations, factors };
}

export async function buildProfile(sources: Sources, civil: Civil, kids: number) {
  const representatives = new Map<string, TaxLocation>();
  for (const loc of sources.locations) if (!representatives.has(loc.Canton)) representatives.set(loc.Canton, loc);
  const cantons: Record<string, TaxRow[]> = {};
  const precision: Record<string, import('../../src/tax').PreciseCanton> = {};
  const { compilePrecision } = await import('./precision');
  for (const [canton, loc] of [...representatives].sort(([a], [b]) => a.localeCompare(b, 'en'))) {
    const rows: TaxRow[] = [];
    for (let i = 0; i < INCOMES.count; i++) rows.push(await buildRow(makeInput(loc, civil, kids, INCOMES.from + i * INCOMES.step)));
    cantons[canton] = rows;
    precision[canton] = await compilePrecision(makeInput(loc,civil,kids,120000));
  }
  return { meta: { ...metadata(), schemaVersion: 2, pensionDefault: 'ESTV2026Age35' as const, budgetDefault: 'ESTV2026Age35' as const, civil, kids, incomes: INCOMES }, cantons, precision };
}

export function buildGemeinden(sources: Sources) {
  const gemeinden: Record<string, Gemeinde> = {};
  for (const loc of sources.locations) {
    const f = sources.factors.get(loc.BfsID);
    if (!f) throw new Error(`Missing factor for ${loc.BfsID}`);
    const rates = [f.IncomeRateCanton, f.IncomeRateCity, f.IncomeRateProtestant, f.IncomeRateRoman];
    if (!rates.every(Number.isFinite)) throw new Error(`Invalid rate for ${loc.BfsID}`);
    gemeinden[loc.BfsID] = [loc.BfsName, loc.Canton, ...rates] as Gemeinde;
  }
  return { meta: metadata(), gemeinden };
}

export async function writeTables(output = `${ROOT}site/data`, log = true) {
  const sources = await loadSources();
  await mkdir(output, { recursive: true });
  await writeFile(`${output}/gemeinden-2026.json`, JSON.stringify(buildGemeinden(sources)));
  for (const civil of ['s', 'm'] as const) for (let kids = 0; kids <= 3; kids++) {
    const name = `tax-2026-${civil}-${kids}.json`;
    await writeFile(`${output}/${name}`, JSON.stringify(await buildProfile(sources, civil, kids)));
    if (log) console.log(`Wrote ${name}: 26 cantons × 461 rows`);
  }
  if (log) console.log('Wrote gemeinden-2026.json: 2110 authentic BFS IDs; official verification pending');
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  writeTables().catch(error => { console.error(error); process.exitCode = 1; });
}
