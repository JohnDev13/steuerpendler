import { calculateTaxableAmount, calculateTaxesBase } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { dineroToNumber, dineroChf } from '../../vendor/swisstaxcalculator/lib/utils/dinero';
import { loadSources, makeInput } from './build';
import { loadSample } from './sample';
const sources = await loadSources();
const ids = process.argv.slice(2);
for (const c of (await loadSample()).filter(c => ids.includes(c.id))) {
  const loc = sources.locations.find(l => l.BfsID === c.bfs)!;
  const input = makeInput(loc, c.civil === 'married' ? 'm' : 's', c.kids, c.income, c.church);
  const t = await calculateTaxableAmount(input);
  const b = await calculateTaxesBase(input, t.taxableIncomeCanton, dineroChf(0));
  const r = c.response;
  console.log(`\n== ${c.id} ${c.canton} ${c.civil} kids=${c.kids} ${c.income}`);
  console.log(`taxable canton ours ${dineroToNumber(t.taxableIncomeCanton)} estv ${r.TaxableIncomeCanton} (rate-determining estv ${r.AssertiveIncomeCanton}) | simple ours ${dineroToNumber(b.taxesIncomeBase)} estv ${r.IncomeSimpleTaxCanton}`);
  console.log('ours:', t.deductionsIncome.map((d: any) => `${d.id}${d.target ? '/' + d.target : ''}=${typeof d.amountCanton === 'number' ? d.amountCanton : dineroToNumber(d.amountCanton)}`).join(' '));
  console.log('estv:', r.InfoCanton.map((e: any) => `${e.Entry.DE}=${e.Value}`).join(' | '));
}
