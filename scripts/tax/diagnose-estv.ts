// Diagnostic: compare engine deductions and taxable income with ESTV line items for every frozen case.
// Usage: npx tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/diagnose-estv.ts [caseId...]
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { calculateTaxableAmount } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { dineroToNumber } from '../../vendor/swisstaxcalculator/lib/utils/dinero';
import { loadSources, makeInput, ROOT } from './build';

const sources = await loadSources();
const csv = (await readFile(resolve(ROOT, 'tests/reference/estv-2026.csv'), 'utf8')).trimEnd().split('\n');
const header = csv[0].split(',');
const col = (row: string[], name: string) => row[header.indexOf(name)];
const only = process.argv.slice(2);
for (const line of csv.slice(1)) {
  const row = line.split(',');
  const id = col(row, 'case_id');
  if (only.length && !only.includes(id)) continue;
  const bfs = Number(col(row, 'bfs'));
  const loc = sources.locations.find(l => l.BfsID === bfs)!;
  const civil = col(row, 'civil') === 'married' ? 'm' : 's';
  const kids = Number(col(row, 'kids') || col(row, 'children') || 0);
  const church = (col(row, 'church') || 'none') as 'none' | 'reformed' | 'catholic';
  const income = Number(col(row, 'income') || col(row, 'gross_income'));
  const input = makeInput(loc, civil, kids, income, church);
  const t = await calculateTaxableAmount(input);
  const estv = JSON.parse(await readFile(resolve(ROOT, `tests/reference/estv-2026/${id}-tax.response.json`), 'utf8')).response;
  console.log(`\n== ${id} ${loc.Canton} ${loc.BfsName} ${civil} kids=${kids} ${income} ${church}`);
  console.log(`taxable canton engine ${dineroToNumber(t.taxableIncomeCanton)} estv ${estv.TaxableIncomeCanton} | fed engine ${dineroToNumber(t.taxableIncomeBund)} estv ${estv.TaxableIncomeFed}`);
  console.log('engine canton deductions:', t.deductionsIncome.map((d: any) => `${d.id}${d.target ? '/' + d.target : ''}=${typeof d.amountCanton === "number" ? d.amountCanton : dineroToNumber(d.amountCanton)}`).join(' '));
  console.log('estv canton lines:', estv.InfoCanton.map((e: any) => `${e.Entry.DE}=${e.Value}`).join(' | '));
}
