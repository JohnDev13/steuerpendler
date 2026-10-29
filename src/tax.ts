import { calculateBvg2026Age35 } from '../scripts/tax/bvg';

export type CivilStatus = 's' | 'm';
export type PensionDefault = 'ESTV2026Age35';
export type BudgetDefault = 'ESTV2026Age35';
export type Church = 'none' | 'reformed' | 'catholic';
export type Gemeinde = readonly [name:string,canton:string,rateCanton:number,rateGemeinde:number,rateReformed:number,rateCatholic:number];
export type DeductionFormat = 'ZERO'|'STANDARDIZED'|'MAXIMUM'|'PERCENT'|'PERCENT,MAXIMUM'|'PERCENT,MINIMUM,MAXIMUM'|'STANDARDIZED,PERCENT,MAXIMUM';
export interface DeductionOp {source:'net'|'constant'|'rent30';value:number;format:DeductionFormat;amount:number;percent:number;minimum:number;maximum:number;multiplier:number}
export type TariffType = 'BUND'|'ZUERICH'|'FORMEL'|'FREIBURG'|'FLATTAX';
export type TariffRounding='split100'|'income100'|'exact';
export interface PreciseTariff {type:TariffType;split:number;rounding:TariffRounding;table:{amount:number;percent:number;taxes:number;formula:string}[]}
// Cantonal deductions on the income after the ordinary ones (vendor patch 22). All fields numeric; unused ones 0.
// addBack: ordinary deductions added to the basis (constant per profile); addBackLate: indices of earlier late ones.
export interface PreciseLate {kind:'fixed'|'percent'|'linear'|'step';amount:number;rate:number;max:number;threshold:number;base:number;step:number;reduction:number;addBack:number;addBackLate:number[]}
export interface PreciseCanton {bund:{deductions:DeductionOp[];tariff:PreciseTariff;late?:PreciseLate[]};canton:{deductions:DeductionOp[];tariff:PreciseTariff;late?:PreciseLate[]};personal:number;personalChurch:{reformed:number;catholic:number};kids:number;persons:number}
export interface TaxProfile {meta:{year:number;incomes:{from:number;step:number;count:number};pensionDefault?:PensionDefault;budgetDefault?:BudgetDefault;[key:string]:unknown};cantons:Record<string,number[][]>;precision?:Record<string,PreciseCanton>}
// Integer ties-to-even, matching the engine's monetary rounding, not display rounding.
// ESTV rounds percentage deductions down to whole francs.
const floorChf=(x:number)=>Math.floor(x+1e-9);
export function halfEven(x:number):number {const f=Math.floor(x),d=x-f;return Math.abs(d-.5)<1e-8?(f%2===0?f:f+1):Math.round(x);}
function formulaValue(formula:string,wert:number):number {
 const compact=formula.replace(/\s/g,'');
 const tokens=compact.match(/\$wert\$|log|\d+(?:\.\d*)?|[()+*/-]/g)??[];let i=0;
 if(tokens.join('')!==compact)throw Error('Ungültige Steuerformel.');
 function atom():number {const t=tokens[i++];if(t==='-')return -atom();if(t==='log')return Math.log(atom());if(t==='('){const v=expr();if(tokens[i++]!==')')throw Error('Ungültige Steuerformel.');return v;}if(t==='$wert$')return wert;const n=Number(t);if(!Number.isFinite(n))throw Error('Ungültige Steuerformel.');return n;}
 function term():number {let v=atom();while(tokens[i]==='*'||tokens[i]==='/'){const op=tokens[i++],r=atom();v=op==='*'?v*r:v/r;}return v;}
 function expr():number {let v=term();while(tokens[i]==='+'||tokens[i]==='-'){const op=tokens[i++],r=term();v=op==='+'?v+r:v-r;}return v;}
 if(!formula.trim())return 0;const v=expr();if(i!==tokens.length||!Number.isFinite(v))throw Error('Ungültige Steuerformel.');return Math.max(0,Math.round(v*100)/100);
}
const deductionFormats = new Set<DeductionFormat>(['ZERO','STANDARDIZED','MAXIMUM','PERCENT','PERCENT,MAXIMUM','PERCENT,MINIMUM,MAXIMUM','STANDARDIZED,PERCENT,MAXIMUM']);
const tariffTypes = new Set<TariffType>(['BUND','ZUERICH','FORMEL','FREIBURG','FLATTAX']);
function validatePrecision(value:unknown):value is PreciseCanton {
 if(!value||typeof value!=='object')return false;
 const p=value as PreciseCanton;
 if(!Number.isFinite(p.personal)||!p.personalChurch||!Number.isFinite(p.personalChurch.reformed)||!Number.isFinite(p.personalChurch.catholic)||!Number.isInteger(p.kids)||p.kids<0||p.kids>3||!Number.isInteger(p.persons)||p.persons<1||p.persons>2)return false;
 for(const part of [p.bund,p.canton]){
  if(!part||!Array.isArray(part.deductions)||!part.tariff)return false;
  for(const op of part.deductions)if(!op||!['net','constant','rent30'].includes(op.source)||!deductionFormats.has(op.format)||![op.value,op.amount,op.percent,op.minimum,op.maximum,op.multiplier].every(Number.isFinite))return false;
  for(const l of part.late??[])if(!l||!['fixed','percent','linear','step'].includes(l.kind)||![l.amount,l.rate,l.max,l.threshold,l.base,l.step,l.reduction,l.addBack].every(Number.isFinite)||(l.kind==='step'&&l.step<=0)||!Array.isArray(l.addBackLate)||!l.addBackLate.every(Number.isInteger))return false;
  const tariff=part.tariff;
  if(!tariffTypes.has(tariff.type)||!['split100','income100','exact'].includes(tariff.rounding)||!Number.isFinite(tariff.split)||tariff.split<=0||!Array.isArray(tariff.table)||tariff.table.length===0)return false;
  for(const row of tariff.table){
   if(!row||![row.amount,row.percent,row.taxes].every(Number.isFinite)||typeof row.formula!=='string')return false;
   try { formulaValue(row.formula,100000); } catch { return false; }
  }
 }
 return true;
}
export function preciseBase(p:PreciseCanton,income:number,pensionDefault?:PensionDefault,budgetDefault?:BudgetDefault):[number,number,number] {
 const gross=Math.round(income*100)/100;
 const pension=pensionDefault==='ESTV2026Age35'?calculateBvg2026Age35(gross):0;
 const net=gross-halfEven(gross*.053)-halfEven(Math.min(gross,148200)*.011)-halfEven(Math.min(gross,148200)*.004)-pension;
 const tax=(part:PreciseCanton['bund'])=>{
  let deductions=0;
  for(const op of part.deductions){const estimatedRent=Math.round(net*.25/10)*10;const v=op.source==='net'?net:op.source==='rent30'&&budgetDefault==='ESTV2026Age35'?estimatedRent*.3:op.value;let d=0;
   if(op.format==='ZERO')d=0;
   else if(op.format==='STANDARDIZED')d=op.amount;
   else if(op.format==='MAXIMUM')d=Math.min(v,op.maximum);
   else if(op.format==='PERCENT')d=floorChf(v*op.percent/100);
   else if(op.format==='PERCENT,MAXIMUM')d=Math.min(op.maximum,floorChf(v*op.percent/100));
   else if(op.format==='PERCENT,MINIMUM,MAXIMUM')d=Math.min(op.maximum,Math.max(op.minimum,floorChf(v*op.percent/100)));
   else if(op.format==='STANDARDIZED,PERCENT,MAXIMUM')d=Math.min(op.maximum,op.amount+floorChf(v*op.percent/100));
   deductions+=d*op.multiplier;
  }
  return preciseTariffTax(part.tariff,applyLate(part.late??[],Math.max(0,halfEven(net-deductions))));
 };
 const bund=Math.max(0,halfEven(tax(p.bund))-263*p.kids);
 // DBG Art. 36 Abs. 3: federal amounts below CHF 25 are not levied (vendor patch 23).
 return [bund<25?0:bund,tax(p.canton),p.personal];
}
// Late cantonal deductions in order (vendor patch 22); returns the taxable income.
export function applyLate(late:PreciseLate[],income:number):number {
 const done:number[]=[];let remaining=income;
 for(const l of late){
  const basis=remaining+l.addBack+l.addBackLate.reduce((s,i)=>s+done[i],0);
  const d=l.kind==='fixed'?l.amount:l.kind==='percent'?Math.min(l.max,Math.floor(l.rate*basis+1e-9)):l.kind==='linear'?Math.max(0,Math.floor(l.rate*(l.threshold-basis)+1e-9)):Math.max(0,l.base-Math.floor(Math.max(0,basis-l.threshold)/l.step+1e-9)*l.reduction);
  done.push(d);remaining-=d;
 }
 return Math.max(0,remaining);
}
// Tax of one tariff for a taxable income, with the canton's rounding around splitting (vendor patch 20).
export function preciseTariffTax(tariff:PreciseTariff,taxable:number):number {
 const split=tariff.split,reciprocal=Math.round(1/split*1e5)/1e5,floor100=(v:number)=>Math.floor(v/100+1e-9)*100;
 let type=tariff.type;
 if(type==='ZUERICH'&&tariff.table.some(x=>x.taxes>0))type='BUND';
 const rate=(v:number)=>Math.round(v*1e5)/1e5;
 const taxOf=(amount:number)=>{
  let result=0;
  if(type==='FLATTAX')result=amount*rate(tariff.table[0].percent)/100;
  else if(type==='ZUERICH'){let left=amount;for(const row of tariff.table){const used=Math.min(left,row.amount);result+=used*rate(row.percent)/100;left-=used;if(!left)break;}}
  else if(type==='FREIBURG'){
   let last:PreciseTariff['table'][number]|undefined;
   for(const row of tariff.table){if(row.amount>=amount){if(last&&last.amount!==0){const r=last.percent+(amount-last.amount)*(row.percent-last.percent)/(row.amount-last.amount);result=amount*Math.round(r*1e5)/1e7;}break;}last=row;}
   if(last&&amount>tariff.table[tariff.table.length-1].amount)result=amount*rate(last.percent)/100;
  }else {let row=tariff.table[0];for(const next of tariff.table){if(next.amount>amount)break;row=next;}result=type==='FORMEL'?formulaValue(row.formula,amount):Math.round(row.taxes*100)/100+(amount-row.amount)*rate(row.percent)/100;}
  return result;
 };
 if(tariff.rounding==='exact')return taxOf(taxable*reciprocal)*split;
 const whole=floor100(taxable);
 if(tariff.rounding==='income100')return taxOf(whole*reciprocal)*split;
 if(split===1)return taxOf(whole);
 const divided=floor100(whole*reciprocal);
 return divided>0?taxOf(divided)/divided*whole:0;
}
export interface TaxBreakdown {bund:number;kanton:number;gemeinde:number;kirche:number;personal:number;total:number;income:number;clamped:boolean}
export function calculateTax(profile:TaxProfile,g:Gemeinde,income:number,church:Church):TaxBreakdown {
 if (!Number.isFinite(income)) throw new Error('Ungültiges Einkommen.');
 const clampedIncome=Math.min(500000,Math.max(40000,income));
 const x=(clampedIncome-40000)/1000;
 const i=Math.min(Math.floor(x),459),t=x-i;
 const table=profile.cantons[g[1]];
 if (!table || !table[i] || !table[i+1]) throw new Error('Steuertabelle für diesen Kanton fehlt.');
 const precise=profile.precision?.[g[1]];
 const row=precise&&t!==0&&t!==1?preciseBase(precise,clampedIncome,profile.meta.pensionDefault,profile.meta.budgetDefault):table[i].map((v,k)=>v+(table[i+1][k]-v)*t);
 const rate=church==='reformed'?g[4]:church==='catholic'?g[5]:0;
 const round=precise?halfEven:(x:number)=>x;
 const churchRate=precise?Math.round(rate/precise.persons*100)/100*precise.persons:rate;
 const bund=row[0],kanton=round(row[1]*g[2]/100),gemeinde=round(row[1]*g[3]/100),kirche=round(row[1]*churchRate/100),personal=row[2]+(precise&&church!=='none'?precise.personalChurch[church]:0);
 const total=bund+kanton+gemeinde+kirche+personal;
 if(!Number.isFinite(total)) throw new Error('Steuerdaten sind unvollständig.');
 return {bund,kanton,gemeinde,kirche,personal,total,income:clampedIncome,clamped:income!==clampedIncome};
}
export type Fetcher = (url:string)=>Promise<Response>;
export interface FileDigest {sha256:string;bytes?:number}
export async function fetchJSON<T>(url:string,fetcher:Fetcher=fetch,expected?:FileDigest):Promise<T> {
 const response=await fetcher(url);
 if(!response.ok) throw new Error(`Daten nicht verfügbar (HTTP ${response.status}).`);
 if(!response.headers.get('content-type')?.includes('application/json')) throw new Error('Die angeforderte Datei enthält keine JSON-Daten.');
 const bytes=await response.arrayBuffer();
 if(expected){
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
  if(digest!==expected.sha256||(expected.bytes!==undefined&&bytes.byteLength!==expected.bytes))throw new Error('Die Datenversion stimmt nicht überein. Bitte lade die Seite neu.');
 }
 try {return JSON.parse(new TextDecoder().decode(bytes)) as T;} catch {throw new Error('Die Datendatei ist beschädigt.');}
}
export class TaxRepository {
 private pending=new Map<string,Promise<unknown>>();
 constructor(private fetcher:Fetcher=fetch,private base='/data',private release='',private files?:Record<string,FileDigest>){}
 url(path:string):string {return `${this.base}/${path}${this.release?`?v=${encodeURIComponent(this.release)}`:''}`;}
 async json<T>(path:string):Promise<T> {
  if(this.files&&!this.files[path])throw new Error('Diese Datendatei gehört nicht zur geladenen Datenversion.');
  return fetchJSON<T>(this.url(path),this.fetcher,this.files?.[path]);
 }
 private once<T>(path:string,validate:(data:unknown)=>T):Promise<T> {
  if(!this.pending.has(path)) {
   const result=this.json<unknown>(path).then(validate).catch(error=>{this.pending.delete(path);throw error;});
   this.pending.set(path,result);
  }
  return this.pending.get(path) as Promise<T>;
 }
 loadGemeinden():Promise<Record<string,Gemeinde>> {
  return this.once('gemeinden-2026.json',data=>{
   const values=(data as {gemeinden?:Record<string,unknown>})?.gemeinden;
   if(!values||!Object.keys(values).length) throw new Error('Gemeindedaten fehlen.');
   for(const [id,row] of Object.entries(values)) if(!/^\d+$/.test(id)||!Array.isArray(row)||row.length!==6||typeof row[0]!=='string'||typeof row[1]!=='string'||!row.slice(2).every(Number.isFinite)) throw new Error('Ungültiges Gemeindeformat.');
   return values as Record<string,Gemeinde>;
  });
 }
 loadProfile(civ:CivilStatus,kids:number):Promise<TaxProfile> {
  if(!['s','m'].includes(civ)||!Number.isInteger(kids)||kids<0||kids>3) return Promise.reject(new Error('Ungültiges Steuerprofil.'));
  return this.once(`tax-2026-${civ}-${kids}.json`,data=>{
   const p=data as TaxProfile;
   if(p?.meta?.pensionDefault!==undefined&&p.meta.pensionDefault!=='ESTV2026Age35') throw new Error('Ungültiger pensionDefault-Marker.');
   if(p?.meta?.budgetDefault!==undefined&&p.meta.budgetDefault!=='ESTV2026Age35') throw new Error('Ungültiger budgetDefault-Marker.');
   if(p?.meta?.budgetDefault!==undefined&&p.meta.pensionDefault!=='ESTV2026Age35') throw new Error('budgetDefault benötigt pensionDefault.');
   if(p?.meta?.year!==2026||p.meta.incomes?.from!==40000||p.meta.incomes.step!==1000||p.meta.incomes.count!==461||!p.cantons||!Object.keys(p.cantons).length) throw new Error('Ungültige Steuertabelle.');
   for(const rows of Object.values(p.cantons)) if(!Array.isArray(rows)||rows.length!==461||rows.some(row=>!Array.isArray(row)||row.length!==3||!row.every(Number.isFinite))) throw new Error('Steuerdaten sind unvollständig.');
   if(p.precision!==undefined||p.meta.schemaVersion!==undefined){
    if(p.meta.schemaVersion!==2)throw new Error('Ungültige precision-Schemaversion.');
    const cantonKeys=Object.keys(p.cantons).sort(),precisionKeys=Object.keys(p.precision??{}).sort();
    if(cantonKeys.length!==26||precisionKeys.length!==26||cantonKeys.some((key,index)=>key!==precisionKeys[index])||!precisionKeys.every(key=>validatePrecision(p.precision![key])))throw new Error('Ungültiges precision-Steuerprogramm.');
    const hasRent30=precisionKeys.some(key=>[p.precision![key].bund,p.precision![key].canton].some(part=>part.deductions.some(op=>op.source==='rent30')));
    if(hasRent30&&p.meta.budgetDefault!=='ESTV2026Age35')throw new Error('rent30 benötigt budgetDefault.');
   }
   return p;
  });
 }
}
