// Health-insurance premiums (mandatory basic insurance, OKP) per Gemeinde, derived from the BAG open data by
// scripts/kk/derive.ts into site/data/kk.json. Values are CHF per year for the whole household of the tax profile.
import type { CivilStatus } from './tax';
export const KK_PROFILES = ['s0','s1','s2','s3','m0','m1','m2','m3'] as const;
export const KK_DEDUCTIBLES = [300,500,1000,1500,2000,2500] as const;
export const KK_YEARS = ['2026','2027'] as const;
export type KkMode = 'median'|'min'|'none';
export type KkYear = typeof KK_YEARS[number];
export interface KkYearData {table:number[][];gemeinden:Record<string,number>}
export interface KkData {meta:{profiles:readonly string[];deductibles:readonly number[]};years:Record<KkYear,KkYearData>}
const ROW=KK_PROFILES.length*KK_DEDUCTIBLES.length*2;
export function validateKk(data:unknown):KkData {
 const d=data as KkData;
 const fail=()=>{throw new Error('Ungültige Krankenkassendaten.');};
 if(!d||typeof d!=='object'||!d.meta||!d.years)fail();
 if(JSON.stringify(d.meta.profiles)!==JSON.stringify(KK_PROFILES)||JSON.stringify(d.meta.deductibles)!==JSON.stringify(KK_DEDUCTIBLES))fail();
 for(const year of KK_YEARS){
  const y=d.years[year];
  if(!y||!Array.isArray(y.table)||!y.gemeinden||typeof y.gemeinden!=='object')fail();
  for(const row of y.table)if(!Array.isArray(row)||row.length!==ROW||!row.every(v=>Number.isFinite(v)&&v>0))fail();
  for(const [id,i] of Object.entries(y.gemeinden))if(!/^\d+$/.test(id)||!Number.isInteger(i)||i<0||i>=y.table.length)fail();
 }
 return d;
}
/** Household premium per year in CHF, or undefined when the Gemeinde has no premium or the mode is 'none'. */
export function premiumFor(data:KkData|null,year:KkYear,bfs:number|string,civ:CivilStatus,kids:number,deductible:number,mode:KkMode):number|undefined {
 if(!data||mode==='none')return undefined;
 const y=data.years[year],index=y?.gemeinden[String(bfs)];
 const p=KK_PROFILES.indexOf(`${civ}${Math.min(3,Math.max(0,kids))}` as typeof KK_PROFILES[number]),d=KK_DEDUCTIBLES.indexOf(deductible as typeof KK_DEDUCTIBLES[number]);
 if(index===undefined||p<0||d<0)return undefined;
 return y.table[index][(p*KK_DEDUCTIBLES.length+d)*2+(mode==='min'?1:0)];
}
