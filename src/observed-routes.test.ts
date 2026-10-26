import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { DESTINATIONS } from './destinations';
import { ALL19_OBSERVED_FILE, adaptObservedRoutes, loadObservedRoutes, validateObservedRoutes } from './observed-routes';
import type { Gemeinde } from './tax';

const municipalityIds = new Set<number>(DESTINATIONS.map(({ bfs }) => bfs));
for (let bfs = 1; municipalityIds.size < 2110; bfs++) municipalityIds.add(bfs);
const gemeinden: Record<string, Gemeinde> = Object.fromEntries([...municipalityIds].map(bfs => [String(bfs), [`Ort ${bfs}`, 'ZH', 100, 100, 0, 0] as const]));
for (const destination of DESTINATIONS) gemeinden[destination.bfs] = [destination.name, destination.canton, 100, 100, 0, 0];
const unknown = () => ({ status: 'unknown', unresolvedReasons: ['no_evidenced_route_from_assigned_stop'] });
const positive = (seconds = 1200, transfers = 0) => ({
  status: 'best_found_unproven', firstBoardSeconds: 23400, arrivalSeconds: 23400 + seconds, elapsedSeconds: seconds,
  firstBoardStopId: 'stop-a', arrivalStopId: 'stop-z', sourceConnectionId: 1, transferCount: transfers,
  transferRuleIds: [], unresolvedReasons: ['optimality_not_proven'],
  legs: Array.from({ length: transfers + 1 }, (_, index) => ({ boardSeconds: 23400 + index * 300, alightSeconds: 23700 + index * 300, boardStopId: `stop-${index}`, alightStopId: `stop-${index + 1}`, connectionIds: [index + 1], routeId: 'r', serviceId: 's', tripId: 't' })),
});
function fixture() {
  const statuses = Object.fromEntries(Object.keys(gemeinden).map(key => [key, unknown()]));
  statuses['1'] = positive(1200, 1);
  const destinations = Object.fromEntries(DESTINATIONS.map(destination => [String(destination.bfs), {
    directOnly: { '1': positive(1500, 0) }, statuses: structuredClone(statuses), targetChildStopIds: ['target'],
    unresolvedReasonClasses: ['no_evidenced_route_from_assigned_stop', 'optimality_not_proven'],
  }]));
  return {
    claims: 'OBSERVED_POSITIVE_PROVISIONAL_UNKNOWN_ABSENCE', defaultAllRoutes: true, destinationCount: 19,
    destinations, externalAccessMeasurement: 'unmeasured', externalAccessSeconds: 0, municipalityCount: 2110,
    schema: 'steuerpendler.dated-observed-route-export.v1', schemaVersion: 1, serviceDate: '2026-10-27',
    sourceSha256: {
      boardStopGemeinde: '53380d7c232074d6097148a7c29a08fe6e3f06213a2301b91a6fb281714f36bb',
      connections: 'fc98b4195f0275dca6e0443c1fdcb63158f9127b30f5f13583ed285f9b6600fb',
      gemeinden: '0cc01b0d5f9fab1a0069394a9b89441ca4264ea0ba7e114e89157c2f748a5928',
      targetRegistry: 'd8a8a926d33f3e3c39be27a053409460f9b78a41faa9f5fc2d3c4af4cbd6f7fb',
      transferScope: '6e2d6869ac4b731e96069b6ce35a20253aa704c92512d7b820bc1d6303e0819b',
    },
  };
}
const release = { files: { [ALL19_OBSERVED_FILE]: { sha256: '426e71f1a361f9b645f4f16fd121854a6955f4b19dab0268b4bed6cf3befb2bb', bytes: 4428922 }, 'gemeinden-2026.json': { sha256: '0cc01b0d5f9fab1a0069394a9b89441ca4264ea0ba7e114e89157c2f748a5928' } } };

