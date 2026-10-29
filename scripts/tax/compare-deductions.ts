// Diagnostic: ESTV canton deduction lines vs engine deductions across the deductions-grid probe for one canton.
// Usage: npx tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/compare-deductions.ts XX [profile]
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { calculateTaxableAmount } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { dineroToNumber } from '../../vendor/swisstaxcalculator/lib/utils/dinero';
import { loadSources, makeInput, ROOT } from './build';
const [canton, profile] = process.argv.slice(2);
const sources = await loadSources();
const cases = (await readFile(resolve(ROOT, 'tests/reference/estv-2026-probes/deductions-grid.jsonl'), 'utf8')).trimEnd().split('\n').map(l => JSON.parse(l))
  .filter(c => c.canton === canton && (!profile || `${c.civil[0]}${c.kids}` === profile));
for (const c of cases) {
  const loc = sources.locations.find(l => l.BfsID === c.bfs)!;
  const t = await calculateTaxableAmount(makeInput(loc, c.civil === 'married' ? 'm' : 's', c.kids, c.income, c.church));
  const ours = dineroToNumber(t.taxableIncomeCanton), r = c.response;
  const lines = r.InfoCanton.filter((e: any) => !['TXT_1', 'TXT_54'].includes(e.Entry.ID)).map((e: any) => `${e.Entry.ID}=${-e.Value}`).join(' ');
  const mine = t.deductionsIncome.map((d: any) => `${d.id.replace('_EK', '')}=${typeof d.amountCanton === 'number' ? d.amountCanton : dineroToNumber(d.amountCanton)}`).filter((s: string) => !s.endsWith('=0')).join(' ');
  console.log(`${c.civil[0]}${c.kids} ${String(c.income / 1000).padStart(3)}k diff ${String(ours - r.TaxableIncomeCanton).padStart(6)} | estv ${lines} | ours ${mine}`);
}
