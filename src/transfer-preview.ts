import type { Gemeinde, TaxRepository } from './tax';
import { AARAU_PREVIEW_SOURCE, adaptAarauPreview, type AarauPreview, type AdaptedAarauPreview, type PreviewReleaseInventory } from './preview';

export const TRANSFER_WITNESS_FILE = 'travel/aarau-transfer-witness-20261027.json';
const DIGEST = { sha256: '1310173f1ac78ff41b966c1cb5a2ce56ac8567d8b80ee139c4dd3e3e05f017ad', bytes: 582 } as const;
const SOURCE_WITNESS_SHA = '3dd58a1f9f89cbb8a86f654d09ca4c78cea9c8c5b4d385063593deb368a307c8';
const BOARD_STOP_INDEX_SHA = '53380d7c232074d6097148a7c29a08fe6e3f06213a2301b91a6fb281714f36bb';
const KEYS = ['status','serviceDay','originBfs','destinationBfs','boardingStopId','firstBoardSeconds','arrivalSeconds','elapsedSeconds','transferCount','minimumTransferSeconds','availableTransferSeconds','sourceWitnessSha256','boardStopIndexSha256','gtfsSha256'];
export interface TransferWitness {
  status: 'witnessed_transfer_not_proven_fastest'; serviceDay: '2026-10-27';
  originBfs: 4210; destinationBfs: 4001; boardingStopId: string;
  firstBoardSeconds: number; arrivalSeconds: number; elapsedSeconds: number;
  transferCount: 1; minimumTransferSeconds: number; availableTransferSeconds: number;
  sourceWitnessSha256: string; boardStopIndexSha256: string; gtfsSha256: string;
}
function invalid(): never { throw new Error('Ungültige indikative Fahrplandaten.'); }
export function validateTransferWitness(value: unknown, release: PreviewReleaseInventory, gemeinden: Record<string, Gemeinde>): TransferWitness {
  const digest = release.files[TRANSFER_WITNESS_FILE];
  if (digest?.sha256 !== DIGEST.sha256 || digest?.bytes !== DIGEST.bytes || !value || typeof value !== 'object' || Array.isArray(value)) invalid();
  const data = value as Record<string, unknown>;
  if (Object.keys(data).sort().join('|') !== [...KEYS].sort().join('|')
    || data.status !== 'witnessed_transfer_not_proven_fastest' || data.serviceDay !== '2026-10-27'
    || data.originBfs !== 4210 || data.destinationBfs !== 4001
    || !gemeinden[4210] || gemeinden[4210][0] !== 'Staufen' || !gemeinden[4001]
    || data.boardingStopId !== 'ch:1:sloid:78699_gen:missingSLOID_pf:B'
    || data.sourceWitnessSha256 !== SOURCE_WITNESS_SHA || data.boardStopIndexSha256 !== BOARD_STOP_INDEX_SHA
    || data.gtfsSha256 !== AARAU_PREVIEW_SOURCE.gtfsSha256
    || data.firstBoardSeconds !== 24420 || data.arrivalSeconds !== 25500 || data.elapsedSeconds !== 1080
    || data.transferCount !== 1 || data.minimumTransferSeconds !== 240 || data.availableTransferSeconds !== 300) invalid();
  return data as unknown as TransferWitness;
}
export async function loadTransferWitness(repository: TaxRepository, release: PreviewReleaseInventory, gemeinden: Record<string, Gemeinde>): Promise<TransferWitness> {
  if (!release.files[TRANSFER_WITNESS_FILE]) invalid();
  return validateTransferWitness(await repository.json<unknown>(TRANSFER_WITNESS_FILE), release, gemeinden);
}
export function adaptObservedAarau(direct: AarauPreview, transfer: TransferWitness, directOnly: boolean): AdaptedAarauPreview {
  const adapted = adaptAarauPreview(direct);
  if (directOnly) return adapted;
  const current = direct.rows.find(row => row.bfs === transfer.originBfs);
  if (current && current.seconds <= transfer.elapsedSeconds) return adapted;
  const access = { ...adapted.access, [transfer.originBfs]: [transfer.boardingStopId, transfer.boardingStopId, 0] as const };
  const rows = [...adapted.rows.filter(([bfs]) => bfs !== transfer.originBfs), [transfer.originBfs, Math.ceil(transfer.elapsedSeconds / 60)] as const];
  return { access, rows };
}