describe('all-19 observed-positive routes', () => {
  it('accepts the pinned source-scale asset and preserves its reviewed positive counts', () => {
    const actualGemeinden = JSON.parse(readFileSync(new URL('../site/data/gemeinden-2026.json', import.meta.url), 'utf8')).gemeinden;
    const actual = JSON.parse(readFileSync(new URL('../site/data/travel/all19-observed-routes-20261027.json', import.meta.url), 'utf8'));
    const validated = validateObservedRoutes(actual, release, actualGemeinden);
    const allCount = Object.values(validated.destinations).reduce((sum, destination) => sum + Object.values(destination.statuses).filter(route => route.status === 'best_found_unproven').length, 0);
    const directCount = Object.values(validated.destinations).reduce((sum, destination) => sum + Object.keys(destination.directOnly).length, 0);
    expect([allCount, directCount]).toEqual([806, 451]);
    for (const { bfs } of DESTINATIONS) expect(adaptObservedRoutes(validated, bfs, false).rows.length).toBeGreaterThan(0);
  });
  it('validates all workplaces and adapts all-mode by default and direct-only independently', () => {
    const data = validateObservedRoutes(fixture(), release, gemeinden);
    expect(Object.keys(data.destinations)).toEqual(DESTINATIONS.map(({ bfs }) => String(bfs)).sort((a, b) => Number(a) - Number(b)));
    for (const { bfs } of DESTINATIONS) {
      expect(adaptObservedRoutes(data, bfs, false).rows).toEqual([[1, 20]]);
      expect(adaptObservedRoutes(data, bfs, true).rows).toEqual([[1, 25]]);
      expect(adaptObservedRoutes(data, bfs, false).access['1']).toEqual(['stop-a', 'stop-a', 0]);
    }
  });
  it('preserves exact-second threshold before ceiling display minutes and unknown absence', () => {
    const value = fixture(); value.destinations['261'].statuses['1'] = positive(1201, 1);
    const data = validateObservedRoutes(value, release, gemeinden);
    expect(adaptObservedRoutes(data, 261, false).rows).toEqual([[1, 21]]);
    expect(data.destinations['261'].statuses['2'].status).toBe('unknown');
  });
  it('fails closed on inventory, lineage, key, status, window, cap, and direct-subset mismatches', () => {
    const mutations = [
      (v: any) => { v.sourceSha256.connections = 'bad'; },
      (v: any) => { delete v.destinations['4566']; },
      (v: any) => { delete v.destinations['261'].statuses['2']; },
      (v: any) => { v.destinations['261'].statuses['2'].status = 'unreachable'; },
      (v: any) => { v.destinations['261'].statuses['1'].elapsedSeconds = 1801; },
      (v: any) => { v.destinations['261'].statuses['1'].firstBoardSeconds = 23399; },
      (v: any) => { v.destinations['261'].directOnly['2'] = positive(); },
      (v: any) => { v.destinations['261'].directOnly['1'].transferCount = 1; },
    ];
    for (const mutate of mutations) { const value = fixture(); mutate(value); expect(() => validateObservedRoutes(value, release, gemeinden)).toThrow(/Fahrplandaten/); }
    expect(() => validateObservedRoutes(fixture(), { files: { ...release.files, [ALL19_OBSERVED_FILE]: { sha256: 'bad', bytes: 4428922 } } }, gemeinden)).toThrow(/Fahrplandaten/);
  });
  it('loads null only when the new asset is genuinely absent', async () => {
    const absent = { files: {} };
    await expect(loadObservedRoutes({ json: async () => { throw new Error('must not fetch'); } } as any, absent, gemeinden)).resolves.toBeNull();
    await expect(loadObservedRoutes({ json: async () => fixture() } as any, release, gemeinden)).resolves.toBeTruthy();
    await expect(loadObservedRoutes({ json: async () => ({}) } as any, release, gemeinden)).rejects.toThrow(/Fahrplandaten/);
  });
});
