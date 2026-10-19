import { readFile } from 'node:fs/promises';
import { expect, it } from 'vitest';
import { TaxRepository } from './tax';

async function profile() {
  return JSON.parse(await readFile(new URL('../site/data/tax-2026-s-0.json', import.meta.url), 'utf8'));
}
function repository(value: unknown) {
  return new TaxRepository(async () => new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } }));
}

it('requires one validated precision program for every serialized canton in schema v2', async () => {
  const p = await profile();
  delete p.precision.AG;
  await expect(repository(p).loadProfile('s', 0)).rejects.toThrow(/precision/i);
});

it.each([
  ['unknown deduction format', (p: any) => { p.precision.AG.bund.deductions[0].format = 'SURPRISE'; }],
  ['non-numeric deduction field', (p: any) => { p.precision.AG.bund.deductions[0].amount = null; }],
  ['unknown tariff type', (p: any) => { p.precision.AG.bund.tariff.type = 'SCRIPT'; }],
  ['malformed schema version', (p: any) => { p.meta.schemaVersion = '2'; }],
  ['unsupported formula characters', (p: any) => {
    const part = Object.values(p.precision).map((x: any) => x.canton).find((x: any) => x.tariff.type === 'FORMEL') as any;
    part.tariff.table[0].formula = '$wert$ + globalThis.alert(1)';
  }],
])('rejects malformed schema-v2 precision payload: %s', async (_name, mutate) => {
  const p = await profile();
  mutate(p);
  await expect(repository(p).loadProfile('s', 0)).rejects.toThrow(/precision/i);
});

it('accepts all 26 authentic schema-v2 precision programs', async () => {
  const p = await profile();
  await expect(repository(p).loadProfile('s', 0)).resolves.toBeTruthy();
});
