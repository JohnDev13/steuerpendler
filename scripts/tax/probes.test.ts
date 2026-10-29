// Targeted official ESTV probes (tests/reference/estv-2026-probes, captured by scripts/tax/estv-probe.mjs).
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from 'vitest';
import { calculateTax, type Gemeinde, type TaxProfile } from '../../src/tax';

const ROOT = resolve(import.meta.dirname, '../..');
const load = async (name: string) => (await readFile(resolve(ROOT, 'tests/reference/estv-2026-probes', `${name}.jsonl`), 'utf8'))
  .trimEnd().split('\n').map(line => JSON.parse(line));
const data = async (file: string) => JSON.parse(await readFile(resolve(ROOT, 'site/data', file), 'utf8'));

test('personal and church personal tax match ESTV in every canton (patch 21)', async () => {
  const gemeinden = (await data('gemeinden-2026.json')).gemeinden as Record<string, Gemeinde>;
  const profiles: Record<string, TaxProfile> = { s: await data('tax-2026-s-0.json'), m: await data('tax-2026-m-0.json') };
  const cases = await load('personal-church');
  expect(cases).toHaveLength(156);
  for (const c of cases) {
    const ours = calculateTax(profiles[c.civil[0]], gemeinden[String(c.bfs)], c.income, c.church);
    expect(ours.personal, `${c.canton} ${c.civil} ${c.church}`).toBe(c.response.PersonalTax);
  }
});
