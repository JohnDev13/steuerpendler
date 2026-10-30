// Derives per-Gemeinde personal taxes (vendor patch 27) from official ESTV probe captures and writes
// vendor/swisstaxcalculator/data/personal/2026.json. SO levies a communal personal tax and a church personal tax
// per person whose amounts differ by Gemeinde; the engine's cantonal constant only fits the capital.
// Usage: npx tsx --tsconfig scripts/tax/tsconfig.json scripts/tax/personal.ts [--write]
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export const PERSONAL_FILE = resolve(ROOT, 'vendor/swisstaxcalculator/data/personal/2026.json');
const PROBES = ['gemeinden-reachable', 'so-personal-bl-church', 'so-personal-rest'];
const CANTONS = ['SO'];

export interface PersonalEntry { name: string; amount: number; protestant: number; roman: number }

export async function derivePersonal(root = ROOT) {
  const seen = new Map<number, { name: string; values: Map<string, number> }>();
  for (const probe of PROBES) {
    let text: string;
    try { text = await readFile(resolve(root, 'tests/reference/estv-2026-probes', `${probe}.jsonl`), 'utf8'); } catch { continue; }
    for (const line of text.trimEnd().split('\n')) {
      const c = JSON.parse(line);
      if (!CANTONS.includes(c.canton)) continue;
      const entry = seen.get(c.bfs) ?? { name: c.city, values: new Map() };
      const key = `${c.civil[0]}-${c.church}`, value = c.response.PersonalTax as number;
      if (entry.values.has(key) && entry.values.get(key) !== value) throw new Error(`Conflicting personal tax for ${c.bfs} ${key}`);
      entry.values.set(key, value);
      seen.set(c.bfs, entry);
    }
  }
  const gemeinden: Record<string, PersonalEntry> = {};
  for (const [bfs, { name, values }] of [...seen].sort((a, b) => a[0] - b[0])) {
    const single = (church: string) => values.get(`s-${church}`);
    const base = single('none'), reformed = single('reformed'), catholic = single('catholic');
    if (base === undefined || reformed === undefined || catholic === undefined) throw new Error(`Incomplete personal-tax evidence for ${bfs} ${name}`);
    const entry = { name, amount: base, protestant: reformed - base, roman: catholic - base };
    // Married households pay per person: every married capture must equal twice the single amounts.
    for (const [church, extra] of [['none', 0], ['reformed', entry.protestant], ['catholic', entry.roman]] as const) {
      const married = values.get(`m-${church}`);
      if (married !== undefined && married !== 2 * (base + extra)) throw new Error(`Married personal tax ${bfs} ${church}: ${married} != 2 x ${base + extra}`);
    }
    gemeinden[bfs] = entry;
  }
  return gemeinden;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const gemeinden = await derivePersonal();
  console.log(`personal: ${Object.keys(gemeinden).length} Gemeinden (${CANTONS.join(', ')})`);
  if (process.argv.includes('--write')) {
    const file = { note: 'Steuerpendler patch 27: personal tax per person by Gemeinde (amount without church; protestant/roman = church personal tax per person). Derived by scripts/tax/personal.ts from official ESTV captures in tests/reference/estv-2026-probes; do not edit by hand.',
      year: 2026, gemeinden };
    await writeFile(PERSONAL_FILE, JSON.stringify(file, null, 1) + '\n');
    console.log(`wrote ${PERSONAL_FILE}`);
  }
}
