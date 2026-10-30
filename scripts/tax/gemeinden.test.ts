// Every Gemeinde the site can show, against official ESTV results (vendor patches 26 and 27).
import { expect, test } from 'vitest';
import { derivePersonal, PERSONAL_FILE } from './personal';
import { runGemeinden } from './gemeinden';
import { readFile } from 'node:fs/promises';

test('every reachable Gemeinde matches ESTV within max(CHF 5, 0.1%)', async () => {
  const results = await runGemeinden();
  expect(results.length).toBeGreaterThanOrEqual(1452);
  const failures = results.filter(r => !r.passed).map(r => `${r.canton} ${r.bfs} ${r.name} ${r.profile} ${r.church}: ${r.ours} vs ${r.official}`);
  expect(failures).toEqual([]);
}, 120000);

test('the per-Gemeinde personal-tax file is exactly what the ESTV captures give', async () => {
  const shipped = JSON.parse(await readFile(PERSONAL_FILE, 'utf8')).gemeinden;
  expect(shipped).toEqual(await derivePersonal());
});
