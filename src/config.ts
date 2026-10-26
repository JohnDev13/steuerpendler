import type { FileDigest } from './tax';
export interface ReleaseManifest {schemaVersion:number;release:string;taxYear:number;availability:{tax:boolean;map:boolean;travel:boolean};approvals:Record<string,boolean>;status:string;files:Record<string,FileDigest>}
declare const __DATA_RELEASE__:ReleaseManifest;
export const DATA_RELEASE = __DATA_RELEASE__;
// Cantons whose estimates are withheld. scripts/tax/official.test.ts fails if any canton
// deviates from its ESTV reference case by more than 5% without being listed here.
// VS: cantonal rebates/coefficients not modelled (ESTV case off by ~270%).
// VD: quotient familial not modelled (~19%). GE: cantonal reduction not modelled (~8%).
// JU: official 2026 parish rates disagree with the factor table for merged municipalities (#58).
export const QUARANTINED_CANTONS: ReadonlySet<string> = new Set(['VS','JU','VD','GE']);
export const COLOURS = ['#3c8064','#88aa72','#d9bf6e','#d89365','#bd6260'] as const;
