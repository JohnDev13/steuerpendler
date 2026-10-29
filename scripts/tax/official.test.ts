import { createHash } from 'node:crypto';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { expect, test } from 'vitest';
import { compareComponents, officialTolerance, runOfficialComparison, verifyResponseEvidence } from './official';

const ROOT = resolve(import.meta.dirname, '../..');

test('official threshold is inclusive and uses the larger CHF 5 or 0.1% bound', () => {
  expect(officialTolerance(1_000)).toBe(5);
  expect(officialTolerance(-10_000)).toBe(10);
  expect(Math.abs(1_005 - 1_000)).toBeLessThanOrEqual(officialTolerance(1_000));
  expect(Math.abs(1_005.01 - 1_000)).toBeGreaterThan(officialTolerance(1_000));
});

test('response evidence rejects a malformed digest and a digest mismatch', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'official-evidence-'));
  const evidence = join(directory, 'response.json');
  await writeFile(evidence, '{"TotalNetTax":123}');
  await expect(verifyResponseEvidence(evidence, 'xyz')).rejects.toThrow(/SHA-256/);
  await expect(verifyResponseEvidence(evidence, '0'.repeat(64))).rejects.toThrow(/mismatch/);
  const digest = createHash('sha256').update('{"TotalNetTax":123}').digest('hex');
  await expect(verifyResponseEvidence(evidence, digest)).resolves.toBe(digest);
});

test('component comparison records amounts, absolute errors, and neutral mismatch group', () => {
  const frontend = { bund: 110, kanton: 205, gemeinde: 300, kirche: 40, personal: 10 };
  const official = { IncomeTaxFed: 100, IncomeTaxCanton: 200, IncomeTaxCity: 300, IncomeTaxChurch: 40, PersonalTax: 10 };
  expect(compareComponents(frontend, official)).toEqual({
    components: {
      federal: { frontend: 110, official: 100, error: 10 },
      canton: { frontend: 205, official: 200, error: 5 },
      city: { frontend: 300, official: 300, error: 0 },
      church: { frontend: 40, official: 40, error: 0 },
      personal: { frontend: 10, official: 10, error: 0 },
    },
    mismatchGroup: 'mixed',
  });
  expect(compareComponents({ ...frontend, bund: 100 }, official).mismatchGroup).toBe('non-federal-only');
  expect(compareComponents({ ...frontend, kanton: 200 }, official).mismatchGroup).toBe('federal-only');
  expect(compareComponents({ ...frontend, bund: 100, kanton: 200 }, official).mismatchGroup).toBe(null);
});

// Ratchet: the official comparison is not yet green. The count of failing ESTV cases
// may only go down; lower this constant in the same PR that fixes a case.
const MAX_OFFICIAL_FAILURES = 3;

test('29-case ESTV catalogue is complete, evidence-bound and does not regress', async () => {
  const report = await runOfficialComparison(ROOT);
  expect(report).toMatchObject({
    sourceCsvSha256: 'ab4ed7731d7165ec5f2afe71f5310713b5797b031f4436edc7e941c63ac0e3b3',
    coverage: { expected: 29, compared: 29, exact: true },
    officialApproval: 'pending',
  });
  expect(report.numericFailureCount, 'ESTV failures regressed').toBeLessThanOrEqual(MAX_OFFICIAL_FAILURES);
  for (const [name, digest] of Object.entries(report.artifactSha256)) {
    const bytes = await readFile(resolve(ROOT, 'site/data', name));
    expect(createHash('sha256').update(bytes).digest('hex'), name).toBe(digest);
  }

  const csv = await readFile(resolve(ROOT, 'tests/reference/estv-2026.csv'), 'utf8');
  const [headerLine, ...rowLines] = csv.trimEnd().split('\n');
  const header = headerLine.split(',');
  const caseIndex = header.indexOf('case_id');
  const requestIndex = header.indexOf('request_sha256');
  expect(rowLines).toHaveLength(29);
  await Promise.all(rowLines.map(async line => {
    const row = line.replace(/\r$/, '').split(',');
    const request = await readFile(resolve(ROOT, `tests/reference/estv-2026/${row[caseIndex]}-tax.request.json`));
    expect(createHash('sha256').update(request).digest('hex')).toBe(row[requestIndex]);
  }));
});

test('Methode page states the current ESTV comparison result, not a stale one', async () => {
  const report = await runOfficialComparison(ROOT);
  const html = await readFile(resolve(ROOT, 'pages/methode.html'), 'utf8');
  const passed = report.coverage.compared - report.numericFailureCount;
  expect(html).toContain(`<strong>${passed} von 29</strong>`);
  expect(html).toContain(`<strong>${report.numericFailureCount} von 29</strong>`);
});

test('every canton more than 5% off its ESTV reference case is quarantined', async () => {
  const report = await runOfficialComparison(ROOT);
  const source = await readFile(resolve(ROOT, 'src/withheld.ts'), 'utf8');
  const listed = new Set([...source.matchAll(/QUARANTINED_CANTONS[^=]*= new Set\(\[([^\]]*)\]/g)][0][1].match(/[A-Z]{2}/g));
  const badlyOff = report.results.filter((r: { error: number; official: number }) => r.error > 0.05 * Math.abs(r.official)).map((r: { canton: string }) => r.canton);
  for (const canton of badlyOff) expect(listed.has(canton), `${canton} deviates >5% from ESTV but is not quarantined`).toBe(true);
});
