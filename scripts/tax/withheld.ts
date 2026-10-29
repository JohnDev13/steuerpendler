// Regenerates TAX_WITHHELD in src/withheld.ts from the broad ESTV sample: every canton x profile more than 5% off
// ESTV is withheld (single parents are sampled with 2 children; 1 and 3+ follow). Prints the sample result.
// Usage: npx tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/withheld.ts [--write]
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { runSample } from './sample';
import { QUARANTINED_CANTONS } from '../../src/withheld';

const results = await runSample();
const cells = new Map<string, Set<string>>();
for (const r of results) {
  if (r.error <= 0.05 * Math.abs(r.official) || QUARANTINED_CANTONS.has(r.canton)) continue;
  const key = `${r.civil[0]}${r.kids}`;
  for (const k of key === 's2' ? ['s1', 's2', 's3'] : [key]) {
    if (!cells.has(k)) cells.set(k, new Set());
    cells.get(k)!.add(r.canton);
  }
}
const body = '{\n' + ['s0', 's1', 's2', 's3', 'm0', 'm1', 'm2', 'm3']
  .map(k => `  ${k}: [${[...(cells.get(k) ?? [])].sort().map(c => `'${c}'`).join(', ')}],\n`).join('') + '}';
const failures = results.filter(r => !r.passed).length;
console.log(`sample ${results.length - failures}/${results.length} pass; withheld cells ${[...cells.values()].reduce((n, s) => n + s.size, 0)}`);
if (process.argv.includes('--write')) {
  const file = resolve(import.meta.dirname, '../../src/withheld.ts');
  const source = await readFile(file, 'utf8');
  await writeFile(file, source.replace(/(export const TAX_WITHHELD[^=]*= )\{[^}]*\};/, `$1${body};`));
  const test = resolve(import.meta.dirname, 'sample.test.ts');
  await writeFile(test, (await readFile(test, 'utf8')).replace(/const MAX_SAMPLE_FAILURES = \d+;/, `const MAX_SAMPLE_FAILURES = ${failures};`));
}
