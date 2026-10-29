import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from 'vitest';
import { loadSample, runSample } from './sample';
import { QUARANTINED_CANTONS, TAX_WITHHELD } from '../../src/withheld';

const ROOT = resolve(import.meta.dirname, '../..');
// Ratchet: cases of the broad official sample outside max(CHF 5, 0.1%). May only go down; lower it in the same
// PR that fixes cases.
const MAX_SAMPLE_FAILURES = 46;

test('broad ESTV sample covers every canton and profile with official evidence', async () => {
  const cases = await loadSample(ROOT);
  expect(cases).toHaveLength(650);
  expect(new Set(cases.map(c => c.canton)).size).toBe(26);
  for (const c of cases) {
    expect(c.responseSha256).toMatch(/^[0-9a-f]{64}$/);
    expect(c.response.Location.BfsID).toBe(c.bfs);
    expect(Number.isFinite(c.response.TotalNetTax)).toBe(true);
  }
});

test('every canton x profile more than 5% off ESTV is withheld', async () => {
  for (const r of await runSample(ROOT)) {
    if (r.error <= 0.05 * Math.abs(r.official) || QUARANTINED_CANTONS.has(r.canton)) continue;
    const keys = r.civil === 'single' && r.kids === 2 ? ['s1', 's2', 's3'] : [`${r.civil[0]}${r.kids}`];
    for (const key of keys)
      expect(TAX_WITHHELD[key], `${r.id} ${r.canton} ${key}: ${r.ours} vs ESTV ${r.official}`).toContain(r.canton);
  }
});

test('broad ESTV sample does not regress', async () => {
  const failures = (await runSample(ROOT)).filter(r => !r.passed).length;
  expect(failures, 'sample failures regressed').toBeLessThanOrEqual(MAX_SAMPLE_FAILURES);
});

test('the withheld list is current: nothing is withheld that the sample shows within 5%', async () => {
  const bad = new Set<string>();
  for (const r of await runSample(ROOT)) {
    if (r.error <= 0.05 * Math.abs(r.official)) continue;
    const keys = r.civil === 'single' && r.kids === 2 ? ['s1', 's2', 's3'] : [`${r.civil[0]}${r.kids}`];
    for (const key of keys) bad.add(`${key}:${r.canton}`);
  }
  for (const [key, cantons] of Object.entries(TAX_WITHHELD))
    for (const canton of cantons) expect(bad.has(`${key}:${canton}`), `${key} ${canton} is withheld but within 5%`).toBe(true);
  expect(await readFile(resolve(ROOT, 'tests/reference/estv-2026-sample.jsonl'), 'utf8')).not.toBe('');
});
