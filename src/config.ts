import type { FileDigest } from './tax';
export interface ReleaseManifest {schemaVersion:number;release:string;taxYear:number;availability:{tax:boolean;map:boolean;travel:boolean};approvals:Record<string,boolean>;status:string;files:Record<string,FileDigest>}
declare const __DATA_RELEASE__:ReleaseManifest;
export const DATA_RELEASE = __DATA_RELEASE__;
// Precautionary quarantine: SPEC R1, not a claim of an official failed check.
export const QUARANTINED_CANTONS: ReadonlySet<string> = new Set(['VS']);
export const COLOURS = ['#3c8064','#88aa72','#d9bf6e','#d89365','#bd6260'] as const;
