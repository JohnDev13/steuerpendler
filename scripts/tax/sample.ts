// Compares the shipped browser tax calculation with the broad official ESTV sample
// (tests/reference/estv-2026-sample.jsonl, captured by scripts/tax/estv-sample.mjs).
// Usage: npx tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/sample.ts [--canton XX] [--fail]
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { calculateTax, type Church, type Gemeinde, type TaxProfile } from '../../src/tax';
import { officialTolerance } from './official';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export interface SampleCase {
  id: string; bfs: number; city: string; canton: string; civil: 'single' | 'married'; kids: number; income: number;
  church: Church; responseSha256: string; response: Record<string, any>;
}

export async function loadSample(root = ROOT): Promise<SampleCase[]> {
  const text = await readFile(resolve(root, 'tests/reference/estv-2026-sample.jsonl'), 'utf8');
  return text.trimEnd().split('\n').map(line => JSON.parse(line));
}

export async function runSample(root = ROOT) {
  const cases = await loadSample(root);
  const data = async (file: string) => JSON.parse(await readFile(resolve(root, 'site/data', file), 'utf8'));
  const gemeinden = (await data('gemeinden-2026.json')).gemeinden as Record<string, Gemeinde>;
  const profiles: Record<string, TaxProfile> = {};
  const results = [];
  for (const c of cases) {
    const key = `tax-2026-${c.civil === 'married' ? 'm' : 's'}-${c.kids}.json`;
    profiles[key] ??= await data(key);
    const r = c.response;
    const official = r.TotalNetTax;
    const ours = calculateTax(profiles[key], gemeinden[String(c.bfs)], c.income, c.church);
    const components = {
      federal: [ours.bund, r.IncomeTaxFed], canton: [ours.kanton, r.IncomeTaxCanton], city: [ours.gemeinde, r.IncomeTaxCity],
      church: [ours.kirche, r.IncomeTaxChurch], personal: [ours.personal, r.PersonalTax],
    } as Record<string, [number, number]>;
    const error = Math.abs(ours.total - official);
    results.push({ ...c, official, ours: ours.total, error, passed: error <= officialTolerance(official), components,
      taxableCanton: r.TaxableIncomeCanton, simpleCanton: r.IncomeSimpleTaxCanton, taxCredit: r.TaxCredit });
  }
  return results;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const args = process.argv.slice(2);
  const canton = args.includes('--canton') ? args[args.indexOf('--canton') + 1] : null;
  const results = (await runSample()).filter(r => !canton || r.canton === canton);
  const byCanton = new Map<string, { n: number; fail: number; worst: number }>();
  for (const r of results) {
    const s = byCanton.get(r.canton) ?? { n: 0, fail: 0, worst: 0 };
    s.n++; if (!r.passed) s.fail++; s.worst = Math.max(s.worst, r.error);
    byCanton.set(r.canton, s);
  }
  console.log(`sample: ${results.filter(r => r.passed).length}/${results.length} within max(5, 0.1%)`);
  console.log([...byCanton].map(([k, s]) => `${k} ${s.n - s.fail}/${s.n}${s.fail ? ` worst ${s.worst}` : ''}`).join(' | '));
  if (args.includes('--fail')) for (const r of results.filter(r => !r.passed)) {
    const diff = Object.entries(r.components).filter(([, [a, b]]) => a !== b).map(([k, [a, b]]) => `${k} ${a}/${b}`).join(' ');
    console.log(`${r.id} ${r.canton} ${r.civil} ${r.kids} ${r.income} ${r.church}: ours ${r.ours} estv ${r.official} (${diff}) credit ${r.taxCredit}`);
  }
}
