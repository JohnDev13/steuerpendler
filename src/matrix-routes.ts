import type { Access, TravelRows } from './filter';
import type { FileDigest, Gemeinde, TaxRepository } from './tax';
import { strings as s } from './strings';

/** Complete Gemeinde→workplace matrix produced by scripts/travel/run_matrix.py (schema steuerpendler.travel-matrix.v1). */
export const MATRIX_META_FILE = 'travel/matrix/meta.json';
export const matrixFile = (workplace: number) => `travel/matrix/to/${workplace}.json`;
const SCHEMA = 'steuerpendler.travel-matrix.v1';
const CAP_SECONDS = 1800;

export interface MatrixMeta {
  serviceDate: string;
  feedSha256: string;
  workplaces: Record<string, { station: string | null; rows: number }>;
}
/** [homeBfs, transitSeconds, transfers, firstBoardStopName, firstBoardSeconds] */
export type MatrixRow = readonly [number, number, number, string, number];
export interface MatrixDestination { to: number; station: string; rows: readonly MatrixRow[]; directRows: readonly MatrixRow[] }

function invalid(): never { throw new Error(s.invalidTravel); }
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);

export function validateMatrixMeta(data: unknown): MatrixMeta {
  if (!record(data)) invalid();
  if (data.schema !== SCHEMA || data.capSeconds !== CAP_SECONDS || data.absence !== 'no_journey_within_cap_under_model'
    || typeof data.serviceDate !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(data.serviceDate)
    || !record(data.feed) || typeof data.feed.sha256 !== 'string' || !record(data.workplaces)) invalid();
  const meta = data as Record<string, any>;
  return { serviceDate: meta.serviceDate, feedSha256: meta.feed.sha256, workplaces: meta.workplaces };
}

export function validateMatrixDestination(data: unknown, workplace: number, serviceDate: string, gemeinden: Record<string, Gemeinde>): MatrixDestination {
  if (!record(data)) invalid();
  if (data.schema !== SCHEMA || data.to !== workplace || data.serviceDate !== serviceDate
    || typeof data.station !== 'string' || !Array.isArray(data.rows)) invalid();
  const validateRows = (value: unknown, directOnly: boolean): readonly MatrixRow[] => {
    if (!Array.isArray(value)) invalid();
    const seen = new Set<number>();
    let previous = -1;
    for (const row of value) {
      if (!Array.isArray(row) || row.length !== 5) invalid();
      const [bfs, seconds, transfers, name, board] = row as unknown[];
      if (!Number.isInteger(bfs) || !gemeinden[bfs as number] || seen.has(bfs as number)
        || !Number.isInteger(seconds) || (seconds as number) < 0 || (seconds as number) > CAP_SECONDS || (seconds as number) < previous
        || !Number.isInteger(transfers) || (transfers as number) < 0 || (directOnly && transfers !== 0)
        || typeof name !== 'string' || !Number.isInteger(board)) invalid();
      if ((seconds as number) === 0 && bfs !== workplace) invalid();
      seen.add(bfs as number);
      previous = seconds as number;
    }
    if (!seen.has(workplace)) invalid();
    return value as MatrixRow[];
  };
  const rows = validateRows(data.rows, false);
  const directRows = validateRows(data.directRows, true);
  const allByBfs = new Map(rows.map(row => [row[0], row[1]]));
  if (directRows.some(row => !allByBfs.has(row[0]) || row[1] < allByBfs.get(row[0])!)) invalid();
  return { to: workplace, station: data.station as string, rows, directRows };
}

/** Rows for the filter: minutes rounded up; access walk is unmeasured and therefore 0. */
export function adaptMatrix(destination: MatrixDestination, directOnly: boolean): { access: Access; rows: TravelRows } {
  const access: Access = {};
  const rows: Array<readonly [number, number]> = [];
  for (const [bfs, seconds, _transfers, name] of (directOnly ? destination.directRows : destination.rows)) {
    access[bfs] = [name, name || destination.station, 0];
    rows.push([bfs, Math.ceil(seconds / 60)]);
  }
  return { access, rows };
}

export function transfersFor(destination: MatrixDestination | null, bfs: number, directOnly = false): number | undefined {
  return (directOnly ? destination?.directRows : destination?.rows)?.find(row => row[0] === bfs)?.[2];
}

export async function loadMatrixMeta(repository: TaxRepository, files: Record<string, FileDigest>, releaseTravelReady: boolean): Promise<MatrixMeta | null> {
  // Keep unverified matrix experiments from displacing independently sourced preview routes.
  if (!releaseTravelReady || !files[MATRIX_META_FILE]) return null;
  return validateMatrixMeta(await repository.json<unknown>(MATRIX_META_FILE));
}

export function createMatrixLoader(repository: TaxRepository, files: Record<string, FileDigest>, meta: MatrixMeta, gemeinden: Record<string, Gemeinde>) {
  const cache = new Map<number, Promise<MatrixDestination | null>>();
  return (workplace: number): Promise<MatrixDestination | null> => {
    if (!files[matrixFile(workplace)]) return Promise.resolve(null);
    if (!cache.has(workplace)) {
      cache.set(workplace, repository.json<unknown>(matrixFile(workplace))
        .then(data => validateMatrixDestination(data, workplace, meta.serviceDate, gemeinden))
        .catch(error => { cache.delete(workplace); throw error; }));
    }
    return cache.get(workplace)!;
  };
}
