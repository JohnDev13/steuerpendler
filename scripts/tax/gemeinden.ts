// Compares the shipped browser tax calculation with the ESTV results for every reachable Gemeinde
// (tests/reference/estv-2026-probes/gemeinden-reachable.jsonl, captured by the ESTV probe workflow).
// Usage: npx tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/gemeinden.ts [--fail] [--canton XX]
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { calculateTax, type Gemeinde, type TaxProfile } from '../../src/tax';
import { officialTolerance } from './official';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export const COMPONENTS = ['federal', 'canton', 'city', 'church', 'personal'] as const;

export async function runGemeinden(root = ROOT) {
  const text = await readFile(resolve(root, 'tests/reference/estv-2026-probes/gemeinden-reachable.jsonl'), 'utf8');
  const cases = text.trimEnd().split('\n').map(line => JSON.parse(line));
  const data = async (file: string) => JSON.parse(await readFile(resolve(root, 'site/data', file), 'utf8'));
  const gemeinden = (await data('gemeinden-2026.json')).gemeinden as Record<string, Gemeinde>;
  const profiles: Record<string, TaxProfile> = {};
  return Promise.all(cases.map(async c => {
    const key = `tax-2026-${c.civil === 'married' ? 'm' : 's'}-${c.kids}.json`;
    profiles[key] ??= await data(key);
    const r = c.response, ours = calculateTax(profiles[key], gemeinden[String(c.bfs)], c.income, c.church);
    const components: Record<string, [number, number]> = {
      federal: [ours.bund, r.IncomeTaxFed], canton: [ours.kanton, r.IncomeTaxCanton], city: [ours.gemeinde, r.IncomeTaxCity],
      church: [ours.kirche, r.IncomeTaxChurch], personal: [ours.personal, r.PersonalTax],
    };
    const error = Math.abs(ours.total - r.TotalNetTax);
    return { id: c.id as string, bfs: c.bfs as number, name: c.city as string, canton: c.canton as string, profile: `${c.civil[0]}${c.kids}`,
      church: c.church as string, income: c.income as number, official: r.TotalNetTax as number, ours: ours.total, error,
      relative: r.TotalNetTax ? error / r.TotalNetTax : 0, passed: error <= officialTolerance(r.TotalNetTax), components };
  }));
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = process.argv.slice(2), canton = args.includes('--canton') ? args[args.indexOf('--canton') + 1] : undefined;
  const results = (await runGemeinden()).filter(r => !canton || r.canton === canton);
  const byCanton = new Map<string, typeof results>();
  for (const r of results) byCanton.set(r.canton, [...(byCanton.get(r.canton) ?? []), r]);
  console.log(`gemeinden: ${results.filter(r => r.passed).length}/${results.length} within max(5, 0.1%)`);
  console.log([...byCanton].map(([k, rs]) => `${k} ${rs.filter(r => r.passed).length}/${rs.length}`).join(' | '));
  if (args.includes('--fail')) for (const r of results.filter(x => !x.passed).sort((a, b) => b.relative - a.relative)) {
    const off = COMPONENTS.filter(k => Math.abs(r.components[k][0] - r.components[k][1]) > 1)
      .map(k => `${k} ${r.components[k][0]}/${r.components[k][1]}`).join(' ');
    console.log(`${r.canton} ${r.bfs} ${r.name} ${r.profile} ${r.church} ${r.income}: ours ${r.ours} estv ${r.official} (${(100 * r.relative).toFixed(2)} %) ${off}`);
  }
}
