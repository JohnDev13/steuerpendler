import { expect, test } from 'vitest';
import { readFile } from 'node:fs/promises';
import { ROOT } from './build';

test('reference executes all 29 original scenarios and preserves historical values without inventing official results', async () => {
  const module = await import('./reference');
  const spec = await readFile(`${ROOT}SPEC.md`, 'utf8');
  const cases = module.parseOriginalScenarios(spec);
  expect(cases).toHaveLength(29);
  expect(cases[0]).toMatchObject({ bfs: 261, civil: 's', kids: 0, income: 120000, church: 'none', historicalEngine: 17407 });
  expect(cases.find(x => x.bfs === 6266)?.historicalEngine).toBe(23933);
  const report = await module.runReference();
  expect(report.results).toHaveLength(29);
  expect(report.officialVerification).toBe('pending');
  for (const row of report.results) {
    expect(row.officialEstv).toBeNull();
    expect(Number.isFinite(row.engine)).toBe(true);
    expect(row.historicalDrift).toBe(row.engine - row.historicalEngine);
    expect(row.tableError).toBe(Math.abs(row.reconstructed - row.engine));
    expect(row.tablePassed).toBe(row.tableError <= 10);
  }
  expect(report.passed).toBe(report.results.every(x => x.tablePassed));
  expect(() => module.parseOriginalScenarios(spec.replace('| Zürich | ZH | 261 |', '| Zürich | ZH | invalid |'))).toThrow();
});
