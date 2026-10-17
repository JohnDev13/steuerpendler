export function withheldCantons(cantons:Iterable<string>,officiallyApproved:boolean,quarantined:Iterable<string>):ReadonlySet<string>{
 return new Set(officiallyApproved?quarantined:[...cantons,...quarantined]);
}
