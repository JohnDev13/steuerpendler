// VS against the official 2026 ESTV results (vendor patch 31): the 173 % cantonal index, family rebates and the CHF 10
// minimum, every commune's own index and communal tariff, the church tax on the communal tax and the single low-income
// deduction. Incomes below the site's CHF 40,000 minimum are clamped by the site and not compared.
import { readFile } from 'node:fs/promises';
import { expect, test } from 'vitest';
import { COMMUNAL_INDEX_FILE, deriveCommunalIndex } from './communal-index';
import { runGemeinden } from './gemeinden';

const VS_PROBES = ['vd-vs-grid', 'vs-gemeinden', 'vs-modest', 'vs-modest-edges'];

test('every VS ESTV capture from CHF 40,000 matches within max(CHF 5, 0.1%)', async () => {
  const results = (await runGemeinden(undefined, VS_PROBES)).filter(r => r.canton === 'VS' && r.income >= 40000);
  expect(new Set(results.map(r => r.bfs)).size).toBe(122);
  expect(results.filter(r => !r.passed).map(r => `${r.name} ${r.profile} ${r.church} ${r.income}: ${r.ours} vs ${r.official}`)).toEqual([]);
}, 120000);

test('the VS communal index file is exactly what the ESTV captures give', async () => {
  const shipped = JSON.parse(await readFile(COMMUNAL_INDEX_FILE, 'utf8')).gemeinden;
  expect(shipped).toEqual(await deriveCommunalIndex());
  expect(Object.keys(shipped)).toHaveLength(122);
});
