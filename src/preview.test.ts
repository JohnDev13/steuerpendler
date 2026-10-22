import { describe, expect, it } from 'vitest';
import { filterAndRank } from './filter';
import {
  AARAU_PREVIEW_FILE,
  AARAU_PREVIEW_SOURCE,
  adaptAarauPreview,
  previewKnowledge,
  validateAarauPreview,
  type PreviewReleaseInventory,
} from './preview';
import type { Gemeinde } from './tax';

const hashes = AARAU_PREVIEW_SOURCE;
const inventory: PreviewReleaseInventory = {
  files: {
    [AARAU_PREVIEW_FILE]: { sha256: '311420191be00d7f8b6d96f81f1e8295f801a26e34deb6d49ad5ec2e7f78b988', bytes: 10435 },
    'gemeinden-2026.json': { sha256: hashes.gemeindenSha256 },
    'map/switzerland-2026.json': { sha256: hashes.mapSha256 },
  },
};
const gemeinden: Record<string, Gemeinde> = {
  ...Object.fromEntries(
  Array.from({ length: 59 }, (_, index) => [String(index + 1), [`Ort ${index + 1}`, 'AG', 100, 100, 0, 0] as const]),
  ),
  '4001': ['Aarau', 'AG', 100, 100, 0, 0],
};
function fixture(seconds = 1200) {
  return {
    status: 'indicative_positive_direct_only',
    destinationBfs: 4001,
    serviceDay: '2026-10-27',
    routeSha256: hashes.routeSha256,
    mapSha256: hashes.mapSha256,
    gtfsSha256: hashes.gtfsSha256,
    gemeindenSha256: hashes.gemeindenSha256,
    accessModel: 'unmeasured_external_access_zero',
    unknownNotNegative: true,
    counts: {
      ambiguousStops: 0,
      assignedMunicipalities: 59,
      assignedStops: 188,
      boardingWindowInclusiveSeconds: [23400, 30600],
      boundaryQuarantinedStops: 24,
      capSecondsInclusive: 1800,
      mapBoundaryQuarantineMetres: 100,
      mapCoordinatesSimplified: true,
      municipalityAuthority: 2110,
      sourceEvents: 1754,
      sourceStops: 212,
      unassignedStops: 0,
    },
    rows: Array.from({ length: 59 }, (_, index) => ({
      bfs: index + 1,
      seconds: index === 0 ? seconds : 60,
      minutes: index === 0 ? Math.ceil(seconds / 60) : 1,
      boardingStopId: `stop-${index + 1}`,
      tripId: `trip-${index + 1}`,
      firstBoardSeconds: 23400,
      observedEvents: 1,
    })),
  };
}

describe('Aarau indicative direct-positive preview', () => {
  it('uses exact ceiling minutes: 1200 is included and 1201 is excluded at 20 minutes', () => {
    const included = adaptAarauPreview(validateAarauPreview(fixture(1200), inventory, gemeinden));
    const excluded = adaptAarauPreview(validateAarauPreview(fixture(1201), inventory, gemeinden));
    const options = { workplace: 4001, maxTime: 20, maxWalk: 0, countWalk: false };
    expect(filterAndRank(gemeinden, included.access, included.rows, options, { 1: 100 })).toHaveLength(1);
    expect(filterAndRank(gemeinden, excluded.access, excluded.rows, options, { 1: 100 })).toHaveLength(0);
  });

  it('rejects duplicate or unknown BFS rows and non-exact ceiling minutes', () => {
    const duplicate = fixture(); duplicate.rows[1].bfs = 1;
    expect(() => validateAarauPreview(duplicate, inventory, gemeinden)).toThrow(/Fahrplandaten/);
    const unknown = fixture(); unknown.rows[58].bfs = 60;
    expect(() => validateAarauPreview(unknown, inventory, gemeinden)).toThrow(/Fahrplandaten/);
    const roundedDown = fixture(1201); roundedDown.rows[0].minutes = 20;
    expect(() => validateAarauPreview(roundedDown, inventory, gemeinden)).toThrow(/Fahrplandaten/);
  });

  it('rejects altered status, date, counts, source hashes, or release-map hashes', () => {
    for (const mutate of [
      (value: any) => { value.status = 'complete'; },
      (value: any) => { value.serviceDay = '2026-10-28'; },
      (value: any) => { value.counts.sourceEvents = 1753; },
      (value: any) => { value.routeSha256 = 'b'.repeat(64); },
    ]) {
      const value = fixture(); mutate(value);
      expect(() => validateAarauPreview(value, inventory, gemeinden)).toThrow(/Fahrplandaten/);
    }
    const wrongInventory = structuredClone(inventory);
    wrongInventory.files['map/switzerland-2026.json'].sha256 = 'b'.repeat(64);
    expect(() => validateAarauPreview(fixture(), wrongInventory, gemeinden)).toThrow(/Fahrplandaten/);
    const alteredPreviewInventory = structuredClone(inventory);
    alteredPreviewInventory.files[AARAU_PREVIEW_FILE].sha256 = 'b'.repeat(64);
    expect(() => validateAarauPreview(fixture(), alteredPreviewInventory, gemeinden)).toThrow(/Fahrplandaten/);
  });

  it('adapts assumed unmeasured access as zero and keeps tax-first ranking stable', () => {
    const adapted = adaptAarauPreview(validateAarauPreview(fixture(), inventory, gemeinden));
    expect(adapted.access['1']).toEqual(['stop-1', 'stop-1', 0]);
    expect(adapted.rows[0]).toEqual([1, 20]);
    const ranked = filterAndRank(gemeinden, adapted.access, adapted.rows.slice(0, 3), { workplace: 4001, maxTime: 30, maxWalk: 0, countWalk: false }, { 1: 300, 2: 100, 3: 200 });
    expect(ranked.map(row => row.id)).toEqual([2, 3, 1]);
  });

  it('treats every unlisted Gemeinde as unknown, never as a negative', () => {
    const preview = validateAarauPreview(fixture(), inventory, gemeinden);
    expect(previewKnowledge(preview, 1)).toBe('witnessed-positive');
    expect(previewKnowledge(preview, 999)).toBe('unknown');
  });
});
