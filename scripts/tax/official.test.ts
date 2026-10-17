import { createHash } from 'node:crypto';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { expect, test } from 'vitest';
import { officialTolerance, verifyResponseEvidence } from './official';

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
