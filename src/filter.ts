import type { Gemeinde } from './tax';
export type Access = Record<string,readonly [stopId:string,stopName:string,walk:number]|null>;
export type TravelRows = ReadonlyArray<readonly [bfs:number,minutes:number]>;
export interface FilterOptions {maxTime:number;maxWalk:number;countWalk:boolean;workplace:number}
export interface RankedResult {id:number;name:string;canton:string;minutes:number;walk:number;total:number;delta:number|null;rank:number;colorGroup:number}
const names=new Intl.Collator('de-CH',{sensitivity:'base'});
export function isReachable(stop:Access[string]|undefined,minutes:number|undefined,options:FilterOptions):boolean {
 return stop!=null&&minutes!==undefined&&Number.isFinite(minutes)&&minutes>=0&&stop[2]<=options.maxWalk&&(minutes+(options.countWalk?stop[2]:0))<=options.maxTime;
}
export function filterAndRank(gemeinden:Record<string,Gemeinde>,access:Access,rows:TravelRows,options:FilterOptions,totals:Record<string,number>,quarantined:ReadonlySet<string>=new Set()):RankedResult[] {
 const workplace=gemeinden[options.workplace];
 const baseline=workplace&&!quarantined.has(workplace[1])?totals[options.workplace]:undefined;
 const result:RankedResult[]=[];
 for(const [id,minutes] of rows){
  const g=gemeinden[id],stop=access[id],total=totals[id];
  if(!g||quarantined.has(g[1])||!isReachable(stop,minutes,options)||!Number.isFinite(total))continue;
  result.push({id,name:g[0],canton:g[1],minutes,walk:stop![2],total,delta:baseline!==undefined&&Number.isFinite(baseline)?total-baseline:null,rank:0,colorGroup:0});
 }
 result.sort((a,b)=>a.total-b.total||a.minutes-b.minutes||names.compare(a.name,b.name)||a.id-b.id);
 const k=Math.min(5,result.length),base=k?Math.floor(result.length/k):0,extra=k?result.length%k:0,boundary=(base+1)*extra;
 return result.map((row,i)=>({...row,rank:i+1,colorGroup:i<boundary?Math.floor(i/(base+1)):extra+Math.floor((i-boundary)/base)}));
}
