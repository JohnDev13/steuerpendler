import { DESTINATIONS } from './destinations';
import type { Access, TravelRows } from './filter';
import type { FileDigest, Gemeinde, TaxRepository } from './tax';

export const ALL19_OBSERVED_FILE = 'travel/all19-observed-routes-20261027.json';
export const ALL19_OBSERVED_DIGEST = { sha256: '426e71f1a361f9b645f4f16fd121854a6955f4b19dab0268b4bed6cf3befb2bb', bytes: 4428922 } as const;
const SOURCE_SHA = {
  boardStopGemeinde: '53380d7c232074d6097148a7c29a08fe6e3f06213a2301b91a6fb281714f36bb',
  connections: 'fc98b4195f0275dca6e0443c1fdcb63158f9127b30f5f13583ed285f9b6600fb',
  gemeinden: '0cc01b0d5f9fab1a0069394a9b89441ca4264ea0ba7e114e89157c2f748a5928',
  targetRegistry: 'd8a8a926d33f3e3c39be27a053409460f9b78a41faa9f5fc2d3c4af4cbd6f7fb',
  transferScope: '6e2d6869ac4b731e96069b6ce35a20253aa704c92512d7b820bc1d6303e0819b',
} as const;
const TOP_KEYS = ['claims','defaultAllRoutes','destinationCount','destinations','externalAccessMeasurement','externalAccessSeconds','municipalityCount','schema','schemaVersion','serviceDate','sourceSha256'];
const DESTINATION_KEYS = ['directOnly','statuses','targetChildStopIds','unresolvedReasonClasses'];
const POSITIVE_KEYS = ['arrivalSeconds','arrivalStopId','elapsedSeconds','firstBoardSeconds','firstBoardStopId','legs','sourceConnectionId','status','transferCount','transferRuleIds','unresolvedReasons'];
const LEG_KEYS = ['alightSeconds','alightStopId','boardSeconds','boardStopId','connectionIds','routeId','serviceId','tripId'];
export interface ObservedReleaseInventory { files: Record<string, FileDigest> }
export interface UnknownRoute { status: 'unknown'; unresolvedReasons: string[] }
export interface PositiveRoute {
  status: 'best_found_unproven'; firstBoardSeconds: number; arrivalSeconds: number; elapsedSeconds: number;
  firstBoardStopId: string; arrivalStopId: string; sourceConnectionId: number; transferCount: number;
  transferRuleIds: number[]; unresolvedReasons: string[]; legs: Array<Record<string, unknown>>;
}
export interface ObservedDestination { directOnly: Record<string, PositiveRoute>; statuses: Record<string, PositiveRoute | UnknownRoute>; targetChildStopIds: string[]; unresolvedReasonClasses: string[] }
export interface ObservedRoutes { destinations: Record<string, ObservedDestination> }

