import type { FileDigest } from './tax';
export interface ReleaseManifest {schemaVersion:number;release:string;taxYear:number;availability:{tax:boolean;map:boolean;travel:boolean;matrix?:boolean};approvals:Record<string,boolean>;status:string;files:Record<string,FileDigest>}
declare const __DATA_RELEASE__:ReleaseManifest;
export const DATA_RELEASE = __DATA_RELEASE__;
export { QUARANTINED_CANTONS, withheldFor } from './withheld';
export const COLOURS = ['#3c8064','#88aa72','#d9bf6e','#d89365','#bd6260'] as const;
