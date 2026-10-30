// Derives each VS commune's income-tax index (vendor patch 31) from official ESTV captures and writes
// vendor/swisstaxcalculator/data/communal-index/2026.json. VS communes de-index the taxable income with their own index
// (110-176 %) before applying the communal tariff; the ESTV data tables do not carry it. For every commune exactly one
// whole-percent index must reproduce ESTV's communal tax for the single, no-church capture (no family rebate applies).
// Usage: npx tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/communal-index.ts [--write]
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { applyTariffRounding, calculateTaxesAmount } from '../../vendor/swisstaxcalculator/lib/taxes/tarif';
import { getCommunalIncomeTarif } from '../../vendor/swisstaxcalculator/lib/taxes/tarif/provider';
import { dineroChf, dineroToNumber } from '../../vendor/swisstaxcalculator/lib/utils/dinero';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export const COMMUNAL_INDEX_FILE = resolve(ROOT, 'vendor/swisstaxcalculator/data/communal-index/2026.json');

export async function deriveCommunalIndex(root = ROOT) {
  const tarif = await getCommunalIncomeTarif(24, 2026);
  if (!tarif) throw new Error('No VS communal tariff (data/parsed/2026/tarifs/24-gemeinde.json)');
  const factors = new Map<number, number>(JSON.parse(await readFile(resolve(root, 'vendor/swisstaxcalculator/data/parsed/2026/factors/24.json'), 'utf8'))
    .map((f: any) => [f.Location.BfsID, f.IncomeRateCity]));
  const text = await readFile(resolve(root, 'tests/reference/estv-2026-probes/vs-gemeinden.jsonl'), 'utf8');
  const gemeinden: Record<string, { name: string; index: number }> = {};
  for (const line of text.trimEnd().split('\n')) {
    const c = JSON.parse(line);
    if (c.civil !== 'single' || c.kids !== 0 || c.church !== 'none' || c.income !== 90000) continue;
    const taxable = c.response.TaxableIncomeCanton as number, city = c.response.IncomeTaxCity as number;
    const coefficient = factors.get(c.bfs);
    if (coefficient === undefined) throw new Error(`No VS factor for ${c.bfs}`);
    const fits: number[] = [];
    for (let index = 100; index <= 200; index++) {
      const simple = applyTariffRounding('index', taxable, 1, a => dineroToNumber(calculateTaxesAmount(dineroChf(a, 5), tarif)), { index });
      if (Math.abs(simple * coefficient / 100 - city) <= 1) fits.push(index);
    }
    if (fits.length !== 1) throw new Error(`${c.bfs} ${c.city}: ${fits.length} indexes fit (${fits.join(', ')})`);
    gemeinden[c.bfs] = { name: c.city, index: fits[0] };
  }
  return Object.fromEntries(Object.entries(gemeinden).sort(([a], [b]) => Number(a) - Number(b)));
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const gemeinden = await deriveCommunalIndex();
  console.log(`communal index: ${Object.keys(gemeinden).length} VS Gemeinden`);
  if (process.argv.includes('--write')) {
    await mkdir(dirname(COMMUNAL_INDEX_FILE), { recursive: true });
    await writeFile(COMMUNAL_INDEX_FILE, JSON.stringify({ note: 'Steuerpendler patch 31: income-tax index (%) of each VS commune, derived by scripts/tax/communal-index.ts from official ESTV captures (tests/reference/estv-2026-probes/vs-gemeinden.jsonl); do not edit by hand.', year: 2026, gemeinden }, null, 1) + '\n');
    console.log(`wrote ${COMMUNAL_INDEX_FILE}`);
  }
}