function invalid(): never { throw new Error('Ungültige indikative Fahrplandaten.'); }
function record(value: unknown): value is Record<string, unknown> { return !!value && typeof value === 'object' && !Array.isArray(value); }
function exactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort(), wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
}
function stringArray(value: unknown): value is string[] { return Array.isArray(value) && value.every(item => typeof item === 'string' && item.length > 0); }
function validatePositive(value: unknown, direct: boolean): PositiveRoute {
  if (!record(value) || !exactKeys(value, POSITIVE_KEYS) || value.status !== 'best_found_unproven'
    || !Number.isInteger(value.firstBoardSeconds) || (value.firstBoardSeconds as number) < 23400 || (value.firstBoardSeconds as number) > 30600
    || !Number.isInteger(value.arrivalSeconds) || !Number.isInteger(value.elapsedSeconds) || (value.elapsedSeconds as number) < 0 || (value.elapsedSeconds as number) > 1800
    || (value.arrivalSeconds as number) - (value.firstBoardSeconds as number) !== value.elapsedSeconds
    || typeof value.firstBoardStopId !== 'string' || value.firstBoardStopId.length === 0
    || typeof value.arrivalStopId !== 'string' || value.arrivalStopId.length === 0
    || !Number.isInteger(value.sourceConnectionId) || !Number.isInteger(value.transferCount) || (value.transferCount as number) < 0
    || (direct && value.transferCount !== 0) || !Array.isArray(value.transferRuleIds) || !value.transferRuleIds.every(Number.isInteger) || !stringArray(value.unresolvedReasons)
    || !Array.isArray(value.legs) || value.legs.length !== (value.transferCount as number) + 1) invalid();
  for (const leg of value.legs) {
    if (!record(leg) || !exactKeys(leg, LEG_KEYS) || !Number.isInteger(leg.boardSeconds) || !Number.isInteger(leg.alightSeconds)
      || (leg.alightSeconds as number) < (leg.boardSeconds as number) || typeof leg.boardStopId !== 'string' || !leg.boardStopId
      || typeof leg.alightStopId !== 'string' || !leg.alightStopId || !Array.isArray(leg.connectionIds) || !leg.connectionIds.length
      || !leg.connectionIds.every(Number.isInteger) || typeof leg.routeId !== 'string' || typeof leg.serviceId !== 'string' || typeof leg.tripId !== 'string') invalid();
  }
  return value as unknown as PositiveRoute;
}
export function validateObservedRoutes(data: unknown, release: ObservedReleaseInventory, gemeinden: Record<string, Gemeinde>): ObservedRoutes {
  const inventory = release.files[ALL19_OBSERVED_FILE];
  if (inventory?.sha256 !== ALL19_OBSERVED_DIGEST.sha256 || inventory.bytes !== ALL19_OBSERVED_DIGEST.bytes || !record(data) || !exactKeys(data, TOP_KEYS)) invalid();
  const source = data.sourceSha256;
  if (data.claims !== 'OBSERVED_POSITIVE_PROVISIONAL_UNKNOWN_ABSENCE' || data.defaultAllRoutes !== true || data.destinationCount !== 19
    || data.externalAccessMeasurement !== 'unmeasured' || data.externalAccessSeconds !== 0 || data.municipalityCount !== 2110
    || data.schema !== 'steuerpendler.dated-observed-route-export.v1' || data.schemaVersion !== 1 || data.serviceDate !== '2026-10-27'
    || !record(source) || !exactKeys(source, Object.keys(SOURCE_SHA))
    || Object.entries(SOURCE_SHA).some(([key, expected]) => source[key] !== expected)
    || release.files['gemeinden-2026.json']?.sha256 !== SOURCE_SHA.gemeinden || !record(data.destinations)) invalid();
  const municipalityKeys = Object.keys(gemeinden).sort((a,b) => Number(a)-Number(b));
  if (municipalityKeys.length !== 2110) invalid();
  const destinationKeys = DESTINATIONS.map(({ bfs }) => String(bfs)).sort((a,b) => Number(a)-Number(b));
  const actualDestinations = Object.keys(data.destinations).sort((a,b) => Number(a)-Number(b));
  if (actualDestinations.length !== destinationKeys.length || actualDestinations.some((key,index) => key !== destinationKeys[index])) invalid();
  const destinations: Record<string, ObservedDestination> = {};
  for (const destinationKey of destinationKeys) {
    const raw = data.destinations[destinationKey];
    if (!record(raw) || !exactKeys(raw, DESTINATION_KEYS) || !record(raw.statuses) || !record(raw.directOnly)
      || !stringArray(raw.targetChildStopIds) || !stringArray(raw.unresolvedReasonClasses)) invalid();
    const statusKeys = Object.keys(raw.statuses).sort((a,b) => Number(a)-Number(b));
    if (statusKeys.length !== 2110 || statusKeys.some((key,index) => key !== municipalityKeys[index])) invalid();
    const statuses: Record<string, PositiveRoute | UnknownRoute> = {};
    for (const key of statusKeys) {
      const status = raw.statuses[key];
      if (!record(status) || (status.status !== 'unknown' && status.status !== 'best_found_unproven')) invalid();
      if (status.status === 'unknown') {
        if (!exactKeys(status, ['status','unresolvedReasons']) || !stringArray(status.unresolvedReasons)) invalid();
        statuses[key] = status as unknown as UnknownRoute;
      } else statuses[key] = validatePositive(status, false);
    }
    const directOnly: Record<string, PositiveRoute> = {};
    for (const [key, route] of Object.entries(raw.directOnly)) {
      if (!gemeinden[key] || statuses[key]?.status !== 'best_found_unproven') invalid();
      directOnly[key] = validatePositive(route, true);
    }
    destinations[destinationKey] = { directOnly, statuses, targetChildStopIds: raw.targetChildStopIds, unresolvedReasonClasses: raw.unresolvedReasonClasses };
  }
  return { destinations };
}
export function adaptObservedRoutes(data: ObservedRoutes, workplace: number, directOnly: boolean): { access: Access; rows: TravelRows } {
  const destination = data.destinations[workplace];
  if (!destination) return { access: {}, rows: [] };
  const positives = directOnly ? destination.directOnly : Object.fromEntries(Object.entries(destination.statuses).filter(([, route]) => route.status === 'best_found_unproven')) as Record<string, PositiveRoute>;
  const access: Access = {}, rows: Array<readonly [number, number]> = [];
  for (const [key, route] of Object.entries(positives)) {
    const bfs = Number(key); access[key] = [route.firstBoardStopId, route.firstBoardStopId, 0]; rows.push([bfs, Math.ceil(route.elapsedSeconds / 60)]);
  }
  rows.sort((a,b) => a[0]-b[0]);
  return { access, rows };
}
export async function loadObservedRoutes(repository: TaxRepository, release: ObservedReleaseInventory, gemeinden: Record<string, Gemeinde>): Promise<ObservedRoutes | null> {
  if (!release.files[ALL19_OBSERVED_FILE]) return null;
  return validateObservedRoutes(await repository.json<unknown>(ALL19_OBSERVED_FILE), release, gemeinden);
}
