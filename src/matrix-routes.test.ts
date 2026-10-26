import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { adaptMatrix, loadMatrixMeta, MATRIX_META_FILE, transfersFor, validateMatrixDestination, validateMatrixMeta } from './matrix-routes';
import type { Gemeinde } from './tax';

// Produced by scripts/travel/matrix.py in tests/travel/test_matrix.py (MatrixContract).
const contract = JSON.parse(readFileSync(new URL('../tests/travel/fixtures/matrix-contract.json', import.meta.url), 'utf8'));
const gemeinden: Record<string, Gemeinde> = Object.fromEntries([100, 200, 300, 261].map(bfs => [String(bfs), [`Ort ${bfs}`, 'ZH', 100, 100, 0, 0] as Gemeinde]));
const clone = () => structuredClone(contract.to);

describe('travel matrix contract', () => {
  it('does not load the experimental matrix before the travel release gate is open', async () => {
    const repository = { json: vi.fn(async () => contract.meta) } as any;
    const files = { [MATRIX_META_FILE]: { sha256: 'a'.repeat(64), bytes: 100 } };
    expect(await loadMatrixMeta(repository, files, false)).toBeNull();
    expect(repository.json).not.toHaveBeenCalled();
    expect((await loadMatrixMeta(repository, files, true))?.serviceDate).toBe('2026-10-27');
    expect(repository.json).toHaveBeenCalledOnce();
  });

  it('accepts what the Python generator writes', () => {
    const meta = validateMatrixMeta(contract.meta);
    expect(meta.serviceDate).toBe('2026-10-27');
    const destination = validateMatrixDestination(contract.to, 261, meta.serviceDate, gemeinden);
    expect(destination.station).toBe('Target');
    expect(destination.rows.map(row => row[0])).toEqual([261, 200, 100, 300]);
  });

  it('rounds seconds up to minutes, keeps the boarding stop name and filters direct-only', () => {
    const destination = validateMatrixDestination(contract.to, 261, '2026-10-27', gemeinden);
    const all = adaptMatrix(destination, false);
    expect(all.rows).toEqual([[261, 0], [200, 7], [100, 12], [300, 15]]);
    expect(all.access['200']).toEqual(['Xenon', 'Xenon', 0]);
    expect(all.access['261']![1]).toBe('Target');
    const withTransfer = { ...destination, rows: [...destination.rows, [300, 1000, 1, 'Ypsilon', 0] as const].filter((row, i, rows) => rows.findIndex(r => r[0] === row[0]) === i) };
    expect(adaptMatrix({ ...withTransfer, rows: withTransfer.rows.map(row => row[0] === 100 ? [100, 720, 2, 'Alpha', 25200] as const : row) }, true).rows.map(row => row[0])).toEqual([261, 200, 100, 300]);
    expect(transfersFor(destination, 100)).toBe(0);
    expect(transfersFor(null, 100)).toBeUndefined();
  });

  it('uses an independently routed slower direct path when a transfer is faster', () => {
    const destination = validateMatrixDestination(contract.to, 261, '2026-10-27', gemeinden);
    const modified = { ...destination,
      rows: destination.rows.map(row => row[0] === 100 ? [100, 600, 1, 'Alpha', 25200] as const : row),
      directRows: [...destination.directRows.filter(row => row[0] !== 100), [100, 1200, 0, 'Alpha', 25200] as const] };
    expect(adaptMatrix(modified, false).rows.find(row => row[0] === 100)).toEqual([100, 10]);
    expect(adaptMatrix(modified, true).rows.find(row => row[0] === 100)).toEqual([100, 20]);
  });

  it('rejects malformed or inconsistent files', () => {
    const mutations: Array<(value: any) => void> = [
      value => { value.to = 351; },
      value => { value.serviceDate = '2026-11-03'; },
      value => { value.rows[1][1] = 1801; },
      value => { value.rows[1][1] = 0; },
      value => { value.rows.push([...value.rows[1]]); },
      value => { value.rows.reverse(); },
      value => { value.rows[2][0] = 999999; },
      value => { value.rows = value.rows.filter((row: number[]) => row[0] !== 261); },
      value => { value.rows[1][2] = -1; },
      value => { delete value.directRows; },
      value => { value.directRows[1][2] = 1; },
      value => { value.directRows[1][1] = 2; },
      value => { value.directRows.push([...value.directRows[1]]); },
      value => { value.directRows[1][0] = 999999; },
      value => { value.schema = 'v0'; },
    ];
    for (const mutate of mutations) {
      const value = clone();
      mutate(value);
      expect(() => validateMatrixDestination(value, 261, '2026-10-27', gemeinden)).toThrow(/Fahrplandaten/);
    }
    expect(() => validateMatrixMeta({ ...contract.meta, absence: 'no_journey_within_cap_under_model' })).toThrow(/Fahrplandaten/);
    expect(() => validateMatrixMeta({ ...contract.meta, capSeconds: 3600 })).toThrow(/Fahrplandaten/);
  });
});
