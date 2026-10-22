import type { Access, TravelRows } from './filter';
import type { Gemeinde, FileDigest, TaxRepository } from './tax';

export const AARAU_PREVIEW_FILE = 'travel/aarau-direct-observed-20261027.json';
export const AARAU_PREVIEW_DIGEST = { sha256: '311420191be00d7f8b6d96f81f1e8295f801a26e34deb6d49ad5ec2e7f78b988', bytes: 10435 } as const;
export const AARAU_PREVIEW_SOURCE = {
  routeSha256: '5f9c6c8648f87ff88cf0c1dc4f158d471a6e55f57ed28cd53e649940d1d4b89e',
  gtfsSha256: 'd5b312e1ff398b505f9a6efef60c365f3c864857f73c55e87b383960a6b3418e',
  mapSha256: 'd118a3e8b47c8d76d4fa2587911aa088573d09a934ea484f2f1a60d573aafe14',
  gemeindenSha256: '0cc01b0d5f9fab1a0069394a9b89441ca4264ea0ba7e114e89157c2f748a5928',
} as const;

const EXPECTED_COUNTS = {
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
} as const;

export interface PreviewReleaseInventory {
  files: Record<string, FileDigest>;
}
export interface AarauPreviewRow {
  bfs: number;
  seconds: number;
  minutes: number;
  boardingStopId: string;
  tripId: string;
  firstBoardSeconds: number;
  observedEvents: number;
}
export interface AarauPreview {
  status: 'indicative_positive_direct_only';
  destinationBfs: 4001;
  serviceDay: '2026-10-27';
  routeSha256: string;
  mapSha256: string;
  gtfsSha256: string;
  gemeindenSha256: string;
  accessModel: 'unmeasured_external_access_zero';
  unknownNotNegative: true;
  counts: typeof EXPECTED_COUNTS;
  rows: AarauPreviewRow[];
}
export interface AdaptedAarauPreview {
  access: Access;
  rows: TravelRows;
}

const invalid = (): never => { throw new Error('Ungültige indikative Fahrplandaten.'); };
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}
function matchesExpectedCounts(value: unknown): value is typeof EXPECTED_COUNTS {
  if (!isRecord(value) || !hasExactKeys(value, Object.keys(EXPECTED_COUNTS))) return false;
  return Object.entries(EXPECTED_COUNTS).every(([key, expected]) => {
    const actual = value[key];
    return Array.isArray(expected)
      ? Array.isArray(actual) && actual.length === expected.length && actual.every((item, index) => item === expected[index])
      : actual === expected;
  });
}

export function validateAarauPreview(data: unknown, release: PreviewReleaseInventory, gemeinden: Record<string, Gemeinde>): AarauPreview {
  if (release.files[AARAU_PREVIEW_FILE]?.sha256 !== AARAU_PREVIEW_DIGEST.sha256
    || release.files[AARAU_PREVIEW_FILE]?.bytes !== AARAU_PREVIEW_DIGEST.bytes || !isRecord(data)) throw new Error('Ungültige indikative Fahrplandaten.');
  if (!hasExactKeys(data, [
    'status', 'destinationBfs', 'serviceDay', 'routeSha256', 'mapSha256', 'gtfsSha256', 'gemeindenSha256',
    'accessModel', 'unknownNotNegative', 'counts', 'rows',
  ])) invalid();
  if (!Array.isArray(data.rows)) throw new Error('Ungültige indikative Fahrplandaten.');
  const rawRows = data.rows;
  if (data.status !== 'indicative_positive_direct_only' || data.destinationBfs !== 4001 || data.serviceDay !== '2026-10-27'
    || data.accessModel !== 'unmeasured_external_access_zero' || data.unknownNotNegative !== true || !matchesExpectedCounts(data.counts)
    || data.routeSha256 !== AARAU_PREVIEW_SOURCE.routeSha256 || data.gtfsSha256 !== AARAU_PREVIEW_SOURCE.gtfsSha256
    || data.mapSha256 !== AARAU_PREVIEW_SOURCE.mapSha256 || data.gemeindenSha256 !== AARAU_PREVIEW_SOURCE.gemeindenSha256
    || release.files['map/switzerland-2026.json']?.sha256 !== data.mapSha256
    || release.files['gemeinden-2026.json']?.sha256 !== data.gemeindenSha256
    || rawRows.length !== EXPECTED_COUNTS.assignedMunicipalities) invalid();

  const rows: AarauPreviewRow[] = [];
  const seen = new Set<number>();
  let previousBfs = -1;
  for (const candidate of rawRows) {
    if (!isRecord(candidate) || !hasExactKeys(candidate, ['bfs', 'seconds', 'minutes', 'boardingStopId', 'tripId', 'firstBoardSeconds', 'observedEvents'])) invalid();
    const { bfs, seconds, minutes, boardingStopId, tripId, firstBoardSeconds, observedEvents } = candidate;
    if (!Number.isInteger(bfs) || typeof bfs !== 'number' || !gemeinden[bfs] || bfs <= previousBfs || seen.has(bfs)
      || !Number.isInteger(seconds) || typeof seconds !== 'number' || seconds < 0 || seconds > EXPECTED_COUNTS.capSecondsInclusive
      || !Number.isInteger(minutes) || minutes !== Math.ceil(seconds / 60)
      || typeof boardingStopId !== 'string' || boardingStopId.length === 0 || typeof tripId !== 'string' || tripId.length === 0
      || !Number.isInteger(firstBoardSeconds) || typeof firstBoardSeconds !== 'number'
      || firstBoardSeconds < EXPECTED_COUNTS.boardingWindowInclusiveSeconds[0] || firstBoardSeconds > EXPECTED_COUNTS.boardingWindowInclusiveSeconds[1]
      || !Number.isInteger(observedEvents) || typeof observedEvents !== 'number' || observedEvents < 1) invalid();
    previousBfs = bfs;
    seen.add(bfs);
    rows.push({ bfs, seconds, minutes, boardingStopId, tripId, firstBoardSeconds, observedEvents });
  }
  return { ...data, counts: EXPECTED_COUNTS, rows } as AarauPreview;
}

export function adaptAarauPreview(preview: AarauPreview): AdaptedAarauPreview {
  const access: Access = {};
  const rows: Array<readonly [number, number]> = [];
  for (const row of preview.rows) {
    access[row.bfs] = [row.boardingStopId, row.boardingStopId, 0];
    rows.push([row.bfs, row.minutes]);
  }
  return { access, rows };
}

export function previewKnowledge(preview: AarauPreview, bfs: number): 'witnessed-positive' | 'unknown' {
  return preview.rows.some(row => row.bfs === bfs) ? 'witnessed-positive' : 'unknown';
}

export async function loadAarauPreview(repository: TaxRepository, release: PreviewReleaseInventory, gemeinden: Record<string, Gemeinde>): Promise<AarauPreview | null> {
  if (!release.files[AARAU_PREVIEW_FILE]) return null;
  return validateAarauPreview(await repository.json<unknown>(AARAU_PREVIEW_FILE), release, gemeinden);
}
