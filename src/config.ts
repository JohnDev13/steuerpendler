import type { FileDigest } from './tax';
export interface ReleaseManifest {schemaVersion:number;release:string;taxYear:number;availability:{tax:boolean;map:boolean;travel:boolean};approvals:Record<string,boolean>;status:string;files:Record<string,FileDigest>}
declare const __DATA_RELEASE__:ReleaseManifest;
export const DATA_RELEASE = __DATA_RELEASE__;
// VS: precautionary (SPEC R1). JU: official 2026 parish rates disagree with
// the shipped factor table and merged municipalities can span different parishes.
export const QUARANTINED_CANTONS: ReadonlySet<string> = new Set(['VS','JU']);
export const COLOURS = ['#3c8064','#88aa72','#d9bf6e','#d89365','#bd6260'] as const;
