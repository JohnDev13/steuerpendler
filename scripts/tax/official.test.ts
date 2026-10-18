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

test('frozen 29-case catalogue preserves exact hashes and the failed pending official gate', async () => {
  const report = await runOfficialComparison(ROOT);
  const frozenReport = JSON.parse(await readFile(resolve(ROOT, 'docs/tax/official-comparison-report.json'), 'utf8'));
  expect(report).toEqual(frozenReport);
  expect(report).toMatchObject({
    sourceCsvSha256: 'ab4ed7731d7165ec5f2afe71f5310713b5797b031f4436edc7e941c63ac0e3b3',
    coverage: { expected: 29, compared: 29, exact: true },
    comparability: 'owner_pending',
    officialApproval: 'pending',
    numericFailureCount: 20,
    numericPassed: false,
    passed: false,
    exitCode: 1,
  });
  expect(report.artifactSha256).toEqual({
    'gemeinden-2026.json': '0cc01b0d5f9fab1a0069394a9b89441ca4264ea0ba7e114e89157c2f748a5928',
    'tax-2026-s-0.json': '8829984d1737450f535eb805ef9d4ef8b7a561cc2a808ce557fd7901e36bf18d',
    'tax-2026-s-1.json': 'f3f311bc8f92c5e470169ebcb1934a0a01696efaf565bc7e8aef0034d6556724',
    'tax-2026-s-2.json': '6be3789933844cbe7c1ed843fc1dc3563457230d67675c540631964badfda72c',
    'tax-2026-s-3.json': '2dbd3addae10a82be1416a16ef05902178bb537883d2ff7b8f445d480e306336',
    'tax-2026-m-0.json': '5b76fde85c93076e9ce60adc85cc21507b7a405c198b1ebf620869361ca627aa',
    'tax-2026-m-1.json': '2d79f57480d2e8f676cbab67849bc8cf67a6ac744d498a2c3b648553ba2daddc',
    'tax-2026-m-2.json': 'ea6427851b10ba1b9e071daaf7a1282917d90d10fb8398a005ad81988d329cbb',
    'tax-2026-m-3.json': 'bab8d9c6d47659198971b0bbb6531b9ecd449c3c215df01c39d8a72ce82dbe33',
  });

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
