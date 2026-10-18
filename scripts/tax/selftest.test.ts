import { expect, test } from 'vitest';
import { loadSources } from './build';
import { mkdtemp, cp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

test('runner evaluates files against the full engine and fails closed on a corrupted artifact', async () => {
  const module = await import('./selftest');
  expect(module, 'missing executable engine-comparison runner').toHaveProperty('runSelftest');
  const dir = await mkdtemp(join(tmpdir(), 'tax-gate-'));
  try {
    await cp(new URL('../../site/data/', import.meta.url), dir, { recursive: true });
    const path = join(dir, 'tax-2026-s-0.json');
    const profile = JSON.parse(await readFile(path, 'utf8'));
    for (const rows of Object.values(profile.cantons) as number[][][]) for (const row of rows) row[0] += 1000000;
    await writeFile(path, JSON.stringify(profile));
    const report = await module.runSelftest(dir);
    expect(report.onGrid.count).toBe(500);
    expect(report.offGrid.count).toBe(300);
    expect(report.onGrid.results).toHaveLength(500);
    expect(report.offGrid.results).toHaveLength(300);
    expect(report.passed).toBe(false);
    expect(report.exitCode).toBe(1);
    expect(report.onGrid.maxAbsoluteError).toBeGreaterThan(900000);
    expect(report.onGrid.failures.some(x => x.civil === 's' && x.kids === 0 && x.error > x.tolerance)).toBe(true);
    expect(report.onGrid.results.some(x => x.error <= x.tolerance)).toBe(true);
    for (const [kind, rows] of [['onGrid', report.onGrid.results], ['offGrid', report.offGrid.results]] as const) {
      for (const x of rows) {
        expect(x).toEqual(expect.objectContaining({
          bfs: expect.any(Number), canton: expect.any(String), civil: expect.stringMatching(/^(s|m)$/),
          kids: expect.any(Number), church: expect.stringMatching(/^(none|reformed|catholic)$/), income: expect.any(Number),
          expected: expect.any(Number), actual: expect.any(Number), error: expect.any(Number), tolerance: expect.any(Number),
        }));
        expect(x.error).toBe(Math.abs(x.actual - x.expected));
        expect(x.tolerance).toBe(kind === 'offGrid' ? 10 : Math.max(2, Math.abs(x.expected) * 0.0001));
      }
    }
    expect(report.onGrid.failures).toEqual(report.onGrid.results.filter(x => x.error > x.tolerance));
    expect(report.offGrid.failures).toEqual(report.offGrid.results.filter(x => x.error > x.tolerance));
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('selftest deterministically samples exactly 500 grid and 300 non-grid actual inputs across all cantons', async () => {
  const { sampleCases } = await import('./selftest');
  const sources = await loadSources();
  const cases = sampleCases(sources, 0x2026);
  expect(cases).toEqual(sampleCases(sources, 0x2026));
  expect(cases).not.toEqual(sampleCases(sources, 0x2027));
  expect(cases.onGrid).toHaveLength(500);
  expect(cases.offGrid).toHaveLength(300);
  for (const [label, rows] of Object.entries(cases)) {
    expect(new Set(rows.map(x => x.loc.Canton)).size).toBe(26);
    expect(new Set(rows.map(x => `${x.civil}-${x.kids}`)).size).toBe(8);
    expect(new Set(rows.map(x => x.church)).size).toBe(3);
    expect(rows.every(x => x.income >= 40000 && x.income <= 500000)).toBe(true);
    expect(rows.every(x => (x.income % 1000 === 0) === (label === 'onGrid'))).toBe(true);
  }
});
