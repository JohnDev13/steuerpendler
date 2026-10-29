// Diagnostic: where does each failing sample case diverge from ESTV? taxable income (deductions), simple tax
// (tariff/splitting) or the final amount (multipliers, credits). Usage: tsx ... scripts/tax/classify-sample.ts
import { calculateTaxableAmount, calculateTaxesBase } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { dineroToNumber, dineroChf } from '../../vendor/swisstaxcalculator/lib/utils/dinero';
import { loadSources, makeInput } from './build';
import { runSample } from './sample';
const sources = await loadSources();
const by = new Map<string, string[]>();
for (const r of (await runSample()).filter(r => !r.passed)) {
  const loc = sources.locations.find(l => l.BfsID === r.bfs)!;
  const input = makeInput(loc, r.civil === 'married' ? 'm' : 's', r.kids, r.income, r.church);
  const t = await calculateTaxableAmount(input);
  const taxable = dineroToNumber(t.taxableIncomeCanton);
  const e = r.response;
  let kind: string;
  if (Math.abs(taxable - e.TaxableIncomeCanton) > 1) kind = 'deductions';
  else {
    const simple = dineroToNumber((await calculateTaxesBase(input, t.taxableIncomeCanton, dineroChf(0))).taxesIncomeBase);
    if (Math.abs(simple - e.IncomeSimpleTaxCanton) > 1.5) kind = 'tariff';
    else if (r.components.federal[0] !== r.components.federal[1] && r.components.canton[0] === r.components.canton[1]) kind = 'federal';
    else kind = e.TaxCredit ? 'credit' : 'final';
  }
  const key = `${r.canton} ${kind}`;
  by.set(key, [...(by.get(key) ?? []), `${r.civil[0]}${r.kids}/${r.income / 1000}k`]);
}
for (const [k, v] of [...by].sort()) console.log(k.padEnd(16), v.length, v.join(' '));
